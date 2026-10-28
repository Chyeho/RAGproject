# -*- coding: utf-8 -*-
'''混合检索器与检索链路工厂（P2）

HybridRetriever：稠密（Qdrant）+ 稀疏（BM25）双路召回 → RRF 融合
RerankRetriever：包装任意检索器，召回后精排取 top_k
build_retriever：按 retrieval_config.yml 开关组装最终链路（支持 overrides 覆盖，
                供评测 --preset 注入开关组合），全关闭时行为等价旧链路。
P3 起末端按 query_optimize.mode 包装 QueryEnhancer（off/multi_query/hyde），
默认 off，链路行为与 P2 完全一致。
query_optimize.fuse_then_rerank=true 时组合 4 改为「融合后统一精排」变体：
QueryEnhancer 包 Hybrid（每路仅混合检索，全路 RRF 融合输出=精排候选数），
RerankRetriever 再包外层（原查询统一精排，最终序=精排序，消除变体打分噪声）。

开关组合语义（最终送入生成的文档数）：
  hybrid off + rerank off → 稠密检索 k=legacy_k（等价 P1 旧链路）
  hybrid on  + rerank off → dense+bm25 → RRF → top_k
  hybrid off + rerank on  → dense(候选 dense_topn) → 精排 → rerank.top_k
  hybrid on  + rerank on  → dense+bm25 → RRF(topn) → 精排 → rerank.top_k
'''
from typing import TYPE_CHECKING, Optional

from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import PrivateAttr

from app.modelFactory.rerank_factory import BaseReranker, _create_reranker
from app.service.rag.retrieval.bm25_retriever import BM25Retriever, bm25_retriever
from app.service.rag.retrieval.rrf import rrf_fuse
from app.utils.config_handler import retrieval_conf
from app.utils.logger_handler import logger

if TYPE_CHECKING:  # 仅类型标注，避免导入期依赖
    from langchain_core.language_models.chat_models import BaseChatModel

    from app.service.rag.vector_store import VectorStoreService


class HybridRetriever(BaseRetriever):
    '''稠密 + BM25 双路召回，RRF 融合（vector_id 去重）'''

    rrf_k: int = 60    # RRF 平滑常数
    topn: int = 20     # 融合后保留条数（送精排候选数或最终条数）

    _dense: BaseRetriever = PrivateAttr()
    _bm25: BM25Retriever = PrivateAttr()

    def __init__(self, dense: BaseRetriever, bm25: BM25Retriever, rrf_k: int = 60, topn: int = 20, **kwargs):
        super().__init__(rrf_k=rrf_k, topn=topn, **kwargs)
        self._dense = dense
        self._bm25 = bm25

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> list[Document]:
        dense_docs = self._dense.invoke(query)
        bm25_docs = self._bm25.invoke(query)
        return rrf_fuse([dense_docs, bm25_docs], rrf_k=self.rrf_k, topn=self.topn)


class RerankRetriever(BaseRetriever):
    '''精排包装：先经底层检索器召回，再按 query 相关度精排取 top_k'''

    _base: BaseRetriever = PrivateAttr()
    _reranker: BaseReranker = PrivateAttr()

    def __init__(self, base: BaseRetriever, reranker: BaseReranker, **kwargs):
        super().__init__(**kwargs)
        self._base = base
        self._reranker = reranker

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> list[Document]:
        docs = self._base.invoke(query)
        if not docs:
            return []
        # safe_rank 内置降级：精排异常时返回 RRF 序前 top_k，链路不中断
        ranked = self._reranker.safe_rank(query, docs)
        return [
            Document(page_content=doc.page_content, metadata={**doc.metadata, "rerank_score": score})
            for doc, score in ranked
        ]


def hybrid_enabled() -> bool:
    """hybrid 开关是否开启（文件配置口径；BM25 增量维护接线点判断用）"""
    return bool(retrieval_conf.get("hybrid", {}).get("enabled", False))


def _effective_conf(overrides: Optional[dict]) -> dict:
    '''合并文件配置与 overrides（section 浅合并、顶层标量直接覆盖；overrides 优先）
    顶层标量（top_k/legacy_k）供评测 preset 覆盖最终条数口径'''
    conf = {
        "hybrid": dict(retrieval_conf.get("hybrid", {})),
        "rerank": dict(retrieval_conf.get("rerank", {})),
        "query_optimize": dict(retrieval_conf.get("query_optimize", {})),
        "top_k": int(retrieval_conf.get("top_k", 5)),
        "legacy_k": int(retrieval_conf.get("legacy_k", 3)),
    }
    if overrides:
        for key, value in overrides.items():
            if isinstance(value, dict):
                conf.setdefault(key, {}).update(value)
            else:
                conf[key] = value
    return conf


def effective_output_k(conf: dict) -> int:
    """链路最终送入生成的文档数（与 retrieval_config.yml 头部注释口径一致）

    rerank 开启 → rerank.top_k；否则 hybrid 开启 → top_k；全关闭 → legacy_k。
    评测报告 meta.k 与 QueryEnhancer 融合 topn 均取此口径。
    """
    if bool(conf["rerank"].get("enabled", False)):
        return int(conf["rerank"].get("top_k", 5))
    if bool(conf["hybrid"].get("enabled", False)):
        return int(conf["top_k"])
    return int(conf["legacy_k"])


def _wrap_query_enhancer(
    retriever: BaseRetriever, conf: dict, chat_model: Optional["BaseChatModel"],
    topn: Optional[int] = None,
) -> BaseRetriever:
    '''P3 查询优化包装（mode=off 或构造失败时原样返回）

    QueryEnhancer 懒导入：mode=off（默认）时不加载 query 包零开销，且避免
    query 包 → rrf → retrieval/__init__ → 本模块 → query.enhancer 的导入环。
    topn 缺省取链路有效输出 k；融合后统一精排变体下由调用方传入精排候选数。
    '''
    mode = str(conf.get("query_optimize", {}).get("mode", "off")).lower()
    if mode not in ("multi_query", "hyde"):
        if mode != "off":
            logger.warning(f"[检索链路]未知 query_optimize.mode='{mode}'，按 off 处理")
        return retriever
    try:
        from app.service.rag.query import QueryEnhancer

        if chat_model is None:
            from app.modelFactory.factory import chat_model as _default_chat_model
            chat_model = _default_chat_model
        enhancer = QueryEnhancer(
            base=retriever,
            chat_model=chat_model,
            mode=mode,
            topn=topn if topn is not None else effective_output_k(conf),
            rrf_k=int(conf["hybrid"].get("rrf_k", 60)),
            multi_query_count=int(conf.get("query_optimize", {}).get("multi_query_count", 3)),
        )
    except Exception as e:
        logger.warning(f"[检索链路]查询优化包装失败，本次降级不启用：{e}", exc_info=True)
        return retriever
    logger.info(f"[检索链路]query_optimize={mode} 前置包装（融合 topn={enhancer.topn}）")
    return enhancer


def build_retriever(
    vector_store_service: "VectorStoreService",
    bm25: Optional[BM25Retriever] = None,
    reranker: Optional[BaseReranker] = None,
    overrides: Optional[dict] = None,
    chat_model: Optional["BaseChatModel"] = None,
) -> BaseRetriever:
    '''按开关组装检索链路（P2 链路入口，替换直接调用 get_retriever）

    Args:
        vector_store_service: 向量库服务（稠密路来源）
        bm25: 稀疏路检索器；缺省用模块单例（应用启动时已 rebuild）
        reranker: 精排器；缺省按生效配置懒创建，不可用时自动降级关闭精排
        overrides: 开关覆盖（如 {"rerank": {"enabled": False}}），供评测 preset 使用
        chat_model: 查询优化生成变体用聊天模型；缺省用模型工厂共享单例（仅 P3 模式用到）
    '''
    conf = _effective_conf(overrides)
    hybrid_on = bool(conf["hybrid"].get("enabled", False))
    rerank_on = bool(conf["rerank"].get("enabled", False))

    # 精排器懒创建：仅 rerank_on 时需要；创建失败（key 缺失/依赖缺失）→ 降级关闭精排
    if rerank_on and reranker is None:
        try:
            reranker = _create_reranker(conf["rerank"])
        except Exception as e:
            logger.warning(f"[检索链路]精排器创建失败，本次降级关闭精排，错误：{e}", exc_info=True)
            reranker = None
    if reranker is None:
        rerank_on = False

    dense_k = (
        int(conf["legacy_k"])
        if not (hybrid_on or rerank_on)
        else int(conf["hybrid"].get("dense_topn", 20))
    )
    dense = vector_store_service.get_retriever(k=dense_k)

    if not hybrid_on and not rerank_on:
        # 组合 1：全关闭 → 稠密 k=legacy_k，行为等价旧链路
        logger.info(f"[检索链路]dense-only（旧链路等价），k={dense_k}")
        retriever: BaseRetriever = dense
    elif rerank_on and not hybrid_on:
        # 组合 3：仅精排 → 稠密候选直送精排
        logger.info(
            f"[检索链路]dense({dense_k}) → rerank({conf['rerank'].get('remote_model') or conf['rerank'].get('local_model')})"
        )
        retriever = RerankRetriever(base=dense, reranker=reranker)
    elif not rerank_on:
        # 组合 2：混合检索，融合 topn 即最终条数
        if bm25 is None:
            bm25 = bm25_retriever
        topn = int(conf["top_k"])
        logger.info(f"[检索链路]dense({dense_k}) + bm25({bm25.topn}) → RRF → top_k={topn}")
        retriever = HybridRetriever(dense=dense, bm25=bm25, rrf_k=int(conf["hybrid"].get("rrf_k", 60)), topn=topn)
    else:
        # 组合 4：RRF 融合 topn 为精排候选数
        if bm25 is None:
            bm25 = bm25_retriever
        topn = int(conf["hybrid"].get("topn", 20))
        hybrid = HybridRetriever(dense=dense, bm25=bm25, rrf_k=int(conf["hybrid"].get("rrf_k", 60)), topn=topn)
        if bool(conf.get("query_optimize", {}).get("fuse_then_rerank", False)):
            # 「融合后统一精排」变体：QueryEnhancer 包 hybrid（每路仅混合检索+路内 RRF，
            # 全路 RRF 融合输出 topn 条精排候选），RerankRetriever 包最外层用原查询
            # 统一精排——最终序=精排序，且精排调用从 N 路×topn 降为 1 次×topn
            enhanced = _wrap_query_enhancer(hybrid, conf, chat_model, topn=topn)
            if enhanced is not hybrid:  # mode 生效；off/包装失败时回退常规链路
                logger.info(
                    f"[检索链路]fuse-then-rerank：dense({dense_k}) + bm25({bm25.topn}) ×多路 → "
                    f"全路RRF(topn={topn}) → rerank(top_k={reranker.top_k}，原查询统一精排)"
                )
                return RerankRetriever(base=enhanced, reranker=reranker)
        logger.info(
            f"[检索链路]dense({dense_k}) + bm25({bm25.topn}) → RRF(topn={topn}) → rerank(top_k={reranker.top_k})"
        )
        retriever = RerankRetriever(base=hybrid, reranker=reranker)

    # P3：查询优化最外层包装（mode=off 时原样返回）
    return _wrap_query_enhancer(retriever, conf, chat_model)

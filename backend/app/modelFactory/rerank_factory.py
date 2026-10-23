# -*- coding: utf-8 -*-
'''重排模型工厂（P2）

按 MODEL_MODE + retrieval_config.yml 的 rerank 配置生产精排器：
  - remote：DashScopeRerank（gte-rerank-v2，阿里云商业 Cross-Encoder）
  - local：sentence-transformers CrossEncoder（BAAI/bge-reranker-v2-m3，
    可选依赖组 local-rerank，未安装则跳过精排）

统一接口：rank(query, docs) -> list[(doc, score)]，精排后取 top_k（默认 5）。
降级策略：任何异常（网络/限额/依赖缺失）→ warning 日志 + 返回 RRF 序前 top_k，链路不中断。
'''
from abc import ABC, abstractmethod
from typing import Optional

from langchain_core.documents import Document

from app.modelFactory.factory import _get_model_mode
from app.utils.config_handler import retrieval_conf
from app.utils.logger_handler import logger


class BaseReranker(ABC):
    '''精排器基类：统一 rank 接口 + safe_rank 降级保障'''

    top_k: int = 5

    @abstractmethod
    def rank(self, query: str, documents: list[Document]) -> list[tuple[Document, float]]:
        '''按与 query 的相关度降序返回 (doc, score)，至多 top_k 条'''

    def safe_rank(self, query: str, documents: list[Document]) -> list[tuple[Document, float]]:
        '''降级保障入口：精排异常时返回输入序（RRF 序）前 top_k，不中断链路'''
        if not documents:
            return []
        try:
            return self.rank(query, documents)
        except Exception as e:
            logger.warning(
                f"[重排]精排失败，降级返回 RRF 序前 {self.top_k} 条，错误：{e}", exc_info=True
            )
            return [
                (doc, float(doc.metadata.get("rrf_score", 0.0)))
                for doc in documents[: self.top_k]
            ]


class RemoteReranker(BaseReranker):
    '''远程精排：DashScope gte-rerank-v2'''

    def __init__(self, model: str, top_k: int):
        # 延迟导入：langchain_community 为重依赖，且便于单测 patch
        from langchain_community.document_compressors.dashscope_rerank import DashScopeRerank

        compressor = DashScopeRerank(model=model, top_n=top_k)
        # langchain_community 的 model_validator 会把用户传入的 model 无条件覆盖为
        # Models.gte_rerank（v1，已下线，API 返回 403/output=None），构造后回写实际模型名
        compressor.model = model
        self._compressor = compressor
        self.top_k = top_k

    def rank(self, query: str, documents: list[Document]) -> list[tuple[Document, float]]:
        ranked = self._compressor.compress_documents(list(documents), query)
        return [(doc, float(doc.metadata["relevance_score"])) for doc in ranked]


class LocalReranker(BaseReranker):
    '''本地精排：sentence-transformers CrossEncoder（需可选依赖组 local-rerank）'''

    def __init__(self, model_name: str, top_k: int):
        # 未安装 sentence-transformers 时在此抛 ImportError，由调用方降级处理
        from sentence_transformers import CrossEncoder

        self._model = CrossEncoder(model_name)
        self.top_k = top_k

    def rank(self, query: str, documents: list[Document]) -> list[tuple[Document, float]]:
        if not documents:
            return []
        scores = self._model.predict([(query, doc.page_content) for doc in documents])
        order = sorted(range(len(documents)), key=lambda i: scores[i], reverse=True)[: self.top_k]
        return [(documents[i], float(scores[i])) for i in order]


def _create_reranker(rerank_conf: Optional[dict] = None) -> Optional[BaseReranker]:
    '''按配置创建精排器；rerank 关闭或依赖不可用时返回 None（精排自动跳过）

    Args:
        rerank_conf: 生效的 rerank 配置段；缺省读 retrieval_config.yml
    '''
    conf = rerank_conf if rerank_conf is not None else retrieval_conf.get("rerank", {})
    if not conf.get("enabled", False):
        logger.info("[重排工厂]rerank.enabled=false，精排关闭")
        return None

    top_k = int(conf.get("top_k", 5))
    mode = _get_model_mode()

    if mode == "local":
        model_name = str(conf.get("local_model", "BAAI/bge-reranker-v2-m3"))
        try:
            reranker = LocalReranker(model_name, top_k)
        except ImportError:
            logger.warning(
                "[重排工厂]local 模式缺少 sentence-transformers"
                "（安装：uv sync --group local-rerank），精排自动关闭"
            )
            return None
        logger.info(f"[重排工厂]精排模型(本地): {model_name}")
        return reranker

    model_name = str(conf.get("remote_model", "gte-rerank-v2"))
    reranker = RemoteReranker(model_name, top_k)
    logger.info(f"[重排工厂]精排模型(远程): {model_name}")
    return reranker


# 懒加载单例：不在 import 时构造（DashScope key 校验/本地模型下载等
# 不应阻断应用启动）；初始化失败按降级策略返回 None
_reranker_singleton: Optional[BaseReranker] = None
_reranker_loaded = False


def get_reranker() -> Optional[BaseReranker]:
    '''获取精排器单例；rerank 关闭或不可用时返回 None'''
    global _reranker_singleton, _reranker_loaded
    if not _reranker_loaded:
        _reranker_loaded = True
        try:
            _reranker_singleton = _create_reranker()
        except Exception as e:
            logger.warning(f"[重排工厂]初始化失败，本进程禁用精排，错误：{e}", exc_info=True)
            _reranker_singleton = None
    return _reranker_singleton


def reset_reranker_cache() -> None:
    '''重置单例缓存（配置变更后重建/单测使用）'''
    global _reranker_singleton, _reranker_loaded
    _reranker_singleton = None
    _reranker_loaded = False

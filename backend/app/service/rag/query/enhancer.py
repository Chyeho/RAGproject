# -*- coding: utf-8 -*-
'''查询优化包装器 QueryEnhancer（P3）

检索链路的最外层前置处理（泛型 BaseRetriever 包装，不依赖具体链路实现）：
  mode=off         → 透传底层链路（默认，行为与 P2 完全一致）
  mode=multi_query → 原查询 + N 个 LLM 改写 → base.batch 并行多路检索 → RRF 融合
  mode=hyde        → 原查询 + 假设文档两路检索 → RRF 融合
                     （假设文档仅用于检索，不进入生成上下文）
变体生成失败时回退为仅原查询直查（不经融合，等价未开启）。
多路检索经 base.batch 并行执行（langchain 默认线程池）。
'''
from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.retrievers import BaseRetriever
from pydantic import PrivateAttr

from app.service.rag.query.hyde import generate_hypothetical_document
from app.service.rag.query.multi_query import generate_multi_queries
from app.service.rag.retrieval.rrf import rrf_fuse
from app.utils.logger_handler import logger

MODES = ("off", "multi_query", "hyde")


class QueryEnhancer(BaseRetriever):
    '''查询优化包装：变体生成 → base.batch 并行多路 → RRF 融合取 topn'''

    mode: str = "off"            # off / multi_query / hyde
    topn: int = 5                # 融合后保留条数（应等于链路有效输出 k）
    rrf_k: int = 60              # RRF 平滑常数（与 hybrid.rrf_k 同源）
    multi_query_count: int = 3   # multi_query 模式改写条数

    _base: BaseRetriever = PrivateAttr()
    _chat_model: BaseChatModel = PrivateAttr()

    def __init__(self, base: BaseRetriever, chat_model: BaseChatModel, mode: str = "off",
                 topn: int = 5, rrf_k: int = 60, multi_query_count: int = 3, **kwargs):
        super().__init__(mode=mode, topn=topn, rrf_k=rrf_k,
                         multi_query_count=multi_query_count, **kwargs)
        self._base = base
        self._chat_model = chat_model

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> list[Document]:
        if self.mode not in ("multi_query", "hyde"):   # off/未知 → 透传
            return self._base.invoke(query)

        if self.mode == "hyde":
            variants = self._hyde_variants(query)
        else:
            variants = self._multi_query_variants(query)

        if len(variants) <= 1:   # 变体生成失败回退：仅原查询直查，不经融合
            logger.warning(f"[查询优化]mode={self.mode} 变体生成失败，回退原查询直查")
            return self._base.invoke(query)

        logger.debug(f"[查询优化]mode={self.mode} 变体数={len(variants)}")
        result_lists = self._base.batch(variants)
        return rrf_fuse(result_lists, rrf_k=self.rrf_k, topn=self.topn)

    def _multi_query_variants(self, query: str) -> list[str]:
        rewrites = generate_multi_queries(self._chat_model, query, self.multi_query_count)
        return [query, *rewrites]

    def _hyde_variants(self, query: str) -> list[str]:
        hypothetical = generate_hypothetical_document(self._chat_model, query)
        return [query, hypothetical] if hypothetical else [query]

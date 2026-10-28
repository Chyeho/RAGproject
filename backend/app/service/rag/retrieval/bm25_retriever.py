# -*- coding: utf-8 -*-
'''BM25 稀疏检索器（P2）

数据源：MySQL document_chunk 表（content 字段），启动时全量构建内存索引；
上传向量化/删除文档事件增量更新；提供 rebuild() 全量重建。
分词：jieba.lcut_for_search（搜索模式，兼顾新词发现）。
'''
import asyncio
import logging

import jieba
from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import PrivateAttr
from rank_bm25 import BM25Okapi
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.database.db import DATABASE_URL
from app.models.document_chunk import DocumentChunk
from app.utils.config_handler import retrieval_conf
from app.utils.logger_handler import logger

# 压掉 jieba 首次分词时 "Building prefix dict" 的构建日志
jieba.setLogLevel(logging.WARNING)


def tokenize(text: str) -> list[str]:
    '''BM25 统一分词：jieba 搜索模式（新词发现 + 长词细切）'''
    return jieba.lcut_for_search(text)


async def fetch_chunk_documents() -> list[Document]:
    '''全量读取 document_chunk 表 → Document 列表

    使用独立短生命周期引擎（NullPool，用完即弃），避免与全局引擎的
    连接在不同事件循环间复用（asyncio.run 的临时循环 / 应用主循环）。
    vector_id 为空的存量分块无法参与 RRF 融合，直接跳过。
    '''
    engine = create_async_engine(DATABASE_URL, poolclass=NullPool)
    try:
        async with AsyncSession(engine) as session:
            rows = (await session.execute(
                select(DocumentChunk.vector_id, DocumentChunk.content, DocumentChunk.document_id)
                .where(DocumentChunk.vector_id.is_not(None))
                .order_by(DocumentChunk.document_id, DocumentChunk.chunk_index)
            )).all()
    finally:
        await engine.dispose()
    return [
        Document(page_content=content, metadata={"vector_id": vector_id, "document_id": document_id})
        for vector_id, content, document_id in rows
    ]


class BM25Retriever(BaseRetriever):
    '''基于 rank_bm25 内存索引的稀疏检索器（BaseRetriever 子类）

    索引结构：{vector_id: Document} 有序字典 + BM25Okapi 统计模型；
    增删后整体重算 BM25 统计（私有知识库规模下开销可忽略，且保证 IDF 一致）。
    '''

    topn: int = 20  # 单路召回条数

    # 内存索引（PrivateAttr：跳过 pydantic 校验，热路径零开销）
    _docs: dict[str, Document] = PrivateAttr(default_factory=dict)
    # 与 BM25Okapi 语料行对齐的 vector_id 顺序表
    _order: list[str] = PrivateAttr(default_factory=list)
    _bm25: BM25Okapi | None = PrivateAttr(default=None)

    @property
    def size(self) -> int:
        '''当前索引文档数'''
        return len(self._docs)

    # ---------- 索引维护 ----------
    def load_documents(self, documents: list[Document]) -> None:
        '''整表替换式重建（传入全量 Document）'''
        self._docs = {}
        for doc in documents:
            vector_id = doc.metadata.get("vector_id")
            if not vector_id:
                logger.warning(f"[BM25]跳过无 vector_id 的分块：{doc.page_content[:30]}...")
                continue
            self._docs[vector_id] = Document(page_content=doc.page_content, metadata=dict(doc.metadata))
        self._rebuild_stats()
        logger.info(f"[BM25]索引已加载，共 {self.size} 个分块")

    def rebuild(self) -> None:
        '''从 MySQL document_chunk 全量重建（同步包装，供 CLI/脚本使用）'''
        documents = asyncio.run(fetch_chunk_documents())
        self.load_documents(documents)

    def add(self, documents: list[Document]) -> None:
        '''增量添加（上传向量化事件）；已存在的 vector_id 覆盖'''
        added = 0
        for doc in documents:
            vector_id = doc.metadata.get("vector_id")
            if not vector_id:
                logger.warning(f"[BM25]增量添加跳过无 vector_id 的分块：{doc.page_content[:30]}...")
                continue
            self._docs[vector_id] = Document(page_content=doc.page_content, metadata=dict(doc.metadata))
            added += 1
        self._rebuild_stats()
        logger.info(f"[BM25]增量添加 {added} 个分块，当前索引 {self.size} 条")

    def remove(self, vector_ids: list[str]) -> None:
        '''增量删除（删除文档事件）'''
        removed = 0
        for vector_id in vector_ids:
            if self._docs.pop(vector_id, None) is not None:
                removed += 1
        self._rebuild_stats()
        logger.info(f"[BM25]增量删除 {removed} 个分块，当前索引 {self.size} 条")

    def _rebuild_stats(self) -> None:
        '''按当前内存文档整体重算 BM25 统计（保证 IDF 与语料一致）'''
        self._order = list(self._docs.keys())
        corpus = [tokenize(self._docs[vid].page_content) for vid in self._order]
        self._bm25 = BM25Okapi(corpus) if corpus else None

    # ---------- 检索 ----------
    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> list[Document]:
        if self._bm25 is None or not query:
            return []
        scores = self._bm25.get_scores(tokenize(query))
        # 语料索引按分数降序；仅保留正相关分（无共同词的文档得 0 分，不参与融合）
        order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        results: list[Document] = []
        for i in order:
            if scores[i] <= 0:
                break
            doc = self._docs[self._order[i]]
            # 返回副本并附 BM25 分数，避免污染索引内对象
            results.append(Document(
                page_content=doc.page_content,
                metadata={**doc.metadata, "bm25_score": float(scores[i])},
            ))
            if len(results) >= self.topn:
                break
        return results


# 模块级单例：应用启动时 rebuild 全量构建，上传/删除事件增量维护（p2-5 接线）
bm25_retriever = BM25Retriever(
    topn=int(retrieval_conf.get("hybrid", {}).get("bm25_topn", 20)),
)

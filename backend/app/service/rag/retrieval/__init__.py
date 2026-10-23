# -*- coding: utf-8 -*-
'''检索组件包（P2：混合检索 + 精排重排）'''
from app.service.rag.retrieval.rrf import rrf_fuse
from app.service.rag.retrieval.bm25_retriever import (
    BM25Retriever,
    bm25_retriever,
    fetch_chunk_documents,
    tokenize,
)
from app.service.rag.retrieval.hybrid_retriever import (
    HybridRetriever,
    RerankRetriever,
    build_retriever,
    hybrid_enabled,
)

__all__ = [
    "rrf_fuse",
    "BM25Retriever",
    "bm25_retriever",
    "fetch_chunk_documents",
    "tokenize",
    "HybridRetriever",
    "RerankRetriever",
    "build_retriever",
    "hybrid_enabled",
]

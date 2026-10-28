# -*- coding: utf-8 -*-
'''RAG 检索/总结工具：复用现有混合检索 + 精排 + 总结链，不写会话历史'''
from typing import Callable

from langchain_core.documents import Document

from app.service.agent.tools.tool_registry import ToolResult


def _doc_score(meta: dict):
    '''评分优先级：rerank_score → bm25_score → score；无则 None'''
    for key in ("rerank_score", "bm25_score", "score"):
        value = meta.get(key)
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                return value
    return None


def doc_to_passage(doc: Document) -> dict:
    '''检索 Document → 工具契约 passage（doc_id / chunk_id / text / score）'''
    meta = doc.metadata or {}
    return {
        "doc_id": meta.get("document_id"),
        "chunk_id": meta.get("vector_id"),
        "text": doc.page_content or "",
        "score": _doc_score(meta),
        "section_path": meta.get("section_path"),
        "page_start": meta.get("page_start"),
        "page_end": meta.get("page_end"),
    }


def build_rag_search_tool(service_getter: Callable | None = None,
                          default_top_k: int = 5):
    '''构造 rag_search 工具

    Args:
        service_getter: 返回 RagSummarizeService 的可调用对象；默认走 registry 单例，
                        保证设置页热更新后工具使用新实例
        default_top_k: 未指定 top_k 时的条数
    '''
    if service_getter is None:
        from app.service.rag import registry
        service_getter = registry.get_rag_service

    def rag_search(action_input: dict) -> ToolResult:
        query = str((action_input or {}).get("query", "")).strip()
        if not query:
            return ToolResult({"error": "query_required", "passages": [], "summary": ""})

        try:
            top_k = int(action_input.get("top_k") or default_top_k)
        except (TypeError, ValueError):
            top_k = default_top_k
        top_k = max(1, min(10, top_k))

        service = service_getter()
        docs = service.retrieve(query, top_k=top_k)
        passages = [doc_to_passage(doc) for doc in docs]
        summary = service.summarize(query, docs, write_history=False) if docs else ""
        return ToolResult({"passages": passages, "summary": summary}, documents=list(docs))

    return rag_search

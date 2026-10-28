# -*- coding: utf-8 -*-
'''rag_search 工具单元测试（检索/总结服务均 mock，全离线）'''
from unittest.mock import MagicMock

from langchain_core.documents import Document

from app.service.agent.tools.rag_search_tool import build_rag_search_tool, doc_to_passage


class TestDocToPassage:
    def test_maps_fields_and_rerank_score(self):
        doc = Document(page_content="差旅住宿标准 500 元", metadata={
            "document_id": "d1", "vector_id": "v1", "rerank_score": 0.92,
            "bm25_score": 5.0, "section_path": "第一章", "page_start": 1, "page_end": 2,
        })
        passage = doc_to_passage(doc)
        assert passage["doc_id"] == "d1"
        assert passage["chunk_id"] == "v1"
        assert passage["text"] == "差旅住宿标准 500 元"
        assert passage["score"] == 0.92
        assert passage["section_path"] == "第一章"
        assert passage["page_start"] == 1
        assert passage["page_end"] == 2

    def test_score_fallback_bm25(self):
        doc = Document(page_content="x", metadata={"bm25_score": 3, "score": 1})
        assert doc_to_passage(doc)["score"] == 3.0

    def test_no_score_returns_none(self):
        doc = Document(page_content="x", metadata={})
        passage = doc_to_passage(doc)
        assert passage["score"] is None
        assert passage["doc_id"] is None
        assert passage["chunk_id"] is None


class TestRagSearchTool:
    def _service(self, docs, summary="总结"):
        service = MagicMock()
        service.retrieve.return_value = docs
        service.summarize.return_value = summary
        return service

    def test_empty_query_rejected(self):
        tool = build_rag_search_tool(service_getter=lambda: MagicMock())
        result = tool({"query": "   "})
        assert result.observation["error"] == "query_required"
        assert result.observation["passages"] == []
        assert result.documents == []

    def test_retrieve_and_summarize_without_history(self):
        docs = [Document(page_content="差旅标准", metadata={
            "document_id": "d1", "vector_id": "v1", "rerank_score": 0.8})]
        service = self._service(docs)
        tool = build_rag_search_tool(service_getter=lambda: service, default_top_k=3)

        result = tool({"query": "差旅标准", "top_k": 2})

        service.retrieve.assert_called_once_with("差旅标准", top_k=2)
        # 子查询不得污染会话历史
        service.summarize.assert_called_once_with("差旅标准", docs, write_history=False)
        assert result.observation["summary"] == "总结"
        assert result.observation["passages"][0]["doc_id"] == "d1"
        assert result.documents == docs

    def test_top_k_clamped_to_1_10(self):
        service = self._service([])
        tool = build_rag_search_tool(service_getter=lambda: service)

        tool({"query": "q", "top_k": 99})
        assert service.retrieve.call_args.kwargs["top_k"] == 10

        tool({"query": "q", "top_k": -3})
        assert service.retrieve.call_args.kwargs["top_k"] == 1

        # 0 视为未指定，回退默认值
        tool({"query": "q", "top_k": 0})
        assert service.retrieve.call_args.kwargs["top_k"] == 5

    def test_invalid_top_k_uses_default(self):
        service = self._service([])
        tool = build_rag_search_tool(service_getter=lambda: service, default_top_k=4)

        tool({"query": "q", "top_k": "abc"})
        service.retrieve.assert_called_once_with("q", top_k=4)

    def test_no_docs_skips_summary(self):
        service = self._service([])
        tool = build_rag_search_tool(service_getter=lambda: service)

        result = tool({"query": "q"})

        service.summarize.assert_not_called()
        assert result.observation["summary"] == ""
        assert result.observation["passages"] == []

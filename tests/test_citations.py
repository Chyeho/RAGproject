# -*- coding: utf-8 -*-
"""引用同源拼装单元测试（P4：build_citations_from_docs，回答与引用来自同一次检索）"""
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.documents import Document

from app.routers.chat import build_citations_from_docs


def _db_doc(doc_id, name):
    d = MagicMock()
    d.id = doc_id
    d.file_name = name
    return d


def _session_with(docs_map):
    """AsyncSession mock：session.get(Document, pk) → docs_map[pk]（缺省 None）"""
    session = MagicMock()
    session.get = AsyncMock(side_effect=lambda model, pk: docs_map.get(pk))
    return session


class TestBuildCitationsFromDocs:

    @pytest.mark.anyio
    async def test_citation_fields_mapped(self):
        """元数据映射：document_id/section_path/page_start/page_end/snippet"""
        doc = Document(page_content="考勤制度内容", metadata={
            "document_id": 7, "section_path": "员工手册/第三章", "page_start": 12, "page_end": 13,
        })
        session = _session_with({7: _db_doc(7, "员工手册.pdf")})

        citations = await build_citations_from_docs([doc], session)

        assert len(citations) == 1
        c = citations[0]
        assert c["documentId"] == 7
        assert c["documentName"] == "员工手册.pdf"
        assert c["sectionPath"] == "员工手册/第三章"
        assert c["pageStart"] == 12
        assert c["pageEnd"] == 13
        assert c["snippet"] == "考勤制度内容"

    @pytest.mark.anyio
    async def test_dedup_by_document_id_keeps_first(self):
        """同一文档多命中块 → 去重保留排序最靠前的块"""
        d1 = Document(page_content="第一块", metadata={"document_id": 7})
        d2 = Document(page_content="第二块", metadata={"document_id": 7})
        session = _session_with({7: _db_doc(7, "手册.pdf")})

        citations = await build_citations_from_docs([d1, d2], session)

        assert len(citations) == 1
        assert citations[0]["snippet"] == "第一块"

    @pytest.mark.anyio
    async def test_skips_docs_without_valid_document_id(self):
        """无 document_id / 非数字 id 跳过；字符串数字 id 可 int() 归一"""
        docs = [
            Document(page_content="无id", metadata={}),
            Document(page_content="非法id", metadata={"document_id": "abc"}),
            Document(page_content="字符串数字id", metadata={"document_id": "9"}),
        ]
        session = _session_with({9: _db_doc(9, "ok.pdf")})

        citations = await build_citations_from_docs(docs, session)

        assert [c["documentId"] for c in citations] == [9]

    @pytest.mark.anyio
    async def test_db_lookup_failure_and_missing_doc_skipped(self):
        """反查异常 / 文档已删除 → 跳过该引用，不影响其余拼装"""
        good = Document(page_content="ok", metadata={"document_id": 5})
        bad = Document(page_content="bad", metadata={"document_id": 6})
        session = MagicMock()

        async def _get(model, pk):
            if pk == 6:
                raise RuntimeError("db down")
            return _db_doc(5, "ok.pdf") if pk == 5 else None

        session.get = AsyncMock(side_effect=_get)

        citations = await build_citations_from_docs([good, bad], session)

        assert len(citations) == 1
        assert citations[0]["documentId"] == 5

    @pytest.mark.anyio
    async def test_snippet_truncated_to_200(self):
        """snippet 超长截断至 200 字符"""
        doc = Document(page_content="x" * 500, metadata={"document_id": 5})
        session = _session_with({5: _db_doc(5, "long.pdf")})

        citations = await build_citations_from_docs([doc], session)

        assert len(citations[0]["snippet"]) == 200

# -*- coding: utf-8 -*-
"""rrf.py RRF 多路召回融合单元测试（纯函数，无外部依赖）"""
import pytest
from langchain_core.documents import Document

from app.service.rag.retrieval.rrf import rrf_fuse


def _doc(vector_id, text, **meta):
    return Document(page_content=text, metadata={"vector_id": vector_id, **meta})


class TestRRFFuse:
    def test_scores_and_order(self):
        """双路重叠文档累加分数，重叠者排前"""
        dense = [_doc("a", "文档A", document_id=1), _doc("b", "文档B", document_id=2)]
        bm25 = [_doc("c", "文档C", document_id=3), _doc("a", "文档A", document_id=1)]

        result = rrf_fuse([dense, bm25], rrf_k=60, topn=10)

        # a = 1/61 + 1/62（双路命中）；c = 1/61；b = 1/62
        assert [d.metadata["vector_id"] for d in result] == ["a", "c", "b"]
        assert result[0].metadata["rrf_score"] == pytest.approx(1 / 61 + 1 / 62, abs=1e-6)
        assert result[1].metadata["rrf_score"] == pytest.approx(1 / 61, abs=1e-6)
        assert result[2].metadata["rrf_score"] == pytest.approx(1 / 62, abs=1e-6)

    def test_dedup_by_vector_id(self):
        """同 vector_id 跨路去重，只输出一个文档"""
        dense = [_doc("a", "文档A内容")]
        bm25 = [_doc("a", "文档A内容")]
        result = rrf_fuse([dense, bm25])
        assert len(result) == 1

    def test_metadata_merge_first_wins(self):
        """metadata 合并：首现文档做底稿，后续仅补缺失键（不覆盖已有键）"""
        dense = [_doc("a", "文档A", document_id=1)]
        bm25 = [_doc("a", "文档A", document_id=999, bm25_score=2.5)]

        result = rrf_fuse([dense, bm25])

        meta = result[0].metadata
        assert meta["document_id"] == 1          # 首现键优先，不被 999 覆盖
        assert meta["bm25_score"] == 2.5         # 缺失键被补齐
        assert "rrf_score" in meta

    def test_topn_truncation(self):
        """融合结果按分数降序截断 topn"""
        docs_a = [_doc(f"v{i}", f"内容{i}") for i in range(5)]
        result = rrf_fuse([docs_a], topn=3)
        assert len(result) == 3
        assert [d.metadata["vector_id"] for d in result] == ["v0", "v1", "v2"]

    def test_skip_docs_without_vector_id(self):
        """无 vector_id 的结果无法参与融合，跳过"""
        with_id = _doc("a", "有ID")
        no_id = Document(page_content="无ID", metadata={"document_id": 9})
        result = rrf_fuse([[with_id, no_id], [no_id]])
        assert len(result) == 1
        assert result[0].metadata["vector_id"] == "a"

    def test_empty_inputs(self):
        """空列表/全无效输入返回空"""
        assert rrf_fuse([]) == []
        assert rrf_fuse([[], []]) == []

    def test_input_docs_not_mutated(self):
        """输出新建 Document，入参对象不被添加 rrf_score"""
        dense = [_doc("a", "文档A")]
        bm25 = [_doc("a", "文档A")]
        rrf_fuse([dense, bm25])
        for doc in dense + bm25:
            assert "rrf_score" not in doc.metadata

    def test_output_page_content_from_first_seen(self):
        """输出去重文档取首现路的正文"""
        dense = [_doc("a", "稠密路正文")]
        bm25 = [_doc("a", "BM25路正文")]
        result = rrf_fuse([dense, bm25])
        assert result[0].page_content == "稠密路正文"

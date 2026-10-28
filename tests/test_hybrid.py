# -*- coding: utf-8 -*-
"""hybrid_retriever.py 混合检索/精排包装/链路工厂单元测试（稠密路与精排器全 mock）"""
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.documents import Document

from app.service.rag.retrieval import hybrid_retriever as hybrid_mod
from app.service.rag.retrieval.bm25_retriever import BM25Retriever
from app.service.rag.retrieval.hybrid_retriever import (
    HybridRetriever, RerankRetriever, _effective_conf, build_retriever, hybrid_enabled,
)


def _doc(vector_id, text, **meta):
    return Document(page_content=text, metadata={"vector_id": vector_id, **meta})


@pytest.fixture
def stub_bm25():
    return BM25Retriever(topn=2)


@pytest.fixture
def mock_svc():
    """稠密路服务 mock：get_retriever 返回可识别的假检索器"""
    svc = MagicMock()
    fake_dense = MagicMock(name="dense")
    svc.get_retriever.return_value = fake_dense
    return svc


# ---------- HybridRetriever ----------

class TestHybridRetriever:
    def test_fuses_dense_and_bm25(self):
        """RRF 融合：双路命中靠前，单路命中保留（bm25 路用 mock，与 BM25 检索行为解耦）"""
        dense = MagicMock()
        dense.invoke.return_value = [_doc("a", "重叠文档"), _doc("b", "仅稠密")]
        bm25 = MagicMock()
        bm25.invoke.return_value = [_doc("a", "重叠文档"), _doc("c", "仅BM25")]

        r = HybridRetriever(dense=dense, bm25=bm25, rrf_k=60, topn=10)
        result = r.invoke("查询")

        dense.invoke.assert_called_once_with("查询")
        bm25.invoke.assert_called_once_with("查询")
        # a 双路命中排首；b/c 单路命中
        assert result[0].metadata["vector_id"] == "a"
        assert {d.metadata["vector_id"] for d in result} == {"a", "b", "c"}
        assert "rrf_score" in result[0].metadata

    def test_topn_limits_output(self, stub_bm25):
        dense = MagicMock()
        dense.invoke.return_value = [_doc(f"d{i}", f"稠密{i}") for i in range(5)]
        r = HybridRetriever(dense=dense, bm25=stub_bm25, topn=3)
        assert len(r.invoke("问题")) == 3


# ---------- RerankRetriever ----------

class TestRerankRetriever:
    def test_reranks_and_attaches_score(self):
        base = MagicMock()
        docs = [_doc("a", "候选一"), _doc("b", "候选二")]
        base.invoke.return_value = docs
        reranker = MagicMock()
        reranker.safe_rank.return_value = [(docs[1], 0.9), (docs[0], 0.1)]

        r = RerankRetriever(base=base, reranker=reranker)
        result = r.invoke("问题")

        reranker.safe_rank.assert_called_once_with("问题", docs)
        assert [d.page_content for d in result] == ["候选二", "候选一"]
        assert result[0].metadata["rerank_score"] == 0.9
        # 原有 metadata 保留
        assert result[0].metadata["vector_id"] == "b"

    def test_empty_base_returns_empty(self):
        base = MagicMock()
        base.invoke.return_value = []
        reranker = MagicMock()
        r = RerankRetriever(base=base, reranker=reranker)
        assert r.invoke("问题") == []
        reranker.safe_rank.assert_not_called()   # 空召回不触发精排


# ---------- hybrid_enabled / _effective_conf ----------

class TestHybridEnabled:
    def test_follows_file_config(self):
        with patch.object(hybrid_mod, "retrieval_conf",
                          {"hybrid": {"enabled": True}}):
            assert hybrid_enabled() is True

    def test_off_or_missing(self):
        with patch.object(hybrid_mod, "retrieval_conf",
                          {"hybrid": {"enabled": False}}):
            assert hybrid_enabled() is False
        with patch.object(hybrid_mod, "retrieval_conf", {}):
            assert hybrid_enabled() is False


class TestEffectiveConf:
    def test_no_overrides_reads_file(self):
        conf = _effective_conf(None)
        assert conf["top_k"] > 0 and conf["legacy_k"] > 0
        assert "enabled" in conf["hybrid"] and "enabled" in conf["rerank"]

    def test_section_shallow_merge(self):
        """section 内浅合并：只覆盖指定键，其余保留文件值"""
        file_hybrid = hybrid_mod.retrieval_conf.get("hybrid", {})
        if "dense_topn" in file_hybrid:   # 文件配置含该键时才可断言保留语义
            conf = _effective_conf({"hybrid": {"enabled": False}})
            assert conf["hybrid"]["enabled"] is False
            assert conf["hybrid"]["dense_topn"] == file_hybrid["dense_topn"]

    def test_scalar_override(self):
        conf = _effective_conf({"legacy_k": 5, "top_k": 8})
        assert conf["legacy_k"] == 5 and conf["top_k"] == 8

    def test_overrides_do_not_pollute_file(self):
        _effective_conf({"hybrid": {"enabled": False}, "legacy_k": 5})
        recheck = _effective_conf(None)
        assert recheck["legacy_k"] == int(hybrid_mod.retrieval_conf.get("legacy_k", 3))
        assert recheck["hybrid"]["enabled"] == bool(
            hybrid_mod.retrieval_conf.get("hybrid", {}).get("enabled", False))


# ---------- build_retriever 四开关组合 ----------

class TestBuildRetriever:
    def _reranker_stub(self):
        stub = MagicMock()
        stub.top_k = 5
        return stub

    def test_all_off_returns_dense_with_legacy_k(self, mock_svc):
        """组合1：全关闭 → 稠密原样 k=legacy_k（等价旧链路）"""
        legacy_k = int(hybrid_mod.retrieval_conf.get("legacy_k", 3))
        r = build_retriever(mock_svc, overrides={"hybrid": {"enabled": False},
                                                 "rerank": {"enabled": False}})
        assert r is mock_svc.get_retriever.return_value
        mock_svc.get_retriever.assert_called_once_with(k=legacy_k)

    def test_all_off_with_k_override(self, mock_svc):
        """全关闭 + legacy_k 标量覆盖 → 稠密 k=覆盖值"""
        r = build_retriever(mock_svc, overrides={"hybrid": {"enabled": False},
                                                 "rerank": {"enabled": False},
                                                 "legacy_k": 5})
        mock_svc.get_retriever.assert_called_once_with(k=5)

    def test_hybrid_only(self, mock_svc, stub_bm25):
        """组合2：仅混合 → HybridRetriever，dense_k=dense_topn，融合 topn=top_k"""
        dense_topn = int(hybrid_mod.retrieval_conf.get("hybrid", {}).get("dense_topn", 20))
        top_k = int(hybrid_mod.retrieval_conf.get("top_k", 5))
        r = build_retriever(mock_svc, bm25=stub_bm25,
                            overrides={"hybrid": {"enabled": True}, "rerank": {"enabled": False}})
        assert isinstance(r, HybridRetriever)
        mock_svc.get_retriever.assert_called_once_with(k=dense_topn)
        assert r.topn == top_k

    def test_rerank_only(self, mock_svc):
        """组合3：仅精排 → 稠密候选直送精排"""
        reranker = self._reranker_stub()
        r = build_retriever(mock_svc, reranker=reranker,
                            overrides={"hybrid": {"enabled": False}, "rerank": {"enabled": True}})
        assert isinstance(r, RerankRetriever)
        assert r._base is mock_svc.get_retriever.return_value
        assert r._reranker is reranker

    def test_hybrid_and_rerank(self, mock_svc, stub_bm25):
        """组合4：全开 → RerankRetriever(HybridRetriever(topn=hybrid.topn))"""
        hybrid_topn = int(hybrid_mod.retrieval_conf.get("hybrid", {}).get("topn", 20))
        reranker = self._reranker_stub()
        with patch.object(hybrid_mod, "_create_reranker", return_value=reranker):
            r = build_retriever(mock_svc, bm25=stub_bm25,
                                overrides={"hybrid": {"enabled": True}, "rerank": {"enabled": True}})
        assert isinstance(r, RerankRetriever)
        assert isinstance(r._base, HybridRetriever)
        assert r._base.topn == hybrid_topn      # 融合候选数（送精排）
        assert r._reranker is reranker

    def test_reranker_creation_failure_degrades(self, mock_svc, stub_bm25):
        """精排器创建失败 → 降级组合2（HybridRetriever），链路不中断"""
        with patch.object(hybrid_mod, "_create_reranker",
                          side_effect=RuntimeError("key missing")):
            r = build_retriever(mock_svc, bm25=stub_bm25,
                                overrides={"hybrid": {"enabled": True}, "rerank": {"enabled": True}})
        assert isinstance(r, HybridRetriever)

    def test_lazy_no_reranker_creation_when_off(self, mock_svc, stub_bm25):
        """rerank 关闭时不创建精排器（懒创建语义）"""
        with patch.object(hybrid_mod, "_create_reranker") as mock_create:
            build_retriever(mock_svc, bm25=stub_bm25,
                            overrides={"hybrid": {"enabled": True}, "rerank": {"enabled": False}})
        mock_create.assert_not_called()

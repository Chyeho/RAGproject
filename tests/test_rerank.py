# -*- coding: utf-8 -*-
"""rerank_factory.py 精排器工厂单元测试（remote/local 构造与 rank 全 mock，不触网不下载模型）"""
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.documents import Document

from app.modelFactory import rerank_factory as rf
from app.modelFactory.rerank_factory import (
    BaseReranker, LocalReranker, RemoteReranker,
    _create_reranker, get_reranker, reset_reranker_cache,
)


def _doc(text, **meta):
    return Document(page_content=text, metadata=meta)


class _StubReranker(BaseReranker):
    """可控桩：ok 时按 rank_result 返回；raise_err 时抛异常"""

    def __init__(self, rank_result=None, raise_err=False, top_k=5):
        self.top_k = top_k
        self._rank_result = rank_result
        self._raise_err = raise_err

    def rank(self, query, documents):
        if self._raise_err:
            raise RuntimeError("精排服务不可用")
        return self._rank_result


@pytest.fixture(autouse=True)
def _reset_singleton():
    """每个用例后重置单例缓存，避免用例间污染"""
    yield
    reset_reranker_cache()


class TestSafeRank:
    def test_normal_passthrough(self):
        docs = [_doc("内容一"), _doc("内容二")]
        stub = _StubReranker(rank_result=[(docs[1], 0.9), (docs[0], 0.1)])
        assert stub.safe_rank("问题", docs) == [(docs[1], 0.9), (docs[0], 0.1)]

    def test_empty_documents_short_circuit(self):
        stub = _StubReranker(raise_err=True)
        assert stub.safe_rank("问题", []) == []   # 空输入不触发 rank

    def test_fallback_on_rank_error(self):
        """精排异常降级：返回输入序（RRF 序）前 top_k 条，分数取 rrf_score"""
        docs = [
            _doc("内容一", vector_id="a", rrf_score=0.033),
            _doc("内容二", vector_id="b", rrf_score=0.020),
            _doc("内容三", vector_id="c"),
        ]
        stub = _StubReranker(raise_err=True, top_k=2)
        result = stub.safe_rank("问题", docs)
        assert result == [(docs[0], pytest.approx(0.033)), (docs[1], pytest.approx(0.020))]


class TestRemoteReranker:
    def test_construct_and_rank(self):
        """构造走 DashScopeRerank；rank 取 relevance_score 元数据"""
        fake_compressor = MagicMock()
        ranked_docs = [
            _doc("相关内容", relevance_score=0.95),
            _doc("次相关", relevance_score=0.40),
        ]
        fake_compressor.compress_documents.return_value = ranked_docs

        with patch("langchain_community.document_compressors.dashscope_rerank.DashScopeRerank",
                   return_value=fake_compressor) as mock_cls:
            reranker = RemoteReranker(model="gte-rerank-v2", top_k=2)

        mock_cls.assert_called_once_with(model="gte-rerank-v2", top_n=2)
        assert reranker.top_k == 2

        result = reranker.rank("问题", [_doc("相关内容"), _doc("次相关"), _doc("无关")])
        fake_compressor.compress_documents.assert_called_once()
        assert result == [(ranked_docs[0], pytest.approx(0.95)),
                          (ranked_docs[1], pytest.approx(0.40))]


class TestLocalReranker:
    def test_rank_sorts_by_score_and_truncates(self):
        """rank 按 CrossEncoder 分数降序取 top_k"""
        fake_model = MagicMock()
        fake_model.predict.return_value = [0.1, 0.9, 0.5]   # doc0/1/2 的分
        reranker = LocalReranker.__new__(LocalReranker)
        reranker._model = fake_model
        reranker.top_k = 2

        docs = [_doc("甲"), _doc("乙"), _doc("丙")]
        result = reranker.rank("问题", docs)
        assert result == [(docs[1], pytest.approx(0.9)), (docs[2], pytest.approx(0.5))]

    def test_rank_empty_documents(self):
        reranker = LocalReranker.__new__(LocalReranker)
        reranker._model = MagicMock()
        reranker.top_k = 2
        assert reranker.rank("问题", []) == []


class TestCreateReranker:
    def test_disabled_returns_none(self):
        assert _create_reranker({"enabled": False}) is None

    def test_remote_mode_construction(self):
        """remote 模式用 remote_model 创建 RemoteReranker"""
        conf = {"enabled": True, "remote_model": "gte-rerank-v2", "top_k": 3}
        stub = _StubReranker()
        with patch.object(rf, "_get_model_mode", return_value="remote"), \
             patch.object(rf, "RemoteReranker", return_value=stub) as mock_rr:
            result = _create_reranker(conf)
        mock_rr.assert_called_once_with("gte-rerank-v2", 3)
        assert result is stub

    def test_local_mode_missing_dependency_returns_none(self):
        """local 模式缺 sentence-transformers：ImportError → 精排关闭返回 None"""
        conf = {"enabled": True, "local_model": "BAAI/bge-reranker-v2-m3", "top_k": 5}
        with patch.object(rf, "_get_model_mode", return_value="local"), \
             patch.object(rf, "LocalReranker", side_effect=ImportError("no module")):
            assert _create_reranker(conf) is None

    def test_local_mode_ok(self):
        conf = {"enabled": True, "local_model": "BAAI/bge-reranker-v2-m3", "top_k": 4}
        stub = _StubReranker()
        with patch.object(rf, "_get_model_mode", return_value="local"), \
             patch.object(rf, "LocalReranker", return_value=stub) as mock_lr:
            result = _create_reranker(conf)
        mock_lr.assert_called_once_with("BAAI/bge-reranker-v2-m3", 4)
        assert result is stub


class TestSingleton:
    def test_lazy_created_once(self):
        stub = _StubReranker()
        with patch.object(rf, "_create_reranker", return_value=stub) as mock_create:
            assert get_reranker() is stub
            assert get_reranker() is stub
        assert mock_create.call_count == 1

    def test_init_failure_disables_rerank(self):
        """初始化异常 → 本进程禁用精排（None），不抛出"""
        with patch.object(rf, "_create_reranker", side_effect=RuntimeError("boom")):
            assert get_reranker() is None
            assert get_reranker() is None   # 失败后不再重试

    def test_reset_recreates(self):
        stub1, stub2 = _StubReranker(), _StubReranker()
        with patch.object(rf, "_create_reranker", side_effect=[stub1, stub2]):
            assert get_reranker() is stub1
            reset_reranker_cache()
            assert get_reranker() is stub2

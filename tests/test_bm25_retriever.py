# -*- coding: utf-8 -*-
"""bm25_retriever.py BM25 稀疏检索器单元测试（内存索引全离线，rebuild 用 mock 数据源）

语料设计说明：BM25Okapi 的 IDF 在 df≥N/2 时非正（负值被替换为 epsilon*均值），
故各用例语料的 query 命中词需满足 df < N/2 才能产生正分，语料均带足量干扰文档。
"""
import importlib

import pytest
from langchain_core.documents import Document
from unittest.mock import AsyncMock, patch

from app.service.rag.retrieval.bm25_retriever import BM25Retriever, tokenize

# 包 __init__ re-export 了单例 bm25_retriever，遮蔽子模块名（py3.7+ 的
# `import a.b as x` 走 getattr(包, 名) 同样拿到单例），经 importlib 取回真模块作 patch 目标
bm25_mod = importlib.import_module("app.service.rag.retrieval.bm25_retriever")


def _chunk(vector_id, text, document_id=1):
    return Document(page_content=text,
                    metadata={"vector_id": vector_id, "document_id": document_id})


@pytest.fixture
def retriever():
    """每个用例独立实例，避免共享模块单例状态"""
    return BM25Retriever(topn=3)


class TestTokenize:
    def test_search_mode_tokens(self):
        """jieba 搜索模式：返回非空 token 列表"""
        tokens = tokenize("年假满一年不满五天")
        assert isinstance(tokens, list) and tokens

    def test_long_word_split(self):
        """搜索模式对长词细切（如'机器学习'含'机器'）"""
        tokens = tokenize("机器学习")
        assert "机器" in tokens and "学习" in tokens


class TestLoadAndRetrieve:
    def test_load_then_retrieve(self, retriever):
        """加载后可检索命中，结果附 bm25_score"""
        retriever.load_documents([
            _chunk("v1", "年假满一年不满五年为五天", document_id=1),
            _chunk("v2", "密码长度不得低于十二位", document_id=2),
            _chunk("v3", "报销发票需在三十天内提交财务", document_id=3),
        ])
        assert retriever.size == 3

        docs = retriever.invoke("年假有几天")
        assert docs
        assert docs[0].metadata["vector_id"] == "v1"
        assert docs[0].metadata["bm25_score"] > 0
        # 返回副本，索引内对象不被污染
        assert "bm25_score" not in retriever._docs["v1"].metadata

    def test_no_overlap_returns_empty(self, retriever):
        """query 与语料无共同词（零分）不参与融合，返回空"""
        retriever.load_documents([_chunk("v1", "报销流程需要在一个月内提交")])
        assert retriever.invoke("asdfjkl") == []

    def test_empty_index_returns_empty(self, retriever):
        """空索引安全返回空列表"""
        assert retriever.invoke("任何问题") == []

    def test_topn_truncation(self, retriever):
        """检索结果最多 topn 条且按分数降序"""
        retriever.load_documents([
            _chunk(f"v{i}", f"服务器运维手册第{['一', '二', '三'][i]}章内容", document_id=1)
            for i in range(3)
        ] + [
            _chunk(f"n{i}", text, document_id=2)
            for i, text in enumerate(
                ["考勤制度说明", "报销流程说明", "密码规范说明", "门禁卡管理规定", "差旅住宿标准"])
        ])
        # "服务器"仅在 3/8 个文档出现（df=3 < N/2=4）→ 正分；topn=3 截断
        docs = retriever.invoke("服务器运维")
        assert len(docs) == 3
        assert {d.metadata["vector_id"] for d in docs} == {"v0", "v1", "v2"}
        scores = [d.metadata["bm25_score"] for d in docs]
        assert scores == sorted(scores, reverse=True)

    def test_load_skips_missing_vector_id(self, retriever):
        """无 vector_id 的分块被跳过"""
        retriever.load_documents([
            _chunk("v1", "正常分块"),
            Document(page_content="存量无ID分块", metadata={}),
        ])
        assert retriever.size == 1


class TestIncremental:
    def test_add_increases_and_overwrites(self, retriever):
        """增量添加；同 vector_id 覆盖旧内容"""
        retriever.load_documents([_chunk("v1", "原始内容存档"), _chunk("v2", "无关干扰文本")])
        retriever.add([_chunk("v1", "服务器运维手册内容"), _chunk("v3", "新增条目文本")])
        assert retriever.size == 3
        # 覆盖后检索命中新内容（"服务器" df=1, N=3 → IDF>0）
        docs = retriever.invoke("服务器运维")
        assert docs and docs[0].page_content == "服务器运维手册内容"

    def test_add_skips_missing_vector_id(self, retriever):
        retriever.load_documents([_chunk("v1", "正常分块")])
        retriever.add([Document(page_content="无ID分块", metadata={})])
        assert retriever.size == 1

    def test_remove_existing_and_missing(self, retriever):
        """删除存在的条目生效；不存在的 id 静默忽略"""
        retriever.load_documents([_chunk("v1", "内容一"), _chunk("v2", "内容二")])
        retriever.remove(["v1", "ghost"])
        assert retriever.size == 1
        assert "v2" in retriever._docs

    def test_remove_then_retrieve_excludes(self, retriever):
        """删除后检索不再命中已删内容"""
        retriever.load_documents([
            _chunk("v1", "年假天数说明"),
            _chunk("v2", "年假天数细则补充"),
        ])
        retriever.remove(["v1"])
        docs = retriever.invoke("年假天数")
        assert all(d.metadata["vector_id"] != "v1" for d in docs)

    def test_full_reload_replaces(self, retriever):
        """load_documents 整表替换（旧数据不残留）"""
        retriever.load_documents([_chunk("v1", "旧内容一"), _chunk("v2", "旧内容二")])
        retriever.load_documents([_chunk("v3", "新内容")])
        assert retriever.size == 1
        assert retriever.invoke("旧内容") == []


class TestRebuild:
    def test_rebuild_from_mocked_source(self, retriever):
        """rebuild 从数据源全量重建（mock fetch_chunk_documents，不连库）"""
        with patch.object(bm25_mod, "fetch_chunk_documents", new_callable=AsyncMock,
                          return_value=[_chunk("v1", "重建后的内容"),
                                        _chunk("n1", "无关干扰甲"), _chunk("n2", "无关干扰乙")]) as mock_fetch:
            retriever.rebuild()
        mock_fetch.assert_called_once()
        assert retriever.size == 3
        assert retriever.invoke("重建后的内容")

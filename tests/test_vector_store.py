# -*- coding: utf-8 -*-
"""向量存储服务（Qdrant 版）模块单元测试"""
from unittest.mock import patch, MagicMock

import pytest
from qdrant_client.models import VectorParams

from app.service.rag.vector_store import VectorStoreService


def _patch_init_env(monkeypatch, **kwargs):
    """清除 QDRANT_* 环境变量，避免 docker/.env 干扰"""
    for key in ("QDRANT_HOST", "QDRANT_PORT", "QDRANT_COLLECTION"):
        monkeypatch.delenv(key, raising=False)


class TestVectorStoreServiceInit:
    """测试初始化"""

    @patch("app.service.rag.vector_store.QdrantClient")
    @patch("app.service.rag.vector_store.QdrantVectorStore")
    @patch("app.service.rag.vector_store.embed_model")
    def test_creates_qdrant_client(self, mock_embed, mock_store, mock_client):
        """验证会创建 QdrantClient 实例"""
        mock_client.return_value = MagicMock()
        mock_store.return_value = MagicMock()
        VectorStoreService()
        mock_client.assert_called_once()

    @patch("app.service.rag.vector_store.QdrantClient")
    @patch("app.service.rag.vector_store.QdrantVectorStore")
    @patch("app.service.rag.vector_store.embed_model")
    def test_creates_collection_when_missing(self, mock_embed, mock_store, mock_client):
        """collection 不存在时自动创建（按嵌入维度 + Cosine 距离）"""
        client_instance = MagicMock()
        client_instance.collection_exists.return_value = False
        mock_client.return_value = client_instance
        # embed_model 是模块级实例：embed_query 返回固定维度向量
        mock_embed.embed_query.return_value = [0.1] * 8
        mock_store.return_value = MagicMock()

        VectorStoreService()

        # 探测维度并创建 collection
        mock_embed.embed_query.assert_called_once()
        client_instance.create_collection.assert_called_once()
        call_kwargs = client_instance.create_collection.call_args[1]
        assert isinstance(call_kwargs["vectors_config"], VectorParams)
        assert call_kwargs["vectors_config"].size == 8

    @patch("app.service.rag.vector_store.QdrantClient")
    @patch("app.service.rag.vector_store.QdrantVectorStore")
    @patch("app.service.rag.vector_store.embed_model")
    def test_skips_collection_when_exists(self, mock_embed, mock_store, mock_client):
        """collection 已存在时不重复创建"""
        client_instance = MagicMock()
        client_instance.collection_exists.return_value = True
        mock_client.return_value = client_instance
        mock_store.return_value = MagicMock()

        VectorStoreService()

        client_instance.create_collection.assert_not_called()

    @patch("app.service.rag.vector_store.QdrantClient")
    @patch("app.service.rag.vector_store.QdrantVectorStore")
    @patch("app.service.rag.vector_store.embed_model")
    def test_creates_vector_store(self, mock_embed, mock_store, mock_client):
        """验证会创建 QdrantVectorStore"""
        mock_client.return_value = MagicMock()
        mock_store.return_value = MagicMock()
        VectorStoreService()
        mock_store.assert_called_once()

    @patch("app.service.rag.vector_store.QdrantClient")
    @patch("app.service.rag.vector_store.QdrantVectorStore")
    @patch("app.service.rag.vector_store.embed_model")
    def test_env_host_port_takes_priority(self, mock_embed, mock_store, mock_client, monkeypatch):
        """环境变量 QDRANT_HOST/PORT 优先于 yaml 配置"""
        monkeypatch.setenv("QDRANT_HOST", "qdrant-internal")
        monkeypatch.setenv("QDRANT_PORT", "6334")
        client_instance = MagicMock()
        mock_client.return_value = client_instance
        mock_store.return_value = MagicMock()

        VectorStoreService()

        # QdrantClient(host=..., port=..., check_compatibility=False) 以关键字传参
        call_kwargs = mock_client.call_args.kwargs
        assert call_kwargs["host"] == "qdrant-internal"
        assert call_kwargs["port"] == 6334


class TestGetRetriever:
    """测试 get_retriever 方法"""

    @patch("app.service.rag.vector_store.QdrantClient")
    @patch("app.service.rag.vector_store.QdrantVectorStore")
    @patch("app.service.rag.vector_store.embed_model")
    def test_returns_retriever(self, mock_embed, mock_store, mock_client):
        mock_client.return_value = MagicMock()
        store_instance = MagicMock()
        mock_retriever = MagicMock()
        store_instance.as_retriever.return_value = mock_retriever
        mock_store.return_value = store_instance

        vs = VectorStoreService()
        result = vs.get_retriever()
        assert result is mock_retriever
        store_instance.as_retriever.assert_called_once()


class TestBuildChunkId:
    """测试 build_chunk_id（P1：确定性 chunk ID）"""

    def test_deterministic_for_same_args(self):
        from app.service.rag.vector_store import build_chunk_id
        assert build_chunk_id(7, 0) == build_chunk_id(7, 0)

    def test_different_for_different_args(self):
        from app.service.rag.vector_store import build_chunk_id
        assert build_chunk_id(7, 0) != build_chunk_id(8, 0)
        assert build_chunk_id(7, 0) != build_chunk_id(7, 1)

    def test_returns_uuid_string(self):
        import uuid
        from app.service.rag.vector_store import build_chunk_id
        chunk_id = build_chunk_id(7, 0)
        assert isinstance(chunk_id, str)
        uuid.UUID(chunk_id)  # 能被解析为合法 UUID


class TestUploadFile:
    """测试 upload_file 方法（P1：格式感知分块 + 确定性 chunk ID）"""

    @patch("app.service.rag.vector_store.QdrantClient")
    @patch("app.service.rag.vector_store.QdrantVectorStore")
    @patch("app.service.rag.vector_store.embed_model")
    def test_returns_chunks_with_deterministic_ids(self, mock_embed, mock_store, mock_client, monkeypatch):
        """成功向量化：确定性 ID 传入 add_documents，返回 [(chunk_text, vector_id)]"""
        _patch_init_env(monkeypatch)
        from langchain_core.documents import Document
        from app.service.rag.vector_store import build_chunk_id

        mock_client.return_value = MagicMock()
        store_instance = MagicMock()
        expected_ids = [build_chunk_id(7, 0), build_chunk_id(7, 1)]
        store_instance.add_documents.return_value = expected_ids
        mock_store.return_value = store_instance

        docs = [
            Document(page_content="第一段内容", metadata={"section_path": "1 总则"}),
            Document(page_content="第二段内容", metadata={}),
        ]
        with patch("app.service.rag.vector_store.chunk_file", return_value=docs):
            vs = VectorStoreService()
            result = vs.upload_file("/tmp/test.pdf", document_id=7)

        # 调用参数：documents + 确定性 ids
        call_args = store_instance.add_documents.call_args
        assert call_args.args[0] == docs
        assert call_args.kwargs["ids"] == expected_ids

        # 元数据合并：保留 chunker 结构信息 + 索引信息（不覆盖原有键）
        assert docs[0].metadata["section_path"] == "1 总则"
        assert docs[0].metadata["chunk_index"] == 0
        assert docs[0].metadata["total_chunks"] == 2
        assert docs[0].metadata["document_id"] == 7
        assert docs[0].metadata["vector_id"] == expected_ids[0]
        assert docs[1].metadata["chunk_index"] == 1

        # 返回 [(chunk_text, vector_id)]
        assert result[0] == ("第一段内容", expected_ids[0])
        assert result[1] == ("第二段内容", expected_ids[1])

    @patch("app.service.rag.vector_store.QdrantClient")
    @patch("app.service.rag.vector_store.QdrantVectorStore")
    @patch("app.service.rag.vector_store.embed_model")
    def test_empty_documents_raises_value_error(self, mock_embed, mock_store, mock_client, monkeypatch):
        """文档无有效文本内容时抛出 ValueError"""
        _patch_init_env(monkeypatch)
        mock_client.return_value = MagicMock()
        mock_store.return_value = MagicMock()
        with patch("app.service.rag.vector_store.chunk_file", return_value=[]):
            vs = VectorStoreService()
            with pytest.raises(ValueError):
                vs.upload_file("/tmp/empty.txt")

    @patch("app.service.rag.vector_store.QdrantClient")
    @patch("app.service.rag.vector_store.QdrantVectorStore")
    @patch("app.service.rag.vector_store.embed_model")
    def test_without_document_id_no_deterministic_ids(self, mock_embed, mock_store, mock_client, monkeypatch):
        """未传 document_id 时不注入确定性 ID，元数据不含 document_id/vector_id"""
        _patch_init_env(monkeypatch)
        from langchain_core.documents import Document

        mock_client.return_value = MagicMock()
        store_instance = MagicMock()
        store_instance.add_documents.return_value = ["vec-1"]
        mock_store.return_value = store_instance

        docs = [Document(page_content="内容", metadata={"source": "a.txt"})]
        with patch("app.service.rag.vector_store.chunk_file", return_value=docs):
            vs = VectorStoreService()
            vs.upload_file("/tmp/test.txt")

        call_kwargs = store_instance.add_documents.call_args.kwargs
        assert call_kwargs["ids"] is None
        assert "document_id" not in docs[0].metadata
        assert "vector_id" not in docs[0].metadata
        # 仍会附加索引信息
        assert docs[0].metadata["chunk_index"] == 0
        assert docs[0].metadata["total_chunks"] == 1
        assert docs[0].metadata["source"] == "a.txt"


class TestDeleteByVectorIds:
    """测试 delete_by_vector_ids 方法"""

    @patch("app.service.rag.vector_store.QdrantClient")
    @patch("app.service.rag.vector_store.QdrantVectorStore")
    @patch("app.service.rag.vector_store.embed_model")
    def test_empty_list_does_nothing(self, mock_embed, mock_store, mock_client):
        """空 vector_ids 不调用删除"""
        mock_client.return_value = MagicMock()
        store_instance = MagicMock()
        mock_store.return_value = store_instance

        vs = VectorStoreService()
        vs.delete_by_vector_ids([])
        store_instance.delete.assert_not_called()

    @patch("app.service.rag.vector_store.QdrantClient")
    @patch("app.service.rag.vector_store.QdrantVectorStore")
    @patch("app.service.rag.vector_store.embed_model")
    def test_deletes_by_ids(self, mock_embed, mock_store, mock_client):
        """非空 vector_ids 调用 vector_store.delete"""
        mock_client.return_value = MagicMock()
        store_instance = MagicMock()
        mock_store.return_value = store_instance

        vs = VectorStoreService()
        vs.delete_by_vector_ids(["vec-1", "vec-2"])
        store_instance.delete.assert_called_once_with(ids=["vec-1", "vec-2"])

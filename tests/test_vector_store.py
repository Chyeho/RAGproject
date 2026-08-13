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
    def test_creates_text_splitter(self, mock_embed, mock_store, mock_client):
        """验证会创建文本分割器"""
        mock_client.return_value = MagicMock()
        mock_store.return_value = MagicMock()
        vs = VectorStoreService()
        assert vs.spliter is not None
        assert hasattr(vs.spliter, "split_documents")

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


class TestUploadFile:
    """测试 upload_file 方法"""

    @patch("app.service.rag.vector_store.QdrantClient")
    @patch("app.service.rag.vector_store.QdrantVectorStore")
    @patch("app.service.rag.vector_store.embed_model")
    def test_returns_chunks_with_vector_ids(self, mock_embed, mock_store, mock_client, monkeypatch):
        """成功向量化：返回 [(chunk_text, vector_id)]，且写入 document_id 元数据"""
        _patch_init_env(monkeypatch)
        mock_client.return_value = MagicMock()
        store_instance = MagicMock()
        store_instance.add_documents.return_value = ["vec-1", "vec-2"]
        mock_store.return_value = store_instance

        from langchain_core.documents import Document
        with patch("app.service.rag.vector_store.get_file_documents", return_value=[
            Document(page_content="第一段内容"),
            Document(page_content="第二段内容"),
        ]):
            vs = VectorStoreService()
            result = vs.upload_file("/tmp/test.txt", document_id=7)

        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0][0] == "第一段内容"
        assert result[0][1] == "vec-1"
        assert result[1][1] == "vec-2"

        # 写入前设置了 document_id 元数据
        added_docs = store_instance.add_documents.call_args[0][0]
        assert all(d.metadata.get("document_id") == 7 for d in added_docs)

    @patch("app.service.rag.vector_store.QdrantClient")
    @patch("app.service.rag.vector_store.QdrantVectorStore")
    @patch("app.service.rag.vector_store.embed_model")
    def test_empty_documents_raises_value_error(self, mock_embed, mock_store, mock_client, monkeypatch):
        """文档无有效文本内容时抛出 ValueError"""
        _patch_init_env(monkeypatch)
        mock_client.return_value = MagicMock()
        mock_store.return_value = MagicMock()
        with patch("app.service.rag.vector_store.get_file_documents", return_value=[]):
            vs = VectorStoreService()
            with pytest.raises(ValueError):
                vs.upload_file("/tmp/empty.txt")

    @patch("app.service.rag.vector_store.QdrantClient")
    @patch("app.service.rag.vector_store.QdrantVectorStore")
    @patch("app.service.rag.vector_store.embed_model")
    def test_without_document_id_keeps_original_metadata(self, mock_embed, mock_store, mock_client, monkeypatch):
        """未传 document_id 时不改写分块元数据"""
        _patch_init_env(monkeypatch)
        mock_client.return_value = MagicMock()
        store_instance = MagicMock()
        store_instance.add_documents.return_value = ["vec-1"]
        mock_store.return_value = store_instance

        from langchain_core.documents import Document
        with patch("app.service.rag.vector_store.get_file_documents", return_value=[
            Document(page_content="内容", metadata={"source": "a.txt"}),
        ]):
            vs = VectorStoreService()
            vs.upload_file("/tmp/test.txt")

        added_docs = store_instance.add_documents.call_args[0][0]
        assert "document_id" not in added_docs[0].metadata


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


class TestLoadDocument:
    """测试 load_document 方法（批量加载 data 目录）"""

    @patch("app.service.rag.vector_store.QdrantClient")
    @patch("app.service.rag.vector_store.QdrantVectorStore")
    @patch("app.service.rag.vector_store.embed_model")
    def test_skips_when_md5_exists(self, mock_embed, mock_store, mock_client, tmp_path):
        """md5_exists 回调返回 True 时跳过加载"""
        mock_client.return_value = MagicMock()
        store_instance = MagicMock()
        mock_store.return_value = store_instance

        data_dir = tmp_path / "data"
        data_dir.mkdir()
        test_file = data_dir / "test.txt"
        test_file.write_text("测试内容", encoding="utf-8")

        with patch("app.service.rag.vector_store.listdir_with_allowed_type", return_value=[str(test_file)]):
            with patch("app.service.rag.vector_store.get_abs_path", return_value=str(data_dir)):
                with patch("app.service.rag.vector_store.get_file_md5_hex", return_value="abc123"):
                    vs = VectorStoreService()
                    vs.load_document(md5_exists=lambda md5: True)
                    store_instance.add_documents.assert_not_called()

    @patch("app.service.rag.vector_store.QdrantClient")
    @patch("app.service.rag.vector_store.QdrantVectorStore")
    @patch("app.service.rag.vector_store.embed_model")
    def test_handles_empty_file_list(self, mock_embed, mock_store, mock_client):
        """文件列表为空时不报错"""
        mock_client.return_value = MagicMock()
        store_instance = MagicMock()
        mock_store.return_value = store_instance
        with patch("app.service.rag.vector_store.listdir_with_allowed_type", return_value=[]):
            with patch("app.service.rag.vector_store.get_abs_path", return_value="/fake"):
                vs = VectorStoreService()
                vs.load_document(md5_exists=lambda md5: False)  # 不应抛出异常

    @patch("app.service.rag.vector_store.QdrantClient")
    @patch("app.service.rag.vector_store.QdrantVectorStore")
    @patch("app.service.rag.vector_store.embed_model")
    def test_catches_loading_exception(self, mock_embed, mock_store, mock_client):
        """加载异常（get_file_documents 失败）不应中断整个流程"""
        mock_client.return_value = MagicMock()
        store_instance = MagicMock()
        mock_store.return_value = store_instance
        with patch("app.service.rag.vector_store.listdir_with_allowed_type", return_value=["fake_file.txt"]):
            with patch("app.service.rag.vector_store.get_abs_path", return_value="/fake"):
                with patch("app.service.rag.vector_store.get_file_md5_hex", return_value="abc123"):
                    with patch("app.service.rag.vector_store.get_file_documents", side_effect=Exception("文档解析异常")):
                        vs = VectorStoreService()
                        vs.load_document(md5_exists=lambda md5: False)  # 应捕获异常而不崩溃

    @patch("app.service.rag.vector_store.QdrantClient")
    @patch("app.service.rag.vector_store.QdrantVectorStore")
    @patch("app.service.rag.vector_store.embed_model")
    def test_loads_document_successfully(self, mock_embed, mock_store, mock_client, tmp_path):
        """正常加载：add_documents 被调用"""
        mock_client.return_value = MagicMock()
        store_instance = MagicMock()
        mock_store.return_value = store_instance

        data_dir = tmp_path / "data"
        data_dir.mkdir()
        test_file = data_dir / "test.txt"
        test_file.write_text("测试内容", encoding="utf-8")

        from langchain_core.documents import Document
        with patch("app.service.rag.vector_store.listdir_with_allowed_type", return_value=[str(test_file)]):
            with patch("app.service.rag.vector_store.get_abs_path", return_value=str(data_dir)):
                with patch("app.service.rag.vector_store.get_file_md5_hex", return_value="def456"):
                    with patch("app.service.rag.vector_store.get_file_documents", return_value=[Document(page_content="测试内容")]):
                        vs = VectorStoreService()
                        vs.load_document(md5_exists=lambda md5: False)
                        store_instance.add_documents.assert_called_once()

    @patch("app.service.rag.vector_store.QdrantClient")
    @patch("app.service.rag.vector_store.QdrantVectorStore")
    @patch("app.service.rag.vector_store.embed_model")
    def test_md5_exists_defaults_to_no_dedup(self, mock_embed, mock_store, mock_client, tmp_path):
        """未传 md5_exists（默认 None）时不做去重，全部加载"""
        mock_client.return_value = MagicMock()
        store_instance = MagicMock()
        mock_store.return_value = store_instance

        data_dir = tmp_path / "data"
        data_dir.mkdir()
        test_file = data_dir / "test.txt"
        test_file.write_text("测试内容", encoding="utf-8")

        from langchain_core.documents import Document
        with patch("app.service.rag.vector_store.listdir_with_allowed_type", return_value=[str(test_file)]):
            with patch("app.service.rag.vector_store.get_abs_path", return_value=str(data_dir)):
                with patch("app.service.rag.vector_store.get_file_md5_hex", return_value="def456"):
                    with patch("app.service.rag.vector_store.get_file_documents", return_value=[Document(page_content="测试内容")]):
                        vs = VectorStoreService()
                        vs.load_document()
                        store_instance.add_documents.assert_called_once()

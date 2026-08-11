# -*- coding: utf-8 -*-
"""向量存储服务模块单元测试"""
from unittest.mock import patch, MagicMock

import pytest

from app.service.rag.vector_store import VectorStoreService


class TestVectorStoreServiceInit:
    """测试初始化"""

    @patch("app.service.rag.vector_store.Chroma")
    def test_creates_chroma_instance(self, mock_chroma):
        """验证会创建 Chroma 实例"""
        mock_chroma.return_value = MagicMock()
        vs = VectorStoreService()
        mock_chroma.assert_called_once()

    @patch("app.service.rag.vector_store.Chroma")
    def test_creates_text_splitter(self, mock_chroma):
        """验证会创建文本分割器"""
        mock_chroma.return_value = MagicMock()
        vs = VectorStoreService()
        assert vs.spliter is not None
        # RecursiveCharacterTextSplitter 实例
        assert hasattr(vs.spliter, "split_documents")


class TestGetRetriever:
    """测试 get_retriever 方法"""

    @patch("app.service.rag.vector_store.Chroma")
    def test_returns_retriever(self, mock_chroma):
        mock_instance = MagicMock()
        mock_retriever = MagicMock()
        mock_instance.as_retriever.return_value = mock_retriever
        mock_chroma.return_value = mock_instance

        vs = VectorStoreService()
        result = vs.get_retriever()
        assert result is mock_retriever
        mock_instance.as_retriever.assert_called_once()


class TestLoadDocument:
    """测试 load_document 方法"""

    @patch("app.service.rag.vector_store.Chroma")
    @patch("app.service.rag.vector_store.listdir_with_allowed_type")
    def test_skips_when_md5_exists(self, mock_listdir, mock_chroma, tmp_path):
        """MD5 值已存在时跳过加载"""
        mock_chroma.return_value = MagicMock()

        # 创建一个临时 MD5 文件和一个临时数据文件
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        test_file = data_dir / "test.txt"
        test_file.write_text("测试内容", encoding="utf-8")

        mock_listdir.return_value = [str(test_file)]

        # patch 相关路径函数
        with patch("app.service.rag.vector_store.get_abs_path", return_value=str(data_dir)):
            with patch("app.service.rag.vector_store.get_file_md5_hex", return_value="abc123"):
                with patch("app.service.rag.vector_store.check_md5_hex", return_value=True):
                    vs = VectorStoreService()
                    vs.load_document()
                    # 应该跳过，不会调用 add_documents
                    mock_instance = mock_chroma.return_value
                    mock_instance.add_documents.assert_not_called()

    @patch("app.service.rag.vector_store.Chroma")
    @patch("app.service.rag.vector_store.listdir_with_allowed_type")
    def test_handles_empty_file_list(self, mock_listdir, mock_chroma):
        """文件列表为空时不报错"""
        mock_chroma.return_value = MagicMock()
        mock_listdir.return_value = []

        with patch("app.service.rag.vector_store.get_abs_path", return_value="/fake"):
            vs = VectorStoreService()
            vs.load_document()  # 不应抛出异常

    @patch("app.service.rag.vector_store.Chroma")
    @patch("app.service.rag.vector_store.listdir_with_allowed_type")
    def test_catches_loading_exception(self, mock_listdir, mock_chroma):
        """加载异常（get_file_documents 失败）不应中断整个流程"""
        mock_chroma.return_value = MagicMock()
        mock_listdir.return_value = ["fake_file.txt"]

        with patch("app.service.rag.vector_store.get_abs_path", return_value="/fake"):
            with patch("app.service.rag.vector_store.get_file_md5_hex", return_value="abc123"):
                with patch("app.service.rag.vector_store.check_md5_hex", return_value=False):
                    # get_file_documents 在 try 块内，抛异常应被捕获
                    with patch("app.service.rag.vector_store.get_file_documents", side_effect=Exception("文档解析异常")):
                        vs = VectorStoreService()
                        vs.load_document()  # 应该捕获异常而不崩溃

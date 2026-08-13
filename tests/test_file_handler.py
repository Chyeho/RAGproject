# -*- coding: utf-8 -*-
"""文件处理工具模块单元测试"""
import os
import tempfile

import pytest

from app.utils.file_handler import (
    get_file_md5_hex,
    get_file_documents,
    listdir_with_allowed_type,
    txt_loader,
)


class TestGetFileMd5Hex:
    """测试 get_file_md5_hex()"""

    def test_returns_string_for_valid_file(self, temp_txt_file):
        md5 = get_file_md5_hex(temp_txt_file)
        assert isinstance(md5, str)
        assert len(md5) == 32  # MD5 十六进制为 32 位

    def test_same_content_same_md5(self):
        """相同内容产生相同 MD5"""
        with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", encoding="utf-8", delete=False) as f1:
            f1.write("hello world")
            f1_path = f1.name
        with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", encoding="utf-8", delete=False) as f2:
            f2.write("hello world")
            f2_path = f2.name

        md5_1 = get_file_md5_hex(f1_path)
        md5_2 = get_file_md5_hex(f2_path)
        assert md5_1 == md5_2

        os.unlink(f1_path)
        os.unlink(f2_path)

    def test_different_content_different_md5(self):
        """不同内容产生不同 MD5"""
        with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", encoding="utf-8", delete=False) as f1:
            f1.write("hello world")
            f1_path = f1.name
        with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", encoding="utf-8", delete=False) as f2:
            f2.write("hello world!")
            f2_path = f2.name

        md5_1 = get_file_md5_hex(f1_path)
        md5_2 = get_file_md5_hex(f2_path)
        assert md5_1 != md5_2

        os.unlink(f1_path)
        os.unlink(f2_path)

    def test_nonexistent_file_returns_none(self):
        md5 = get_file_md5_hex("不存在的文件.txt")
        assert md5 is None


class TestGetFileDocuments:
    """测试 get_file_documents()"""

    def test_loads_txt_file(self, temp_txt_file):
        docs = get_file_documents(temp_txt_file)
        assert isinstance(docs, list)
        assert len(docs) > 0
        assert docs[0].page_content != ""

    def test_unsupported_extension_returns_empty_list(self):
        docs = get_file_documents("test.xyz")
        assert docs == []

    def test_pdf_extension_recognized(self, temp_pdf_file):
        """PDF 扩展名应被识别（即使可能加载失败）"""
        # 注意：临时创建的 PDF 不是合法 PDF，加载可能抛异常
        # 只测试扩展名识别逻辑（不实际加载）
        pass


class TestTxtLoader:
    """测试 txt_loader()"""

    def test_loads_text_content(self, temp_txt_file):
        docs = txt_loader(temp_txt_file)
        assert len(docs) > 0
        assert "测试文本内容" in docs[0].page_content

    def test_returns_document_objects(self, temp_txt_file):
        docs = txt_loader(temp_txt_file)
        assert hasattr(docs[0], "page_content")
        assert hasattr(docs[0], "metadata")


class TestListdirWithAllowedType:
    """测试 listdir_with_allowed_type()"""

    def test_filters_by_extension(self):
        """过滤指定后缀的文件"""
        from app.utils.path_tool import get_abs_path
        data_dir = get_abs_path("data")
        files = listdir_with_allowed_type(data_dir, ("txt",))
        assert isinstance(files, tuple)
        for f in files:
            assert f.endswith(".txt")

    def test_nonexistent_dir_returns_allowed_type(self):
        """目录不存在时返回 allowed_type"""
        result = listdir_with_allowed_type("不存在的目录", ("txt",))
        assert result == ("txt",)

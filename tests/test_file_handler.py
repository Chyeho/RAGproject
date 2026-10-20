# -*- coding: utf-8 -*-
"""文件处理工具模块单元测试"""
import os
import tempfile

import pytest

from app.utils.file_handler import (
    get_file_md5_hex,
    listdir_with_allowed_type,
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

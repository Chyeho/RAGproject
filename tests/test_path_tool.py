# -*- coding: utf-8 -*-
"""路径工具模块单元测试"""
import os
from app.utils.path_tool import get_root_path, get_abs_path


class TestGetRootPath:
    """测试 get_root_path() 函数"""

    def test_returns_string(self):
        """验证返回值为字符串类型"""
        result = get_root_path()
        assert isinstance(result, str)

    def test_returns_existing_directory(self):
        """验证返回的路径是真实存在的目录"""
        result = get_root_path()
        assert os.path.exists(result)
        assert os.path.isdir(result)

    def test_ends_with_app(self):
        """验证返回的是 app 包所在根目录（以 app 结尾或包含 utils 的父目录）"""
        result = get_root_path()
        # path_tool.py 在 app/utils/ 下，get_root_path 取 os.path.dirname(os.path.dirname(current_file))
        # 即 app/utils/ -> app/ -> app/
        assert "app" in os.path.basename(result) or result.endswith("app")


class TestGetAbsPath:
    """测试 get_abs_path() 函数"""

    def test_empty_string(self):
        """传入空字符串应返回 app 根目录"""
        result = get_abs_path("")
        assert os.path.isdir(result)

    def test_relative_subdirectory(self):
        """传入相对子目录路径"""
        result = get_abs_path("config")
        assert os.path.isdir(result)
        assert result.endswith("config")

    def test_relative_file_path(self):
        """传入相对文件路径（不要求文件必须存在）"""
        result = get_abs_path("config/rag_config.yml")
        assert result.endswith("rag_config.yml")

    def test_returns_absolute_path(self):
        """验证返回的是绝对路径"""
        result = get_abs_path("data")
        assert os.path.isabs(result)

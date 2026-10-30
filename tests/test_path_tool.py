# -*- coding: utf-8 -*-
"""路径工具模块单元测试"""
import os
from app.utils.path_tool import get_root_path, get_abs_path, get_config_path


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


class TestGetConfigPath:
    """测试 get_config_path()：默认配置只读 + 运行时可写副本"""

    def test_returns_default_when_env_unset(self, monkeypatch):
        """未设置 RUNTIME_CONFIG_DIR（本地开发）→ 直接读 app/config 默认配置"""
        monkeypatch.delenv("RUNTIME_CONFIG_DIR", raising=False)
        result = get_config_path("retrieval_config.yml")
        assert result == get_abs_path(os.path.join("config", "retrieval_config.yml"))
        assert os.path.exists(result)

    def test_copies_default_to_runtime_dir(self, monkeypatch, tmp_path):
        """设置 RUNTIME_CONFIG_DIR（容器部署）→ 首次调用复制默认配置到可写目录"""
        monkeypatch.setenv("RUNTIME_CONFIG_DIR", str(tmp_path / "runtime"))
        result = get_config_path("retrieval_config.yml")
        assert result == str(tmp_path / "runtime" / "retrieval_config.yml")
        with open(result, encoding="utf-8") as f:
            assert "top_k" in f.read()

    def test_keeps_existing_runtime_copy(self, monkeypatch, tmp_path):
        """副本已存在时不被默认配置覆盖（保留设置页保存的参数）"""
        runtime = tmp_path / "runtime"
        runtime.mkdir()
        target = runtime / "retrieval_config.yml"
        target.write_text("top_k: 99\n", encoding="utf-8")
        monkeypatch.setenv("RUNTIME_CONFIG_DIR", str(runtime))

        assert get_config_path("retrieval_config.yml") == str(target)
        assert "99" in target.read_text(encoding="utf-8")

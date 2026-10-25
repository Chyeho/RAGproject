# -*- coding: utf-8 -*-
"""env_loader（模型环境变量白名单加载器）单元测试"""
import os
from pathlib import Path
from unittest.mock import patch

from app.utils.env_loader import (
    DEFAULT_ENV_FILE,
    MODEL_ENV_WHITELIST,
    load_model_env,
    parse_env_file,
)


def _write_env(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


class TestParseEnvFile:
    """测试 env 文件解析"""

    def test_missing_file_returns_empty(self, tmp_path):
        assert parse_env_file(tmp_path / "nope.env") == {}

    def test_parses_key_value(self, tmp_path):
        f = _write_env(tmp_path / "a.env", "OPENAI_CHAT_MODEL=deepseek-flash\n")
        assert parse_env_file(f) == {"OPENAI_CHAT_MODEL": "deepseek-flash"}

    def test_skips_comments_blank_and_no_eq_lines(self, tmp_path):
        f = _write_env(tmp_path / "a.env", "# 注释行\n\nINVALID_LINE\nK=v\n")
        assert parse_env_file(f) == {"K": "v"}

    def test_strips_paired_quotes_and_whitespace(self, tmp_path):
        f = _write_env(tmp_path / "a.env", 'A="x y"\nB=\'z\'\nC = w \n')
        assert parse_env_file(f) == {"A": "x y", "B": "z", "C": "w"}

    def test_keeps_unpaired_quotes(self, tmp_path):
        f = _write_env(tmp_path / "a.env", 'A="unpaired\n')
        assert parse_env_file(f) == {"A": '"unpaired'}


class TestLoadModelEnv:
    """测试白名单注入逻辑"""

    def test_default_env_file_points_to_docker_env_dev(self):
        """默认路径应指向 docker/env/.env.dev（项目根下）"""
        parts = DEFAULT_ENV_FILE.parts
        assert parts[-3:] == ("docker", "env", ".env.dev")

    def test_injects_only_whitelisted_missing_keys(self, tmp_path):
        """只注入白名单内且进程缺失的键；编排专用值（MYSQL_HOST 等）不得进入"""
        f = _write_env(tmp_path / "a.env", "\n".join([
            "OPENAI_CHAT_MODEL=deepseek-flash",
            "OPENAI_API_KEY=sk-x",
            "MYSQL_HOST=mysql",
            "OLLAMA_BASE_URL=http://ollama:11434",
        ]))
        mysql_before = os.environ.get("MYSQL_HOST")
        ollama_before = os.environ.get("OLLAMA_BASE_URL")
        with patch.dict(os.environ, {}, clear=False):
            for k in MODEL_ENV_WHITELIST:      # 模拟全新进程：白名单键全缺失
                os.environ.pop(k, None)
            injected = load_model_env(f)
            assert injected == {"OPENAI_CHAT_MODEL": "deepseek-flash", "OPENAI_API_KEY": "sk-x"}
            assert os.environ["OPENAI_CHAT_MODEL"] == "deepseek-flash"
            assert os.environ["OPENAI_API_KEY"] == "sk-x"
            # 非白名单键（Docker 编排值）不被本加载器改动
            assert os.environ.get("MYSQL_HOST") == mysql_before
            assert os.environ.get("OLLAMA_BASE_URL") == ollama_before

    def test_does_not_override_existing_env(self, tmp_path):
        """已存在的真实环境变量优先，文件值不得覆盖"""
        f = _write_env(tmp_path / "a.env", "OPENAI_CHAT_MODEL=from-file\n")
        with patch.dict(os.environ, {"OPENAI_CHAT_MODEL": "from-env"}):
            injected = load_model_env(f)
            assert injected == {}
            assert os.environ["OPENAI_CHAT_MODEL"] == "from-env"

    def test_missing_file_returns_empty_without_injection(self, tmp_path):
        """文件缺失时静默返回空 dict，不抛错"""
        with patch.dict(os.environ, {}, clear=False):
            assert load_model_env(tmp_path / "nope.env") == {}

    def test_privrag_env_file_override(self, tmp_path):
        """PRIVRAG_ENV_FILE 环境变量可指定其他 env 文件"""
        f = _write_env(tmp_path / "b.env", "RERANK_MODEL=gte-rerank-v2-custom\n")
        with patch.dict(os.environ, {"PRIVRAG_ENV_FILE": str(f)}):
            os.environ.pop("RERANK_MODEL", None)
            injected = load_model_env()
            assert injected == {"RERANK_MODEL": "gte-rerank-v2-custom"}
            assert os.environ["RERANK_MODEL"] == "gte-rerank-v2-custom"

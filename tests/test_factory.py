# -*- coding: utf-8 -*-
"""模型工厂模块单元测试"""
import os
from unittest.mock import patch, MagicMock
from typing import Optional, List

import pytest

from app.modelFactory.factory import (
    DashScopeTextEmbeddings,
    BaseModelFactory,
    ChatModelFactory,
    EmbeddingFactory,
    _get_model_mode,
)
from langchain_core.embeddings import Embeddings


# ========================================
# DashScopeTextEmbeddings 测试（保持不变）
# ========================================
class TestDashScopeTextEmbeddingsInit:
    """测试初始化"""

    def test_model_stored(self):
        """验证 model 参数被正确存储"""
        obj = DashScopeTextEmbeddings(model="text-embedding-v4")
        assert obj.model == "text-embedding-v4"

    def test_max_batch_size_default(self):
        """验证默认批量大小"""
        obj = DashScopeTextEmbeddings(model="test-model")
        assert obj.MAX_BATCH_SIZE == 10

    def test_inherits_from_embeddings(self):
        """验证继承自 LangChain Embeddings 基类"""
        obj = DashScopeTextEmbeddings(model="test")
        assert isinstance(obj, Embeddings)


class TestDashScopeTextEmbeddingsCallApi:
    """测试 _call_api 方法"""

    @patch("dashscope.TextEmbedding.call")
    def test_single_text_calls_api_correctly(self, mock_call):
        """单条文本应正确调用 API"""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.output = {
            "embeddings": [
                {"text_index": 0, "embedding": [0.1, 0.2, 0.3]}
            ]
        }
        mock_call.return_value = mock_resp

        obj = DashScopeTextEmbeddings(model="test-model")
        result = obj._call_api(["hello"])
        assert len(result) == 1
        assert result[0] == [0.1, 0.2, 0.3]
        # 验证 input 参数为字符串（单条）而非列表
        call_args = mock_call.call_args[1]
        assert call_args["input"] == "hello"

    @patch("dashscope.TextEmbedding.call")
    def test_batch_multiple_texts_calls_api_correctly(self, mock_call):
        """多条文本应正确调用 API"""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.output = {
            "embeddings": [
                {"text_index": 0, "embedding": [0.1, 0.2]},
                {"text_index": 1, "embedding": [0.3, 0.4]},
                {"text_index": 2, "embedding": [0.5, 0.6]},
            ]
        }
        mock_call.return_value = mock_resp

        obj = DashScopeTextEmbeddings(model="test-model")
        result = obj._call_api(["a", "b", "c"])
        assert len(result) == 3
        # 多条时传列表
        call_args = mock_call.call_args[1]
        assert call_args["input"] == ["a", "b", "c"]

    @patch("dashscope.TextEmbedding.call")
    def test_batch_splits_when_exceeds_max(self, mock_call):
        """超过 MAX_BATCH_SIZE 应分批调用"""
        # 21 条 → 3 批 (10 + 10 + 1)
        texts = [f"text_{i}" for i in range(21)]
        mock_resp_10 = MagicMock()
        mock_resp_10.status_code = 200
        mock_resp_10.output = {
            "embeddings": [{"text_index": i, "embedding": [float(i)]} for i in range(10)]
        }
        mock_resp_1 = MagicMock()
        mock_resp_1.status_code = 200
        mock_resp_1.output = {
            "embeddings": [{"text_index": 0, "embedding": [99.0]}]
        }

        mock_call.side_effect = [mock_resp_10, mock_resp_10, mock_resp_1]

        obj = DashScopeTextEmbeddings(model="test-model")
        result = obj._call_api(texts)
        assert len(result) == 21
        assert mock_call.call_count == 3

    @patch("dashscope.TextEmbedding.call")
    def test_raises_on_non_200_status(self, mock_call):
        """非 200 状态码应抛出 ValueError"""
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.code = "InvalidParameter"
        mock_resp.message = "bad request"
        mock_call.return_value = mock_resp

        obj = DashScopeTextEmbeddings(model="test-model")
        with pytest.raises(ValueError, match="status_code"):
            obj._call_api(["hello"])

    @patch("dashscope.TextEmbedding.call")
    def test_preserves_order_with_text_index(self, mock_call):
        """验证按 text_index 排序保持原始顺序"""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        # API 返回的顺序可能是乱的
        mock_resp.output = {
            "embeddings": [
                {"text_index": 2, "embedding": [3.0]},
                {"text_index": 0, "embedding": [1.0]},
                {"text_index": 1, "embedding": [2.0]},
            ]
        }
        mock_call.return_value = mock_resp

        obj = DashScopeTextEmbeddings(model="test-model")
        result = obj._call_api(["A", "B", "C"])
        # 验证按 text_index 排序后顺序正确
        assert result == [[1.0], [2.0], [3.0]]


class TestDashScopeTextEmbeddingsEmbedQuery:
    """测试 embed_query 方法"""

    @patch("dashscope.TextEmbedding.call")
    def test_returns_single_embedding(self, mock_call):
        """应返回单个向量"""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.output = {
            "embeddings": [{"text_index": 0, "embedding": [0.1, 0.2, 0.3]}]
        }
        mock_call.return_value = mock_resp

        obj = DashScopeTextEmbeddings(model="test")
        result = obj.embed_query("hello")
        assert isinstance(result, list)
        assert result == [0.1, 0.2, 0.3]


class TestDashScopeTextEmbeddingsEmbedDocuments:
    """测试 embed_documents 方法"""

    @patch("dashscope.TextEmbedding.call")
    def test_returns_list_of_embeddings(self, mock_call):
        """应返回向量列表"""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.output = {
            "embeddings": [
                {"text_index": 0, "embedding": [0.1, 0.2]},
                {"text_index": 1, "embedding": [0.3, 0.4]},
            ]
        }
        mock_call.return_value = mock_resp

        obj = DashScopeTextEmbeddings(model="test")
        result = obj.embed_documents(["a", "b"])
        assert len(result) == 2
        assert result == [[0.1, 0.2], [0.3, 0.4]]


# ========================================
# BaseModelFactory 测试（保持不变）
# ========================================
class TestBaseModelFactory:
    """测试抽象基类"""

    def test_is_abstract(self):
        """不能直接实例化"""
        with pytest.raises(TypeError):
            BaseModelFactory()

    def test_has_abstract_generator(self):
        """有 generator 抽象方法"""
        assert hasattr(BaseModelFactory, "generator")
        assert getattr(BaseModelFactory.generator, "__isabstractmethod__", False)


# ========================================
# _get_model_mode 测试
# ========================================
class TestGetModelMode:
    """测试模式开关函数"""

    def test_default_is_remote(self):
        """未设置 MODEL_MODE 时默认 remote"""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MODEL_MODE", None)
            assert _get_model_mode() == "remote"

    def test_local(self):
        """MODEL_MODE=local 时返回 local"""
        with patch.dict(os.environ, {"MODEL_MODE": "local"}):
            assert _get_model_mode() == "local"

    def test_remote_explicit(self):
        """显式设置 remote"""
        with patch.dict(os.environ, {"MODEL_MODE": "remote"}):
            assert _get_model_mode() == "remote"

    def test_case_insensitive(self):
        """大小写不敏感"""
        with patch.dict(os.environ, {"MODEL_MODE": "LOCAL"}):
            assert _get_model_mode() == "local"

    def test_invalid_falls_back_to_remote(self):
        """非法值回退 remote"""
        with patch.dict(os.environ, {"MODEL_MODE": "invalid"}):
            assert _get_model_mode() == "remote"


# ========================================
# ChatModelFactory 测试
# ========================================
class TestChatModelFactory:
    """测试聊天模型工厂"""

    @patch("app.modelFactory.factory.ChatOpenAI")
    def test_remote_mode_returns_chatopenai(self, mock_openai):
        """远程模式应返回 ChatOpenAI 实例"""
        mock_openai.return_value = MagicMock()
        env = {"MODEL_MODE": "remote", "OPENAI_API_KEY": "sk-test", "OPENAI_BASE_URL": "https://api.test.com/v1"}
        with patch.dict(os.environ, env):
            factory = ChatModelFactory()
            result = factory.generator()
            assert result is not None
            mock_openai.assert_called_once()
            call_kwargs = mock_openai.call_args[1]
            assert call_kwargs["api_key"] == "sk-test"
            assert call_kwargs["base_url"] == "https://api.test.com/v1"

    @patch("app.modelFactory.factory.ChatOllama")
    def test_local_mode_returns_chatollama(self, mock_ollama):
        """本地模式应返回 ChatOllama 实例"""
        mock_ollama.return_value = MagicMock()
        env = {"MODEL_MODE": "local", "OLLAMA_BASE_URL": "http://ollama:11434"}
        with patch.dict(os.environ, env):
            factory = ChatModelFactory()
            result = factory.generator()
            assert result is not None
            mock_ollama.assert_called_once()
            call_kwargs = mock_ollama.call_args[1]
            assert call_kwargs["base_url"] == "http://ollama:11434"

    @patch("app.modelFactory.factory.ChatOpenAI")
    def test_remote_mode_uses_env_model_name(self, mock_openai):
        """远程模式应支持 OPENAI_CHAT_MODEL 环境变量覆盖模型名"""
        mock_openai.return_value = MagicMock()
        env = {"MODEL_MODE": "remote", "OPENAI_API_KEY": "sk-test", "OPENAI_CHAT_MODEL": "deepseek-chat"}
        with patch.dict(os.environ, env):
            factory = ChatModelFactory()
            factory.generator()
            call_kwargs = mock_openai.call_args[1]
            assert call_kwargs["model"] == "deepseek-chat"

    @patch("app.modelFactory.factory.ChatOllama")
    def test_local_mode_uses_env_model_name(self, mock_ollama):
        """本地模式应支持 OLLAMA_CHAT_MODEL 环境变量覆盖模型名"""
        mock_ollama.return_value = MagicMock()
        env = {"MODEL_MODE": "local", "OLLAMA_CHAT_MODEL": "llama3:8b"}
        with patch.dict(os.environ, env):
            factory = ChatModelFactory()
            factory.generator()
            call_kwargs = mock_ollama.call_args[1]
            assert call_kwargs["model"] == "llama3:8b"

    @patch("app.modelFactory.factory.ChatOpenAI")
    def test_remote_mode_uses_yml_model_name_when_no_env(self, mock_openai):
        """远程模式无环境变量覆盖时用 yml 配置的模型名"""
        mock_openai.return_value = MagicMock()
        env = {"MODEL_MODE": "remote", "OPENAI_API_KEY": "sk-test"}
        with patch.dict(os.environ, env):
            factory = ChatModelFactory()
            factory.generator()
            call_kwargs = mock_openai.call_args[1]
            assert call_kwargs["model"] == "qwen3.7-max"


# ========================================
# EmbeddingFactory 测试
# ========================================
class TestEmbeddingFactory:
    """测试嵌入模型工厂"""

    def test_remote_mode_returns_dashscope(self):
        """远程模式应返回 DashScopeTextEmbeddings"""
        env = {"MODEL_MODE": "remote"}
        with patch.dict(os.environ, env):
            factory = EmbeddingFactory()
            result = factory.generator()
            assert isinstance(result, DashScopeTextEmbeddings)

    @patch("app.modelFactory.factory.OllamaEmbeddings")
    def test_local_mode_returns_ollama_embeddings(self, mock_ollama):
        """本地模式应返回 OllamaEmbeddings 实例"""
        mock_ollama.return_value = MagicMock()
        env = {"MODEL_MODE": "local", "OLLAMA_BASE_URL": "http://ollama:11434"}
        with patch.dict(os.environ, env):
            factory = EmbeddingFactory()
            result = factory.generator()
            assert result is not None
            mock_ollama.assert_called_once()
            call_kwargs = mock_ollama.call_args[1]
            assert call_kwargs["base_url"] == "http://ollama:11434"

    @patch("app.modelFactory.factory.OllamaEmbeddings")
    def test_local_mode_uses_env_model_name(self, mock_ollama):
        """本地模式应支持 OLLAMA_EMBEDDING_MODEL 环境变量覆盖模型名"""
        mock_ollama.return_value = MagicMock()
        env = {"MODEL_MODE": "local", "OLLAMA_EMBEDDING_MODEL": "nomic-embed-text"}
        with patch.dict(os.environ, env):
            factory = EmbeddingFactory()
            factory.generator()
            call_kwargs = mock_ollama.call_args[1]
            assert call_kwargs["model"] == "nomic-embed-text"

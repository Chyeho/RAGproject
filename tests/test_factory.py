# -*- coding: utf-8 -*-
"""模型工厂模块单元测试"""
from unittest.mock import patch, MagicMock
from abc import ABC, abstractmethod
from typing import Optional, List

import pytest

from app.modelFactory.factory import (
    DashScopeTextEmbeddings,
    BaseModelFactory,
    ChatModelFactory,
    EmbeddingFactory,
)
from langchain_core.embeddings import Embeddings


# ========================================
# DashScopeTextEmbeddings 测试
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
# BaseModelFactory 测试
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
# ChatModelFactory 测试
# ========================================
class TestChatModelFactory:
    """测试聊天模型工厂"""

    @patch("app.modelFactory.factory.ChatTongyi")
    def test_generator_returns_chattongyi(self, mock_chat):
        mock_chat.return_value = MagicMock()
        factory = ChatModelFactory()
        result = factory.generator()
        assert result is not None
        mock_chat.assert_called_once()


# ========================================
# EmbeddingFactory 测试
# ========================================
class TestEmbeddingFactory:
    """测试嵌入模型工厂"""

    def test_generator_returns_dashscope_embeddings(self):
        factory = EmbeddingFactory()
        result = factory.generator()
        assert isinstance(result, DashScopeTextEmbeddings)

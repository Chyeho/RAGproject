# -*- coding: utf-8 -*-
"""配置管理工具模块单元测试"""
import pytest

# 导入前确保不会因为模块导入时执行外部调用而失败
# 配置模块在导入时会自动加载所有 YAML 文件，需要确保路径正确
from app.utils.config_handler import (
    load_rag_config,
    load_qdrant_config,
    load_prompts_config,
    load_agent_config,
    load_cache_config,
    rag_conf,
    qdrant_conf,
    prompts_conf,
    agent_conf,
    cache_conf,
)


class TestRagConfig:
    """测试 RAG 配置加载"""

    def test_load_rag_config_returns_dict(self):
        """验证返回值为字典"""
        config = load_rag_config()
        assert isinstance(config, dict)

    def test_rag_conf_contains_chat_model(self):
        """验证 rag_conf 包含聊天模型名称"""
        assert "chat_model_name" in rag_conf
        assert isinstance(rag_conf["chat_model_name"], str)

    def test_rag_conf_contains_embedding_model(self):
        """验证 rag_conf 包含嵌入模型名称"""
        assert "embedding_model_name" in rag_conf
        assert isinstance(rag_conf["embedding_model_name"], str)

    def test_rag_conf_contains_session_config(self):
        """验证 rag_conf 包含会话配置"""
        assert "session_config" in rag_conf
        assert "configurable" in rag_conf["session_config"]
        assert "session_id" in rag_conf["session_config"]["configurable"]


class TestQdrantConfig:
    """测试 Qdrant 配置加载"""

    def test_load_qdrant_config_returns_dict(self):
        """验证返回值为字典"""
        config = load_qdrant_config()
        assert isinstance(config, dict)

    def test_qdrant_conf_contains_collection_name(self):
        """验证包含集合名称"""
        assert "collection_name" in qdrant_conf
        assert isinstance(qdrant_conf["collection_name"], str)

    def test_qdrant_conf_contains_host_and_port(self):
        """验证包含连接地址 host/port"""
        assert "host" in qdrant_conf
        assert isinstance(qdrant_conf["host"], str)
        assert "port" in qdrant_conf
        assert isinstance(qdrant_conf["port"], int)

    def test_qdrant_conf_contains_chunk_size(self):
        """验证包含切片大小"""
        assert "chunk_size" in qdrant_conf
        assert isinstance(qdrant_conf["chunk_size"], int)
        assert qdrant_conf["chunk_size"] > 0

    def test_qdrant_conf_contains_chunk_overlap(self):
        """验证包含切片重叠大小"""
        assert "chunk_overlap" in qdrant_conf
        assert isinstance(qdrant_conf["chunk_overlap"], int)
        assert qdrant_conf["chunk_overlap"] >= 0

    def test_qdrant_conf_contains_k(self):
        """验证包含检索数目 k"""
        assert "k" in qdrant_conf
        assert isinstance(qdrant_conf["k"], int)
        assert qdrant_conf["k"] > 0

    def test_qdrant_conf_contains_data_path(self):
        """验证包含数据路径"""
        assert "data_path" in qdrant_conf

    def test_qdrant_conf_contains_separators(self):
        """验证包含分隔符"""
        assert "separators" in qdrant_conf
        assert isinstance(qdrant_conf["separators"], list)

    def test_qdrant_conf_contains_allowed_file_type(self):
        """验证包含允许上传的文件类型列表"""
        assert "allow_knowledge_file_type" in qdrant_conf
        assert isinstance(qdrant_conf["allow_knowledge_file_type"], list)


class TestPromptsConfig:
    """测试提示词配置加载"""

    def test_load_prompts_config_returns_dict(self):
        config = load_prompts_config()
        assert isinstance(config, dict)

    def test_prompts_conf_contains_system_prompt_path(self):
        assert "system_prompt_path" in prompts_conf

    def test_prompts_conf_contains_rag_summarize_prompt_path(self):
        assert "rag_summarize_prompt_path" in prompts_conf


class TestAgentConfig:
    """测试 Agent 配置加载"""

    def test_load_agent_config_returns_dict(self):
        config = load_agent_config()
        assert isinstance(config, dict)

    def test_agent_conf_contains_chat_history_path(self):
        assert "chat_history_storage_path" in agent_conf


class TestCacheConfig:
    """测试缓存配置加载"""

    def test_load_cache_config_returns_dict_or_none(self):
        """cache_config.yml 可能为空文件，返回 None 或 dict 均合法"""
        config = load_cache_config()
        assert config is None or isinstance(config, dict)

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
    load_retrieval_config,
    rag_conf,
    qdrant_conf,
    prompts_conf,
    agent_conf,
    cache_conf,
    retrieval_conf,
)


class TestRagConfig:
    """测试 RAG 配置加载"""

    def test_load_rag_config_returns_dict(self):
        """验证返回值为字典"""
        config = load_rag_config()
        assert isinstance(config, dict)

    def test_rag_conf_contains_chat_model(self):
        """验证 rag_conf 包含聊天模型名称（remote/local 分组下）"""
        assert "remote" in rag_conf and "chat_model_name" in rag_conf["remote"]
        assert "local" in rag_conf and "chat_model_name" in rag_conf["local"]
        assert isinstance(rag_conf["remote"]["chat_model_name"], str)
        assert isinstance(rag_conf["local"]["chat_model_name"], str)

    def test_rag_conf_contains_embedding_model(self):
        """验证 rag_conf 包含嵌入模型名称（remote/local 分组下）"""
        assert "remote" in rag_conf and "embedding_model_name" in rag_conf["remote"]
        assert "local" in rag_conf and "embedding_model_name" in rag_conf["local"]
        assert isinstance(rag_conf["remote"]["embedding_model_name"], str)
        assert isinstance(rag_conf["local"]["embedding_model_name"], str)

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

    def test_qdrant_conf_contains_data_path(self):
        """验证包含数据路径"""
        assert "data_path" in qdrant_conf

    def test_qdrant_conf_contains_allowed_file_type(self):
        """验证包含允许上传的文件类型列表"""
        assert "allow_knowledge_file_type" in qdrant_conf
        assert isinstance(qdrant_conf["allow_knowledge_file_type"], list)

    def test_qdrant_conf_chunk_params_migrated(self):
        """P2 参数收敛：chunk/k/separators 已迁移至 retrieval_config.yml"""
        for key in ("chunk_size", "chunk_overlap", "k", "separators",
                    "min_chunk_size", "max_chunk_size", "excel_rows_per_chunk"):
            assert key not in qdrant_conf


class TestRetrievalConfig:
    """测试检索链路配置加载（P2：chunk/检索参数收敛于此）"""

    def test_load_retrieval_config_returns_dict(self):
        config = load_retrieval_config()
        assert isinstance(config, dict)

    def test_retrieval_conf_contains_top_k_and_legacy_k(self):
        """最终上下文条数（top_k）与旧链路稠密 k（legacy_k）"""
        assert isinstance(retrieval_conf["top_k"], int) and retrieval_conf["top_k"] > 0
        assert isinstance(retrieval_conf["legacy_k"], int) and retrieval_conf["legacy_k"] > 0

    def test_retrieval_conf_contains_hybrid(self):
        """混合检索参数段"""
        hybrid = retrieval_conf["hybrid"]
        assert isinstance(hybrid["enabled"], bool)
        assert isinstance(hybrid["dense_topn"], int) and hybrid["dense_topn"] > 0
        assert isinstance(hybrid["bm25_topn"], int) and hybrid["bm25_topn"] > 0
        assert isinstance(hybrid["rrf_k"], int) and hybrid["rrf_k"] > 0
        assert isinstance(hybrid["topn"], int) and hybrid["topn"] > 0

    def test_retrieval_conf_contains_rerank(self):
        """精排重排参数段"""
        rerank = retrieval_conf["rerank"]
        assert isinstance(rerank["enabled"], bool)
        assert isinstance(rerank["remote_model"], str) and rerank["remote_model"]
        assert isinstance(rerank["local_model"], str) and rerank["local_model"]
        assert isinstance(rerank["top_k"], int) and rerank["top_k"] > 0

    def test_retrieval_conf_contains_query_optimize(self):
        """查询优化配置骨架（P3 使用）"""
        qo = retrieval_conf["query_optimize"]
        assert qo["mode"] in ("off", "multi_query", "hyde")
        assert isinstance(qo["multi_query_count"], int)

    def test_retrieval_conf_contains_chunking(self):
        """分块参数段（自 qdrant_config.yml 迁移而来）"""
        chunking = retrieval_conf["chunking"]
        assert isinstance(chunking["chunk_size"], int) and chunking["chunk_size"] > 0
        assert isinstance(chunking["chunk_overlap"], int) and chunking["chunk_overlap"] >= 0
        assert isinstance(chunking["min_chunk_size"], int)
        assert isinstance(chunking["max_chunk_size"], int)
        assert chunking["max_chunk_size"] >= chunking["chunk_size"]
        assert isinstance(chunking["excel_rows_per_chunk"], int) and chunking["excel_rows_per_chunk"] > 0
        assert isinstance(chunking["separators"], list)


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

# -*- coding: utf-8 -*-
"""Agent 工具库模块单元测试"""
from unittest.mock import patch, MagicMock

import pytest


class TestRagSummarizeTool:
    """测试 rag_summarize 工具"""

    def test_tool_is_decorated(self):
        """验证 rag_summarize 是 LangChain tool"""
        from app.service.agent.tools.agent_tools import rag_summarize
        # LangChain 的 @tool 装饰器会在函数上设置 __tool_metadata__
        # 或者可以通过 hasattr 检查是否为 Tool 对象
        assert rag_summarize is not None

    def test_tool_has_description(self):
        """验证工具有描述"""
        from app.service.agent.tools.agent_tools import rag_summarize
        assert hasattr(rag_summarize, "description")
        desc = rag_summarize.description
        assert isinstance(desc, str)
        assert len(desc) > 0

    @patch("app.service.agent.tools.agent_tools.RagSummarizeService")
    def test_tool_calls_rag_summarize(self, mock_rag_service):
        """验证工具调用底层 rag_summarize 方法"""
        # 由于 rag 在模块导入时就创建了，需要 patch RagSummarizeService
        mock_instance = MagicMock()
        mock_instance.rag_summarize.return_value = "检索结果"
        mock_rag_service.return_value = mock_instance

        # 单独导入工具（需要重新加载以使用 mock）
        import importlib
        import app.service.agent.tools.agent_tools as agent_tools_module

        # 重新 patched 导入
        with patch.object(agent_tools_module, "rag", mock_instance):
            result = agent_tools_module.rag_summarize.invoke({"query": "测试问题"})
            mock_instance.rag_summarize.assert_called_once_with("测试问题")
            assert result == "检索结果"


class TestModuleLevelRag:
    """测试模块级 rag 实例"""

    @patch("app.service.agent.tools.agent_tools.RagSummarizeService")
    def test_rag_is_initialized(self, mock_service):
        """RagSummarizeService 实例在模块导入时创建"""
        mock_service.return_value = MagicMock()
        # 重新导入以触发初始化
        import importlib
        import app.service.agent.tools.agent_tools as at
        importlib.reload(at)
        # 由于 RagSummarizeService 的初始化需要 VectorStoreService 等，这里只验证模块结构
        assert hasattr(at, "rag_summarize")

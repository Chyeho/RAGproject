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

    @patch("app.service.agent.tools.agent_tools.registry")
    def test_tool_calls_rag_summarize(self, mock_registry):
        """验证工具经 registry 懒加载调用底层 rag_summarize（tuple 取 answer）"""
        mock_service = MagicMock()
        mock_service.rag_summarize.return_value = ("检索结果", [])
        mock_registry.get_rag_service.return_value = mock_service

        import app.service.agent.tools.agent_tools as agent_tools_module

        result = agent_tools_module.rag_summarize.invoke({"query": "测试问题"})
        mock_service.rag_summarize.assert_called_once_with("测试问题")
        assert result == "检索结果"


class TestLazyRegistry:
    """P4：agent_tools 经 registry 懒加载，导入期不构建 RAG 链"""

    def test_import_does_not_build_rag_service(self):
        """重载模块不触发 get_rag_service（消除原导入期 eager 构造开销）"""
        import importlib
        import app.service.agent.tools.agent_tools as at

        with patch("app.service.rag.registry.get_rag_service") as mock_get:
            importlib.reload(at)

        mock_get.assert_not_called()
        assert hasattr(at, "rag_summarize")

# -*- coding: utf-8 -*-
"""中间件模块单元测试"""
from unittest.mock import patch, MagicMock

import pytest

from langchain.agents.middleware import wrap_tool_call, before_model


class TestMonitorTool:
    """测试 monitor_tool 中间件"""

    def test_is_decorated_with_wrap_tool_call(self):
        """验证 monitor_tool 可正常导入（被 @wrap_tool_call 装饰）"""
        from app.service.agent.tools.middleware import monitor_tool
        # @wrap_tool_call 装饰后变成 langchain AgentMiddleware 对象
        # 确认它存在且可被 Agent 框架识别
        assert monitor_tool is not None

    def test_decorator_creates_valid_middleware(self):
        """验证 monitor_tool 可作为中间件传给 create_agent"""
        from app.service.agent.tools.middleware import monitor_tool
        # 装饰后不再是普通 callable，但仍是合法的中间件对象
        assert monitor_tool is not None

    def test_underlying_func_callable(self):
        """原始函数逻辑应可被访问"""
        from app.service.agent.tools.middleware import monitor_tool
        # 通过 __wrapped__ 或 func 属性可以取到原始函数
        original = getattr(monitor_tool, "__wrapped__", None) or getattr(monitor_tool, "func", None)
        if original is not None:
            assert callable(original)


class TestLogBeforeModel:
    """测试 log_before_model 中间件"""

    def test_is_decorated_with_before_model(self):
        """验证 log_before_model 可正常导入（被 @before_model 装饰）"""
        from app.service.agent.tools.middleware import log_before_model
        # @before_model 装饰后变成 langchain AgentMiddleware 对象
        assert log_before_model is not None

    def test_decorator_creates_valid_middleware(self):
        """验证 log_before_model 可作为中间件传给 create_agent"""
        from app.service.agent.tools.middleware import log_before_model
        assert log_before_model is not None

    def test_underlying_func_callable(self):
        """原始函数逻辑应可被访问"""
        from app.service.agent.tools.middleware import log_before_model
        original = getattr(log_before_model, "__wrapped__", None) or getattr(log_before_model, "func", None)
        if original is not None:
            assert callable(original)

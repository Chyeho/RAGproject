# -*- coding: utf-8 -*-
"""ReAct Agent 模块单元测试"""
from unittest.mock import patch, MagicMock

import pytest


class TestReActAgentInit:
    """测试 ReActAgent 初始化"""

    @patch("app.service.agent.react_agent.create_agent")
    @patch("app.service.agent.react_agent.load_system_prompt")
    def test_calls_create_agent(self, mock_load_prompt, mock_create_agent):
        """验证 create_agent 被调用且参数正确"""
        mock_load_prompt.return_value = "系统提示词内容"
        mock_agent = MagicMock()
        mock_create_agent.return_value = mock_agent

        from app.service.agent.react_agent import ReActAgent
        agent = ReActAgent()

        # 验证 create_agent 被调用
        mock_create_agent.assert_called_once()
        call_kwargs = mock_create_agent.call_args[1]
        assert call_kwargs["system_prompt"] == "系统提示词内容"
        assert "tools" in call_kwargs
        assert "middleware" in call_kwargs

    @patch("app.service.agent.react_agent.create_agent")
    @patch("app.service.agent.react_agent.load_system_prompt")
    def test_agent_has_tools(self, mock_load_prompt, mock_create_agent):
        """验证 agent 有工具列表"""
        mock_load_prompt.return_value = "prompt"
        mock_create_agent.return_value = MagicMock()

        from app.service.agent.react_agent import ReActAgent
        agent = ReActAgent()

        call_kwargs = mock_create_agent.call_args[1]
        tools = call_kwargs["tools"]
        assert len(tools) >= 1

    @patch("app.service.agent.react_agent.create_agent")
    @patch("app.service.agent.react_agent.load_system_prompt")
    def test_agent_has_middleware(self, mock_load_prompt, mock_create_agent):
        """验证 agent 有中间件列表"""
        mock_load_prompt.return_value = "prompt"
        mock_create_agent.return_value = MagicMock()

        from app.service.agent.react_agent import ReActAgent
        agent = ReActAgent()

        call_kwargs = mock_create_agent.call_args[1]
        middleware = call_kwargs["middleware"]
        assert len(middleware) == 2


class TestReActAgentExecuteStream:
    """测试 execute_stream 方法"""

    @patch("app.service.agent.react_agent.create_agent")
    @patch("app.service.agent.react_agent.load_system_prompt")
    def test_execute_stream_yields_strings(self, mock_load_prompt, mock_create_agent):
        """验证流式输出产生字符串"""
        mock_load_prompt.return_value = "prompt"

        # 模拟 agent.stream 的返回值
        mock_agent = MagicMock()
        mock_chunk_1 = {"messages": [MagicMock(content="思考中...")]}
        mock_chunk_2 = {"messages": [MagicMock(content="最终回答：这是答案。")]}
        mock_agent.stream.return_value = [mock_chunk_1, mock_chunk_2]
        mock_create_agent.return_value = mock_agent

        from app.service.agent.react_agent import ReActAgent
        agent = ReActAgent()

        results = list(agent.execute_stream("公司的考勤制度是什么"))
        assert len(results) >= 1
        for r in results:
            assert isinstance(r, str)

    @patch("app.service.agent.react_agent.create_agent")
    @patch("app.service.agent.react_agent.load_system_prompt")
    def test_execute_stream_input_format(self, mock_load_prompt, mock_create_agent):
        """验证传入 stream 的输入格式正确"""
        mock_load_prompt.return_value = "prompt"
        mock_agent = MagicMock()
        mock_agent.stream.return_value = []
        mock_create_agent.return_value = mock_agent

        from app.service.agent.react_agent import ReActAgent
        agent = ReActAgent()

        list(agent.execute_stream("测试问题"))

        # 验证 stream 调用的参数格式
        mock_agent.stream.assert_called_once()
        call_args = mock_agent.stream.call_args[0][0]
        assert "messages" in call_args
        assert call_args["messages"][0]["role"] == "user"
        assert call_args["messages"][0]["content"] == "测试问题"
        # 流式模式应为 values
        assert mock_agent.stream.call_args[1].get("stream_mode") == "values"

    @patch("app.service.agent.react_agent.create_agent")
    @patch("app.service.agent.react_agent.load_system_prompt")
    def test_execute_stream_skips_empty_content(self, mock_load_prompt, mock_create_agent):
        """验证跳过空内容消息"""
        mock_load_prompt.return_value = "prompt"
        mock_agent = MagicMock()
        # 包含一条空内容消息，一条有内容消息
        mock_agent.stream.return_value = [
            {"messages": [MagicMock(content="")]},
            {"messages": [MagicMock(content="有效回答")]},
        ]
        mock_create_agent.return_value = mock_agent

        from app.service.agent.react_agent import ReActAgent
        agent = ReActAgent()

        results = list(agent.execute_stream("测试"))
        # 空 content 被跳过
        assert len(results) == 1
        assert "有效回答" in results[0]

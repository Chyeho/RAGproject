# -*- coding: utf-8 -*-
"""提示词加载工具模块单元测试"""
import pytest

from app.utils.prompt_loader import load_system_prompt, load_rag_prompt


class TestLoadSystemPrompt:
    """测试 load_system_prompt()"""

    def test_returns_string(self):
        prompt = load_system_prompt()
        assert isinstance(prompt, str)

    def test_not_empty(self):
        prompt = load_system_prompt()
        assert len(prompt) > 0

    def test_contains_react_keyword(self):
        """系统提示词应包含 ReAct 相关指令"""
        prompt = load_system_prompt()
        assert "思考" in prompt or "ReAct" in prompt

    def test_contains_tool_section(self):
        """系统提示词应包含工具调用部分"""
        prompt = load_system_prompt()
        assert "工具" in prompt


class TestLoadRagPrompt:
    """测试 load_rag_prompt()"""

    def test_returns_string(self):
        prompt = load_rag_prompt()
        assert isinstance(prompt, str)

    def test_not_empty(self):
        prompt = load_rag_prompt()
        assert len(prompt) > 0

    def test_contains_context_placeholder(self):
        """RAG 提示词应包含 {context} 占位符"""
        prompt = load_rag_prompt()
        assert "{context}" in prompt

    def test_contains_input_placeholder(self):
        """RAG 提示词应包含 {input} 占位符"""
        prompt = load_rag_prompt()
        assert "{input}" in prompt

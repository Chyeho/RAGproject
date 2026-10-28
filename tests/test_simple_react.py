# -*- coding: utf-8 -*-
'''极简 ReAct 循环单元测试（模型/工具全 mock，全离线）'''
import time
from types import SimpleNamespace

from langchain_core.documents import Document

from app.service.agent.simple_react import SimpleReAct
from app.service.agent.tools.tool_registry import ToolRegistry, ToolResult

PROMPT = "HISTORY=<<HISTORY>>\nQUERY=<<QUERY>>\nOBS=<<OBSERVATIONS>>"


class FakeModel:
    '''按顺序返回预设输出；元素为异常时抛出'''

    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = 0

    def invoke(self, prompt):
        self.calls += 1
        content = self.outputs.pop(0)
        if isinstance(content, Exception):
            raise content
        return SimpleNamespace(content=content)


class SlowModel:
    def invoke(self, prompt):
        time.sleep(0.5)
        return SimpleNamespace(
            content='{"thought":"t","action":"final_answer","action_input":{"answer":"a"}}'
        )


def _registry(handler=None):
    registry = ToolRegistry()
    registry.register("rag_search", handler or (
        lambda action_input: ToolResult({"passages": [{"text": "证据"}]},
                                        documents=[Document(page_content="证据")])
    ))
    return registry


def _react(model, registry=None, **kwargs):
    params = dict(tools=registry or _registry(), max_steps=3,
                  timeout_ms=30000, tool_timeout_ms=10000, prompt_template=PROMPT)
    params.update(kwargs)
    return SimpleReAct(chat_model=model, **params)


class TestSimpleReActSuccess:
    def test_search_then_final_answer(self):
        model = FakeModel([
            '{"thought": "需要检索差旅标准", "action": "rag_search", "action_input": {"query": "差旅"}}',
            '{"thought": "已有证据", "action": "final_answer", "action_input": {"answer": "住宿 500 元"}}',
        ])
        result = _react(model).run("对比差旅标准")

        assert result.ok is True
        assert result.answer == "住宿 500 元"
        assert result.tool_calls == 1
        assert result.model_calls == 2
        assert len(result.steps) == 2
        assert result.steps[0]["action"] == "rag_search"
        assert len(result.documents) == 1

    def test_prompt_contains_query_and_observations(self):
        captured = {}

        class RecordingModel(FakeModel):
            def invoke(self, prompt):
                captured["prompt"] = prompt
                return super().invoke(prompt)

        model = RecordingModel([
            '{"thought": "t", "action": "rag_search", "action_input": {"query": "差旅"}}',
            '{"thought": "t", "action": "final_answer", "action_input": {"answer": "a"}}',
        ])
        _react(model).run("差旅问题")

        assert "QUERY=差旅问题" in captured["prompt"]
        assert "证据" in captured["prompt"]


class TestSimpleReActFallback:
    def test_parse_error(self):
        result = _react(FakeModel(["这不是 JSON"])).run("q")
        assert result.fallback_reason == "parse_error"
        assert result.answer == ""

    def test_empty_answer(self):
        model = FakeModel([
            '{"thought": "t", "action": "rag_search", "action_input": {"query": "q"}}',
            '{"thought": "t", "action": "final_answer", "action_input": {"answer": "  "}}',
        ])
        assert _react(model).run("q").fallback_reason == "empty_answer"

    def test_no_evidence(self):
        model = FakeModel([
            '{"thought": "t", "action": "final_answer", "action_input": {"answer": "直接回答"}}',
        ])
        assert _react(model).run("q").fallback_reason == "no_evidence"

    def test_max_steps_exceeded(self):
        model = FakeModel([
            '{"thought": "t", "action": "rag_search", "action_input": {"query": "q"}}',
            '{"thought": "t", "action": "rag_search", "action_input": {"query": "q"}}',
            # 收尾轮仍试图调用工具 → 视为超轮次
            '{"thought": "t", "action": "rag_search", "action_input": {"query": "q"}}',
        ])
        result = _react(model, max_steps=2).run("q")
        assert result.fallback_reason == "max_steps_exceeded"
        assert result.tool_calls == 2

    def test_closing_answer_after_tool_budget(self):
        """工具轮次用尽后允许一次纯总结调用（不再执行工具）"""
        model = FakeModel([
            '{"thought": "t", "action": "rag_search", "action_input": {"query": "上海"}}',
            '{"thought": "t", "action": "rag_search", "action_input": {"query": "北京"}}',
            '{"thought": "总结", "action": "final_answer", "action_input": {"answer": "上海400，北京350"}}',
        ])
        result = _react(model, max_steps=2).run("对比上海和北京")
        assert result.ok is True
        assert result.answer == "上海400，北京350"
        assert result.tool_calls == 2
        assert result.steps[-1]["action"] == "final_answer"
        assert result.steps[-1]["step"] == 3

    def test_tool_failed_twice(self):
        failing = _registry(lambda action_input: ToolResult({"error": "boom"}))
        model = FakeModel([
            '{"thought": "t", "action": "rag_search", "action_input": {"query": "q"}}',
            '{"thought": "t", "action": "rag_search", "action_input": {"query": "q"}}',
        ])
        assert _react(model, registry=failing).run("q").fallback_reason == "tool_failed"

    def test_unknown_tool_twice(self):
        # compare_calc 是合法 action，但不在注入的白名单里
        model = FakeModel([
            '{"thought": "t", "action": "compare_calc", "action_input": {}}',
            '{"thought": "t", "action": "compare_calc", "action_input": {}}',
        ])
        assert _react(model).run("q").fallback_reason == "parse_error"

    def test_model_timeout(self):
        result = _react(SlowModel(), timeout_ms=100).run("q")
        assert result.fallback_reason == "timeout"

    def test_model_exception_internal_error(self):
        result = _react(FakeModel([RuntimeError("boom")])).run("q")
        assert result.fallback_reason == "internal_error"

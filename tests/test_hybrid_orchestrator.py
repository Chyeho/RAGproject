# -*- coding: utf-8 -*-
'''混合编排器单元测试（路由/ReAct/RAG 服务均注入 mock，全离线）'''
from unittest.mock import patch

from langchain_core.documents import Document

from app.service.agent.simple_react import ReActResult
from app.service.observability.trace import TraceRecorder
from app.service.orchestration.hybrid_orchestrator import HybridOrchestrator
from app.service.routing.rule_router import COMPLEX, DIRECT, RouteDecision
from app.utils.config_handler import hybrid_conf


class FakeRouter:
    def __init__(self, route):
        self.decision = RouteDecision(route=route, reason="fake", matched_rules=("test",), score=2)
        self.calls = 0

    def route(self, query):
        self.calls += 1
        return self.decision


class FakeReact:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    def run(self, query, session_id=None):
        self.calls += 1
        return self.result


class FakeRagService:
    def __init__(self):
        self.calls = []
        self.summarize_calls = []

    def rag_summarize(self, query, session_id=None):
        self.calls.append((query, session_id))
        return "直调答案", [Document(page_content="直调文档", metadata={"vector_id": "d1"})]

    def summarize(self, query, docs, session_id=None, write_history=False):
        self.summarize_calls.append((query, docs, session_id, write_history))
        return "非业务直达答案"


def _recorder(tmp_path):
    return TraceRecorder(trace_dir=str(tmp_path), log_level="off")


def _build(tmp_path, router=None, react=None, rag=None):
    rag = rag or FakeRagService()
    orchestrator = HybridOrchestrator(
        router=router, react=react, recorder=_recorder(tmp_path),
        rag_service_getter=lambda: rag,
    )
    return orchestrator, rag


class TestSwitchOff:
    def test_direct_only_without_loading_router_or_react(self, tmp_path, monkeypatch):
        monkeypatch.setitem(hybrid_conf, "ENABLE_HYBRID_ROUTER", False)
        router = FakeRouter(COMPLEX)
        react = FakeReact(ReActResult(answer="不应被调用"))
        orchestrator, rag = _build(tmp_path, router=router, react=react)

        result = orchestrator.answer("任意问题")

        assert result.answer == "直调答案"
        assert router.calls == 0
        assert react.calls == 0
        assert len(rag.calls) == 1
        assert result.trace["answer_source"] == "rag_direct"
        assert result.trace["route"] == DIRECT


class TestDirectRoute:
    def test_simple_query_goes_direct(self, tmp_path, monkeypatch):
        monkeypatch.setitem(hybrid_conf, "ENABLE_HYBRID_ROUTER", True)
        react = FakeReact(ReActResult(answer="不应被调用"))
        orchestrator, rag = _build(tmp_path, router=FakeRouter(DIRECT), react=react)

        result = orchestrator.answer("年假多少天？")

        assert result.answer == "直调答案"
        assert react.calls == 0
        assert result.trace["route"] == DIRECT
        assert result.trace["answer_source"] == "rag_direct"
        assert result.trace["matched_rules"] == ["test"]


class TestNonBusinessDirect:
    def test_greeting_skips_retrieval_and_router(self, tmp_path, monkeypatch):
        monkeypatch.setitem(hybrid_conf, "ENABLE_HYBRID_ROUTER", True)
        router = FakeRouter(COMPLEX)
        react = FakeReact(ReActResult(answer="不应被调用"))
        orchestrator, rag = _build(tmp_path, router=router, react=react)

        query = "你好，你能介绍一下你吗？我该如何使用你"
        result = orchestrator.answer(query, session_id="s1")

        assert result.answer == "非业务直达答案"
        assert result.documents == []
        assert router.calls == 0
        assert react.calls == 0
        assert rag.calls == []
        assert rag.summarize_calls == [(query, [], "s1", True)]
        assert result.trace["route"] == "non_business"
        assert result.trace["answer_source"] == "direct_llm"
        assert result.trace["tool_calls"] == 0

    def test_switch_off_keeps_legacy_direct(self, tmp_path, monkeypatch):
        monkeypatch.setitem(hybrid_conf, "ENABLE_HYBRID_ROUTER", False)
        orchestrator, rag = _build(tmp_path)

        result = orchestrator.answer("你好", session_id="s1")

        assert result.answer == "直调答案"
        assert len(rag.calls) == 1
        assert rag.summarize_calls == []
        assert result.trace["answer_source"] == "rag_direct"


class TestComplexRoute:
    def test_react_success_dedups_docs_and_writes_history_once(self, tmp_path, monkeypatch):
        monkeypatch.setitem(hybrid_conf, "ENABLE_HYBRID_ROUTER", True)
        docs = [
            Document(page_content="A", metadata={"vector_id": "v1"}),
            Document(page_content="A 重复", metadata={"vector_id": "v1"}),
            Document(page_content="B", metadata={"vector_id": "v2"}),
        ]
        react = FakeReact(ReActResult(
            answer="复杂答案", documents=docs, tool_calls=2,
            steps=[{"step": 1, "thought": "t", "action": "rag_search",
                    "action_input": {}, "observation": {}, "elapsed_ms": 1}],
        ))
        rag = FakeRagService()
        orchestrator, _ = _build(tmp_path, router=FakeRouter(COMPLEX), react=react, rag=rag)

        with patch("app.service.orchestration.hybrid_orchestrator.get_chat_history") as mock_history:
            result = orchestrator.answer("对比上海和北京的差旅标准", session_id="s1")

        assert result.answer == "复杂答案"
        assert len(result.documents) == 2
        assert rag.calls == []
        assert result.trace["route"] == COMPLEX
        assert result.trace["answer_source"] == "react"
        assert result.trace["tool_calls"] == 2
        assert len(result.trace["steps"]) == 1
        mock_history.return_value.add_messages.assert_called_once()

    def test_react_failure_falls_back_to_direct(self, tmp_path, monkeypatch):
        monkeypatch.setitem(hybrid_conf, "ENABLE_HYBRID_ROUTER", True)
        monkeypatch.setitem(hybrid_conf, "ENABLE_REACT_FALLBACK", True)
        react = FakeReact(ReActResult(answer="", fallback_reason="timeout"))
        orchestrator, rag = _build(tmp_path, router=FakeRouter(COMPLEX), react=react)

        result = orchestrator.answer("对比上海和北京")

        assert result.answer == "直调答案"
        assert len(rag.calls) == 1
        assert result.trace["fallback"] is True
        assert result.trace["fallback_reason"] == "timeout"
        assert result.trace["answer_source"] == "rag_direct_fallback"

    def test_react_failure_without_fallback(self, tmp_path, monkeypatch):
        monkeypatch.setitem(hybrid_conf, "ENABLE_HYBRID_ROUTER", True)
        monkeypatch.setitem(hybrid_conf, "ENABLE_REACT_FALLBACK", False)
        react = FakeReact(ReActResult(answer="", fallback_reason="tool_failed"))
        orchestrator, rag = _build(tmp_path, router=FakeRouter(COMPLEX), react=react)

        result = orchestrator.answer("对比上海和北京")

        assert "复杂问题分析失败" in result.answer
        assert result.documents == []
        assert rag.calls == []
        assert result.trace["answer_source"] == "react_failed"

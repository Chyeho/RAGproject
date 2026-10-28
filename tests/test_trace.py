# -*- coding: utf-8 -*-
'''trace 结构、截断与落盘单元测试（全离线）'''
import json
import os

from app.service.observability.trace import Trace, TraceRecorder


class TestTrace:
    def test_to_dict_fields_and_truncate(self):
        trace = Trace(query="测试问题")
        trace.set_route({"route": "react_complex", "reason": "命中对比", "matched_rules": ["compare"], "score": 2})
        trace.add_step(1, "需要检索", "rag_search", {"query": "差旅"},
                       {"passages": [{"text": "很长" * 100}]}, 12)
        trace.add_tool_call()
        trace.mark_fallback("timeout")
        trace.finish("rag_direct_fallback", 100)

        data = trace.to_dict(include_steps=True, max_text_chars=10)
        assert data["route"] == "react_complex"
        assert data["matched_rules"] == ["compare"]
        assert data["tool_calls"] == 1
        assert data["fallback"] is True
        assert data["fallback_reason"] == "timeout"
        assert data["answer_source"] == "rag_direct_fallback"
        assert data["total_ms"] == 100
        assert data["steps"][0]["observation"]["passages"][0]["text"] == "很长很长很长很长很长...(truncated)"

    def test_summary_omits_steps(self):
        trace = Trace(query="q")
        trace.add_step(1, "t", "rag_search", {}, {}, 1)
        assert "steps" not in trace.to_dict(include_steps=False)


class TestTraceRecorder:
    def test_persist_full_and_get(self, tmp_path):
        recorder = TraceRecorder(trace_dir=str(tmp_path), log_level="full", text_max_chars=20)
        trace = recorder.start("问题")
        trace.add_step(1, "thought", "rag_search", {"query": "q"}, {"text": "x" * 100}, 5)
        data = recorder.finish(trace, "react")

        assert data["steps"][0]["observation"]["text"].endswith("...(truncated)")
        files = list(tmp_path.glob("*.jsonl"))
        assert len(files) == 1
        line = files[0].read_text(encoding="utf-8").strip()
        persisted = json.loads(line)
        assert persisted["trace_id"] == trace.trace_id
        assert "steps" in persisted
        assert recorder.get(trace.trace_id)["trace_id"] == trace.trace_id

    def test_summary_persist_without_steps(self, tmp_path):
        recorder = TraceRecorder(trace_dir=str(tmp_path), log_level="summary")
        trace = recorder.start("问题")
        trace.add_step(1, "t", "rag_search", {}, {}, 1)
        recorder.finish(trace, "rag_direct")
        persisted = json.loads(next(tmp_path.glob("*.jsonl")).read_text(encoding="utf-8").strip())
        assert "steps" not in persisted
        # 内存缓存仍保留完整步骤，供调试接口使用
        assert "steps" in recorder.get(trace.trace_id)

    def test_off_does_not_persist(self, tmp_path):
        recorder = TraceRecorder(trace_dir=str(tmp_path), log_level="off")
        trace = recorder.start("问题")
        recorder.finish(trace, "rag_direct")
        assert list(tmp_path.glob("*.jsonl")) == []
        assert recorder.get(trace.trace_id) is None

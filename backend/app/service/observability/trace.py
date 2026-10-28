# -*- coding: utf-8 -*-
'''请求级可回放 trace：路由、每轮 thought/action/observation、工具耗时、降级、总耗时

设计约束：
- 不记录敏感文档全文：observation 中字符串按 OBS_TEXT_MAX_CHARS 截断
- 内存缓存供调试接口快速查询；JSONL 落盘供跨进程回放
- LOG_TRACE_LEVEL=off 时不落盘；summary 落盘不含 steps；full 落盘含 steps
'''
import json
import os
import threading
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime

from app.utils.config_handler import hybrid_conf
from app.utils.logger_handler import logger
from app.utils.path_tool import get_abs_path


def _resolve_dir(path: str) -> str:
    return path if os.path.isabs(path) else get_abs_path(path)


def _truncate(value, max_chars: int):
    '''递归截断长字符串，避免 trace 记录文档全文'''
    if isinstance(value, str):
        if len(value) <= max_chars:
            return value
        return value[:max_chars] + "...(truncated)"
    if isinstance(value, dict):
        return {k: _truncate(v, max_chars) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_truncate(v, max_chars) for v in value]
    return value


@dataclass
class Trace:
    '''单次请求 trace（由编排器创建并逐步填充）'''
    query: str
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    route: str = "rag_direct"
    route_reason: str = ""
    matched_rules: list[str] = field(default_factory=list)
    route_score: int = 0
    steps: list[dict] = field(default_factory=list)
    tool_calls: int = 0
    fallback: bool = False
    fallback_reason: str | None = None
    answer_source: str = "rag_direct"
    total_ms: int = 0
    started_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="milliseconds"))
    _start_monotonic: float = field(default_factory=time.monotonic, repr=False)

    def set_route(self, decision) -> None:
        '''写入路由决策（支持 RouteDecision 或 dict）'''
        if hasattr(decision, "to_dict"):
            decision = decision.to_dict()
        self.route = decision.get("route", "rag_direct")
        self.route_reason = decision.get("reason", "")
        self.matched_rules = list(decision.get("matched_rules", []))
        self.route_score = int(decision.get("score", 0) or 0)

    def add_step(self, step: int, thought: str, action: str, action_input: dict,
                 observation: dict | None = None, elapsed_ms: int = 0) -> None:
        self.steps.append({
            "step": step,
            "thought": thought,
            "action": action,
            "action_input": action_input or {},
            "observation": observation or {},
            "elapsed_ms": int(elapsed_ms),
        })

    def add_tool_call(self, count: int = 1) -> None:
        self.tool_calls += count

    def mark_fallback(self, reason: str, elapsed_ms: int | None = None) -> None:
        self.fallback = True
        self.fallback_reason = reason
        if elapsed_ms is not None:
            self.total_ms = int(elapsed_ms)

    def finish(self, answer_source: str, elapsed_ms: int | None = None) -> None:
        self.answer_source = answer_source
        if elapsed_ms is None:
            elapsed_ms = int((time.monotonic() - self._start_monotonic) * 1000)
        self.total_ms = int(elapsed_ms)

    def to_dict(self, include_steps: bool = True, max_text_chars: int = 200) -> dict:
        data = {
            "trace_id": self.trace_id,
            "query": self.query,
            "route": self.route,
            "route_reason": self.route_reason,
            "matched_rules": self.matched_rules,
            "route_score": self.route_score,
            "tool_calls": self.tool_calls,
            "fallback": self.fallback,
            "fallback_reason": self.fallback_reason,
            "answer_source": self.answer_source,
            "total_ms": self.total_ms,
            "started_at": self.started_at,
        }
        if include_steps:
            data["steps"] = _truncate(self.steps, max_text_chars)
        return data


class TraceRecorder:
    '''trace 创建、缓存与落盘'''

    def __init__(self, trace_dir: str | None = None, log_level: str | None = None,
                 text_max_chars: int | None = None, cache_size: int = 200):
        self.trace_dir = _resolve_dir(trace_dir or str(hybrid_conf.get("OBS_TRACE_DIR", "logs/traces")))
        self.log_level = (log_level or str(hybrid_conf.get("LOG_TRACE_LEVEL", "summary"))).lower()
        self.text_max_chars = int(text_max_chars or hybrid_conf.get("OBS_TEXT_MAX_CHARS", 200))
        self.cache_size = max(1, int(cache_size))
        self._cache: OrderedDict[str, dict] = OrderedDict()
        self._lock = threading.Lock()

    def start(self, query: str) -> Trace:
        return Trace(query=query)

    def finish(self, trace: Trace, answer_source: str) -> dict:
        '''结束 trace：计算总耗时、缓存、按级别落盘；返回对外 dict（含 steps）'''
        trace.finish(answer_source)
        full = trace.to_dict(include_steps=True, max_text_chars=self.text_max_chars)
        if self.log_level != "off":
            with self._lock:
                self._cache[trace.trace_id] = full
                while len(self._cache) > self.cache_size:
                    self._cache.popitem(last=False)
            self._persist(trace, include_steps=self.log_level == "full")
        logger.info(
            f"[trace]id={trace.trace_id} route={trace.route} source={trace.answer_source} "
            f"tools={trace.tool_calls} fallback={trace.fallback} total_ms={trace.total_ms}"
        )
        return full

    def _persist(self, trace: Trace, include_steps: bool) -> None:
        try:
            os.makedirs(self.trace_dir, exist_ok=True)
            path = os.path.join(self.trace_dir, f"{datetime.now().strftime('%Y%m%d')}.jsonl")
            payload = trace.to_dict(include_steps=include_steps, max_text_chars=self.text_max_chars)
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning(f"[trace]落盘失败（不影响请求）：{e}")

    def get(self, trace_id: str) -> dict | None:
        '''按 trace_id 查询：先内存缓存，再扫描当日 JSONL'''
        with self._lock:
            if trace_id in self._cache:
                return self._cache[trace_id]
        if self.log_level == "off":
            return None
        path = os.path.join(self.trace_dir, f"{datetime.now().strftime('%Y%m%d')}.jsonl")
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in reversed(f.readlines()):
                    data = json.loads(line)
                    if data.get("trace_id") == trace_id:
                        return data
        except FileNotFoundError:
            return None
        except Exception as e:
            logger.warning(f"[trace]查询失败：{e}")
        return None


_recorder_lock = threading.Lock()
_default_recorder: TraceRecorder | None = None


def get_trace_recorder() -> TraceRecorder:
    global _default_recorder
    if _default_recorder is None:
        with _recorder_lock:
            if _default_recorder is None:
                _default_recorder = TraceRecorder()
    return _default_recorder


def get_trace(trace_id: str) -> dict | None:
    return get_trace_recorder().get(trace_id)

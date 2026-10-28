# -*- coding: utf-8 -*-
'''极简 ReAct 循环：while + 工具字典，最多 3 轮，超时/超轮次/工具失败返回降级信号'''
import json
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass, field

from app.service.agent.react_parser import ReactDecision, ReactParseError, parse_react_output
from app.service.agent.tools.compare_calc_tool import build_compare_calc_tool
from app.service.agent.tools.rag_search_tool import build_rag_search_tool
from app.service.agent.tools.tool_registry import ToolRegistry, ToolResult
from app.service.history.history_store import get_chat_history
from app.utils.config_handler import hybrid_conf
from app.utils.logger_handler import logger
from app.utils.prompt_loader import load_prompt


@dataclass
class ReActResult:
    '''循环结果：answer 为空表示需要降级，fallback_reason 说明原因'''
    answer: str = ""
    documents: list = field(default_factory=list)
    steps: list[dict] = field(default_factory=list)
    tool_calls: int = 0
    model_calls: int = 0
    fallback_reason: str | None = None

    @property
    def ok(self) -> bool:
        return bool(self.answer) and self.fallback_reason is None


def _history_text(session_id: str | None, max_messages: int = 6, max_chars: int = 300) -> str:
    if not session_id:
        return "（无）"
    try:
        messages = get_chat_history(session_id).messages[-max_messages:]
    except Exception as e:
        logger.warning(f"[ReAct]读取历史失败，按空历史处理：{e}")
        return "（无）"
    lines = []
    for msg in messages:
        role = "用户" if getattr(msg, "type", "") == "human" else "助手"
        content = str(getattr(msg, "content", ""));
        lines.append(f"{role}：{content[:max_chars]}")
    return "\n".join(lines) or "（无）"


class SimpleReAct:
    '''极简 ReAct：每轮模型输出一个 JSON 决策，工具 observation 回填后继续'''

    def __init__(self, chat_model=None, tools: ToolRegistry | None = None,
                 max_steps: int | None = None, timeout_ms: int | None = None,
                 tool_timeout_ms: int | None = None, prompt_template: str | None = None):
        self.chat_model = chat_model
        self.tools = tools or self._build_default_tools()
        self.max_steps = int(max_steps if max_steps is not None else hybrid_conf.get("REACT_MAX_STEPS", 3))
        self.timeout_ms = int(timeout_ms if timeout_ms is not None else hybrid_conf.get("REACT_TIMEOUT_MS", 30000))
        self.tool_timeout_ms = int(tool_timeout_ms if tool_timeout_ms is not None else hybrid_conf.get("TOOL_TIMEOUT_MS", 10000))
        self.prompt_template = prompt_template if prompt_template is not None else load_prompt("react_complex_prompt_path")

    @staticmethod
    def _build_default_tools() -> ToolRegistry:
        registry = ToolRegistry()
        registry.register("rag_search", build_rag_search_tool())
        registry.register("compare_calc", build_compare_calc_tool())
        return registry

    def _get_model(self):
        if self.chat_model is None:
            from app.modelFactory.factory import chat_model
            self.chat_model = chat_model
        return self.chat_model

    def _invoke_model(self, prompt: str, timeout_s: float) -> str:
        '''带剩余时间约束的模型调用；超时/异常抛出，由 run 统一降级'''
        model = self._get_model()
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(model.invoke, prompt)
        try:
            response = future.result(timeout=max(0.001, timeout_s))
        except FutureTimeoutError:
            executor.shutdown(wait=False)
            raise TimeoutError("model_timeout")
        except Exception:
            executor.shutdown(wait=False)
            raise
        executor.shutdown(wait=False)
        return response.content if hasattr(response, "content") else str(response)

    def _render(self, query: str, session_id: str | None, observations: list[dict]) -> str:
        return (self.prompt_template
                .replace("<<HISTORY>>", _history_text(session_id))
                .replace("<<QUERY>>", query)
                .replace("<<OBSERVATIONS>>", json.dumps(observations, ensure_ascii=False, indent=2)))

    def run(self, query: str, session_id: str | None = None) -> ReActResult:
        '''执行 ReAct 循环；任何异常都转为 fallback_reason，不向编排层抛出'''
        started = time.monotonic()
        deadline = started + self.timeout_ms / 1000
        observations: list[dict] = []
        documents: list = []
        steps: list[dict] = []
        tool_calls = 0
        model_calls = 0
        consecutive_tool_failures = 0
        invalid_actions = 0

        def fail(reason: str) -> ReActResult:
            logger.warning(f"[ReAct]降级：{reason}（已调用模型 {model_calls} 次，工具 {tool_calls} 次）")
            return ReActResult(
                answer="", documents=documents, steps=steps, tool_calls=tool_calls,
                model_calls=model_calls, fallback_reason=reason,
            )

        def finalize(decision: ReactDecision, step_no: int, step_started: float) -> ReActResult:
            '''落 final_answer 步骤并校验答案；空答案/无证据一律降级'''
            answer = str(decision.action_input.get("answer") or "").strip()
            steps.append({
                "step": step_no, "thought": decision.thought, "action": "final_answer",
                "action_input": decision.action_input, "observation": {"answer": answer},
                "elapsed_ms": int((time.monotonic() - step_started) * 1000),
            })
            if not answer:
                return fail("empty_answer")
            if not observations:
                return fail("no_evidence")
            return ReActResult(answer=answer, documents=documents, steps=steps,
                               tool_calls=tool_calls, model_calls=model_calls)

        for step_no in range(1, self.max_steps + 1):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return fail("timeout")

            step_started = time.monotonic()
            prompt = self._render(query, session_id, observations)
            try:
                raw = self._invoke_model(prompt, remaining)
                model_calls += 1
            except TimeoutError:
                return fail("timeout")
            except Exception as e:
                logger.error(f"[ReAct]模型调用失败：{e}", exc_info=True)
                return fail("internal_error")

            try:
                decision: ReactDecision = parse_react_output(raw)
            except ReactParseError as e:
                steps.append({
                    "step": step_no, "thought": "", "action": "parse_error",
                    "action_input": {}, "observation": {"error": str(e)},
                    "elapsed_ms": int((time.monotonic() - step_started) * 1000),
                })
                return fail("parse_error")

            if decision.action == "final_answer":
                return finalize(decision, step_no, step_started)

            if decision.action not in self.tools.names:
                invalid_actions += 1
                observation = {"error": "unknown_action", "action": decision.action}
                observations.append(observation)
                steps.append({
                    "step": step_no, "thought": decision.thought, "action": decision.action,
                    "action_input": decision.action_input, "observation": observation,
                    "elapsed_ms": int((time.monotonic() - step_started) * 1000),
                })
                if invalid_actions >= 2:
                    return fail("parse_error")
                continue

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return fail("timeout")
            result: ToolResult = self.tools.call(
                decision.action, decision.action_input,
                timeout_ms=min(self.tool_timeout_ms, int(remaining * 1000)),
            )
            tool_calls += 1
            observations.append(result.observation)
            documents.extend(result.documents)
            steps.append({
                "step": step_no, "thought": decision.thought, "action": decision.action,
                "action_input": decision.action_input, "observation": result.observation,
                "elapsed_ms": int((time.monotonic() - step_started) * 1000),
            })
            if result.observation.get("error"):
                consecutive_tool_failures += 1
                if consecutive_tool_failures >= 2:
                    return fail("tool_failed")
            else:
                consecutive_tool_failures = 0

        # 工具轮次用尽后的收尾总结：只允许 final_answer，不再执行工具
        if observations:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return fail("timeout")
            step_no = self.max_steps + 1
            step_started = time.monotonic()
            prompt = self._render(query, session_id, observations) + (
                "\n\n【系统】工具调用轮次已用尽，请立即输出 final_answer，"
                "不要再调用任何工具；答案只能基于上面的 observation。"
            )
            try:
                raw = self._invoke_model(prompt, remaining)
                model_calls += 1
            except TimeoutError:
                return fail("timeout")
            except Exception as e:
                logger.error(f"[ReAct]收尾总结失败：{e}", exc_info=True)
                return fail("internal_error")
            try:
                decision = parse_react_output(raw)
            except ReactParseError as e:
                steps.append({
                    "step": step_no, "thought": "", "action": "parse_error",
                    "action_input": {}, "observation": {"error": str(e)},
                    "elapsed_ms": int((time.monotonic() - step_started) * 1000),
                })
                return fail("parse_error")
            if decision.action == "final_answer":
                return finalize(decision, step_no, step_started)

        return fail("max_steps_exceeded")

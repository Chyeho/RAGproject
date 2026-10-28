# -*- coding: utf-8 -*-
'''混合编排入口：配置开关 → 规则路由 → RAG 直调 / ReAct → 降级 → trace'''
import threading
from dataclasses import dataclass, field

from langchain_core.messages import AIMessage, HumanMessage

from app.service.agent.simple_react import SimpleReAct
from app.service.history.history_store import get_chat_history
from app.service.observability.trace import TraceRecorder, get_trace_recorder
from app.service.rag import registry
from app.service.routing.business_intent import is_non_business
from app.service.routing.rule_router import DIRECT, RuleRouter, get_rule_router
from app.utils.config_handler import hybrid_conf, rag_conf
from app.utils.logger_handler import logger

NON_BUSINESS = "non_business"


@dataclass
class OrchestrationResult:
    '''问答编排结果：answer/docs 供路由层使用，trace 供日志与调试接口使用'''
    answer: str
    documents: list = field(default_factory=list)
    trace: dict = field(default_factory=dict)

    @property
    def trace_id(self) -> str:
        return self.trace.get("trace_id", "")


def _resolve_session_id(session_id: str | None) -> str:
    return session_id or rag_conf["session_config"]["configurable"]["session_id"]


def _dedup_documents(docs: list) -> list:
    '''按 vector_id / document_id 去重，保持首次出现顺序（引用拼装用）'''
    seen, result = set(), []
    for doc in docs:
        meta = getattr(doc, "metadata", {}) or {}
        key = meta.get("vector_id") or (meta.get("document_id"), getattr(doc, "page_content", "")[:50])
        if key in seen:
            continue
        seen.add(key)
        result.append(doc)
    return result


class HybridOrchestrator:
    '''窄路由混合编排器（所有依赖可注入，便于单测）'''

    def __init__(self, router: RuleRouter | None = None, react: SimpleReAct | None = None,
                 recorder: TraceRecorder | None = None, rag_service_getter=None):
        # 路由与 ReAct 延迟构建：ENABLE_HYBRID_ROUTER=false 时不需要加载规则/提示词
        self.router = router
        self.react = react
        self.recorder = recorder or get_trace_recorder()
        self._rag_getter = rag_service_getter or registry.get_rag_service

    def _get_router(self) -> RuleRouter:
        if self.router is None:
            self.router = get_rule_router()
        return self.router

    def _get_react(self) -> SimpleReAct:
        if self.react is None:
            self.react = SimpleReAct()
        return self.react

    def _direct(self, query: str, session_id: str | None):
        return self._rag_getter().rag_summarize(query, session_id)

    def _direct_chat(self, query: str, session_id: str | None) -> str:
        '''非业务直达：不检索、不路由，直接用聊天模型回答（仍复用 RAG 提示词与历史）'''
        return self._rag_getter().summarize(
            query, [], session_id=_resolve_session_id(session_id), write_history=True
        )

    def answer(self, query: str, session_id: str | None = None) -> OrchestrationResult:
        '''主入口：开关关闭时纯直调；开启时按规则路由，ReAct 失败降级直调'''
        trace = self.recorder.start(query)

        # 总开关关闭：行为与改造前一致，仅额外记录 route/耗时
        if not bool(hybrid_conf.get("ENABLE_HYBRID_ROUTER", False)):
            trace.route = DIRECT
            trace.route_reason = "ENABLE_HYBRID_ROUTER=false，全部走 RAG 直调"
            answer, docs = self._direct(query, session_id)
            return OrchestrationResult(answer, docs, self.recorder.finish(trace, "rag_direct"))

        # 非业务问题直达：问候/自我介绍/使用咨询等，跳过检索与规则路由
        if is_non_business(query):
            trace.route = NON_BUSINESS
            trace.route_reason = "非业务问题直达：跳过检索与规则路由"
            answer = self._direct_chat(query, session_id)
            return OrchestrationResult(answer, [], self.recorder.finish(trace, "direct_llm"))

        decision = self._get_router().route(query)
        trace.set_route(decision)

        if decision.route == DIRECT:
            answer, docs = self._direct(query, session_id)
            return OrchestrationResult(answer, docs, self.recorder.finish(trace, "rag_direct"))

        # 复杂通道
        react_result = self._get_react().run(query, session_id)
        for step in react_result.steps:
            trace.add_step(
                step=step.get("step", 0), thought=step.get("thought", ""),
                action=step.get("action", ""), action_input=step.get("action_input", {}),
                observation=step.get("observation", {}), elapsed_ms=step.get("elapsed_ms", 0),
            )
        trace.add_tool_call(react_result.tool_calls)

        if react_result.ok:
            _write_history(session_id, query, react_result.answer)
            docs = _dedup_documents(react_result.documents)
            return OrchestrationResult(react_result.answer, docs, self.recorder.finish(trace, "react"))

        # 降级：默认回 RAG 直调，用户无感
        trace.mark_fallback(react_result.fallback_reason or "unknown")
        logger.warning(f"[编排]ReAct 失败，降级 RAG 直调，原因：{trace.fallback_reason}")
        if bool(hybrid_conf.get("ENABLE_REACT_FALLBACK", True)):
            answer, docs = self._direct(query, session_id)
            return OrchestrationResult(answer, docs, self.recorder.finish(trace, "rag_direct_fallback"))

        answer = "复杂问题分析失败，请稍后重试或简化问题。"
        return OrchestrationResult(answer, [], self.recorder.finish(trace, "react_failed"))


def _write_history(session_id: str | None, query: str, answer: str) -> None:
    '''ReAct 成功路径写回一次会话历史（工具子查询不写）'''
    try:
        get_chat_history(_resolve_session_id(session_id)).add_messages(
            [HumanMessage(content=query), AIMessage(content=answer)]
        )
    except Exception as e:
        logger.warning(f"[编排]ReAct 历史写入失败（不影响回答）：{e}")


_orchestrator_lock = threading.Lock()
_orchestrator: HybridOrchestrator | None = None


def get_orchestrator() -> HybridOrchestrator:
    '''线程安全懒加载默认编排器'''
    global _orchestrator
    if _orchestrator is None:
        with _orchestrator_lock:
            if _orchestrator is None:
                _orchestrator = HybridOrchestrator()
    return _orchestrator

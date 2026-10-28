# -*- coding: utf-8 -*-
'''极简工具注册表：白名单 + 统一超时 + 异常包装

不引入 LangChain Tool 抽象，工具就是普通可调用对象：
    fn(action_input: dict) -> ToolResult
'''
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass, field
from typing import Callable

from app.utils.config_handler import hybrid_conf
from app.utils.logger_handler import logger


@dataclass
class ToolResult:
    '''工具执行结果：observation 进模型上下文，documents 供引用拼装'''
    observation: dict
    documents: list = field(default_factory=list)


class ToolRegistry:
    '''工具白名单注册与统一调用'''

    def __init__(self):
        self._tools: dict[str, Callable[[dict], ToolResult]] = {}

    def register(self, name: str, func: Callable[[dict], ToolResult]) -> None:
        self._tools[name] = func

    def has(self, name: str) -> bool:
        return name in self._tools

    @property
    def names(self) -> list[str]:
        return list(self._tools)

    def call(self, name: str, action_input: dict | None, timeout_ms: int | None = None) -> ToolResult:
        '''调用工具：未知工具/参数非法/超时/异常都返回结构化 observation，不抛出'''
        if name not in self._tools:
            return ToolResult({"error": "unknown_tool", "tool": name})
        if action_input is None:
            action_input = {}
        if not isinstance(action_input, dict):
            return ToolResult({"error": "invalid_action_input", "detail": "action_input 必须是对象"})

        timeout_ms = int(timeout_ms if timeout_ms is not None else hybrid_conf.get("TOOL_TIMEOUT_MS", 10000))
        timeout_s = max(0.001, timeout_ms / 1000)
        started = time.monotonic()
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(self._tools[name], action_input)
        try:
            result = future.result(timeout=timeout_s)
        except FutureTimeoutError:
            executor.shutdown(wait=False)
            logger.warning(f"[工具]调用超时：{name}，{timeout_ms}ms")
            return ToolResult({"error": "tool_timeout", "tool": name, "timeout_ms": timeout_ms})
        except Exception as e:
            executor.shutdown(wait=False)
            logger.error(f"[工具]调用失败：{name}，{e}", exc_info=True)
            return ToolResult({"error": "tool_failed", "tool": name, "detail": str(e)})
        finally:
            elapsed = int((time.monotonic() - started) * 1000)
        executor.shutdown(wait=False)

        if isinstance(result, ToolResult):
            pass
        elif isinstance(result, dict):
            result = ToolResult(result)
        else:
            result = ToolResult({"result": result})
        logger.info(f"[工具]调用完成：{name}，耗时 {elapsed}ms")
        return result

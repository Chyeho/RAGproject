# -*- coding: utf-8 -*-
'''ReAct 模型输出解析：严格 JSON + 容错 markdown/前后杂文'''
import json
import re
from dataclasses import dataclass

ALLOWED_ACTIONS = ("rag_search", "compare_calc", "final_answer")


@dataclass
class ReactDecision:
    thought: str
    action: str
    action_input: dict
    raw: str = ""


class ReactParseError(ValueError):
    '''模型输出无法解析为合法 ReAct 决策'''


def _extract_json_object(text: str) -> str | None:
    '''优先找 ```json 代码块，其次用 raw_decode 从第一个 { 开始解析'''
    if not text:
        return None
    candidates = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidates.append(text)
    for candidate in candidates:
        start = candidate.find("{")
        if start < 0:
            continue
        try:
            _, end = json.JSONDecoder().raw_decode(candidate[start:])
            return candidate[start:start + end]
        except json.JSONDecodeError:
            continue
    return None


def parse_react_output(text: str) -> ReactDecision:
    '''解析模型输出；失败一律抛 ReactParseError（由循环降级，不做猜测）'''
    payload = _extract_json_object(text if isinstance(text, str) else str(text))
    if payload is None:
        raise ReactParseError("未找到合法 JSON 对象")
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as e:
        raise ReactParseError(f"JSON 解析失败：{e}") from e
    if not isinstance(data, dict):
        raise ReactParseError("JSON 根节点必须是对象")

    action = str(data.get("action") or "").strip()
    if action not in ALLOWED_ACTIONS:
        raise ReactParseError(f"非法 action：{action!r}")
    action_input = data.get("action_input")
    if action_input is None:
        action_input = {}
    if not isinstance(action_input, dict):
        raise ReactParseError("action_input 必须是对象")

    return ReactDecision(
        thought=str(data.get("thought") or ""),
        action=action,
        action_input=action_input,
        raw=payload,
    )

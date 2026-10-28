# -*- coding: utf-8 -*-
'''对比/计算/条件判断工具（纯函数，不调用 LLM，不做复杂计算引擎）'''
import difflib
import re

from app.service.agent.tools.tool_registry import ToolResult
from app.utils.config_handler import hybrid_conf

_NUM_PATTERN = re.compile(r"-?\d+(?:\.\d+)?")
_OPERATORS = {
    "gt": lambda a, b: a > b,
    "gte": lambda a, b: a >= b,
    "lt": lambda a, b: a < b,
    "lte": lambda a, b: a <= b,
    "eq": lambda a, b: a == b,
    "ne": lambda a, b: a != b,
}


def _to_number(value):
    '''把数字/数字字符串转 float；无法转换返回 None（避免把“3天”误当 3）'''
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if _NUM_PATTERN.fullmatch(text):
            try:
                return float(text)
            except ValueError:
                return None
    return None


def _normalize_items(items) -> list[dict]:
    if not isinstance(items, list):
        return []
    max_items = int(hybrid_conf.get("COMPARE_CALC_MAX_ITEMS", 20))
    normalized = []
    for idx, item in enumerate(items[:max_items], start=1):
        if not isinstance(item, dict):
            item = {"text": str(item)}
        normalized.append({
            "label": str(item.get("label") or f"item{idx}"),
            "text": str(item.get("text") or ""),
            "value": item.get("value"),
            "source": str(item.get("source") or ""),
        })
    return normalized


def _evidence(items: list[dict]) -> list[dict]:
    return [
        {"label": it["label"], "text": it["text"], "source": it["source"]}
        for it in items
        if it["text"] or it["source"]
    ]


def _compare(items: list[dict], criteria: dict) -> dict:
    field = str(criteria.get("field") or "value")
    values = []
    for it in items:
        raw = it.get(field)
        if raw is None and field == "text":
            raw = it.get("text")
        values.append({"label": it["label"], "value": raw, "source": it["source"]})

    numeric = [(v["label"], _to_number(v["value"])) for v in values]
    numeric = [(label, num) for label, num in numeric if num is not None]
    result = {"field": field, "items": values}
    if len(numeric) >= 2:
        max_label, max_value = max(numeric, key=lambda x: x[1])
        min_label, min_value = min(numeric, key=lambda x: x[1])
        result.update({
            "max": {"label": max_label, "value": max_value},
            "min": {"label": min_label, "value": min_value},
            "diff": round(max_value - min_value, 4),
        })
        explanation = f"按 {field} 比较：最大为 {max_label}（{max_value:g}），最小为 {min_label}（{min_value:g}），差值为 {max_value - min_value:g}。"
    else:
        explanation = f"按 {field} 比较完成；可数值化条目不足 2 个，仅返回明细。"
    return {"result": result, "explanation": explanation}


def _diff(items: list[dict]) -> dict:
    if len(items) != 2:
        return {"error": "diff_requires_two_items", "explanation": "diff 操作要求恰好 2 个 item。"}
    left, right = items
    ratio = difflib.SequenceMatcher(None, left["text"], right["text"]).ratio()
    diffs = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, left["text"], right["text"]).get_opcodes():
        if tag == "equal":
            continue
        diffs.append({
            "type": tag,
            "left": left["text"][i1:i2],
            "right": right["text"][j1:j2],
        })
        if len(diffs) >= 10:
            break
    return {
        "result": {
            "similarity": round(ratio, 4),
            "left": left["label"],
            "right": right["label"],
            "differences": diffs,
        },
        "explanation": f"{left['label']} 与 {right['label']} 文本相似度 {ratio:.2%}，差异片段 {len(diffs)} 处。",
    }


def _sum(items: list[dict], criteria: dict) -> dict:
    values = []
    for it in items:
        num = _to_number(it.get("value"))
        if num is None:
            num = _to_number(it.get("text"))
        if num is not None:
            values.append({"label": it["label"], "value": num})
    if not values:
        return {"error": "no_numeric_items", "explanation": "没有可求和的数值条目。"}
    total = round(sum(v["value"] for v in values), 4)
    return {
        "result": {
            "total": total,
            "count": len(values),
            "unit": criteria.get("unit"),
            "values": values,
        },
        "explanation": f"共 {len(values)} 个数值，合计 {total:g}{criteria.get('unit') or ''}。",
    }


def _condition_check(items: list[dict], criteria: dict) -> dict:
    field = str(criteria.get("field") or "value")
    operator = str(criteria.get("operator") or "eq")
    target = criteria.get("value")
    if operator not in _OPERATORS and operator != "contains":
        return {"error": "unsupported_operator", "explanation": f"不支持的操作符：{operator}"}

    details = []
    for it in items:
        actual = it.get(field)
        if actual is None and field == "text":
            actual = it.get("text")
        passed = False
        if operator == "contains":
            passed = str(target) in str(actual or "")
        else:
            left, right = _to_number(actual), _to_number(target)
            if left is not None and right is not None:
                passed = bool(_OPERATORS[operator](left, right))
        details.append({
            "label": it["label"],
            "actual": actual,
            "passed": passed,
            "source": it["source"],
        })
    passed_count = sum(1 for d in details if d["passed"])
    return {
        "result": {
            "field": field,
            "operator": operator,
            "target": target,
            "passed_count": passed_count,
            "total": len(details),
            "details": details,
        },
        "explanation": f"条件 {field} {operator} {target}：{passed_count}/{len(details)} 项满足。",
    }


def build_compare_calc_tool():
    '''构造 compare_calc 工具（operation: compare|diff|sum|condition_check）'''

    def compare_calc(action_input: dict) -> ToolResult:
        action_input = action_input or {}
        operation = str(action_input.get("operation") or "").strip()
        if operation not in ("compare", "diff", "sum", "condition_check"):
            return ToolResult({"error": "invalid_operation", "explanation": f"未知操作：{operation}"})

        items = _normalize_items(action_input.get("items"))
        if not items:
            return ToolResult({"error": "items_required", "explanation": "items 不能为空。"})

        criteria = action_input.get("criteria")
        if not isinstance(criteria, dict):
            criteria = {}

        if operation == "compare":
            payload = _compare(items, criteria)
        elif operation == "diff":
            payload = _diff(items)
        elif operation == "sum":
            payload = _sum(items, criteria)
        else:
            payload = _condition_check(items, criteria)

        observation = {
            "result": payload.get("result"),
            "evidence": _evidence(items),
            "explanation": payload.get("explanation", ""),
        }
        if "error" in payload:
            observation["error"] = payload["error"]
        return ToolResult(observation)

    return compare_calc

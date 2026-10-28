# -*- coding: utf-8 -*-
'''窄规则路由：只区分 rag_direct / react_complex，不做 LLM 或向量分类'''
import os
import re
import threading
from dataclasses import dataclass, field

import yaml

from app.utils.config_handler import hybrid_conf
from app.utils.logger_handler import logger
from app.utils.path_tool import get_abs_path

DIRECT = "rag_direct"
COMPLEX = "react_complex"


@dataclass(frozen=True)
class RouteDecision:
    '''路由结果（可解释：reason + 命中规则 + 累计分值）'''
    route: str
    reason: str
    matched_rules: tuple[str, ...] = field(default_factory=tuple)
    score: int = 0

    def to_dict(self) -> dict:
        return {
            "route": self.route,
            "reason": self.reason,
            "matched_rules": list(self.matched_rules),
            "score": self.score,
        }


def _resolve_path(path: str) -> str:
    '''配置路径支持绝对路径与相对 app 根目录的路径'''
    return path if os.path.isabs(path) else get_abs_path(path)


def load_router_rules(rules_path: str | None = None) -> dict:
    '''加载规则 YAML；失败时返回空规则（路由保守回退 rag_direct）'''
    path = _resolve_path(rules_path or str(hybrid_conf.get("ROUTER_RULES_PATH", "config/router_rules.yml")))
    try:
        with open(path, "r", encoding="utf-8") as f:
            conf = yaml.load(f, Loader=yaml.FullLoader) or {}
        if not isinstance(conf, dict):
            raise ValueError("规则文件根节点必须是对象")
        return conf
    except Exception as e:
        logger.warning(f"[路由]规则文件加载失败，保守回退 rag_direct：{path}，{e}")
        return {"threshold": 2, "rules": [], "load_error": str(e)}


class RuleRouter:
    '''规则路由：强规则直接命中，弱规则按 weight 累计达到阈值后命中'''

    def __init__(self, rules_config: dict | None = None, rules_path: str | None = None):
        conf = rules_config if rules_config is not None else load_router_rules(rules_path)
        self.threshold = int(conf.get("threshold", 2) or 2)
        self.load_error = conf.get("load_error")
        self.rules: list[dict] = []
        for raw in conf.get("rules", []) or []:
            if not isinstance(raw, dict) or not raw.get("enabled", True):
                continue
            pattern = raw.get("pattern")
            if not pattern:
                continue
            try:
                compiled = re.compile(str(pattern))
            except re.error as e:
                logger.warning(f"[路由]规则 {raw.get('id')} 正则非法，已忽略：{e}")
                continue
            self.rules.append({
                "id": str(raw.get("id", "unnamed")),
                "description": str(raw.get("description", "")),
                "regex": compiled,
                "weight": int(raw.get("weight", 1) or 1),
                "strong": bool(raw.get("strong", False)),
            })

    def route(self, query: str, context: str | None = None) -> RouteDecision:
        '''对用户问题做规则判定；context 预留但不参与匹配，避免历史问题污染当前路由'''
        query = (query or "").strip()
        if not query:
            return RouteDecision(DIRECT, "空问题，默认 RAG 直调", (), 0)
        if self.load_error:
            return RouteDecision(DIRECT, f"路由规则不可用，保守回退：{self.load_error}", (), 0)
        if not self.rules:
            return RouteDecision(DIRECT, "无可用路由规则，默认 RAG 直调", (), 0)

        matched: list[str] = []
        score = 0
        has_strong = False
        for rule in self.rules:
            if rule["regex"].search(query):
                matched.append(rule["id"])
                score += rule["weight"]
                has_strong = has_strong or rule["strong"]

        if has_strong or score >= self.threshold:
            reason = (
                f"命中强规则 {', '.join(matched)}" if has_strong
                else f"弱规则累计 {score} ≥ 阈值 {self.threshold}（{', '.join(matched)}）"
            )
            return RouteDecision(COMPLEX, reason, tuple(matched), score)
        if matched:
            reason = f"仅命中弱规则 {', '.join(matched)}，累计 {score} < 阈值 {self.threshold}，保持直调"
        else:
            reason = "未命中复杂规则，默认 RAG 直调"
        return RouteDecision(DIRECT, reason, tuple(matched), score)


_router_lock = threading.Lock()
_default_router: RuleRouter | None = None


def get_rule_router() -> RuleRouter:
    '''默认规则路由器单例（规则文件在首次使用时加载）'''
    global _default_router
    if _default_router is None:
        with _router_lock:
            if _default_router is None:
                _default_router = RuleRouter()
    return _default_router

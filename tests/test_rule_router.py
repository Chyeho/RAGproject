# -*- coding: utf-8 -*-
'''规则路由与混合配置单元测试（全离线）'''
import os

from app.service.routing.rule_router import COMPLEX, DIRECT, RuleRouter
from app.utils.config_handler import load_hybrid_config

RULES = {
    "threshold": 2,
    "rules": [
        {"id": "compare", "pattern": "对比|比较|差异", "weight": 2, "strong": True},
        {"id": "multi_entity", "pattern": "上海.*北京|北京.*上海", "weight": 2, "strong": True},
        {"id": "condition_calc", "pattern": "预算|计算|汇总", "weight": 1, "strong": False},
    ],
}


class TestRuleRouter:
    def test_compare_triggers_complex(self):
        decision = RuleRouter(rules_config=RULES).route("对比上海和北京的差旅住宿标准")
        assert decision.route == COMPLEX
        assert "compare" in decision.matched_rules
        assert "multi_entity" in decision.matched_rules

    def test_single_weak_rule_stays_direct(self):
        decision = RuleRouter(rules_config=RULES).route("预算编制几月启动？")
        assert decision.route == DIRECT
        assert decision.score == 1
        assert "condition_calc" in decision.matched_rules

    def test_two_weak_rules_trigger_complex(self):
        rules = {"threshold": 2, "rules": [
            {"id": "w1", "pattern": "预算", "weight": 1, "strong": False},
            {"id": "w2", "pattern": "汇总", "weight": 1, "strong": False},
        ]}
        decision = RuleRouter(rules_config=rules).route("预算汇总怎么做")
        assert decision.route == COMPLEX
        assert decision.score == 2

    def test_simple_query_direct(self):
        decision = RuleRouter(rules_config=RULES).route("公司年假多少天？")
        assert decision.route == DIRECT
        assert decision.matched_rules == ()

    def test_empty_query_direct(self):
        decision = RuleRouter(rules_config=RULES).route("   ")
        assert decision.route == DIRECT

    def test_load_error_falls_back_direct(self):
        router = RuleRouter(rules_path="does/not/exist.yml")
        decision = router.route("对比上海和北京的制度")
        assert decision.route == DIRECT
        assert "保守回退" in decision.reason

    def test_disabled_rule_ignored(self):
        rules = {"threshold": 2, "rules": [
            {"id": "compare", "pattern": "对比", "weight": 2, "strong": True, "enabled": False},
        ]}
        assert RuleRouter(rules_config=rules).route("对比一下").route == DIRECT

    def test_invalid_regex_ignored(self):
        rules = {"threshold": 2, "rules": [
            {"id": "bad", "pattern": "[", "weight": 2, "strong": True},
        ]}
        assert RuleRouter(rules_config=rules).route("任意问题").route == DIRECT


class TestHybridConfig:
    def test_defaults_without_file(self):
        conf = load_hybrid_config(config_path="does/not/exist.yml")
        assert conf["REACT_MAX_STEPS"] == 3
        assert conf["REACT_TIMEOUT_MS"] == 30000
        assert conf["TOOL_TIMEOUT_MS"] == 10000
        assert conf["ENABLE_HYBRID_ROUTER"] is False

    def test_yaml_values_and_env_override(self, tmp_path, monkeypatch):
        path = tmp_path / "hybrid.yml"
        path.write_text(
            "ENABLE_HYBRID_ROUTER: true\nREACT_MAX_STEPS: 2\nREACT_TIMEOUT_MS: 1234\n",
            encoding="utf-8",
        )
        monkeypatch.setenv("REACT_TIMEOUT_MS", "9999")
        monkeypatch.setenv("ENABLE_HYBRID_ROUTER", "false")
        conf = load_hybrid_config(config_path=str(path))
        assert conf["REACT_MAX_STEPS"] == 2
        assert conf["REACT_TIMEOUT_MS"] == 9999
        assert conf["ENABLE_HYBRID_ROUTER"] is False

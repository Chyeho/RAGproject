# -*- coding: utf-8 -*-
'''compare_calc 工具单元测试（纯函数，全离线）'''
from app.service.agent.tools.compare_calc_tool import build_compare_calc_tool
from app.utils.config_handler import hybrid_conf


def _tool():
    return build_compare_calc_tool()


class TestCompareCalcArgs:
    def test_invalid_operation(self):
        result = _tool()({"operation": "unknown", "items": [{"value": 1}]})
        assert result.observation["error"] == "invalid_operation"

    def test_items_required(self):
        result = _tool()({"operation": "sum", "items": []})
        assert result.observation["error"] == "items_required"

    def test_non_dict_items_normalized(self):
        result = _tool()({"operation": "sum", "items": [1, "2"]})
        assert result.observation["result"]["total"] == 3

    def test_max_items_cap(self, monkeypatch):
        monkeypatch.setitem(hybrid_conf, "COMPARE_CALC_MAX_ITEMS", 2)
        result = _tool()({"operation": "sum", "items": [{"value": i} for i in range(5)]})
        assert result.observation["result"]["count"] == 2


class TestCompare:
    def test_numeric_compare(self):
        result = _tool()({
            "operation": "compare",
            "items": [
                {"label": "上海", "value": 500, "text": "住宿 500", "source": "doc1"},
                {"label": "北京", "value": 650, "text": "住宿 650", "source": "doc2"},
            ],
            "criteria": {"field": "value"},
        })
        data = result.observation
        assert data["result"]["max"] == {"label": "北京", "value": 650.0}
        assert data["result"]["min"]["label"] == "上海"
        assert data["result"]["diff"] == 150.0
        assert len(data["evidence"]) == 2
        assert "北京" in data["explanation"]

    def test_non_numeric_only_details(self):
        result = _tool()({
            "operation": "compare",
            "items": [{"label": "a", "value": "三天"}, {"label": "b", "value": "两天"}],
            "criteria": {"field": "value"},
        })
        assert "max" not in result.observation["result"]
        assert "数值化条目不足" in result.observation["explanation"]


class TestDiff:
    def test_diff_two_items(self):
        result = _tool()({
            "operation": "diff",
            "items": [{"label": "旧版", "text": "年假 5 天"},
                      {"label": "新版", "text": "年假 10 天"}],
        })
        data = result.observation
        assert data["result"]["similarity"] > 0
        assert data["result"]["differences"]
        assert data["result"]["left"] == "旧版"

    def test_diff_requires_two_items(self):
        result = _tool()({"operation": "diff", "items": [{"text": "只有一条"}]})
        assert result.observation["error"] == "diff_requires_two_items"


class TestSum:
    def test_sum_values(self):
        result = _tool()({
            "operation": "sum",
            "items": [{"value": 1.5}, {"value": "2.5"}, {"text": "3"}],
            "criteria": {"unit": "天"},
        })
        data = result.observation
        assert data["result"]["total"] == 7.0
        assert data["result"]["count"] == 3
        assert data["result"]["unit"] == "天"

    def test_sum_no_numeric(self):
        result = _tool()({"operation": "sum", "items": [{"value": "三天"}]})
        assert result.observation["error"] == "no_numeric_items"


class TestConditionCheck:
    def test_numeric_operator(self):
        result = _tool()({
            "operation": "condition_check",
            "items": [{"label": "A", "value": 120}, {"label": "B", "value": 80}],
            "criteria": {"field": "value", "operator": "gt", "value": 100},
        })
        data = result.observation["result"]
        assert data["passed_count"] == 1
        assert data["total"] == 2

    def test_contains_operator(self):
        result = _tool()({
            "operation": "condition_check",
            "items": [{"label": "A", "text": "需要提前三天申请"}],
            "criteria": {"field": "text", "operator": "contains", "value": "提前"},
        })
        assert result.observation["result"]["passed_count"] == 1

    def test_unsupported_operator(self):
        result = _tool()({
            "operation": "condition_check",
            "items": [{"value": 1}],
            "criteria": {"operator": "between", "value": 1},
        })
        assert result.observation["error"] == "unsupported_operator"

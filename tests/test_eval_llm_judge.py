# -*- coding: utf-8 -*-
"""eval.llm_judge LLM 裁判单元测试（mock chat_model，不调外部 API）"""
from app.service.eval.llm_judge import (
    aggregate_generation,
    answer_relevancy,
    faithfulness,
    parse_score_json,
)


class FakeModel:
    """假聊天模型：bind 返回自身，invoke 返回预置 content 并记录 prompt"""

    def __init__(self, content: str):
        self.content = content
        self.prompts = []
        self.bound_kwargs = []

    def bind(self, **kwargs):
        self.bound_kwargs.append(kwargs)
        return self

    def invoke(self, prompt):
        self.prompts.append(prompt)
        return type("Resp", (), {"content": self.content})()


# ---------- JSON 解析 ----------

class TestParseScoreJson:
    def test_plain_json(self):
        assert parse_score_json('{"score": 0.8, "reason": "基本有依据"}') == 0.8

    def test_markdown_wrapped(self):
        text = '```json\n{"score": 1.0, "reason": "完全一致"}\n```'
        assert parse_score_json(text) == 1.0

    def test_with_surrounding_text(self):
        text = '评估结果如下：{"score": 0.4, "reason": "部分推测"} 以上。'
        assert parse_score_json(text) == 0.4

    def test_score_clamped(self):
        assert parse_score_json('{"score": 1.5}') == 1.0
        assert parse_score_json('{"score": -0.3}') == 0.0

    def test_invalid_returns_none(self):
        assert parse_score_json("这不是JSON") is None
        assert parse_score_json('{"reason": "缺score"}') is None
        assert parse_score_json("") is None
        assert parse_score_json(None) is None


# ---------- 裁判调用 ----------

class TestFaithfulness:
    def test_invoke_with_temperature_zero(self):
        model = FakeModel('{"score": 1.0, "reason": "ok"}')
        score = faithfulness(model, "年假有几天？", "十五天", ["年假满十年为十五天"])
        assert score == 1.0
        assert {"temperature": 0} in model.bound_kwargs

    def test_prompt_contains_all_parts(self):
        model = FakeModel('{"score": 0.7}')
        faithfulness(model, "Q问题", "A回答", ["C1上下文", "C2上下文"])
        prompt = model.prompts[0]
        assert "Q问题" in prompt and "A回答" in prompt
        assert "C1上下文" in prompt and "C2上下文" in prompt

    def test_empty_context_still_works(self):
        model = FakeModel('{"score": 0.0}')
        assert faithfulness(model, "Q", "A", []) == 0.0

    def test_llm_error_returns_none(self):
        class BrokenModel:
            def bind(self, **kw):
                return self

            def invoke(self, prompt):
                raise RuntimeError("api down")

        assert faithfulness(BrokenModel(), "Q", "A", ["C"]) is None


class TestAnswerRelevancy:
    def test_score_parsed(self):
        model = FakeModel('{"score": 0.7, "reason": "大体切题"}')
        assert answer_relevancy(model, "报销时效多久？", "三十天内提交") == 0.7
        assert "报销时效多久？" in model.prompts[0]


# ---------- 聚合 ----------

class TestAggregateGeneration:
    def test_mixed_scores(self):
        stat = aggregate_generation([1.0, None, 0.5])
        assert stat == {"num_judged": 2, "num_judge_error": 1, "mean": 0.75}

    def test_all_none(self):
        stat = aggregate_generation([None, None])
        assert stat["num_judged"] == 0
        assert stat["num_judge_error"] == 2
        assert stat["mean"] is None

    def test_empty(self):
        assert aggregate_generation([])["mean"] is None

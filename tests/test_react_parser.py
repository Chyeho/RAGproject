# -*- coding: utf-8 -*-
'''ReAct 输出解析单元测试'''
import pytest

from app.service.agent.react_parser import ReactParseError, parse_react_output


class TestReactParser:
    def test_plain_json(self):
        decision = parse_react_output(
            '{"thought": "查制度", "action": "rag_search", "action_input": {"query": "差旅"}}'
        )
        assert decision.action == "rag_search"
        assert decision.action_input["query"] == "差旅"

    def test_markdown_json(self):
        text = '```json\n{"thought": "t", "action": "final_answer", "action_input": {"answer": "答案"}}\n```'
        decision = parse_react_output(text)
        assert decision.action == "final_answer"
        assert decision.action_input["answer"] == "答案"

    def test_extra_text_around_json(self):
        text = '先说明一下：\n{"thought": "t", "action": "rag_search", "action_input": {}}\n结束'
        assert parse_react_output(text).action == "rag_search"

    def test_empty_answer_allowed(self):
        decision = parse_react_output('{"thought": "t", "action": "final_answer", "action_input": {}}')
        assert decision.action == "final_answer"

    def test_invalid_action_raises(self):
        with pytest.raises(ReactParseError):
            parse_react_output('{"thought": "t", "action": "web_search", "action_input": {}}')

    def test_invalid_action_input_raises(self):
        with pytest.raises(ReactParseError):
            parse_react_output('{"thought": "t", "action": "rag_search", "action_input": "bad"}')

    def test_non_json_raises(self):
        with pytest.raises(ReactParseError):
            parse_react_output("我需要先查一下资料")

    def test_empty_input_raises(self):
        with pytest.raises(ReactParseError):
            parse_react_output("")

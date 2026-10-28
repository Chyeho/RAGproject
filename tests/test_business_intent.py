# -*- coding: utf-8 -*-
'''非业务问题识别单元测试（纯规则，全离线）'''
from app.service.routing.business_intent import is_non_business


class TestNonBusinessIntent:
    def test_greeting_intro_usage_and_farewell(self):
        queries = [
            "你好", "您好呀", "在吗？", "hello", "谢谢！", "再见",
            "你是谁？", "你能做什么", "你有哪些能力", "你是AI吗",
            "怎么使用你", "你能帮我做什么",
            "你好，你能介绍一下你吗？我该如何使用你",
        ]
        for query in queries:
            assert is_non_business(query) is True, query

    def test_business_or_mixed_intent_not_direct(self):
        queries = [
            "上海总部出差住宿标准是多少",
            "你好，差旅报销标准是多少",
            "你能做什么采购流程",
            "谢谢，帮我查一下会议室的预订方式",
            "怎么使用会议室",
            "你能帮我对比一下上海和北京的住宿标准吗",
        ]
        for query in queries:
            assert is_non_business(query) is False, query

    def test_empty_or_overlong_not_direct(self):
        assert is_non_business("") is False
        assert is_non_business("   ") is False
        assert is_non_business(None) is False
        assert is_non_business("介绍一下你自己" + "啊" * 40) is False

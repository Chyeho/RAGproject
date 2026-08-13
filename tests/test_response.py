# -*- coding: utf-8 -*-
"""统一响应包裹（{code, message, data}）单元测试"""
from app.core.response import ok, err


class TestOk:
    """测试成功响应 ok()"""

    def test_default_structure(self):
        """默认：code=0, message=success, data=None"""
        resp = ok()
        assert resp == {"code": 0, "message": "success", "data": None}

    def test_with_data(self):
        """携带 data"""
        resp = ok({"id": 1})
        assert resp["code"] == 0
        assert resp["data"] == {"id": 1}

    def test_custom_message(self):
        """自定义 message"""
        resp = ok(None, "注册成功")
        assert resp["message"] == "注册成功"

    def test_keeps_contract_keys(self):
        """响应只含契约定义的三字段"""
        resp = ok([1, 2])
        assert set(resp.keys()) == {"code", "message", "data"}


class TestErr:
    """测试失败响应 err()"""

    def test_structure(self):
        """code/message 透传，data 恒为 None"""
        resp = err(2001, "手机号或密码错误")
        assert resp == {"code": 2001, "message": "手机号或密码错误", "data": None}

    def test_code_is_int(self):
        """code 与契约错误码一致（int）"""
        for code in (1001, 2001, 2002, 2003, 3001, 4001, 4002, 4003, 5001, 5000):
            resp = err(code, "x")
            assert isinstance(resp["code"], int)
            assert resp["code"] == code

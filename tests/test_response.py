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
        resp = ok(None, "保存成功")
        assert resp["message"] == "保存成功"

    def test_keeps_contract_keys(self):
        """响应只含契约定义的三字段"""
        resp = ok([1, 2])
        assert set(resp.keys()) == {"code", "message", "data"}


class TestErr:
    """测试失败响应 err()"""

    def test_structure(self):
        """code/message 透传，data 恒为 None"""
        resp = err(2001, "账号或密码错误")
        assert resp == {"code": 2001, "message": "账号或密码错误", "data": None}

    def test_code_is_int(self):
        """code 与契约错误码一致（int）"""
        # 契约 v2.1 现役错误码（注册/验证码相关 2002/2003 已随接口下线）
        for code in (1001, 2001, 2005, 3001, 3002, 4001, 4002, 4003, 4004, 4005, 4006, 5001, 5000):
            resp = err(code, "x")
            assert isinstance(resp["code"], int)
            assert resp["code"] == code

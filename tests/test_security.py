# -*- coding: utf-8 -*-
"""安全工具（bcrypt 密码哈希 + JWT）单元测试"""
import jwt
import pytest

from app.core.security import (
    SECRET_KEY,
    ALGORITHM,
    hash_password,
    verify_password,
    create_access_token,
    decode_token,
)


class TestHashPassword:
    """测试密码哈希"""

    def test_returns_bcrypt_hash_string(self):
        """返回 bcrypt 格式哈希（$2b$ 前缀）"""
        hashed = hash_password("123456")
        assert isinstance(hashed, str)
        assert hashed.startswith("$2")

    def test_same_password_different_salt(self):
        """相同密码两次哈希结果不同（带随机盐）"""
        h1 = hash_password("123456")
        h2 = hash_password("123456")
        assert h1 != h2

    def test_verify_correct_password(self):
        """正确密码校验通过"""
        hashed = hash_password("123456")
        assert verify_password("123456", hashed) is True

    def test_verify_wrong_password(self):
        """错误密码校验失败"""
        hashed = hash_password("123456")
        assert verify_password("654321", hashed) is False

    def test_verify_malformed_hash_returns_false(self):
        """畸形哈希不抛异常，返回 False"""
        assert verify_password("123456", "not-a-bcrypt-hash") is False


class TestCreateAccessToken:
    """测试 JWT 签发"""

    def test_returns_jwt_string(self):
        """返回三段式 JWT"""
        token = create_access_token(1)
        assert isinstance(token, str)
        assert token.count(".") == 2

    def test_payload_contains_user_id(self):
        """payload 的 sub 为用户 ID"""
        token = create_access_token(42)
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        assert payload["sub"] == "42"

    def test_default_expire_about_one_day(self):
        """默认（remember=False）有效期约 24 小时"""
        import time
        token = create_access_token(1, remember=False)
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        remain_hours = (payload["exp"] - int(time.time())) / 3600
        assert 20 <= remain_hours <= 26

    def test_remember_expire_about_seven_days(self):
        """remember=True 有效期约 7 天"""
        import time
        token = create_access_token(1, remember=True)
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        remain_days = (payload["exp"] - int(time.time())) / 86400
        assert 6.5 <= remain_days <= 7.5


class TestDecodeToken:
    """测试 JWT 解析"""

    def test_returns_user_id_for_valid_token(self):
        """有效 token 返回用户 ID（int）"""
        token = create_access_token(7)
        assert decode_token(token) == 7

    def test_returns_none_for_garbage(self):
        """非法字符串返回 None"""
        assert decode_token("not-a-token") is None

    def test_returns_none_for_tampered_token(self):
        """被篡改的 token 返回 None"""
        token = create_access_token(1)
        tampered = token[:-2] + "xx"
        assert decode_token(tampered) is None

    def test_returns_none_for_expired_token(self):
        """过期 token 返回 None"""
        import datetime
        expired_payload = {"sub": "1", "exp": datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)}
        expired_token = jwt.encode(expired_payload, SECRET_KEY, algorithm=ALGORITHM)
        assert decode_token(expired_token) is None

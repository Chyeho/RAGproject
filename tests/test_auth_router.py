# -*- coding: utf-8 -*-
"""认证路由（/api/auth）单元测试：TestClient + mock 数据库会话"""
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.security import hash_password, create_access_token
from app.database.db import get_session
from app.dependencies import get_current_user
from app.models.users import User
from app.routers import auth


def _make_test_app():
    """独立的 FastAPI 实例（不触发 main.py 的 lifespan 建表）"""
    app = FastAPI()
    app.include_router(auth.router)
    return app


def _override_get_session(session):
    async def _dep():
        yield session

    return _dep


def _override_current_user(user):
    async def _dep():
        return user

    return _dep


def _mock_session(first_result=None):
    """AsyncMock 会话：session.exec().first() 返回 first_result"""
    session = AsyncMock()
    result = MagicMock()
    result.first.return_value = first_result
    session.exec.return_value = result
    # session.add 是同步方法（AsyncMock 默认返回协程，会触发未 await 警告）
    session.add = MagicMock()
    return session


def _user(phone="13800138000", password="123456", user_id=1):
    return User(
        id=user_id,
        phone=phone,
        password_hash=hash_password(password),
        full_name=phone,
        avatar="",
    )


@pytest.fixture
def client():
    return TestClient(_make_test_app())


class TestRegister:
    """注册接口"""

    def test_register_success(self, client):
        session = _mock_session(first_result=None)
        client.app.dependency_overrides[get_session] = _override_get_session(session)

        resp = client.post("/api/auth/register", json={
            "phone": "13900001111",
            "smsCode": "123456",
            "password": "123456",
            "confirmPassword": "123456",
        })
        assert resp.status_code == 200
        assert resp.json()["code"] == 0
        session.commit.assert_awaited_once()

    def test_register_wrong_sms_code(self, client):
        resp = client.post("/api/auth/register", json={
            "phone": "13900001111",
            "smsCode": "000000",
            "password": "123456",
            "confirmPassword": "123456",
        })
        assert resp.json()["code"] == 2002

    def test_register_password_mismatch(self, client):
        resp = client.post("/api/auth/register", json={
            "phone": "13900001111",
            "smsCode": "123456",
            "password": "123456",
            "confirmPassword": "654321",
        })
        assert resp.json()["code"] == 1001

    def test_register_password_too_short(self, client):
        resp = client.post("/api/auth/register", json={
            "phone": "13900001111",
            "smsCode": "123456",
            "password": "123",
            "confirmPassword": "123",
        })
        assert resp.json()["code"] == 1001

    def test_register_phone_exists(self, client):
        session = _mock_session(first_result=_user())
        client.app.dependency_overrides[get_session] = _override_get_session(session)

        resp = client.post("/api/auth/register", json={
            "phone": "13800138000",
            "smsCode": "123456",
            "password": "123456",
            "confirmPassword": "123456",
        })
        assert resp.json()["code"] == 2003


class TestLogin:
    """登录接口"""

    def test_login_success(self, client):
        user = _user()
        session = _mock_session(first_result=user)
        client.app.dependency_overrides[get_session] = _override_get_session(session)

        resp = client.post("/api/auth/login", json={
            "phone": "13800138000",
            "password": "123456",
            "remember": True,
        })
        body = resp.json()
        assert body["code"] == 0
        assert body["data"]["user"]["phone"] == "13800138000"
        # token 可解析出用户 ID
        from app.core.security import decode_token
        assert decode_token(body["data"]["token"]) == user.id

    def test_login_wrong_password(self, client):
        user = _user()
        session = _mock_session(first_result=user)
        client.app.dependency_overrides[get_session] = _override_get_session(session)

        resp = client.post("/api/auth/login", json={
            "phone": "13800138000",
            "password": "wrong-pass",
            "remember": True,
        })
        assert resp.json()["code"] == 2001

    def test_login_user_not_found(self, client):
        session = _mock_session(first_result=None)
        client.app.dependency_overrides[get_session] = _override_get_session(session)

        resp = client.post("/api/auth/login", json={
            "phone": "13900009999",
            "password": "123456",
            "remember": True,
        })
        assert resp.json()["code"] == 2001


class TestSmsCode:
    """验证码接口"""

    def test_send_sms_code_success(self, client):
        resp = client.post("/api/auth/sms-code", json={"phone": "13800138000", "scene": "register"})
        assert resp.json()["code"] == 0

    def test_invalid_scene(self, client):
        resp = client.post("/api/auth/sms-code", json={"phone": "13800138000", "scene": "other"})
        assert resp.json()["code"] == 1001


class TestMe:
    """当前用户信息接口"""

    def test_returns_current_user(self, client):
        user = _user()
        client.app.dependency_overrides[get_current_user] = _override_current_user(user)

        resp = client.get("/api/auth/me")
        body = resp.json()
        assert body["code"] == 0
        assert body["data"]["phone"] == "13800138000"

    def test_unauthorized_without_token(self, client):
        resp = client.get("/api/auth/me")
        assert resp.status_code == 401


class TestUpdateProfile:
    """修改个人信息接口"""

    def test_update_nickname(self, client):
        user = _user()
        client.app.dependency_overrides[get_current_user] = _override_current_user(user)
        session = _mock_session()
        client.app.dependency_overrides[get_session] = _override_get_session(session)

        resp = client.put("/api/auth/profile", json={"nickname": "宸甄管理员"})
        body = resp.json()
        assert body["code"] == 0
        assert body["data"]["nickname"] == "宸甄管理员"


class TestUpdatePassword:
    """修改密码接口"""

    def test_change_password_success(self, client):
        user = _user(password="old123")
        client.app.dependency_overrides[get_current_user] = _override_current_user(user)
        session = _mock_session()
        client.app.dependency_overrides[get_session] = _override_get_session(session)

        resp = client.put("/api/auth/password", json={
            "oldPassword": "old123",
            "newPassword": "new123",
            "confirmPassword": "new123",
        })
        assert resp.json()["code"] == 0
        # 新密码哈希已生效
        from app.core.security import verify_password
        assert verify_password("new123", user.password_hash)

    def test_wrong_old_password(self, client):
        user = _user(password="old123")
        client.app.dependency_overrides[get_current_user] = _override_current_user(user)
        session = _mock_session()
        client.app.dependency_overrides[get_session] = _override_get_session(session)

        resp = client.put("/api/auth/password", json={
            "oldPassword": "wrong",
            "newPassword": "new123",
            "confirmPassword": "new123",
        })
        assert resp.json()["code"] == 2001


class TestLogout:
    """退出登录接口"""

    def test_logout_returns_ok(self, client):
        resp = client.post("/api/auth/logout")
        assert resp.json()["code"] == 0

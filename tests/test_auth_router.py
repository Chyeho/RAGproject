# -*- coding: utf-8 -*-
"""认证路由（/api/auth）单元测试：TestClient + mock 数据库会话

覆盖账号管理重构后的行为：账号+密码登录、禁用/锁定、当前用户权限、改密。
注册/验证码/个人信息接口已下线，不再测试。
"""
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.security import decode_token, hash_password, verify_password
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
    session.add = MagicMock()
    return session


def _user(username="czzsk000002", password="oldPass123", user_id=2, **kwargs):
    return User(
        id=user_id,
        username=username,
        password_hash=hash_password(password),
        role=kwargs.pop("role", "user"),
        level=kwargs.pop("level", 1),
        status=kwargs.pop("status", "active"),
        **kwargs,
    )


@pytest.fixture
def client():
    return TestClient(_make_test_app())


class TestLogin:
    """登录接口"""

    def test_login_success(self, client):
        user = _user()
        session = _mock_session(first_result=user)
        client.app.dependency_overrides[get_session] = _override_get_session(session)

        resp = client.post("/api/auth/login", json={
            "username": "czzsk000002",
            "password": "oldPass123",
            "remember": True,
        })
        body = resp.json()
        assert body["code"] == 0
        assert body["data"]["user"]["username"] == "czzsk000002"
        assert body["data"]["user"]["permissions"]["knowledgeWrite"] is False
        assert body["data"]["user"]["permissions"]["accountManage"] is False
        assert decode_token(body["data"]["token"]) == user.id

    def test_admin_login_permissions_all_true(self, client):
        user = _user(username="admin", role="admin", level=None, user_id=1)
        session = _mock_session(first_result=user)
        client.app.dependency_overrides[get_session] = _override_get_session(session)

        body = client.post("/api/auth/login", json={
            "username": "admin", "password": "oldPass123", "remember": False,
        }).json()
        assert body["code"] == 0
        assert body["data"]["user"]["level"] is None
        assert all(body["data"]["user"]["permissions"].values())

    def test_login_wrong_password(self, client):
        session = _mock_session(first_result=_user())
        client.app.dependency_overrides[get_session] = _override_get_session(session)

        resp = client.post("/api/auth/login", json={
            "username": "czzsk000002",
            "password": "wrong-pass",
            "remember": True,
        })
        assert resp.json()["code"] == 2001

    def test_login_user_not_found(self, client):
        session = _mock_session(first_result=None)
        client.app.dependency_overrides[get_session] = _override_get_session(session)

        resp = client.post("/api/auth/login", json={
            "username": "czzsk999999",
            "password": "oldPass123",
            "remember": True,
        })
        assert resp.json()["code"] == 2001

    def test_login_disabled_user_rejected(self, client):
        session = _mock_session(first_result=_user(status="disabled"))
        client.app.dependency_overrides[get_session] = _override_get_session(session)

        resp = client.post("/api/auth/login", json={
            "username": "czzsk000002",
            "password": "oldPass123",
            "remember": True,
        })
        assert resp.json()["code"] == 2001

    def test_login_locked_user_returns_2005(self, client):
        user = _user(locked_until=datetime.now() + timedelta(minutes=5))
        session = _mock_session(first_result=user)
        client.app.dependency_overrides[get_session] = _override_get_session(session)

        resp = client.post("/api/auth/login", json={
            "username": "czzsk000002",
            "password": "oldPass123",
            "remember": True,
        })
        assert resp.json()["code"] == 2005

    def test_login_empty_account(self, client):
        resp = client.post("/api/auth/login", json={
            "username": "", "password": "oldPass123", "remember": True,
        })
        assert resp.json()["code"] == 1001


class TestMe:
    """当前用户信息接口"""

    def test_returns_current_user(self, client):
        user = _user()
        client.app.dependency_overrides[get_current_user] = _override_current_user(user)

        body = client.get("/api/auth/me").json()
        assert body["code"] == 0
        assert body["data"]["username"] == "czzsk000002"
        assert body["data"]["permissions"]["chat"] is True

    def test_unauthorized_without_token(self, client):
        resp = client.get("/api/auth/me")
        assert resp.status_code == 401
        assert resp.json()["detail"]["code"] == 3001


class TestChangePassword:
    """修改密码接口"""

    def test_change_password_success(self, client):
        user = _user(password="oldPass123")
        user.must_change_password = True
        client.app.dependency_overrides[get_current_user] = _override_current_user(user)
        session = _mock_session()
        client.app.dependency_overrides[get_session] = _override_get_session(session)

        resp = client.post("/api/auth/change-password", json={
            "oldPassword": "oldPass123",
            "newPassword": "newPass456",
            "confirmPassword": "newPass456",
        })
        assert resp.json()["code"] == 0
        assert verify_password("newPass456", user.password_hash)
        assert user.must_change_password is False

    def test_wrong_old_password(self, client):
        user = _user(password="oldPass123")
        client.app.dependency_overrides[get_current_user] = _override_current_user(user)
        client.app.dependency_overrides[get_session] = _override_get_session(_mock_session())

        resp = client.post("/api/auth/change-password", json={
            "oldPassword": "wrongPass1",
            "newPassword": "newPass456",
            "confirmPassword": "newPass456",
        })
        assert resp.json()["code"] == 2001

    def test_password_mismatch(self, client):
        user = _user(password="oldPass123")
        client.app.dependency_overrides[get_current_user] = _override_current_user(user)

        resp = client.post("/api/auth/change-password", json={
            "oldPassword": "oldPass123",
            "newPassword": "newPass456",
            "confirmPassword": "newPass789",
        })
        assert resp.json()["code"] == 1001

    def test_password_too_weak(self, client):
        user = _user(password="oldPass123")
        client.app.dependency_overrides[get_current_user] = _override_current_user(user)

        resp = client.post("/api/auth/change-password", json={
            "oldPassword": "oldPass123",
            "newPassword": "short",
            "confirmPassword": "short",
        })
        assert resp.json()["code"] == 1001


class TestLogout:
    """退出登录接口"""

    def test_logout_returns_ok(self, client):
        resp = client.post("/api/auth/logout")
        assert resp.json()["code"] == 0

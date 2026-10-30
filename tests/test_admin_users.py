# -*- coding: utf-8 -*-
"""账号管理接口（/api/admin）与账号服务单元测试"""
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database.db import get_session
from app.dependencies import get_current_user
from app.models.users import User
from app.routers import admin
from app.service.account_service import create_user_account


def _user(user_id=1, role="admin", level=None, username="admin"):
    return User(id=user_id, username=username, password_hash="hash", role=role, level=level)


def _app_with(user):
    app = FastAPI()
    app.include_router(admin.router)

    async def _dep():
        return user

    app.dependency_overrides[get_current_user] = _dep
    return app


def _session_with_get(target):
    session = AsyncMock()
    session.get.return_value = target

    async def _dep():
        yield session

    return session, _dep


class TestAdminPermission:
    def test_l1_cannot_list_users(self):
        """普通 L1 调用账号管理接口 → 403 / 3002"""
        app = _app_with(_user(user_id=2, role="user", level=1, username="czzsk000002"))
        resp = TestClient(app).get("/api/admin/users")
        assert resp.status_code == 403
        assert resp.json()["detail"]["code"] == 3002


class TestAdminOperations:
    def test_target_not_found(self):
        """目标账号不存在 → 4004"""
        app = _app_with(_user())
        _, dep = _session_with_get(None)
        app.dependency_overrides[get_session] = dep
        body = TestClient(app).delete("/api/admin/users/999").json()
        assert body["code"] == 4004

    def test_cannot_operate_self(self):
        """操作自己的账号 → 4005"""
        me = _user(user_id=1)
        app = _app_with(me)
        _, dep = _session_with_get(me)
        app.dependency_overrides[get_session] = dep
        body = TestClient(app).delete("/api/admin/users/1").json()
        assert body["code"] == 4005

    def test_cannot_operate_builtin_admin(self):
        """目标是内置管理员 → 4005"""
        me = _user(user_id=1)
        target = _user(user_id=3, username="admin2")
        app = _app_with(me)
        _, dep = _session_with_get(target)
        app.dependency_overrides[get_session] = dep
        body = TestClient(app).delete("/api/admin/users/3").json()
        assert body["code"] == 4005


class _FakeSession:
    """最小异步会话：add 时模拟自增 ID"""

    def __init__(self, next_id=7):
        self.next_id = next_id
        self.added = []

    def add(self, obj):
        self.added.append(obj)
        if getattr(obj, "id", None) is None:
            obj.id = self.next_id

    async def flush(self):
        pass

    async def commit(self):
        pass

    async def refresh(self, obj):
        pass


class TestCreateUserAccount:
    @pytest.mark.anyio
    async def test_account_name_and_password(self):
        """账号名 = czzsk + 6 位补零 ID；初始密码随机 16 位；必须改密"""
        session = _FakeSession(next_id=7)
        user, password = await create_user_account(session, _user())

        assert user.username == "czzsk000007"
        assert user.role == "user"
        assert user.level == 1
        assert user.status == "active"
        assert user.must_change_password is True
        assert len(password) == 16
        assert any(c.isupper() for c in password)
        assert any(c.islower() for c in password)
        assert any(c.isdigit() for c in password)

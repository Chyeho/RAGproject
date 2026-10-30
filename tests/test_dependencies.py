# -*- coding: utf-8 -*-
"""公共依赖（get_current_user / require_permission）单元测试"""
from datetime import datetime
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.core.permissions import KNOWLEDGE_WRITE
from app.core.security import create_access_token
from app.dependencies import get_current_user, require_permission
from app.models.users import User


def _make_user(user_id=1, **kwargs):
    """构造一个测试用户（默认 active 普通账号 L1）"""
    return User(
        id=user_id,
        username=kwargs.pop("username", "czzsk000002"),
        password_hash="hash",
        role=kwargs.pop("role", "user"),
        level=kwargs.pop("level", 1),
        status=kwargs.pop("status", "active"),
        **kwargs,
    )


async def _call_current_user(creds, user):
    session = AsyncMock()
    session.get.return_value = user
    return await get_current_user(creds, session)


def _creds(token):
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


class TestGetCurrentUser:
    """测试 get_current_user"""

    @pytest.mark.anyio
    async def test_missing_credentials_raises_401(self):
        """未携带凭证 → 401"""
        with pytest.raises(HTTPException) as exc:
            await get_current_user(None, AsyncMock())
        assert exc.value.status_code == 401
        assert exc.value.detail["code"] == 3001

    @pytest.mark.anyio
    async def test_invalid_token_raises_401(self):
        """无效 token → 401"""
        with pytest.raises(HTTPException) as exc:
            await get_current_user(_creds("garbage-token"), AsyncMock())
        assert exc.value.status_code == 401

    @pytest.mark.anyio
    async def test_returns_user_for_valid_token(self):
        """有效 token 且用户存在 → 返回用户"""
        user = _make_user()
        result = await _call_current_user(_creds(create_access_token(user.id)), user)
        assert result is user

    @pytest.mark.anyio
    async def test_user_not_found_raises_401(self):
        """token 有效但用户已被删除 → 401"""
        with pytest.raises(HTTPException) as exc:
            await _call_current_user(_creds(create_access_token(999)), None)
        assert exc.value.status_code == 401

    @pytest.mark.anyio
    async def test_disabled_user_raises_401(self):
        """禁用账号的存量 token 立即失效 → 401 / 3001"""
        user = _make_user(status="disabled")
        with pytest.raises(HTTPException) as exc:
            await _call_current_user(_creds(create_access_token(user.id)), user)
        assert exc.value.status_code == 401
        assert exc.value.detail["code"] == 3001

    @pytest.mark.anyio
    async def test_soft_deleted_user_raises_401(self):
        """软删账号 → 401 / 3001"""
        user = _make_user(deleted_at=datetime.now())
        with pytest.raises(HTTPException) as exc:
            await _call_current_user(_creds(create_access_token(user.id)), user)
        assert exc.value.status_code == 401


class TestRequirePermission:
    """测试权限依赖工厂"""

    @pytest.mark.anyio
    async def test_l1_denied_knowledge_write(self):
        """L1 无 knowledge:write → 403 / 3002"""
        checker = require_permission(KNOWLEDGE_WRITE)
        with pytest.raises(HTTPException) as exc:
            await checker(_make_user(level=1))
        assert exc.value.status_code == 403
        assert exc.value.detail["code"] == 3002

    @pytest.mark.anyio
    async def test_l2_allowed_knowledge_write(self):
        """L2 拥有 knowledge:write → 返回用户"""
        checker = require_permission(KNOWLEDGE_WRITE)
        user = _make_user(level=2)
        assert await checker(user) is user

    @pytest.mark.anyio
    async def test_admin_allowed(self):
        """管理员拥有全部权限"""
        checker = require_permission(KNOWLEDGE_WRITE)
        user = _make_user(role="admin", level=None)
        assert await checker(user) is user

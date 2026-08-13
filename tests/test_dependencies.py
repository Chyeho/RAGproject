# -*- coding: utf-8 -*-
"""公共依赖（get_current_user 认证鉴权）单元测试"""
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.core.security import create_access_token
from app.dependencies import get_current_user
from app.models.users import User


def _make_user(user_id=1, phone="13800138000"):
    """构造一个测试用户"""
    return User(id=user_id, phone=phone, password_hash="hash", full_name="测试用户")


class TestGetCurrentUser:
    """测试 get_current_user"""

    @pytest.mark.anyio
    async def test_missing_credentials_raises_401(self):
        """未携带凭证 → 401"""
        with pytest.raises(HTTPException) as exc:
            await get_current_user(None, AsyncMock())
        assert exc.value.status_code == 401

    @pytest.mark.anyio
    async def test_invalid_token_raises_401(self):
        """无效 token → 401"""
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="garbage-token")
        with pytest.raises(HTTPException) as exc:
            await get_current_user(creds, AsyncMock())
        assert exc.value.status_code == 401

    @pytest.mark.anyio
    async def test_returns_user_for_valid_token(self):
        """有效 token 且用户存在 → 返回用户"""
        user = _make_user()
        token = create_access_token(user.id)
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        session = AsyncMock()
        session.get.return_value = user

        result = await get_current_user(creds, session)
        assert result is user
        session.get.assert_called_once_with(User, user.id)

    @pytest.mark.anyio
    async def test_user_not_found_raises_401(self):
        """token 有效但用户已被删除 → 401"""
        token = create_access_token(999)
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        session = AsyncMock()
        session.get.return_value = None

        with pytest.raises(HTTPException) as exc:
            await get_current_user(creds, session)
        assert exc.value.status_code == 401

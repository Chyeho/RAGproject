'''公共依赖：认证鉴权

- get_current_user：解析 Bearer token，校验账号存在且未被禁用/软删
- require_permission(perm)：在登录基础上校验权限（集中鉴权，业务代码不散落判断）
'''
from typing import Optional

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.permissions import ACCOUNT_MANAGE, has_permission
from app.core.security import decode_token
from app.database.db import get_session
from app.models.users import User

security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    session: AsyncSession = Depends(get_session),
) -> User:
    """解析 Bearer token 并返回当前登录用户；未携带/失效抛 401"""
    if credentials is None:
        raise HTTPException(status_code=401, detail={"code": 3001, "message": "未登录，请先登录"})

    user_id = decode_token(credentials.credentials)
    if user_id is None:
        raise HTTPException(status_code=401, detail={"code": 3001, "message": "登录已过期，请重新登录"})

    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail={"code": 3001, "message": "用户不存在"})

    # 禁用/软删账号：复用登录失效处理，前端清除本地登录态
    if user.status != "active" or user.deleted_at is not None:
        raise HTTPException(status_code=401, detail={"code": 3001, "message": "账号已被禁用，请重新登录"})

    return user


def require_permission(permission: str):
    """依赖工厂：要求当前用户拥有指定权限，否则 403 / code=3002"""

    async def _checker(current_user: User = Depends(get_current_user)) -> User:
        if not has_permission(current_user, permission):
            raise HTTPException(status_code=403, detail={"code": 3002, "message": "无权限执行该操作"})
        return current_user

    return _checker


# 账号管理接口统一依赖
require_admin = require_permission(ACCOUNT_MANAGE)

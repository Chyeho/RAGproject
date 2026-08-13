'''公共依赖：认证鉴权'''
from typing import Optional

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel.ext.asyncio.session import AsyncSession

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

    return user

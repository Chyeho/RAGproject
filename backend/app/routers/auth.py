'''认证路由：登录 / 修改密码 / 当前用户信息

- 已删除注册、短信验证码、昵称头像相关接口（账号由管理员在账号管理中创建）
- 登录失败次数限制与账号锁定：failed_attempts / locked_until
- 禁用、软删账号与密码错误统一返回 2001，不泄露账号是否存在
'''
import os
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.permissions import permissions_for
from app.core.response import err, ok
from app.core.security import create_access_token, hash_password, validate_password_strength, verify_password
from app.database.db import get_session
from app.dependencies import get_current_user
from app.models.users import User
from app.service.account_service import user_to_dict
from app.utils.logger_handler import logger

router = APIRouter(prefix="/api/auth", tags=["auth"])

# 登录安全配置（环境变量可覆盖）
LOGIN_MAX_FAILURES = int(os.getenv("LOGIN_MAX_FAILURES", "5"))
LOGIN_LOCK_MINUTES = int(os.getenv("LOGIN_LOCK_MINUTES", "15"))


class LoginReq(BaseModel):
    username: Optional[str] = Field(default=None, description="登录账号")
    phone: Optional[str] = Field(default=None, description="历史字段：手机号（兼容旧调用方）")
    password: str = Field(description="密码")
    remember: bool = True


class PasswordReq(BaseModel):
    oldPassword: str = Field(description="原密码")
    newPassword: str = Field(description="新密码")
    confirmPassword: str = Field(description="确认新密码")


def _auth_payload(user: User, token: str) -> dict:
    """登录成功返回体：token + 用户对象 + 权限"""
    return {
        "token": token,
        "user": {**user_to_dict(user), "permissions": permissions_for(user)},
    }


@router.post("/login")
async def login(req: LoginReq, session: AsyncSession = Depends(get_session)):
    """登录：账号 + 密码 → JWT；含失败次数限制与账号禁用校验"""
    account = (req.username or req.phone or "").strip()
    if not account or not req.password:
        return err(1001, "请输入账号和密码")

    user = (await session.exec(select(User).where(User.username == account))).first()
    if user is None:
        # 兼容历史账号（迁移前 username 为空，用手机号登录）
        user = (await session.exec(select(User).where(User.phone == account))).first()

    # 不存在 / 已禁用 / 已软删：统一提示，不泄露账号是否存在
    if user is None or user.status != "active" or user.deleted_at is not None:
        logger.warning(f"[认证]账号{account}登录失败")
        return err(2001, "账号或密码错误")

    now = datetime.now()
    if user.locked_until and user.locked_until > now:
        logger.warning(f"[认证]账号{account}登录失败：账号处于锁定期")
        return err(2005, "登录失败次数过多，请稍后再试")

    if not verify_password(req.password, user.password_hash):
        user.failed_attempts = (user.failed_attempts or 0) + 1
        if user.failed_attempts >= LOGIN_MAX_FAILURES:
            user.locked_until = now + timedelta(minutes=LOGIN_LOCK_MINUTES)
            user.failed_attempts = 0
            logger.warning(f"[认证]账号{account}连续登录失败，已锁定 {LOGIN_LOCK_MINUTES} 分钟")
        session.add(user)
        await session.commit()
        logger.warning(f"[认证]账号{account}登录失败：账号或密码错误")
        return err(2001, "账号或密码错误")

    # 登录成功：清空失败计数与锁定状态，更新最后登录时间
    user.failed_attempts = 0
    user.locked_until = None
    user.last_login = now
    session.add(user)
    await session.commit()
    await session.refresh(user)

    token = create_access_token(user.id, remember=req.remember)
    logger.info(f"[认证]账号{user.username}登录成功")
    return ok(_auth_payload(user, token))


@router.post("/logout")
async def logout():
    """退出登录（JWT 无状态，前端清除本地 token 即可）"""
    return ok(None, "已退出登录")


@router.get("/me")
async def get_me(current_user: User = Depends(get_current_user)):
    """获取当前登录用户信息与权限"""
    return ok({**user_to_dict(current_user), "permissions": permissions_for(current_user)})


@router.post("/change-password")
async def change_password(
    req: PasswordReq,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """修改自己的密码：校验原密码 + 新密码强度"""
    if req.newPassword != req.confirmPassword:
        return err(1001, "两次输入的新密码不一致")

    strength_error = validate_password_strength(req.newPassword)
    if strength_error:
        return err(1001, strength_error)

    if not verify_password(req.oldPassword, current_user.password_hash):
        logger.warning(f"[认证]用户{current_user.id}修改密码失败：原密码错误")
        return err(2001, "原密码错误")

    current_user.password_hash = hash_password(req.newPassword)
    current_user.must_change_password = False
    session.add(current_user)
    await session.commit()
    logger.info(f"[认证]用户{current_user.id}修改密码成功")
    return ok(None, "密码修改成功")

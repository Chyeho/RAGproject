'''认证路由：登录/注册/验证码/退出/个人信息/修改密码'''
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.response import err, ok
from app.core.security import create_access_token, hash_password, verify_password
from app.database.db import get_session
from app.dependencies import get_current_user
from app.models.users import User
from app.utils.logger_handler import logger

router = APIRouter(prefix="/api/auth", tags=["auth"])

# 开发环境固定验证码
DEV_SMS_CODE = "123456"


class LoginReq(BaseModel):
    phone: str = Field(description="手机号")
    password: str = Field(description="密码")
    remember: bool = True


class RegisterReq(BaseModel):
    phone: str = Field(description="手机号")
    smsCode: str = Field(description="短信验证码")
    password: str = Field(description="密码")
    confirmPassword: str = Field(description="确认密码")


class SmsCodeReq(BaseModel):
    phone: str = Field(description="手机号")
    scene: str = Field(description="场景：register | login")


class ProfileReq(BaseModel):
    nickname: Optional[str] = Field(default=None, description="昵称")
    avatar: Optional[str] = Field(default=None, description="头像（URL 或 base64）")


class PasswordReq(BaseModel):
    oldPassword: str = Field(description="原密码")
    newPassword: str = Field(description="新密码")
    confirmPassword: str = Field(description="确认新密码")


def user_to_dict(user: User) -> dict:
    """User 模型 → 契约 user 对象"""
    return {
        "id": user.id,
        "phone": user.phone,
        "nickname": user.full_name or "",
        "avatar": user.avatar or "",
        "createdAt": user.created_at.strftime("%Y-%m-%d %H:%M:%S") if user.created_at else "",
    }


@router.post("/login")
async def login(req: LoginReq, session: AsyncSession = Depends(get_session)):
    """登录：查表验证手机号+密码，签发 JWT"""
    user = (await session.exec(select(User).where(User.phone == req.phone))).first()
    if not user or not verify_password(req.password, user.password_hash):
        logger.warning(f"[认证]手机号{req.phone}登录失败：账号或密码错误")
        return err(2001, "手机号或密码错误")

    # 更新最后登录时间
    user.last_login = datetime.now()
    session.add(user)
    await session.commit()

    token = create_access_token(user.id, remember=req.remember)
    logger.info(f"[认证]手机号{req.phone}登录成功")
    return ok({"token": token, "user": user_to_dict(user)})


@router.post("/register")
async def register(req: RegisterReq, session: AsyncSession = Depends(get_session)):
    """注册：校验验证码与两次密码，手机号查重，bcrypt 存储密码"""
    if req.smsCode != DEV_SMS_CODE:
        logger.warning(f"[认证]手机号{req.phone}注册失败：验证码错误")
        return err(2002, "验证码错误")
    if req.password != req.confirmPassword:
        return err(1001, "两次输入的密码不一致")
    if len(req.password) < 6:
        return err(1001, "密码长度不能少于 6 位")

    exist = (await session.exec(select(User).where(User.phone == req.phone))).first()
    if exist:
        logger.warning(f"[认证]手机号{req.phone}注册失败：已注册")
        return err(2003, "手机号已注册")

    user = User(
        phone=req.phone,
        password_hash=hash_password(req.password),
        full_name=req.phone,  # 默认昵称取手机号，可在个人设置中修改
    )
    session.add(user)
    await session.commit()
    logger.info(f"[认证]手机号{req.phone}注册成功")
    return ok(None, "注册成功")


@router.post("/sms-code")
async def send_sms_code(req: SmsCodeReq):
    """发送短信验证码（开发环境固定 123456，仅记录日志）"""
    if req.scene not in ("register", "login"):
        return err(1001, "scene 取值非法")
    logger.info(f"[认证]手机号{req.phone} 场景{req.scene} 发送验证码（开发环境固定 {DEV_SMS_CODE}）")
    return ok(None, "验证码已发送（开发环境固定 123456）")


@router.post("/logout")
async def logout():
    """退出登录（JWT 无状态，前端清除本地 token 即可）"""
    return ok(None, "已退出登录")


@router.get("/me")
async def get_me(current_user: User = Depends(get_current_user)):
    """获取当前登录用户信息"""
    return ok(user_to_dict(current_user))


@router.put("/profile")
async def update_profile(
    req: ProfileReq,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """修改个人信息（昵称/头像）"""
    if req.nickname is not None:
        current_user.full_name = req.nickname
    if req.avatar is not None:
        current_user.avatar = req.avatar
    session.add(current_user)
    await session.commit()
    await session.refresh(current_user)
    logger.info(f"[认证]用户{current_user.id}更新个人信息")
    return ok(user_to_dict(current_user))


@router.put("/password")
async def update_password(
    req: PasswordReq,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """修改密码：校验原密码，新密码 bcrypt 重哈希"""
    if req.newPassword != req.confirmPassword:
        return err(1001, "两次输入的新密码不一致")
    if len(req.newPassword) < 6:
        return err(1001, "新密码长度不能少于 6 位")
    if not verify_password(req.oldPassword, current_user.password_hash):
        logger.warning(f"[认证]用户{current_user.id}修改密码失败：原密码错误")
        return err(2001, "原密码错误")

    current_user.password_hash = hash_password(req.newPassword)
    session.add(current_user)
    await session.commit()
    logger.info(f"[认证]用户{current_user.id}修改密码成功")
    return ok(None, "密码修改成功")

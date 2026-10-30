'''账号服务：管理员初始化、建号取号、密码重置、审计写入'''
import os
import uuid
from datetime import datetime
from typing import Optional

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.security import generate_password, hash_password
from app.models.audit_log import AuditLog
from app.models.users import User
from app.utils.logger_handler import logger

# 账号名前缀与自增 id 位数上限
ACCOUNT_PREFIX = "czzsk"
ACCOUNT_ID_WIDTH = 6
ACCOUNT_ID_MAX = 10 ** ACCOUNT_ID_WIDTH - 1

# 管理员最多支持 3 个（环境变量 ADMIN1_* / ADMIN2_* / ADMIN3_*）
ADMIN_SLOT_RANGE = (1, 2, 3)


def user_to_dict(user: User) -> dict:
    """User 模型 → 契约 user 对象（不含手机号/昵称/头像）"""
    return {
        "id": user.id,
        "username": user.username or "",
        "role": user.role,
        "level": None if user.role == "admin" else user.level,
        "status": user.status,
        "mustChangePassword": bool(user.must_change_password),
        "createdAt": user.created_at.strftime("%Y-%m-%d %H:%M:%S") if user.created_at else "",
        "lastLoginAt": user.last_login.strftime("%Y-%m-%d %H:%M:%S") if user.last_login else "",
    }


def add_audit(
    session: AsyncSession,
    actor_id: Optional[int],
    action: str,
    target_id: Optional[int] = None,
    detail: Optional[str] = None,
) -> None:
    """写入管理员操作审计（由调用方统一 commit；detail 禁止包含明文密码）"""
    session.add(AuditLog(
        actor_id=actor_id,
        action=action,
        target_id=target_id,
        detail=(detail or "")[:500] or None,
        created_at=datetime.now(),
    ))


async def seed_admins(session: AsyncSession) -> None:
    """按环境变量创建内置管理员（已存在不覆盖密码，绝不打印密码）"""
    for slot in ADMIN_SLOT_RANGE:
        username = (os.getenv(f"ADMIN{slot}_USERNAME") or "").strip()
        password = os.getenv(f"ADMIN{slot}_PASSWORD") or ""
        if not username or not password:
            continue

        existing = (await session.exec(select(User).where(User.username == username))).first()
        if existing:
            if existing.role == "admin":
                logger.info(
                    f"[账号]管理员 {username} 已存在，跳过初始化"
                    f"（不覆盖现有密码，env 中的 ADMIN{slot}_PASSWORD 仅首次建号生效；"
                    f"如需改密请执行 python -m app.cli.reset_password --username {username}）"
                )
            else:
                logger.error(f"[账号]配置的管理员账号 {username} 已存在且不是管理员，请人工处理（不会自动提权）")
            continue

        if len(password) < 12:
            logger.warning(f"[账号]管理员 {username} 的初始密码强度偏低（建议 12 位以上）")

        user = User(
            username=username,
            password_hash=hash_password(password),
            role="admin",
            level=None,
            status="active",
            must_change_password=False,
            created_at=datetime.now(),
        )
        session.add(user)
        await session.commit()
        logger.info(f"[账号]已创建内置管理员 {username}（id={user.id}）")


async def create_user_account(session: AsyncSession, actor: User) -> tuple[User, str]:
    """新建普通账号：同一事务内先插入拿自增 id，再用 id 生成账号名

    Returns: (user, 初始密码明文) —— 明文仅调用方返回前端一次，不落库不写日志
    """
    password = generate_password()
    user = User(
        phone=None,
        # 临时唯一账号名，flush 拿到 id 后立即替换为正式账号名
        username=f"tmp_{uuid.uuid4().hex[:16]}",
        password_hash=hash_password(password),
        role="user",
        level=1,
        status="active",
        must_change_password=True,
        created_by=actor.id,
        created_at=datetime.now(),
    )
    session.add(user)
    await session.flush()

    if not user.id or user.id > ACCOUNT_ID_MAX:
        await session.rollback()
        raise ValueError("账号名生成失败：自增 id 超出 6 位上限")

    user.username = f"{ACCOUNT_PREFIX}{user.id:0{ACCOUNT_ID_WIDTH}d}"
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user, password


async def reset_password(session: AsyncSession, target: User) -> str:
    """重置为随机临时密码（只返回一次，仅存哈希）"""
    password = generate_password()
    target.password_hash = hash_password(password)
    target.must_change_password = True
    target.failed_attempts = 0
    target.locked_until = None
    session.add(target)
    await session.commit()
    return password

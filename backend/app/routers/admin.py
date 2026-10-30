'''账号管理路由（仅管理员）：列表 / 新建 / 改等级或状态 / 重置密码 / 软删除'''
from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.response import err, ok
from app.database.db import get_session
from app.dependencies import require_admin
from app.models.users import User
from app.service.account_service import (
    add_audit,
    create_user_account,
    reset_password,
    user_to_dict,
)
from app.utils.logger_handler import logger

router = APIRouter(prefix="/api/admin", tags=["admin"])


class UserUpdateReq(BaseModel):
    """改等级 / 改状态（至少一项）"""
    level: Optional[Literal[1, 2, 3]] = Field(default=None, description="权限等级 1/2/3")
    status: Optional[Literal["active", "disabled"]] = Field(default=None, description="账号状态")


def admin_user_to_dict(user: User, created_by_name: str = "") -> dict:
    """账号管理列表项"""
    return {**user_to_dict(user), "createdBy": user.created_by, "createdByName": created_by_name}


async def _get_operable_user(session: AsyncSession, user_id: int, actor: User) -> tuple[User | None, dict | None]:
    """取目标账号并校验可操作性；返回 (user, error_response)"""
    target = await session.get(User, user_id)
    if target is None or target.deleted_at is not None:
        return None, err(4004, "账号不存在")
    if target.id == actor.id:
        return None, err(4005, "不能操作自己的账号")
    if target.role != "user":
        return None, err(4005, "内置管理员账号不允许该操作")
    return target, None


@router.get("/users")
async def list_users(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=10, ge=1, le=100),
    keyword: str = Query(default=""),
    level: Optional[int] = Query(default=None, ge=1, le=3),
    status: Optional[Literal["active", "disabled"]] = Query(default=None),
    current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """账号列表：分页 + 账号名模糊搜索 + 等级/状态筛选（不含软删账号）"""
    conditions = [User.deleted_at.is_(None)]
    if keyword:
        conditions.append(User.username.like(f"%{keyword}%"))
    if level is not None:
        conditions.append(User.level == level)
    if status is not None:
        conditions.append(User.status == status)

    count_stmt = select(func.count()).select_from(User).where(*conditions)
    list_stmt = (
        select(User)
        .where(*conditions)
        .order_by(User.id.asc())
        .offset((page - 1) * size)
        .limit(size)
    )
    total = (await session.exec(count_stmt)).one()
    rows = (await session.exec(list_stmt)).all()

    creator_ids = {u.created_by for u in rows if u.created_by}
    creators: dict[int, str] = {}
    if creator_ids:
        creator_rows = (await session.exec(select(User).where(User.id.in_(creator_ids)))).all()
        creators = {c.id: (c.username or "") for c in creator_rows}

    return ok({
        "list": [admin_user_to_dict(u, creators.get(u.created_by or 0, "")) for u in rows],
        "total": total,
        "page": page,
        "size": size,
    })


@router.post("/users")
async def create_user(
    current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """新建普通账号（level=1），返回初始密码一次"""
    try:
        user, initial_password = await create_user_account(session, current_user)
    except ValueError as e:
        logger.error(f"[账号]管理员{current_user.id}新建账号失败：{e}")
        return err(4006, str(e))

    add_audit(session, current_user.id, "create_user", user.id, f"新建账号 {user.username}")
    await session.commit()

    logger.info(f"[账号]管理员{current_user.id}新建账号 {user.username}（id={user.id}）")
    return ok({
        "id": user.id,
        "username": user.username,
        "initialPassword": initial_password,
    }, "账号创建成功，初始密码仅显示一次")


@router.patch("/users/{user_id}")
async def update_user(
    user_id: int,
    req: UserUpdateReq,
    current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """修改普通账号的等级 / 状态（立即生效）"""
    if req.level is None and req.status is None:
        return err(1001, "没有需要修改的字段")

    target, error = await _get_operable_user(session, user_id, current_user)
    if error:
        return error

    changes: list[str] = []
    if req.level is not None and req.level != target.level:
        changes.append(f"等级 {target.level}→{req.level}")
        target.level = req.level
    if req.status is not None and req.status != target.status:
        changes.append(f"状态 {target.status}→{req.status}")
        target.status = req.status
    if not changes:
        return ok(admin_user_to_dict(target), "无变更")

    session.add(target)
    action = "update_status" if req.status is not None else "update_level"
    add_audit(session, current_user.id, action, target.id, f"{target.username}：{'；'.join(changes)}")
    await session.commit()
    await session.refresh(target)

    logger.info(f"[账号]管理员{current_user.id}修改账号 {target.username}：{'；'.join(changes)}")
    return ok(admin_user_to_dict(target), "修改成功")


@router.post("/users/{user_id}/reset-password")
async def reset_user_password(
    user_id: int,
    current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """重置普通账号密码，返回临时密码一次"""
    target, error = await _get_operable_user(session, user_id, current_user)
    if error:
        return error

    add_audit(session, current_user.id, "reset_password", target.id, f"重置账号 {target.username} 密码")
    temp_password = await reset_password(session, target)

    logger.info(f"[账号]管理员{current_user.id}重置账号 {target.username} 密码")
    return ok({
        "username": target.username,
        "tempPassword": temp_password,
        "mustChangePassword": True,
    }, "密码已重置，临时密码仅显示一次")


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """软删除账号：置为禁用并记录 deleted_at（不物理删除）"""
    target, error = await _get_operable_user(session, user_id, current_user)
    if error:
        return error

    target.status = "disabled"
    target.deleted_at = datetime.now()
    session.add(target)
    add_audit(session, current_user.id, "delete_user", target.id, f"软删除账号 {target.username}")
    await session.commit()

    logger.info(f"[账号]管理员{current_user.id}软删除账号 {target.username}（id={target.id}）")
    return ok(None, "账号已删除（禁用），历史数据保留")

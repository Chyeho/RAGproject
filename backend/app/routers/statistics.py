'''统计路由：SQL 聚合查询 document 表'''
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.response import ok
from app.database.db import get_session
from app.dependencies import get_current_user
from app.models.documents import Document
from app.models.users import User

router = APIRouter(prefix="/api/statistics", tags=["statistics"])


@router.get("/overview")
async def overview(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """总览统计：文档总数/总大小/向量化成功数/失败数"""
    total = (await session.exec(select(func.count()).select_from(Document))).one()
    total_size = (await session.exec(select(func.coalesce(func.sum(Document.file_size), 0)))).one()
    success = (await session.exec(
        select(func.count()).select_from(Document).where(Document.vectorize_status == "success")
    )).one()
    failed = (await session.exec(
        select(func.count()).select_from(Document).where(Document.vectorize_status == "failed")
    )).one()
    return ok({
        "totalDocuments": total,
        "totalSize": total_size,
        "vectorizeSuccess": success,
        "vectorizeFailed": failed,
    })


@router.get("/file-type-distribution")
async def file_type_distribution(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """各文件类型文档数量占比"""
    rows = (await session.exec(
        select(Document.file_type, func.count()).group_by(Document.file_type)
    )).all()
    return ok({"list": [{"type": t, "count": c} for t, c in rows]})


@router.get("/daily-trend")
async def daily_trend(
    days: int = 30,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """近 N 天每日入库趋势"""
    start = datetime.now() - timedelta(days=max(1, days))
    rows = (await session.exec(
        select(func.date(Document.created_at), func.count())
        .where(Document.created_at >= start)
        .group_by(func.date(Document.created_at))
    )).all()
    return ok({"list": [
        {"date": d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d), "count": c}
        for d, c in rows
    ]})


@router.get("/vectorization-status")
async def vectorization_status(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """向量化成功/失败计数（环形图）"""
    success = (await session.exec(
        select(func.count()).select_from(Document).where(Document.vectorize_status == "success")
    )).one()
    failed = (await session.exec(
        select(func.count()).select_from(Document).where(Document.vectorize_status == "failed")
    )).one()
    return ok({"success": success, "failed": failed})

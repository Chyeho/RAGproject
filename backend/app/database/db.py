'''数据库引擎与会话管理'''
import os

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.utils.logger_handler import logger

# 数据库连接参数：环境变量提供，本地开发有默认值；docker 部署通过 compose 注入覆盖
DB_HOST     = os.getenv("MYSQL_HOST", "127.0.0.1")
DB_PORT     = os.getenv("MYSQL_PORT", "3306")
DB_USER     = os.getenv("MYSQL_USER", "privrag")
DB_PASSWORD = os.getenv("MYSQL_PASSWORD", "privrag_dev_123456")
DB_DATABASE = os.getenv("MYSQL_DATABASE", "privrag_dev")

DATABASE_URL = (
    f"mysql+aiomysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_DATABASE}"
    "?charset=utf8mb4"
)

# 异步引擎
async_engine = create_async_engine(DATABASE_URL, echo=False)

# 异步会话工厂
async_session = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)


async def get_session():
    """FastAPI 依赖：提供一个数据库会话"""
    async with async_session() as session:
        yield session


async def init_db() -> None:
    """初始化数据库表结构（幂等：已存在的表不会重建，新增表自动创建）"""
    # 导入全部模型以确保注册到 SQLModel.metadata
    from app.models import users, documents, document_chunk, chat_conversation, chat_message  # noqa: F401

    try:
        async with async_engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)
        logger.info("[数据库]表结构初始化完成")
    except Exception as e:
        logger.error(f"[数据库]表结构初始化失败，错误信息：{str(e)}", exc_info=True)
        raise

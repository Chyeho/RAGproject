# -*- coding: utf-8 -*-
"""数据库连接层（db.py）单元测试：连接串 / 会话 / 建表"""
from unittest.mock import patch, AsyncMock, MagicMock

import pytest

from app.database import db


class TestDatabaseUrl:
    """测试 DATABASE_URL 拼接"""

    def test_uses_aiomysql_driver(self):
        assert db.DATABASE_URL.startswith("mysql+aiomysql://")

    def test_contains_charset_param(self):
        assert "charset=utf8mb4" in db.DATABASE_URL

    def test_contains_defaults(self):
        """默认参数（环境变量缺省时）应出现在连接串中"""
        assert "privrag" in db.DATABASE_URL
        assert "privrag_dev" in db.DATABASE_URL
        assert "127.0.0.1" in db.DATABASE_URL

    def test_engine_is_async(self):
        """异步引擎"""
        assert db.async_engine.dialect.name == "mysql"


class TestGetSession:
    """测试 get_session 依赖"""

    @pytest.mark.anyio
    async def test_yields_session_from_factory(self):
        """通过 async_session 工厂产出会话"""
        mock_session = AsyncMock()
        # 工厂用 MagicMock（可调用、同步），返回值是 async 上下文管理器
        mock_factory = MagicMock()
        cm = AsyncMock()
        cm.__aenter__.return_value = mock_session
        cm.__aexit__.return_value = None
        mock_factory.return_value = cm

        with patch("app.database.db.async_session", mock_factory):
            async for session in db.get_session():
                assert session is mock_session
                break


class TestInitDb:
    """测试 init_db 建表"""

    @pytest.mark.anyio
    @patch("app.database.db.SQLModel")
    async def test_creates_all_tables(self, mock_sqlmodel):
        """调用 create_all 建表"""
        conn = AsyncMock()
        mock_engine = MagicMock()
        mock_engine.begin.return_value.__aenter__.return_value = conn
        mock_engine.begin.return_value.__aexit__.return_value = None

        with patch("app.database.db.async_engine", mock_engine):
            await db.init_db()

        conn.run_sync.assert_called_once_with(mock_sqlmodel.metadata.create_all)

    @pytest.mark.anyio
    async def test_raises_on_failure(self):
        """建表失败时向上抛异常"""
        mock_engine = MagicMock()
        mock_engine.begin.side_effect = RuntimeError("连接失败")

        with patch("app.database.db.async_engine", mock_engine):
            with pytest.raises(RuntimeError):
                await db.init_db()

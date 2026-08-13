# -*- coding: utf-8 -*-
"""设置路由（/api/settings）单元测试：RAG 参数读写 qdrant_config.yml"""
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies import get_current_user
from app.models.users import User
from app.routers import settings as settings_router


def _make_test_app():
    app = FastAPI()
    app.include_router(settings_router.router)
    return app


def _override_current_user():
    async def _dep():
        return User(id=1, phone="13800138000", password_hash="hash", full_name="测试用户")

    return _dep


@pytest.fixture
def client():
    app = _make_test_app()
    app.dependency_overrides[get_current_user] = _override_current_user()
    return TestClient(app)


class TestGetRagConfig:
    """获取 RAG 参数"""

    def test_returns_config_structure(self, client):
        resp = client.get("/api/settings/rag-config")
        body = resp.json()
        assert body["code"] == 0
        data = body["data"]
        # 契约字段：chunkSize / topK / chunkOverlap / separators
        assert set(data.keys()) == {"chunkSize", "topK", "chunkOverlap", "separators"}
        assert isinstance(data["chunkSize"], int)
        assert isinstance(data["topK"], int)
        assert isinstance(data["separators"], list)


class TestUpdateRagConfig:
    """保存 RAG 参数"""

    def test_update_chunk_size_and_top_k(self, client, tmp_path):
        """写入 yaml 并同步内存配置"""
        config_file = tmp_path / "qdrant_config.yml"
        config_file.write_text(
            "chunk_size: 100\nchunk_overlap: 20\nk: 3\nseparators:\n- ' '\n",
            encoding="utf-8",
        )
        in_memory_conf = {"chunk_size": 100, "chunk_overlap": 20, "k": 3, "separators": [" "]}

        with patch("app.routers.settings.CONFIG_PATH", str(config_file)):
            with patch("app.routers.settings.qdrant_conf", in_memory_conf):
                resp = client.put("/api/settings/rag-config", json={"chunkSize": 200, "topK": 5})

        body = resp.json()
        assert body["code"] == 0
        assert body["data"]["chunkSize"] == 200
        assert body["data"]["topK"] == 5
        assert in_memory_conf["chunk_size"] == 200  # 内存同步

        # 落盘验证
        written = config_file.read_text(encoding="utf-8")
        assert "chunk_size: 200" in written
        assert "k: 5" in written

    def test_update_only_chunk_size(self, client, tmp_path):
        """只传 chunkSize 时 topK 保持不变"""
        config_file = tmp_path / "qdrant_config.yml"
        config_file.write_text(
            "chunk_size: 100\nchunk_overlap: 20\nk: 3\nseparators:\n- ' '\n",
            encoding="utf-8",
        )
        in_memory_conf = {"chunk_size": 100, "chunk_overlap": 20, "k": 3, "separators": [" "]}

        with patch("app.routers.settings.CONFIG_PATH", str(config_file)):
            with patch("app.routers.settings.qdrant_conf", in_memory_conf):
                resp = client.put("/api/settings/rag-config", json={"chunkSize": 150})

        body = resp.json()
        assert body["data"]["chunkSize"] == 150
        assert body["data"]["topK"] == 3

    def test_no_params_returns_error(self, client):
        """未传任何参数 → 1001"""
        resp = client.put("/api/settings/rag-config", json={})
        assert resp.json()["code"] == 1001

    def test_invalid_chunk_size(self, client):
        """chunkSize 越界（<10）→ 参数校验失败"""
        resp = client.put("/api/settings/rag-config", json={"chunkSize": 1})
        assert resp.status_code == 422

    def test_unauthorized_without_token(self):
        app = _make_test_app()  # 不 override 认证
        resp = TestClient(app).get("/api/settings/rag-config")
        assert resp.status_code == 401

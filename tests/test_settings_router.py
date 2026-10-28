# -*- coding: utf-8 -*-
"""设置路由（/api/settings）单元测试：RAG 参数读写 retrieval_config.yml（P2 参数收敛 + P4 全参数热更新）"""
from unittest.mock import patch, AsyncMock

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
        # 契约字段：v1 平铺（旧前端兼容）+ P4 分组（legacyK + hybrid/rerank/queryOptimize/chunking）
        assert set(data.keys()) == {
            "chunkSize", "topK", "chunkOverlap", "separators",
            "legacyK", "hybrid", "rerank", "queryOptimize", "chunking",
        }
        assert isinstance(data["chunkSize"], int)
        assert isinstance(data["topK"], int)
        assert isinstance(data["separators"], list)
        # 分组结构（P4 全参数）
        assert set(data["hybrid"].keys()) == {"enabled", "denseTopn", "bm25Topn", "rrfK", "topn"}
        assert set(data["rerank"].keys()) == {"enabled", "remoteModel", "localModel", "topK"}
        assert set(data["queryOptimize"].keys()) == {"mode", "multiQueryCount", "fuseThenRerank"}
        assert set(data["chunking"].keys()) == {
            "chunkSize", "chunkOverlap", "minChunkSize", "maxChunkSize", "excelRowsPerChunk", "separators",
        }


class TestUpdateRagConfig:
    """保存 RAG 参数"""

    def test_update_chunk_size_and_top_k(self, client, tmp_path):
        """写入 yaml 并同步内存配置"""
        config_file = tmp_path / "retrieval_config.yml"
        config_file.write_text(
            "top_k: 3\nlegacy_k: 3\n"
            "rerank:\n  enabled: true\n  top_k: 3\n"
            "chunking:\n  chunk_size: 100\n  chunk_overlap: 20\n  separators:\n  - ' '\n",
            encoding="utf-8",
        )
        in_memory_conf = {
            "top_k": 3, "legacy_k": 3,
            "rerank": {"enabled": True, "top_k": 3},
            "chunking": {"chunk_size": 100, "chunk_overlap": 20, "separators": [" "]},
        }

        with patch("app.routers.settings.CONFIG_PATH", str(config_file)):
            with patch("app.routers.settings.retrieval_conf", in_memory_conf):
                with patch("app.routers.settings.registry") as mock_registry:
                    mock_registry.rebuild.return_value = True
                    resp = client.put("/api/settings/rag-config", json={"chunkSize": 200, "topK": 5})

        body = resp.json()
        assert body["code"] == 0
        assert body["data"]["chunkSize"] == 200
        assert body["data"]["topK"] == 5
        assert in_memory_conf["chunking"]["chunk_size"] == 200  # 内存同步
        assert in_memory_conf["top_k"] == 5
        assert in_memory_conf["rerank"]["top_k"] == 5  # rerank 开启时同步最终条数
        # topK 属检索参数 → 触发链路热重建
        mock_registry.rebuild.assert_called_once()

        # 落盘验证
        written = config_file.read_text(encoding="utf-8")
        assert "chunk_size: 200" in written
        assert "top_k: 5" in written

    def test_update_only_chunk_size(self, client, tmp_path):
        """只传 chunkSize 时 topK 保持不变"""
        config_file = tmp_path / "retrieval_config.yml"
        config_file.write_text(
            "top_k: 3\nlegacy_k: 3\n"
            "chunking:\n  chunk_size: 100\n  chunk_overlap: 20\n  separators:\n  - ' '\n",
            encoding="utf-8",
        )
        in_memory_conf = {
            "top_k": 3, "legacy_k": 3,
            "chunking": {"chunk_size": 100, "chunk_overlap": 20, "separators": [" "]},
        }

        with patch("app.routers.settings.CONFIG_PATH", str(config_file)):
            with patch("app.routers.settings.retrieval_conf", in_memory_conf):
                with patch("app.routers.settings.registry") as mock_registry:
                    resp = client.put("/api/settings/rag-config", json={"chunkSize": 150})

        body = resp.json()
        assert body["data"]["chunkSize"] == 150
        assert body["data"]["topK"] == 3
        # chunking 为上传期参数 → 不触发链路重建
        mock_registry.rebuild.assert_not_called()

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


class TestUpdateRagConfigGroups:
    """P4 分组参数保存：分组写入 + 热更新副作用（BM25 构建 / 单例更新 / 重建降级）"""

    @staticmethod
    def _write_config(tmp_path, text):
        config_file = tmp_path / "retrieval_config.yml"
        config_file.write_text(text, encoding="utf-8")
        return config_file

    def test_hybrid_group_write_and_rebuild(self, client, tmp_path):
        """分组参数落盘 + 检索参数变更触发链路重建（BM25 索引已就绪则不重建）"""
        config_file = self._write_config(tmp_path,
            "top_k: 5\nlegacy_k: 3\n"
            "hybrid:\n  enabled: false\n  dense_topn: 20\n  bm25_topn: 20\n  rrf_k: 60\n  topn: 30\n")
        in_memory_conf = {"top_k": 5, "legacy_k": 3,
                          "hybrid": {"enabled": False, "dense_topn": 20, "bm25_topn": 20, "rrf_k": 60, "topn": 30}}

        with patch("app.routers.settings.CONFIG_PATH", str(config_file)):
            with patch("app.routers.settings.retrieval_conf", in_memory_conf):
                with patch("app.routers.settings.registry") as mock_registry:
                    with patch("app.routers.settings.bm25_retriever") as mock_bm25:
                        mock_bm25.size = 5  # 索引已就绪
                        resp = client.put("/api/settings/rag-config",
                                          json={"hybrid": {"enabled": True, "rrfK": 100}})

        body = resp.json()
        assert body["code"] == 0
        assert body["data"]["hybrid"]["enabled"] is True
        assert body["data"]["hybrid"]["rrfK"] == 100
        assert in_memory_conf["hybrid"]["rrf_k"] == 100  # 内存同步
        mock_registry.rebuild.assert_called_once()  # 检索参数 → 链路重建
        mock_bm25.load_documents.assert_not_called()  # 索引非空 → 不重建 BM25

        written = config_file.read_text(encoding="utf-8")
        assert "rrf_k: 100" in written
        assert "enabled: true" in written

    def test_hybrid_off_to_on_builds_bm25_index(self, client, tmp_path):
        """hybrid off→on 且 BM25 索引为空（启动时未构建）→ PUT 内全量构建"""
        config_file = self._write_config(tmp_path, "top_k: 5\nlegacy_k: 3\nhybrid:\n  enabled: false\n")
        in_memory_conf = {"top_k": 5, "legacy_k": 3, "hybrid": {"enabled": False}}

        with patch("app.routers.settings.CONFIG_PATH", str(config_file)):
            with patch("app.routers.settings.retrieval_conf", in_memory_conf):
                with patch("app.routers.settings.registry"):
                    with patch("app.routers.settings.bm25_retriever") as mock_bm25:
                        mock_bm25.size = 0  # 启动时未构建
                        with patch("app.routers.settings.fetch_chunk_documents",
                                   new=AsyncMock(return_value=["chunk_a", "chunk_b"])) as mock_fetch:
                            resp = client.put("/api/settings/rag-config",
                                              json={"hybrid": {"enabled": True}})

        assert resp.json()["code"] == 0
        mock_fetch.assert_awaited_once()
        mock_bm25.load_documents.assert_called_once_with(["chunk_a", "chunk_b"])

    def test_bm25_topn_updates_singleton_directly(self, client, tmp_path):
        """hybrid.bm25_topn 为检索期参数 → 直接更新 BM25 单例 topn"""
        config_file = self._write_config(tmp_path,
            "top_k: 5\nlegacy_k: 3\nhybrid:\n  enabled: true\n  bm25_topn: 10\n")
        in_memory_conf = {"top_k": 5, "legacy_k": 3,
                          "hybrid": {"enabled": True, "bm25_topn": 10}}

        with patch("app.routers.settings.CONFIG_PATH", str(config_file)):
            with patch("app.routers.settings.retrieval_conf", in_memory_conf):
                with patch("app.routers.settings.registry"):
                    with patch("app.routers.settings.bm25_retriever") as mock_bm25:
                        mock_bm25.size = 5  # 索引已就绪，跳过全量构建
                        resp = client.put("/api/settings/rag-config",
                                          json={"hybrid": {"bm25Topn": 15}})

        assert resp.json()["code"] == 0
        assert mock_bm25.topn == 15

    def test_rebuild_failure_returns_fallback_message(self, client, tmp_path):
        """链路重建失败 → 配置已保存，提示下次重启生效（不报错）"""
        config_file = self._write_config(tmp_path, "top_k: 5\nlegacy_k: 3\n")
        in_memory_conf = {"top_k": 5, "legacy_k": 3}

        with patch("app.routers.settings.CONFIG_PATH", str(config_file)):
            with patch("app.routers.settings.retrieval_conf", in_memory_conf):
                with patch("app.routers.settings.registry") as mock_registry:
                    mock_registry.rebuild.return_value = False
                    resp = client.put("/api/settings/rag-config", json={"topK": 8})

        body = resp.json()
        assert body["code"] == 0
        assert body["message"] == "配置已保存，但链路重建失败，将在下次重启后生效"
        assert body["data"]["topK"] == 8

    def test_invalid_query_optimize_mode_rejected(self, client):
        """queryOptimize.mode 非法值 → 422 参数校验失败"""
        resp = client.put("/api/settings/rag-config", json={"queryOptimize": {"mode": "bad"}})
        assert resp.status_code == 422

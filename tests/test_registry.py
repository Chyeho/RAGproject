# -*- coding: utf-8 -*-
"""RAG 服务注册表单元测试（P4 参数热更新：单例懒加载 + 线程安全重建）"""
from unittest.mock import patch, MagicMock

import pytest

from app.service.rag import registry


@pytest.fixture(autouse=True)
def reset_singleton(monkeypatch):
    """每个用例前重置全局单例为 None（monkeypatch 用例后自动还原原值）"""
    monkeypatch.setattr(registry, "_rag_service", None)


class TestGetRagService:
    """线程安全懒加载单例"""

    def test_lazy_singleton_builds_once(self):
        """首次调用构建，后续调用复用同一实例"""
        instance = MagicMock()
        with patch.object(registry, "RagSummarizeService", return_value=instance) as mock_cls:
            s1 = registry.get_rag_service()
            s2 = registry.get_rag_service()
        assert s1 is s2 is instance
        mock_cls.assert_called_once()

    def test_returns_existing_without_rebuild(self):
        """已有实例时直接返回，不重新构建（读路径无锁快查）"""
        existing = MagicMock()
        with patch.object(registry, "_rag_service", existing):
            with patch.object(registry, "RagSummarizeService") as mock_cls:
                assert registry.get_rag_service() is existing
                mock_cls.assert_not_called()


class TestRebuild:
    """热更新重建（锁外构建 + 锁内原子替换）"""

    def test_rebuild_replaces_instance(self):
        """重建成功 → 原子替换为新实例"""
        old, new = MagicMock(), MagicMock()
        with patch.object(registry, "_rag_service", old):
            with patch.object(registry, "RagSummarizeService", return_value=new):
                assert registry.rebuild() is True
                assert registry.get_rag_service() is new

    def test_rebuild_failure_keeps_old_instance(self):
        """构建失败 → 返回 False，旧实例保留继续服务（新配置下次重启生效）"""
        old = MagicMock()
        with patch.object(registry, "_rag_service", old):
            with patch.object(registry, "RagSummarizeService", side_effect=RuntimeError("构建失败")):
                assert registry.rebuild() is False
                assert registry.get_rag_service() is old

    def test_rebuild_from_none(self):
        """单例尚未构建时重建 → 直接产出新实例"""
        new = MagicMock()
        with patch.object(registry, "RagSummarizeService", return_value=new):
            assert registry.rebuild() is True
            assert registry.get_rag_service() is new

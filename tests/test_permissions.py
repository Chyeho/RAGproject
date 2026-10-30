# -*- coding: utf-8 -*-
"""权限矩阵单元测试：角色/等级 → 权限集合"""
import pytest

from app.core.permissions import (
    ACCOUNT_MANAGE,
    ACCOUNT_PASSWORD,
    CHAT_USE,
    KNOWLEDGE_READ,
    KNOWLEDGE_WRITE,
    SETTINGS_RAG,
    STATISTICS_READ,
    has_permission,
    permissions_for,
)
from app.models.users import User


def _user(role="user", level=1):
    return User(id=1, username="czzsk000002", password_hash="hash", role=role, level=level)


class TestPermissionMatrix:
    def test_l1_readonly(self):
        user = _user(level=1)
        assert has_permission(user, CHAT_USE)
        assert has_permission(user, STATISTICS_READ)
        assert has_permission(user, KNOWLEDGE_READ)
        assert has_permission(user, ACCOUNT_PASSWORD)
        assert not has_permission(user, KNOWLEDGE_WRITE)
        assert not has_permission(user, SETTINGS_RAG)
        assert not has_permission(user, ACCOUNT_MANAGE)

    def test_l2_can_write_knowledge(self):
        user = _user(level=2)
        assert has_permission(user, KNOWLEDGE_WRITE)
        assert not has_permission(user, SETTINGS_RAG)
        assert not has_permission(user, ACCOUNT_MANAGE)

    def test_l3_can_edit_rag(self):
        user = _user(level=3)
        assert has_permission(user, KNOWLEDGE_WRITE)
        assert has_permission(user, SETTINGS_RAG)
        assert not has_permission(user, ACCOUNT_MANAGE)

    def test_admin_has_all(self):
        user = _user(role="admin", level=None)
        for perm in (CHAT_USE, STATISTICS_READ, KNOWLEDGE_READ, KNOWLEDGE_WRITE,
                     ACCOUNT_PASSWORD, SETTINGS_RAG, ACCOUNT_MANAGE):
            assert has_permission(user, perm)

    def test_level_none_defaults_to_l1(self):
        user = _user(role="user", level=None)
        assert not has_permission(user, KNOWLEDGE_WRITE)

    def test_permissions_for_returns_api_keys(self):
        perms = permissions_for(_user(level=2))
        assert perms == {
            "chat": True,
            "statistics": True,
            "knowledgeRead": True,
            "knowledgeWrite": True,
            "ragConfig": False,
            "accountManage": False,
        }
        # 内部权限 account:password 不对外暴露
        assert "password" not in perms

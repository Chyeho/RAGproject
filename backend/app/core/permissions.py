'''权限矩阵（唯一判定源，供依赖层与接口返回共用）

角色与等级：
- role = admin：内置管理员，拥有全部权限
- role = user：普通账号，level = 1/2/3，等级包含关系 L3 ⊃ L2 ⊃ L1
'''
CHAT_USE = "chat:use"
STATISTICS_READ = "statistics:read"
KNOWLEDGE_READ = "knowledge:read"
KNOWLEDGE_WRITE = "knowledge:write"
ACCOUNT_PASSWORD = "account:password"
SETTINGS_RAG = "settings:rag"
ACCOUNT_MANAGE = "account:manage"

ALL_PERMISSIONS = frozenset({
    CHAT_USE, STATISTICS_READ, KNOWLEDGE_READ, KNOWLEDGE_WRITE,
    ACCOUNT_PASSWORD, SETTINGS_RAG, ACCOUNT_MANAGE,
})

# 内部权限标识 → 接口返回给前端的 permissions 键（account:password 不对外）
API_PERMISSION_KEYS = {
    CHAT_USE: "chat",
    STATISTICS_READ: "statistics",
    KNOWLEDGE_READ: "knowledgeRead",
    KNOWLEDGE_WRITE: "knowledgeWrite",
    SETTINGS_RAG: "ragConfig",
    ACCOUNT_MANAGE: "accountManage",
}


def _allowed_permissions(role: str, level: int | None) -> set[str]:
    """按角色/等级计算可用权限集合"""
    if role == "admin":
        return set(ALL_PERMISSIONS)

    perms = {CHAT_USE, STATISTICS_READ, KNOWLEDGE_READ, ACCOUNT_PASSWORD}
    lv = level or 1
    if lv >= 2:
        perms.add(KNOWLEDGE_WRITE)
    if lv >= 3:
        perms.add(SETTINGS_RAG)
    return perms


def permissions_for(user) -> dict[str, bool]:
    """当前用户权限 → 前端可读的布尔字典"""
    allowed = _allowed_permissions(user.role, user.level)
    return {api_key: (perm in allowed) for perm, api_key in API_PERMISSION_KEYS.items()}


def has_permission(user, permission: str) -> bool:
    """判断用户是否拥有指定内部权限标识"""
    return permission in _allowed_permissions(user.role, user.level)

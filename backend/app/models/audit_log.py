'''管理员操作审计表模块（轻量记录，不做复杂审计系统）'''
from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class AuditLog(SQLModel, table=True):
    __tablename__ = "audit_log"

    id: Optional[int] = Field(default=None, primary_key=True, description="日志ID")
    actor_id: Optional[int] = Field(default=None, description="操作人 user.id")
    action: str = Field(max_length=32, index=True, description="操作类型")
    target_id: Optional[int] = Field(default=None, description="被操作账号 user.id")
    detail: Optional[str] = Field(default=None, max_length=500, description="变更摘要（不含明文密码）")
    created_at: datetime = Field(default_factory=datetime.now, description="操作时间")

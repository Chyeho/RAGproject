'''用户数据表模块'''
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy.orm import Mapped
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.models.documents import Document


class User(SQLModel, table=True):
    __tablename__ = "user"

    id: Optional[int] = Field(default=None, primary_key=True, description="用户ID")
    phone: str = Field(max_length=20, unique=True, index=True, description="手机号（登录账号）")
    username: Optional[str] = Field(default=None, max_length=50, description="登录账号（兼容保留，可空）")
    password_hash: str = Field(max_length=255, description="密码哈希值")
    full_name: Optional[str] = Field(default=None, max_length=100, description="昵称/真实姓名")
    avatar: Optional[str] = Field(default=None, description="头像（URL 或 base64）")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    last_login: Optional[datetime] = Field(default=None, description="最后登录时间")

    # 关系
    documents: Mapped[List["Document"]] = Relationship(back_populates="uploader")

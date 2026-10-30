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
    # 手机号：历史登录字段，新账号不再填写（保留列，唯一索引不变）
    phone: Optional[str] = Field(default=None, max_length=20, unique=True, index=True, description="手机号（历史字段，新账号为空）")
    # 登录账号：czzsk + 6 位补零 id（管理员为配置值），创建后不可修改
    username: Optional[str] = Field(default=None, max_length=50, unique=True, index=True, description="登录账号")
    password_hash: str = Field(max_length=255, description="密码哈希值")
    # 昵称/头像：功能已下线，列保留兼容历史数据
    full_name: Optional[str] = Field(default=None, max_length=100, description="昵称/真实姓名（历史字段）")
    avatar: Optional[str] = Field(default=None, description="头像（历史字段）")

    role: str = Field(default="user", max_length=10, description="角色：admin | user")
    level: Optional[int] = Field(default=1, description="普通用户等级：1/2/3；管理员为 NULL")
    status: str = Field(default="active", max_length=10, description="状态：active | disabled")
    must_change_password: bool = Field(default=False, description="是否需修改密码（初始/临时密码）")
    created_by: Optional[int] = Field(default=None, description="创建人 user.id（管理员创建时记录）")

    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    last_login: Optional[datetime] = Field(default=None, description="最后登录时间")
    deleted_at: Optional[datetime] = Field(default=None, description="软删除时间")

    failed_attempts: int = Field(default=0, description="连续登录失败次数")
    locked_until: Optional[datetime] = Field(default=None, description="登录锁定截止时间")

    # 关系
    documents: Mapped[List["Document"]] = Relationship(back_populates="uploader")

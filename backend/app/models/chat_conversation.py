'''会话数据表模块'''
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy.orm import Mapped
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.models.chat_message import ChatMessage


class ChatConversation(SQLModel, table=True):
    __tablename__ = "chat_conversation"

    id: Optional[int] = Field(default=None, primary_key=True, description="会话ID")
    user_id: int = Field(foreign_key="user.id", description="所属用户ID")
    title: str = Field(default="新会话", max_length=255, description="会话标题")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.now, description="最后更新时间")

    # 关系
    messages: Mapped[List["ChatMessage"]] = Relationship(back_populates="conversation", cascade_delete=True)

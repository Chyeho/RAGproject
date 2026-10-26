'''会话消息数据表模块'''
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import JSON, Column, Text
from sqlalchemy.orm import Mapped
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.models.chat_conversation import ChatConversation


class ChatMessage(SQLModel, table=True):
    __tablename__ = "chat_message"

    id: Optional[int] = Field(default=None, primary_key=True, description="消息ID")
    conversation_id: int = Field(foreign_key="chat_conversation.id", description="所属会话ID")
    role: str = Field(max_length=20, description="角色(user/assistant)")
    content: str = Field(
        # 助手回答可达数百上千字符（P1 后检索内容更丰富），必须用 TEXT 而非默认 VARCHAR(255)
        sa_column=Column("content", Text, nullable=False),
        description="消息内容",
    )
    citations: Optional[list] = Field(
        default_factory=list, sa_column=Column(JSON), description="引用来源列表 [{documentId, documentName, snippet}]"
    )
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")

    # 关系
    conversation: Mapped["ChatConversation"] = Relationship(back_populates="messages")

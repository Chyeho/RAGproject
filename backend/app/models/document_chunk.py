'''文档分块表'''
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Column, Text
from sqlalchemy.orm import Mapped
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.models.documents import Document


class DocumentChunk(SQLModel, table=True):
    __tablename__ = "document_chunk"

    id: Optional[int] = Field(default=None, primary_key=True, description="分块ID")
    chunk_index: int = Field(description="分块顺序索引")
    # 分块正文可达数千字符（如 Excel 每组 N 行），必须用 TEXT 而非默认 VARCHAR(255)
    content: str = Field(sa_column=Column("content", Text, nullable=False), description="分块文本内容")
    vector_id: Optional[str] = Field(default=None, max_length=64, index=True, description="向量数据库中的ID")

    # 外键
    document_id: int = Field(foreign_key="document.id", description="所属文档ID")

    # 关系：分块属于一个文档
    document: Mapped["Document"] = Relationship(back_populates="chunks")

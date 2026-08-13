'''文档元数据表模块'''
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy.orm import Mapped
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.models.document_chunk import DocumentChunk
    from app.models.users import User


class Document(SQLModel, table=True):
    __tablename__ = "document"

    id: Optional[int] = Field(default=None, primary_key=True, description="文档ID")
    md5_hash: str = Field(max_length=32, unique=True, index=True, description="文档md5值")
    file_name: str = Field(max_length=255, description="原始文件名")
    file_type: str = Field(max_length=20, description="文件类型")
    file_size: Optional[int] = Field(default=None, description="文件大小")
    file_path: Optional[str] = Field(default=None, max_length=500, description="文件存储路径")
    created_at: datetime = Field(default_factory=datetime.now, description="入库时间")
    vectorize_status: str = Field(default="processing", max_length=20, description="向量化状态(processing/success/failed)")
    vectorize_message: Optional[str] = Field(default=None, max_length=500, description="向量化失败原因")

    # 外键
    uploader_id: int = Field(foreign_key="user.id", description="上传者ID")

    # 关系
    uploader: Mapped["User"] = Relationship(back_populates="documents")
    chunks: Mapped[List["DocumentChunk"]] = Relationship(back_populates="document", cascade_delete=True)

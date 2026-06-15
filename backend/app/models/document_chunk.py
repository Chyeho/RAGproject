'''文档分块表'''
from datetime import datetime
from typing import Optional,List
from sqlmodel import SQLModel,Field,Relationship
from documents import Document

class DocumentChunk(SQLModel,table=True):
    id: Optional[int] = Field(default=None, primary_key=True, description="分块ID")
    chunk_index: int = Field(description="分块顺序索引")
    content: str = Field(description="分块文本内容")
    vector_id: Optional[str] = Field(default=None, max_length=64, index=True, description="向量数据库中的ID")

    # 外键
    document_id:int = Field(foreign_key="document_id",description="所属文档ID")

    # 关系：分块属于一个文档
    document: Document = Relationship(back_populates="chunks")
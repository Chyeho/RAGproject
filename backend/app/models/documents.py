'''文档元数据表模块'''
from datetime import datetime
from typing import Optional,List
from sqlmodel import SQLModel,Field,Relationship
from users import User
from document_chunk import DocumentChunk

class Document(SQLModel,table=True):
    id:Optional[int] = Field(default=None,primary_key=True,description="文档ID")
    md5_hash:str = Field(max_length=32,unique=True,index=True,description="文档md5值")
    title:str = Field(max_length=255,description="文档标题")
    file_name:str = Field(max_length=255,description="原始文件名")
    file_type:str = Field(max_length=20,description="文件类型")
    file_size:Optional[int] = Field(default=None,description="文件大小")

    # 外键
    uploader_id: int = Field(foreign_key="user.id", description="上传者ID")

    # 关系
    uploader: User = Relationship(back_populates="documents")
    chunks: List[DocumentChunk] = Relationship(back_populates="document", cascade_delete=True)


    

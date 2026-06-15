'''用户数据表模块'''
from datetime import datetime
from typing import Optional,List
from sqlmodel import SQLModel,Field,Relationship
from documents import Document

class User(SQLModel,table=True):
    id:Optional[int] = Field(default=None,primary_key=True,description="用户ID")
    username:str = Field(max_length=50,unique=True,description="登录账号")
    password_hash:str = Field(max_length=255,description="密码哈希值")
    full_name:Optional[str] = Field(default=None,max_length=100,description="真实姓名")
    created_at: datetime = Field(default_factory=datetime, description="创建时间")
    last_login: Optional[datetime] = Field(default=None, description="最后登录时间")   

    # 关系
    documents: List[Document] = Relationship(back_populates="uploader")


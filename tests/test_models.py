# -*- coding: utf-8 -*-
"""SQLModel 数据模型（5 张表）定义单元测试"""
from datetime import datetime

import pytest
from sqlmodel import SQLModel

from app.models import User, Document, DocumentChunk, ChatConversation, ChatMessage


class TestTableNames:
    """表名与数据库映射"""

    def test_user_table_name(self):
        assert User.__tablename__ == "user"

    def test_document_table_name(self):
        assert Document.__tablename__ == "document"

    def test_document_chunk_table_name(self):
        assert DocumentChunk.__tablename__ == "document_chunk"

    def test_chat_conversation_table_name(self):
        assert ChatConversation.__tablename__ == "chat_conversation"

    def test_chat_message_table_name(self):
        assert ChatMessage.__tablename__ == "chat_message"


class TestUserModel:
    """用户表"""

    def test_required_fields(self):
        """关键字段存在且类型正确"""
        assert User.__table__.c.phone.unique is True
        assert User.__table__.c.phone.index is True
        assert User.__table__.c.password_hash is not None

    def test_default_created_at(self):
        """created_at 默认当前时间"""
        user = User(phone="13800138000", password_hash="hash")
        assert user.id is None
        assert isinstance(user.created_at, datetime)
        assert user.full_name is None  # 可空

    def test_relationship_documents(self):
        """与文档表存在 uploader 关系"""
        assert hasattr(User, "documents")


class TestDocumentModel:
    """文档表"""

    def test_unique_md5_hash(self):
        """md5_hash 唯一（去重依据，替代原 md5.txt）"""
        assert Document.__table__.c.md5_hash.unique is True
        assert Document.__table__.c.md5_hash.index is True

    def test_default_vectorize_status(self):
        """向量化状态默认 processing"""
        doc = Document(md5_hash="a" * 32, file_name="手册.txt", file_type="txt", uploader_id=1)
        assert doc.vectorize_status == "processing"
        assert doc.vectorize_message is None

    def test_foreign_key_to_user(self):
        """uploader_id 外键指向 user.id"""
        assert Document.__table__.c.uploader_id.foreign_keys
        fk = next(iter(Document.__table__.c.uploader_id.foreign_keys))
        assert fk.target_fullname == "user.id"

    def test_relationship_chunks(self):
        """与分块表存在 chunks 关系（级联删除）"""
        assert hasattr(Document, "chunks")


class TestDocumentChunkModel:
    """文档分块表"""

    def test_required_fields(self):
        chunk = DocumentChunk(document_id=1, chunk_index=0, content="分块内容")
        assert chunk.vector_id is None

    def test_foreign_key_to_document(self):
        """document_id 外键指向 document.id"""
        fk = next(iter(DocumentChunk.__table__.c.document_id.foreign_keys))
        assert fk.target_fullname == "document.id"


class TestChatConversationModel:
    """会话表"""

    def test_default_title(self):
        """title 默认 '新会话'"""
        conv = ChatConversation(user_id=1)
        assert conv.title == "新会话"
        assert isinstance(conv.created_at, datetime)
        assert isinstance(conv.updated_at, datetime)

    def test_foreign_key_to_user(self):
        fk = next(iter(ChatConversation.__table__.c.user_id.foreign_keys))
        assert fk.target_fullname == "user.id"

    def test_relationship_messages(self):
        """与消息表存在 messages 关系（级联删除）"""
        assert hasattr(ChatConversation, "messages")


class TestChatMessageModel:
    """消息表"""

    def test_default_citations(self):
        """citations 默认空列表（契约：user 消息恒为空数组）"""
        msg = ChatMessage(conversation_id=1, role="user", content="你好")
        assert msg.citations == []

    def test_foreign_key_to_conversation(self):
        fk = next(iter(ChatMessage.__table__.c.conversation_id.foreign_keys))
        assert fk.target_fullname == "chat_conversation.id"

    def test_relationship_conversation(self):
        assert hasattr(ChatMessage, "conversation")


class TestMetadataRegistration:
    """全部模型注册到 SQLModel.metadata（建表依据）"""

    def test_all_tables_registered(self):
        table_names = set(SQLModel.metadata.tables.keys())
        for name in ("user", "document", "document_chunk", "chat_conversation", "chat_message"):
            assert name in table_names

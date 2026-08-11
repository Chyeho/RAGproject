# -*- coding: utf-8 -*-
"""历史消息存储模块单元测试"""
import os
import json
import tempfile

import pytest
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage

from app.service.history.history_store import ChatMessageHistory, get_chat_history


class TestChatMessageHistoryInit:
    """测试初始化"""

    def test_creates_storage_dir(self, sample_chat_history_dir):
        storage = os.path.join(sample_chat_history_dir, "sub", "nested")
        file_path = os.path.join(storage, "user_001")
        ChatMessageHistory("user_001", storage)
        assert os.path.isdir(storage)

    def test_creates_empty_json_file(self, sample_chat_history_dir):
        """新会话应创建包含 [] 的文件"""
        storage = sample_chat_history_dir
        history = ChatMessageHistory("new_user", storage)
        assert os.path.exists(history.file_path)
        with open(history.file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data == []

    def test_does_not_overwrite_existing_file(self, sample_chat_history_dir):
        """已存在的合法文件不应被覆盖"""
        storage = sample_chat_history_dir
        file_path = os.path.join(storage, "existing_user")
        os.makedirs(storage, exist_ok=True)
        messages = [{"type": "human", "data": {"content": "你好", "type": "human"}}]
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(messages, f)

        history = ChatMessageHistory("existing_user", storage)
        msgs = history.messages
        assert len(msgs) == 1

    def test_repair_empty_file(self, sample_chat_history_dir):
        """0 字节空文件应被修复为 []"""
        storage = sample_chat_history_dir
        os.makedirs(storage, exist_ok=True)
        file_path = os.path.join(storage, "empty_user")
        open(file_path, "wb").close()  # 创建 0 字节文件

        history = ChatMessageHistory("empty_user", storage)
        msgs = history.messages
        assert msgs == []
        # 确认文件已被修复
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data == []


class TestChatMessageHistoryMessages:
    """测试 messages 属性"""

    def test_empty_messages_for_new_user(self, sample_chat_history_dir):
        history = ChatMessageHistory("brand_new", sample_chat_history_dir)
        assert history.messages == []

    def test_loads_messages_from_file(self, sample_chat_history_dir):
        storage = sample_chat_history_dir
        os.makedirs(storage, exist_ok=True)
        file_path = os.path.join(storage, "loaded_user")
        messages = [{"type": "human", "data": {"content": "你好", "type": "human"}}]
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(messages, f)

        history = ChatMessageHistory("loaded_user", storage)
        msgs = history.messages
        assert len(msgs) == 1
        assert msgs[0].content == "你好"

    def test_setter_persists_messages(self, sample_chat_history_dir):
        history = ChatMessageHistory("setter_user", sample_chat_history_dir)
        new_msgs = [HumanMessage(content="setter test")]
        history.messages = new_msgs
        # 重新加载验证
        reloaded = ChatMessageHistory("setter_user", sample_chat_history_dir)
        assert len(reloaded.messages) == 1
        assert reloaded.messages[0].content == "setter test"


class TestChatMessageHistoryAddMessages:
    """测试 add_messages 方法"""

    def test_add_single_message(self, sample_chat_history_dir):
        history = ChatMessageHistory("add_user", sample_chat_history_dir)
        msg = HumanMessage(content="单条消息")
        history.add_messages(msg)
        assert len(history.messages) == 1

    def test_add_message_list(self, sample_chat_history_dir):
        history = ChatMessageHistory("add_list_user", sample_chat_history_dir)
        msgs = [HumanMessage(content="问题1"), AIMessage(content="回答1")]
        history.add_messages(msgs)
        assert len(history.messages) == 2

    def test_append_to_existing(self, sample_chat_history_dir):
        history = ChatMessageHistory("append_user", sample_chat_history_dir)
        history.add_messages(HumanMessage(content="第一轮"))
        history.add_messages(AIMessage(content="回复第一轮"))
        history.add_messages(HumanMessage(content="第二轮"))
        assert len(history.messages) == 3


class TestChatMessageHistoryClear:
    """测试 clear 方法"""

    def test_clear_empties_messages(self, sample_chat_history_dir):
        history = ChatMessageHistory("clear_user", sample_chat_history_dir)
        history.add_messages(HumanMessage(content="test"))
        assert len(history.messages) == 1
        history.clear()
        assert history.messages == []


class TestGetChatHistory:
    """测试 get_chat_history 工厂函数"""

    def test_returns_chat_message_history(self):
        history = get_chat_history("test_session")
        assert isinstance(history, ChatMessageHistory)

    def test_session_id_correct(self):
        history = get_chat_history("user_999")
        assert history.session_id == "user_999"

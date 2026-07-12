'''历史消息服务'''
import os
import json
from app.utils.logger_handler import logger
from app.utils.path_tool import get_root_path
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.messages import BaseMessage, message_to_dict, messages_from_dict


def get_chat_history(session_id):
    """
    获取历史消息服务类
    Args:
        session_id (str): 会话ID
    Returns:
        BaseChatMessageHistory: 历史消息服务类
    """
    backend_dir = os.path.dirname(get_root_path())
    return ChatMessageHistory(session_id, os.path.join(backend_dir, "chat_history"))


class ChatMessageHistory(BaseChatMessageHistory):
    def __init__(self, session_id, storage_path):
        """
        初始化函数
        Args:
            session_id (str): 会话ID
            storage_path (str): 不同会话ID的存储文件所在的文件夹路径
        """
        self.session_id = session_id
        self.storage_path = storage_path
        self.file_path = os.path.join(self.storage_path, self.session_id)

        os.makedirs(self.storage_path, exist_ok=True)

        # 文件不存在或内容为空时，初始化为合法的空数组
        if not os.path.exists(self.file_path) or os.path.getsize(self.file_path) == 0:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump([], f)

    def _load_messages(self) -> list:
        """从文件中加载历史消息，防御空文件/损坏文件"""
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if not content:
                    return []
                messages_data = json.loads(content)
                return messages_from_dict(messages_data)
        except FileNotFoundError:
            return []
        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"[ChatMessageHistory]历史消息文件损坏或解析失败：{str(e)}，已重置为空列表")
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump([], f)
            return []

    def _save_messages(self, messages: list) -> None:
        """将消息列表持久化到文件"""
        try:
            serializable = [message_to_dict(msg) for msg in messages]
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(serializable, f)
        except Exception as e:
            logger.error(f"[ChatMessageHistory]历史消息写入失败，错误信息：{str(e)}")

    @property
    def messages(self) -> list:
        """获取历史消息列表
        Returns:
            list: BaseMessage 对象列表
        """
        return self._load_messages()

    @messages.setter
    def messages(self, value: list) -> None:
        """允许外部直接覆盖 messages（LangChain 内部可能调用）"""
        self._save_messages(value)

    def add_messages(self, messages) -> None:
        """
        添加消息到历史记录（支持单个 BaseMessage 或消息列表）
        这是 LangChain BaseChatMessageHistory 标准方法
        Args:
            messages: 单个 BaseMessage 对象或消息列表
        """
        existing = self._load_messages()
        if isinstance(messages, BaseMessage):
            messages = [messages]
        existing.extend(messages)
        self._save_messages(existing)

    def clear(self) -> None:
        """清空历史消息"""
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump([], f)


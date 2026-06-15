'''历史消息服务'''
import os
from app.utils.logger_handler import logger
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.messages import message_to_dict,messages_from_dict
import json

def get_chat_history(session_id):
    """
    获取历史消息服务类
    Args:
        session_id (str): 会话ID
    Returns:
        BaseChatMessageHistory: 历史消息服务类
    """
    return ChatMessageHistory(session_id,"./chat_history")

class ChatMessageHistory(BaseChatMessageHistory):
    def __init__(self,session_id,storage_path):
        """
        初始化函数
        Args:
            session_id (str): 会话ID
            storage_path (str): 不同会话ID的存储文件所在的文件夹路径
        """
        self.session_id = session_id
        self.storage_path = storage_path
        self.file_path = os.path.join(self.storage_path,self.session_id)

        os.makedirs(os.path.dirname(self.file_path),exist_ok=True)

    def add_message(self, message):
        """
        添加新的历史消息
        Args:
            message (list): 新的历史消息列表
        """
        all_messages = list(self.messages)   # 原有的消息列表
        all_messages.extend(message)         # 将已有的消息列表和新的合并

        new_messages = [message_to_dict(message) for message in all_messages]
        try:
            with open(self.file_path,"w",encoding="utf-8") as f:
                json.dump(new_messages,f)
        except Exception as e:
            logger.error(f"[add_message]历史消息写入失败，错误信息：{str(e)}")
            return None
        
    def message(self):
        """
        获取历史消息列表
        Returns:
            list: 历史消息列表
        """
        try:
            with open(self.file_path,"r",encoding="utf-8") as f:
                messages_data = json.load(f)
                return messages_from_dict(messages_data)
        except FileNotFoundError:
            logger.error(f"[message]文件不存在")
            return []
        
    def clear(self):
        """清空历史消息"""
        with open(self.file_path,"w",encoding="utf-8") as f:
            json.dump([],f)


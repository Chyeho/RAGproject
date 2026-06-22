'''
历史消息记录服务
'''
import os
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.messages import message_to_dict,messages_from_dict
import json

def get_history(session_id):
    return FileChatMessageHistory(session_id,"./chat_history")

class FileChatMessageHistory(BaseChatMessageHistory):
    def __init__(self,session_id,storage_path):
        self.session_id = session_id         # 会话ID
        self.storage_path = storage_path     # 不同会话ID的存储文件所在的文件夹路径

        # 完整的文件路径
        self.file_path = os.path.join(self.storage_path,self.session_id)

        # 保证文件夹存在，不存在就创建
        os.makedirs(self.storage_path, exist_ok=True)

        # 文件不存在或内容为空时，初始化为合法的空数组
        if not os.path.exists(self.file_path) or os.path.getsize(self.file_path) == 0:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump([], f)


    def add_messages(self, messages):
        all_messages = list(self.messages)   # 原有的消息列表
        all_messages.extend(messages)        # 将已有的消息列表和新的合并

        # 将消息列表转换成列表套字典的形式
        new_messages = [message_to_dict(message) for message in all_messages]

        with open(self.file_path,"w",encoding="utf-8") as f:
            json.dump(new_messages,f)     # 转成json格式存到文件中

    @property
    def messages(self):
        try:
            with open(self.file_path,"r",encoding="utf-8") as f:
                messages_data = json.load(f) # 加载文件内容
                return messages_from_dict(messages_data)
        except FileNotFoundError:
            return []
        
    def clear(self):
        with open(self.file_path,"w",encoding="utf-8") as f:
            json.dump([],f)  # 写入空内容，即清除所有
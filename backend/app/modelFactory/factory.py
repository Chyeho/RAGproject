'''工厂模式，用于生产模型（文本嵌入模型，聊天模型等）'''
from abc import ABC,abstractmethod                                # 导入抽象类
from typing import Optional                                       # 可空类型
from langchain_core.embeddings import Embeddings                  # 文本嵌入模型类型
from langchain_community.chat_models.tongyi import BaseChatModel  # 聊天模型类型
from langchain_community.embeddings import DashScopeEmbeddings    # 文本嵌入模型
from langchain_community.chat_models.tongyi import ChatTongyi     # 聊天模型

from app.utils.config_handler import rag_conf                     # 导入rag配置项

class BaseModelFactory(ABC):
    """模型工厂基类
    Args:
        ABC (_type_): 抽象类
    """
    @abstractmethod
    def generator(self) -> Optional[Embeddings | BaseChatModel]:
        pass

class ChatModelFactory(BaseModelFactory):
    """聊天模型"""
    def generator(self) -> Optional[Embeddings | BaseChatModel]:
        return ChatTongyi(model=rag_conf["chat_model_name"])
    
class EmbeddingFactory(BaseModelFactory):
    """文本嵌入模型"""
    def generator(self) -> Optional[Embeddings | BaseChatModel]:
        return DashScopeEmbeddings(model=rag_conf["embedding_model_name"])
    
chat_model = ChatModelFactory().generator()
embed_model = EmbeddingFactory().generator()
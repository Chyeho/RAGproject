'''工厂模式，用于生产模型（文本嵌入模型，聊天模型等）'''
import dashscope
from abc import ABC, abstractmethod                               # 导入抽象类
from typing import Optional, List                                 # 类型注解
from langchain_core.embeddings import Embeddings                  # 文本嵌入模型类型
from langchain_community.chat_models.tongyi import BaseChatModel  # 聊天模型类型
from langchain_community.chat_models.tongyi import ChatTongyi     # 聊天模型

from app.utils.config_handler import rag_conf                     # 导入rag配置项


class DashScopeTextEmbeddings(Embeddings):
    """
    问题：Langchain的DashScopeEmbeddings类的封装方式和当前版本的dashscope SDK不兼容（传参格式不对），导致 InvalidParameter 报错
    解决：
    直接继承 LangChain Embeddings 基类，完全自主控制 API 请求参数。绕过 langchain_community 的 DashScopeEmbeddings 封装
    已验证：text-embedding-v4 模型的正确参数结构是 input=字符串（单条）/ input=列表（批量）
    """

    def __init__(self, model: str):
        self.model = model   # 模型名称

    MAX_BATCH_SIZE = 10      # 最大批量大小

    def _call_api(self, texts: List[str]) -> List[List[float]]:
        """调用 DashScope TextEmbedding API，按原顺序返回向量列表"""
        # 单条传字符串，批量传列表，但最多 MAX_BATCH_SIZE 条/批
        results = []
        for i in range(0, len(texts), self.MAX_BATCH_SIZE):
            batch = texts[i:i + self.MAX_BATCH_SIZE]
            # 构建 API 请求参数。单条传字符串，批量传列表，但最多 MAX_BATCH_SIZE 条/批
            input_value = batch[0] if len(batch) == 1 else list(batch)
            # 调用 API
            resp = dashscope.TextEmbedding.call(
                input=input_value,
                model=self.model,
            )
            # 检查响应状态码
            if resp.status_code != 200:
                raise ValueError(
                    f"status_code: {resp.status_code}, code: {resp.code}, message: {resp.message}"
                )
            # 解析 API 响应，按原顺序返回向量列表（按 text_index 排序）
            embeddings = resp.output["embeddings"]
            sorted_batch = sorted(embeddings, key=lambda x: x["text_index"])
            results.extend(item["embedding"] for item in sorted_batch)
        return results

    def embed_query(self, text: str) -> List[float]:
        """单条查询文本的向量表示"""
        # 用户提问，返回单条向量
        return self._call_api([text])[0]

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """批量文本的向量表示"""
        # 加载文档，返回批量向量列表
        return self._call_api(texts)


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
        return DashScopeTextEmbeddings(model=rag_conf["embedding_model_name"])


chat_model = ChatModelFactory().generator()
embed_model = EmbeddingFactory().generator()
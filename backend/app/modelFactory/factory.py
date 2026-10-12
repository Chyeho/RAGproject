'''工厂模式，用于生产模型（文本嵌入模型，聊天模型等）

通过环境变量 MODEL_MODE 切换加载模式：
  - remote（默认）：聊天模型用 langchain_openai.ChatOpenAI（兼容 OpenAI 协议），嵌入模型用 DashScope
  - local：聊天模型和嵌入模型均用 langchain_ollama（本地 Ollama 服务）
'''
import os
import dashscope
from abc import ABC, abstractmethod                               # 导入抽象类
from typing import Optional, List                                 # 类型注解
from langchain_core.embeddings import Embeddings                  # 文本嵌入模型类型
from langchain_core.language_models.chat_models import BaseChatModel  # 聊天模型通用基类
from langchain_openai import ChatOpenAI                           # 远程模式聊天模型（OpenAI 协议）
from langchain_ollama import ChatOllama, OllamaEmbeddings          # 本地模式聊天+嵌入模型

from app.utils.config_handler import rag_conf                     # 导入rag配置项
from app.utils.logger_handler import logger                       # 日志器


def _get_model_mode() -> str:
    """读取环境变量 MODEL_MODE，返回 'remote' 或 'local'；非法值回退 remote 并告警"""
    mode = os.environ.get("MODEL_MODE", "remote").lower()
    if mode not in ("remote", "local"):
        logger.warning(f"[模型工厂]MODEL_MODE='{mode}' 不合法，回退为 'remote'")
        mode = "remote"
    return mode


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
        mode = _get_model_mode()
        if mode == "local":
            # 本地模式：Ollama 聊天模型
            model_name = os.environ.get(
                "OLLAMA_CHAT_MODEL",
                rag_conf["local"]["chat_model_name"],
            )
            base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
            logger.info(f"[模型工厂]聊天模型(本地): {model_name} @ {base_url}")
            return ChatOllama(model=model_name, base_url=base_url)

        # 远程模式：OpenAI 协议聊天模型
        api_key = os.environ.get("OPENAI_API_KEY", "not-configured")
        if api_key == "not-configured":
            logger.warning(
                "[模型工厂]远程模式未配置 OPENAI_API_KEY，"
                "模型可加载但调用时会失败。请在环境变量中设置 OPENAI_API_KEY。"
                "通义兼容端点示例: https://dashscope.aliyuncs.com/compatible-mode/v1"
            )
        model_name = os.environ.get(
            "OPENAI_CHAT_MODEL",
            rag_conf["remote"]["chat_model_name"],
        )
        base_url = os.environ.get("OPENAI_BASE_URL")
        logger.info(f"[模型工厂]聊天模型(远程): {model_name} @ {base_url}")
        return ChatOpenAI(model=model_name, api_key=api_key, base_url=base_url)


class EmbeddingFactory(BaseModelFactory):
    """文本嵌入模型"""
    def generator(self) -> Optional[Embeddings | BaseChatModel]:
        mode = _get_model_mode()
        if mode == "local":
            # 本地模式：Ollama 嵌入模型
            model_name = os.environ.get(
                "OLLAMA_EMBEDDING_MODEL",
                rag_conf["local"]["embedding_model_name"],
            )
            base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
            logger.info(f"[模型工厂]嵌入模型(本地): {model_name} @ {base_url}")
            return OllamaEmbeddings(model=model_name, base_url=base_url)

        # 远程模式：DashScope 嵌入模型（保持不变）
        model_name = rag_conf["remote"]["embedding_model_name"]
        logger.info(f"[模型工厂]嵌入模型(远程-DashScope): {model_name}")
        return DashScopeTextEmbeddings(model=model_name)


chat_model = ChatModelFactory().generator()
embed_model = EmbeddingFactory().generator()

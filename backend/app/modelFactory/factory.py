'''工厂模式，用于生产模型（文本嵌入模型，聊天模型等）

通过环境变量 MODEL_MODE 切换加载模式：
  - remote（默认）：聊天模型用 langchain_openai.ChatOpenAI（兼容 OpenAI 协议），嵌入模型用 DashScope
  - local：聊天模型和嵌入模型均用 langchain_ollama（本地 Ollama 服务）
'''
import os
import ollama
import dashscope
from abc import ABC, abstractmethod                               # 导入抽象类
from typing import Optional, List                                 # 类型注解
from langchain_core.embeddings import Embeddings                  # 文本嵌入模型类型
from langchain_core.language_models.chat_models import BaseChatModel  # 聊天模型通用基类
from langchain_openai import ChatOpenAI                           # 远程模式聊天模型（OpenAI 协议）
from langchain_ollama import ChatOllama, OllamaEmbeddings          # 本地模式聊天+嵌入模型

from app.utils.config_handler import rag_conf                     # 导入rag配置项
from app.utils.logger_handler import logger                       # 日志器

# 远程聊天模型默认值：环境变量 OPENAI_CHAT_MODEL 缺失时的兜底
DEFAULT_OPENAI_CHAT_MODEL = "qwen-plus"
# DashScope OpenAI 协议兼容端点：评测聊天模型默认供应商
DEFAULT_DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
# 评测模型默认值：固定 DashScope qwen-plus，与 EV2/P0-P3 历史报告口径可比
DEFAULT_EVAL_CHAT_MODEL = "qwen-plus"


def _get_model_mode() -> str:
    """读取环境变量 MODEL_MODE，返回 'remote' 或 'local'；非法值回退 remote 并告警"""
    mode = os.environ.get("MODEL_MODE", "remote").lower()
    if mode not in ("remote", "local"):
        logger.warning(f"[模型工厂]MODEL_MODE='{mode}' 不合法，回退为 'remote'")
        mode = "remote"
    return mode


def get_remote_chat_model_name() -> str:
    """读取远程聊天模型名：取 OPENAI_CHAT_MODEL 环境变量，未配置时回退默认值并告警"""
    model_name = os.environ.get("OPENAI_CHAT_MODEL", "").strip()
    if not model_name:
        logger.warning(
            f"[模型工厂]未配置 OPENAI_CHAT_MODEL，回退默认模型: {DEFAULT_OPENAI_CHAT_MODEL}"
        )
        return DEFAULT_OPENAI_CHAT_MODEL
    return model_name


def get_remote_embedding_model_name() -> str:
    """读取远程嵌入模型名：TEXT_EMBEDDING_MODEL 环境变量优先，未配置回退 rag_config.yml"""
    model_name = os.environ.get("TEXT_EMBEDDING_MODEL", "").strip()
    if model_name:
        return model_name
    return str(rag_conf["remote"]["embedding_model_name"])


def get_eval_chat_model_name() -> str:
    """读取评测模型名（裁判/评测集生成）：EVAL_CHAT_MODEL 环境变量优先，回退 qwen-plus"""
    model_name = os.environ.get("EVAL_CHAT_MODEL", "").strip()
    return model_name or DEFAULT_EVAL_CHAT_MODEL


def get_eval_chat_model() -> BaseChatModel:
    """评测专用聊天模型：固定 DashScope 供应商（默认 qwen-plus），与业务聊天模型解耦

    业务聊天切第三方供应商（如 DeepSeek）后，评测裁判与评测集生成仍走 DashScope，
    保证与 EV2/P0-P3 历史报告的 qwen-plus 口径可比。
    凭据取 DASHSCOPE_API_KEY，端点取 DASHSCOPE_BASE_URL（缺省为 DashScope 兼容端点）。
    """
    api_key = os.environ.get("DASHSCOPE_API_KEY", "not-configured")
    if api_key == "not-configured":
        logger.warning(
            "[模型工厂]评测模型未配置 DASHSCOPE_API_KEY，"
            "模型可加载但调用时会失败。请在环境变量中设置 DASHSCOPE_API_KEY。"
        )
    base_url = os.environ.get("DASHSCOPE_BASE_URL", "").strip() or DEFAULT_DASHSCOPE_BASE_URL
    model_name = get_eval_chat_model_name()
    logger.info(f"[模型工厂]评测模型(远程-DashScope): {model_name} @ {base_url}")
    return ChatOpenAI(model=model_name, api_key=api_key, base_url=base_url)


def _normalize_model_name(name: str) -> str:
    """规范化模型名用于比较：去掉 ':latest' 后缀、去首尾空白"""
    name = name.strip()
    if name.endswith(":latest"):
        name = name[: -len(":latest")]
    return name


def _ensure_ollama_model(model_name: str, base_url: str) -> None:
    """本地模式启动前检查 Ollama 模型是否存在，不存在则自动 pull。

    Args:
        model_name: 模型名，如 'qwen2.5:7b'、'bge-m3'
        base_url: Ollama 服务地址
    """
    try:
        client = ollama.Client(host=base_url)
        # 列出本地已有模型
        response = client.list()
        installed = [m.model for m in response.models] if response.models else []
        installed_norm = [_normalize_model_name(m) for m in installed]

        # 规范化比较：用户传 'bge-m3' 应匹配到列表里的 'bge-m3:latest'
        if _normalize_model_name(model_name) in installed_norm:
            logger.info(f"[模型工厂]Ollama 模型已存在: {model_name}")
            return

        # 不存在则自动拉取
        logger.warning(f"[模型工厂]Ollama 模型缺失: {model_name}，开始自动拉取（可能耗时较长）...")
        client.pull(model_name)
        logger.info(f"[模型工厂]Ollama 模型拉取完成: {model_name}")
    except Exception as e:
        logger.error(f"[模型工厂]Ollama 模型检查/拉取失败: {model_name} @ {base_url}，错误: {e}")
        # 不中断启动，让后续调用时报错


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
            # 本地模式：Ollama 聊天模型（启动前确保模型已存在，不存在则自动拉取）
            model_name = os.environ.get(
                "OLLAMA_CHAT_MODEL",
                rag_conf["local"]["chat_model_name"],
            )
            base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
            _ensure_ollama_model(model_name, base_url)
            logger.info(f"[模型工厂]聊天模型(本地): {model_name} @ {base_url}")
            # keep_alive=3600：模型常驻内存 3600 秒（Ollama 默认 5 分钟即卸载），
            # 避免闲置后再次请求触发重新加载导致的长时间等待
            return ChatOllama(model=model_name, base_url=base_url, keep_alive=3600)

        # 远程模式：OpenAI 协议聊天模型
        api_key = os.environ.get("OPENAI_API_KEY", "not-configured")
        if api_key == "not-configured":
            logger.warning(
                "[模型工厂]远程模式未配置 OPENAI_API_KEY，"
                "模型可加载但调用时会失败。请在环境变量中设置 OPENAI_API_KEY。"
                "通义兼容端点示例: https://dashscope.aliyuncs.com/compatible-mode/v1"
            )
        model_name = get_remote_chat_model_name()
        base_url = os.environ.get("OPENAI_BASE_URL")
        logger.info(f"[模型工厂]聊天模型(远程): {model_name} @ {base_url}")
        return ChatOpenAI(model=model_name, api_key=api_key, base_url=base_url)


class EmbeddingFactory(BaseModelFactory):
    """文本嵌入模型"""
    def generator(self) -> Optional[Embeddings | BaseChatModel]:
        mode = _get_model_mode()
        if mode == "local":
            # 本地模式：Ollama 嵌入模型（启动前确保模型已存在，不存在则自动拉取）
            model_name = os.environ.get(
                "OLLAMA_EMBEDDING_MODEL",
                rag_conf["local"]["embedding_model_name"],
            )
            base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
            _ensure_ollama_model(model_name, base_url)
            logger.info(f"[模型工厂]嵌入模型(本地): {model_name} @ {base_url}")
            return OllamaEmbeddings(model=model_name, base_url=base_url, keep_alive=3600)

        # 远程模式：DashScope 嵌入模型（模型名可由 TEXT_EMBEDDING_MODEL 环境变量覆盖）
        model_name = get_remote_embedding_model_name()
        logger.info(f"[模型工厂]嵌入模型(远程-DashScope): {model_name}")
        return DashScopeTextEmbeddings(model=model_name)


chat_model = ChatModelFactory().generator()
embed_model = EmbeddingFactory().generator()

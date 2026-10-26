# -*- coding: utf-8 -*-
'''HyDE 假设文档生成（P3）

LLM（temperature=0，bind 不改共享单例）按原查询生成一段假设答案文本，
用其 embedding 做检索以拉近查询与文档的向量分布。假设文档仅用于检索，
不进入生成上下文。失败返回 None，调用方回退为仅用原查询。
'''
from langchain_core.language_models.chat_models import BaseChatModel

from app.utils.logger_handler import logger
from app.utils.prompt_loader import load_prompt

HYDE_PROMPT = load_prompt("hyde_prompt_path")


def generate_hypothetical_document(chat_model: BaseChatModel, query: str) -> str | None:
    '''生成假设答案段落（temperature=0）；失败/为空返回 None（调用方回退原查询）'''
    try:
        prompt = HYDE_PROMPT.format(question=query)
        response = chat_model.bind(temperature=0).invoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)
        text = content.strip()
    except Exception as e:
        logger.warning(f"[查询优化]hyde 假设文档生成失败，回退原查询：{e}")
        return None
    if not text:
        logger.warning("[查询优化]hyde 假设文档为空，回退原查询")
        return None
    return text

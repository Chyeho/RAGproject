# -*- coding: utf-8 -*-
'''multi-query 查询改写（P3）

LLM（temperature=0，bind 不改共享单例）把原查询改写为 N 个不同表述的
查询变体，供 QueryEnhancer 并行多路检索扩召回。任何失败（调用异常/解析
为空）返回空列表，调用方回退为仅用原查询，链路不中断。
'''
import re

from langchain_core.language_models.chat_models import BaseChatModel

from app.utils.logger_handler import logger
from app.utils.prompt_loader import load_prompt

MULTI_QUERY_PROMPT = load_prompt("multi_query_prompt_path")

# 常见编号/项目符号前缀：1. 1、1) 1） (1) （一） a. A) - * • 等
_BULLET_PREFIX = re.compile(
    r"^\s*(?:\d+\s*[\.、\)）]"
    r"|[a-zA-Z]\s*[\.、\)）]"
    r"|[（(][\da-zA-Z一二三四五六七八九十]+[)）]"
    r"|[-*•])\s*"
)


def parse_multi_queries(text: str, original: str, n: int) -> list[str]:
    '''逐行解析改写输出：去编号前缀/空白/代码围栏行，滤除空行、重复项与原查询，至多 n 条'''
    queries: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("```"):
            continue
        cleaned = _BULLET_PREFIX.sub("", line).strip()
        if not cleaned or cleaned == original or cleaned in queries:
            continue
        queries.append(cleaned)
        if len(queries) >= n:
            break
    return queries


def generate_multi_queries(chat_model: BaseChatModel, query: str, n: int = 3) -> list[str]:
    '''生成 n 个改写查询（temperature=0）；失败/解析为空返回 []（调用方回退原查询）'''
    try:
        prompt = MULTI_QUERY_PROMPT.format(question=query, n=n)
        response = chat_model.bind(temperature=0).invoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)
        queries = parse_multi_queries(content, query, n)
    except Exception as e:
        logger.warning(f"[查询优化]multi_query 改写失败，回退原查询：{e}")
        return []
    if not queries:
        logger.warning("[查询优化]multi_query 解析结果为空，回退原查询")
    return queries

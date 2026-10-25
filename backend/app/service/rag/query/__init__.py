# -*- coding: utf-8 -*-
'''查询优化包（P3：multi-query 改写 + HyDE 假设文档）'''
from app.service.rag.query.enhancer import MODES, QueryEnhancer
from app.service.rag.query.hyde import generate_hypothetical_document
from app.service.rag.query.multi_query import generate_multi_queries, parse_multi_queries

__all__ = [
    "MODES",
    "QueryEnhancer",
    "generate_multi_queries",
    "parse_multi_queries",
    "generate_hypothetical_document",
]

'''格式感知解析与智能分块包（P1）'''
from app.service.rag.chunking.strategy import apply_smart_rules, chunk_file

__all__ = ["chunk_file", "apply_smart_rules"]

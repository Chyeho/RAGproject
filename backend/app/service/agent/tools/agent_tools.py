'''agent工具库'''
from langchain_core.tools import tool
from app.service.rag import registry


@tool(description="从向量存储中检索参考资料")
def rag_summarize(query: str) -> str:
    answer, _ = registry.get_rag_service().rag_summarize(query)
    return answer

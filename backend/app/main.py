'''
系统后端主入口
'''
from fastapi import FastAPI
from routers import documents

app = FastAPI(
    title="宸甄 PrivRAG 企业私有知识库问答系统API",
    description="基于FastAPI+Langchain的企业私有知识库RAG问答系统后端API",
)

# 注册路由
app.include_router(router=documents.router)

'''
系统后端主入口
'''
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from app.database.db import init_db
from app.routers import auth, chat, debug, documents, settings, statistics
from app.service.rag.retrieval import bm25_retriever, fetch_chunk_documents, hybrid_enabled
from app.utils.config_handler import hybrid_conf
from app.utils.logger_handler import logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动：初始化数据库表结构；hybrid 开启时全量构建 BM25 内存索引"""
    logger.info("[启动]后端服务开始启动...")
    await init_db()
    # P2：BM25 启动全量构建（以 DB 为准）；失败不阻断启动，空索引降级（稠密路仍可用）
    if hybrid_enabled():
        try:
            bm25_retriever.load_documents(await fetch_chunk_documents())
        except Exception as e:
            logger.error(f"[启动]BM25 索引构建失败，本次以空索引降级运行：{e}", exc_info=True)
    logger.info("[启动]后端服务启动完成")
    yield
    logger.info("[关闭]后端服务已关闭")


app = FastAPI(
    title="宸甄 PrivRAG 企业私有知识库问答系统API",
    description="基于FastAPI+Langchain的企业私有知识库RAG问答系统后端API",
    lifespan=lifespan,
)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """统一异常响应：{code, message, data}（契约 0.2）"""
    detail = exc.detail
    if isinstance(detail, dict):
        return JSONResponse(status_code=exc.status_code, content=detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.status_code, "message": str(detail), "data": None},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """兜底异常处理：记录完整堆栈，返回统一 500（不向客户端泄漏内部错误细节）"""
    logger.error(
        f"[全局异常]{request.method} {request.url.path} 未捕获异常：{str(exc)}",
        exc_info=True,
    )
    return JSONResponse(
        status_code=500,
        content={"code": 5000, "message": "服务器内部错误", "data": None},
    )


@app.get("/api/health")
async def health():
    """健康检查"""
    return {"code": 0, "message": "success", "data": {"status": "ok"}}


# 注册路由
app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(documents.router)
app.include_router(statistics.router)
app.include_router(settings.router)
# 调试 trace 接口：生产默认关闭，演示环境通过 ENABLE_TRACE_API=true 开启
if bool(hybrid_conf.get("ENABLE_TRACE_API", False)):
    app.include_router(debug.router)

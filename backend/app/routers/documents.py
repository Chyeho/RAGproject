'''文档管理路由：上传（异步向量化）/列表/预览/下载/删除（三方同步）'''
import hashlib
import os
import time

from fastapi import APIRouter, BackgroundTasks, Depends, File, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.response import err, ok
from app.database.db import async_session, get_session
from app.dependencies import get_current_user
from app.models.document_chunk import DocumentChunk
from app.models.documents import Document
from app.models.users import User
from app.service.rag.vector_store import VectorStoreService
from app.utils.config_handler import qdrant_conf
from app.utils.logger_handler import logger
from app.utils.path_tool import get_abs_path

router = APIRouter(prefix="/api/documents", tags=["documents"])

# 上传限制（字节）：单文件 100MB，批量 125MB
MAX_FILE_SIZE = 100 * 1024 * 1024
MAX_BATCH_SIZE = 125 * 1024 * 1024
# 允许的文件格式（与前端上传弹窗说明一致）
ALLOWED_TYPES = {"pdf", "docx", "doc", "txt", "md", "xlsx"}

DATA_DIR = get_abs_path(qdrant_conf["data_path"])


def ensure_data_dir():
    """确保 data 目录存在"""
    os.makedirs(DATA_DIR, exist_ok=True)


def doc_to_dict(doc: Document) -> dict:
    """Document 模型 → 契约文档对象"""
    return {
        "id": doc.id,
        "name": doc.file_name,
        "type": doc.file_type,
        "size": doc.file_size or 0,
        "uploadedAt": doc.created_at.strftime("%Y-%m-%d %H:%M:%S") if doc.created_at else "",
        "vectorizeStatus": doc.vectorize_status,
        "vectorizeMessage": doc.vectorize_message or "",
    }


async def vectorize_document(document_id: int, file_path: str):
    """后台任务：切分 → 入 Qdrant → 写 document_chunk → 更新向量化状态"""
    try:
        vs = VectorStoreService()
        chunks = vs.upload_file(file_path, document_id=document_id)  # [(chunk_text, vector_id)]

        async with async_session() as session:
            for index, (text, vector_id) in enumerate(chunks):
                session.add(DocumentChunk(
                    chunk_index=index, content=text, vector_id=vector_id, document_id=document_id,
                ))
            doc = await session.get(Document, document_id)
            if doc:
                doc.vectorize_status = "success"
                doc.vectorize_message = None
                session.add(doc)
            await session.commit()
        logger.info(f"[文档]文档(id={document_id})异步向量化完成，共 {len(chunks)} 个分块")
    except Exception as e:
        logger.error(f"[文档]文档(id={document_id})异步向量化失败：{str(e)}", exc_info=True)
        async with async_session() as session:
            doc = await session.get(Document, document_id)
            if doc:
                doc.vectorize_status = "failed"
                doc.vectorize_message = str(e)[:500]
                session.add(doc)
                await session.commit()


@router.post("/upload")
async def upload_documents(
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """上传文档（多文件）：校验 → md5 去重 → 落盘 → 写 Document 行 → 后台异步向量化"""
    ensure_data_dir()

    # 批量总大小校验
    total_size = 0
    contents: list[tuple[UploadFile, bytes]] = []
    for f in files:
        content = await f.read()
        total_size += len(content)
        contents.append((f, content))
    if total_size > MAX_BATCH_SIZE:
        return err(4003, "批量文件总大小超过 125MB 限制")

    saved: list[dict] = []
    for f, content in contents:
        # 单文件大小校验
        if len(content) > MAX_FILE_SIZE:
            return err(4003, f"文件 {f.filename} 超过 100MB 大小限制")

        # 文件类型校验
        ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
        if ext not in ALLOWED_TYPES:
            return err(4002, f"文件 {f.filename} 类型不支持，支持格式：pdf、docx、doc、txt、md、xlsx")

        # md5 查重（迁移自 md5.txt：现由 document 表 md5_hash 承担）
        md5_hash = hashlib.md5(content).hexdigest()
        exist = (await session.exec(select(Document).where(Document.md5_hash == md5_hash))).first()
        if exist:
            logger.info(f"[文档]文件 {f.filename} 内容已存在知识库，跳过")
            continue

        # 落盘（时间戳前缀避免同名覆盖）
        file_path = os.path.join(DATA_DIR, f"{int(time.time() * 1000)}_{f.filename}")
        with open(file_path, "wb") as wf:
            wf.write(content)

        doc = Document(
            md5_hash=md5_hash,
            file_name=f.filename,
            file_type=ext,
            file_size=len(content),
            file_path=file_path,
            vectorize_status="processing",
            uploader_id=current_user.id,
        )
        session.add(doc)
        await session.commit()
        await session.refresh(doc)

        # 后台异步向量化
        background_tasks.add_task(vectorize_document, doc.id, file_path)
        saved.append(doc_to_dict(doc))
        logger.info(f"[文档]用户{current_user.id}上传文件 {f.filename} 成功（id={doc.id}）")

    return ok({"list": saved})


@router.get("")
async def get_documents(
    page: int = 1,
    size: int = 10,
    keyword: str = "",
    sortBy: str = "uploadedAt",
    sortOrder: str = "desc",
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """文档列表：分页 + 名称模糊搜索 + 排序"""
    page = max(1, page)
    size = max(1, min(size, 100))

    count_stmt = select(func.count()).select_from(Document)
    list_stmt = select(Document)
    if keyword:
        like = f"%{keyword}%"
        count_stmt = count_stmt.where(Document.file_name.like(like))
        list_stmt = list_stmt.where(Document.file_name.like(like))

    # 排序字段映射（契约 sortBy 取值）
    sort_map = {
        "uploadedAt": Document.created_at,
        "name": Document.file_name,
        "size": Document.file_size,
        "type": Document.file_type,
    }
    column = sort_map.get(sortBy, Document.created_at)
    list_stmt = list_stmt.order_by(
        column.asc() if sortOrder == "asc" else column.desc()
    ).offset((page - 1) * size).limit(size)

    total = (await session.exec(count_stmt)).one()
    rows = (await session.exec(list_stmt)).all()
    return ok({"list": [doc_to_dict(d) for d in rows], "total": total, "page": page, "size": size})


@router.get("/{document_id}/preview")
async def preview_document(
    document_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """文档预览：返回文件纯文本内容（超长截断）"""
    doc = await session.get(Document, document_id)
    if not doc or not doc.file_path or not os.path.exists(doc.file_path):
        return err(4001, "文档不存在")

    content = ""
    try:
        with open(doc.file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()[:10000]
    except Exception as e:
        logger.warning(f"[文档]预览文档(id={document_id})读取失败：{str(e)}")
        content = ""

    return ok({**doc_to_dict(doc), "content": content})


@router.get("/{document_id}/download")
async def download_document(
    document_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """文档下载：文件流"""
    doc = await session.get(Document, document_id)
    if not doc or not doc.file_path or not os.path.exists(doc.file_path):
        return err(4001, "文档不存在")
    return FileResponse(doc.file_path, filename=doc.file_name, media_type="application/octet-stream")


@router.delete("/{document_id}")
async def delete_document(
    document_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """删除文档：Qdrant 向量 → DB 行（级联 chunk）→ 物理文件，三方同步"""
    doc = await session.get(Document, document_id)
    if not doc:
        return err(4001, "文档不存在")

    # 1. 删除 Qdrant 向量
    chunks = (await session.exec(select(DocumentChunk).where(DocumentChunk.document_id == document_id))).all()
    vector_ids = [c.vector_id for c in chunks if c.vector_id]
    if vector_ids:
        try:
            VectorStoreService().delete_by_vector_ids(vector_ids)
        except Exception as e:
            logger.error(f"[文档]删除文档(id={document_id})向量失败：{str(e)}", exc_info=True)
            return err(5000, f"删除向量失败：{str(e)}")

    # 2. 删除 DB 行（document_chunk 级联删除）
    file_path = doc.file_path
    await session.delete(doc)
    await session.commit()

    # 3. 删除物理文件
    if file_path and os.path.exists(file_path):
        os.remove(file_path)

    logger.info(f"[文档]用户{current_user.id}删除文档 {doc.file_name}（id={document_id}）")
    return ok(None, "删除成功")

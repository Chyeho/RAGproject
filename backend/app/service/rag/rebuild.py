'''存量文档向量重建脚本（P1）：删除旧向量 + 重跑新链路 + 重建 document_chunk 表

用法（在 backend 目录下）：
    uv run python -m app.service.rag.rebuild --all          # 重建全部存量文档
    uv run python -m app.service.rag.rebuild --doc-id 3     # 重建指定文档

单文档流程：
    1. 按 document_chunk 表记录的 vector_id 删除 Qdrant 旧向量
    2. 删除旧 document_chunk 行
    3. 走新链路重新解析分块并写入 Qdrant（确定性 chunk ID，覆盖写入）
    4. 重建 document_chunk 行，更新 vectorize_status / vectorize_message
'''
import argparse
import asyncio
import os

from sqlmodel import select

from app.database.db import async_session
from app.models.document_chunk import DocumentChunk
from app.models.documents import Document
from app.service.rag.vector_store import VectorStoreService
from app.utils.logger_handler import logger

# 重建结果状态
RESULT_SUCCESS = "success"
RESULT_FAILED = "failed"
RESULT_SKIPPED = "skipped"
RESULT_NOT_FOUND = "not_found"


async def rebuild_document(vs: VectorStoreService, document_id: int) -> str:
    """重建单个文档：删旧向量/旧分块行 → 重跑新链路 → 重建分块行 → 更新向量化状态"""
    async with async_session() as session:
        doc = await session.get(Document, document_id)
        if not doc:
            logger.error(f"[重建]文档(id={document_id})不存在")
            return RESULT_NOT_FOUND

        # 源文件缺失：无法重建，跳过
        if not doc.file_path or not os.path.exists(doc.file_path):
            logger.warning(f"[重建]文档(id={document_id}) {doc.file_name} 源文件缺失：{doc.file_path}，跳过")
            return RESULT_SKIPPED

        # 1. 删除 Qdrant 旧向量（按 document_chunk 表记录的 vector_id）
        old_chunks = (await session.exec(
            select(DocumentChunk).where(DocumentChunk.document_id == document_id)
        )).all()
        try:
            vs.delete_by_vector_ids([c.vector_id for c in old_chunks if c.vector_id])
        except Exception as e:
            logger.error(f"[重建]文档(id={document_id})删除旧向量失败：{str(e)}", exc_info=True)
            return RESULT_FAILED

        # 2. 删除旧 document_chunk 行
        for chunk in old_chunks:
            await session.delete(chunk)
        await session.commit()

        # 3+4. 重跑新链路并重建分块行，更新向量化状态
        try:
            chunks = vs.upload_file(doc.file_path, document_id=document_id)  # [(chunk_text, vector_id)]
            for index, (text, vector_id) in enumerate(chunks):
                session.add(DocumentChunk(
                    chunk_index=index, content=text, vector_id=vector_id, document_id=document_id,
                ))
            doc.vectorize_status = "success"
            doc.vectorize_message = None
            session.add(doc)
            await session.commit()
            logger.info(f"[重建]文档(id={document_id}) {doc.file_name} 重建成功，共 {len(chunks)} 个分块")
            return RESULT_SUCCESS
        except Exception as e:
            logger.error(f"[重建]文档(id={document_id}) {doc.file_name} 重建失败：{str(e)}", exc_info=True)
            # flush 失败后 session 处于 PendingRollback 状态，必须先回滚才能写状态
            await session.rollback()
            doc.vectorize_status = "failed"
            doc.vectorize_message = str(e)[:500]
            session.add(doc)
            await session.commit()
            return RESULT_FAILED


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="存量文档向量重建：删除旧向量 + 重跑新链路 + 重建 document_chunk 表"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--all", action="store_true", help="重建全部存量文档")
    group.add_argument("--doc-id", type=int, default=None, help="重建指定文档（document 表 ID）")
    return parser.parse_args()


async def main() -> int:
    args = parse_args()
    vs = VectorStoreService()

    # 指定文档：失败即非零退出
    if args.doc_id is not None:
        result = await rebuild_document(vs, args.doc_id)
        return 0 if result == RESULT_SUCCESS else 1

    # 全量重建：单文档失败记录并继续，结束打印汇总
    async with async_session() as session:
        docs = (await session.exec(select(Document).order_by(Document.id))).all()
    logger.info(f"[重建]全量重建开始，共 {len(docs)} 个文档")

    counts = {RESULT_SUCCESS: 0, RESULT_FAILED: 0, RESULT_SKIPPED: 0, RESULT_NOT_FOUND: 0}
    for doc in docs:
        result = await rebuild_document(vs, doc.id)
        counts[result] += 1

    summary = (
        f"重建完成：成功 {counts[RESULT_SUCCESS]}，失败 {counts[RESULT_FAILED]}，"
        f"跳过（文件缺失）{counts[RESULT_SKIPPED]}，未找到 {counts[RESULT_NOT_FOUND]}"
    )
    logger.info(f"[重建]{summary}")
    print(summary)
    return 1 if counts[RESULT_FAILED] else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

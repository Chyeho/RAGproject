# -*- coding: utf-8 -*-
'''评测语料批量入库 CLI：复用 Web 上传链路（与手工上传完全同构，执行文档 4.6）

用法：
    uv run python -m app.service.eval.ingest
    uv run python -m app.service.eval.ingest --dir app/service/eval/datasets/corpus_v2

流程（逐条对齐 app.routers.documents.upload_documents）：
1. 遍历语料目录，按上传白名单 ALLOWED_TYPES 过滤扩展名
2. md5 查重（document.md5_hash）：已成功入库则跳过（幂等，可重跑）；
   failed / 残留 processing 行复用原 id+file_path 重试（重试前清旧 chunk 行，
   Qdrant 侧 chunk_id 为确定性 uuid5，upsert 天然幂等无需清理）
3. 落盘 DATA_DIR（时间戳前缀避免同名覆盖），file_name 保留原文件名
4. 写 Document 行（uploader_id 取 DB 首个用户），同步 await vectorize_document
   （其内部自带异常捕获，失败会写回 failed 状态并记录 vectorize_message）
5. 汇总：文件总数 / 跳过 / 成功 / 失败 / 新增 chunks / 全库成功文档数与总 chunks
'''
import argparse
import asyncio
import hashlib
import os
import time

from sqlalchemy import delete, func, select

from app.database.db import async_session
from app.models.document_chunk import DocumentChunk
from app.models.documents import Document
from app.models.users import User
from app.routers.documents import ALLOWED_TYPES, DATA_DIR, ensure_data_dir, vectorize_document
from app.utils.logger_handler import logger

DEFAULT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "datasets", "corpus_v2")


async def ingest_dir(corpus_dir: str) -> dict:
    """把目录内全部语料按上传链路入库，返回汇总统计"""
    if not os.path.isdir(corpus_dir):
        raise FileNotFoundError(f"语料目录不存在：{corpus_dir}")
    files = sorted(fn for fn in os.listdir(corpus_dir)
                   if fn.rsplit(".", 1)[-1].lower() in ALLOWED_TYPES)
    if not files:
        raise FileNotFoundError(f"语料目录内没有可入库文件：{corpus_dir}")

    ensure_data_dir()
    stats = {"total": len(files), "skipped": 0, "ingested": 0,
             "failed": 0, "chunks_added": 0}

    async with async_session() as session:
        uploader = (await session.execute(select(User.id).limit(1))).scalar()
        if uploader is None:
            raise RuntimeError("document.uploader_id 需要至少一个用户，请先注册用户")

        for fn in files:
            src = os.path.join(corpus_dir, fn)
            with open(src, "rb") as f:
                content = f.read()
            md5_hash = hashlib.md5(content).hexdigest()

            # md5 查重：success 跳过；failed / 残留 processing 复用原行重试
            exist = (await session.execute(
                select(Document.id, Document.vectorize_status, Document.file_path)
                .where(Document.md5_hash == md5_hash))).one_or_none()
            if exist and exist.vectorize_status == "success":
                stats["skipped"] += 1
                logger.info(f"[入库]文件 {fn} 内容已存在知识库，跳过")
                continue

            if exist:
                # 失败重试：复用原 id+file_path，先清旧 chunk 行避免重复插行
                # （Qdrant 侧 chunk_id 为确定性 uuid5，upsert 天然幂等无需清理）
                doc_id, file_path = exist.id, exist.file_path
                await session.execute(
                    delete(DocumentChunk).where(DocumentChunk.document_id == doc_id))
                await session.commit()
                logger.info(f"[入库]文件 {fn} 原记录(id={doc_id})状态 {exist.vectorize_status}，重试")
            else:
                file_path = os.path.join(DATA_DIR, f"{int(time.time() * 1000)}_{fn}")
                with open(file_path, "wb") as wf:
                    wf.write(content)

                doc = Document(
                    md5_hash=md5_hash,
                    file_name=fn,
                    file_type=fn.rsplit(".", 1)[-1].lower(),
                    file_size=len(content),
                    file_path=file_path,
                    vectorize_status="processing",
                    uploader_id=uploader,
                )
                session.add(doc)
                await session.commit()
                await session.refresh(doc)
                doc_id = doc.id

            await vectorize_document(doc_id, file_path)   # 同步等待，内部自带失败兜底

            # vectorize_document 在独立 session 提交；本 session 的事务快照早于该提交
            # （MySQL REPEATABLE READ，refresh 后未开启新事务），须用新 session 核对状态
            async with async_session() as check:
                status = (await check.execute(
                    select(Document.vectorize_status, Document.vectorize_message)
                    .where(Document.id == doc_id))).one()
                if status.vectorize_status == "success":
                    n_chunks = (await check.execute(
                        select(func.count()).select_from(DocumentChunk)
                        .where(DocumentChunk.document_id == doc_id))).scalar()
                    stats["ingested"] += 1
                    stats["chunks_added"] += n_chunks
                    logger.info(f"[入库]文件 {fn} 成功（id={doc_id}，{n_chunks} chunks）")
                else:
                    stats["failed"] += 1
                    logger.error(f"[入库]文件 {fn} 向量化失败：{status.vectorize_message}")

    # 全库口径（验证 4.6 迭代目标：65 份 / 总 chunks ≈ 450+）
    async with async_session() as session:
        stats["library_success_docs"] = (await session.execute(
            select(func.count()).select_from(Document)
            .where(Document.vectorize_status == "success"))).scalar()
        stats["library_total_chunks"] = (await session.execute(
            select(func.count()).select_from(DocumentChunk))).scalar()
    return stats


def main():
    parser = argparse.ArgumentParser(description="评测语料批量入库 CLI（复用上传链路，md5 幂等可重跑）")
    parser.add_argument("--dir", default=DEFAULT_DIR, help=f"语料目录（默认 corpus_v2）")
    args = parser.parse_args()
    stats = asyncio.run(ingest_dir(args.dir))
    print(f"\n入库汇总：共 {stats['total']} 个文件，新增 {stats['ingested']}"
          f"（+{stats['chunks_added']} chunks），跳过 {stats['skipped']}，失败 {stats['failed']}")
    print(f"当前知识库：成功文档 {stats['library_success_docs']} 份，"
          f"总 chunks {stats['library_total_chunks']}")


if __name__ == "__main__":
    main()

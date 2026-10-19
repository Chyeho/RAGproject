'''评测编排 CLI：直接实例化现有链路对象（不动链路一行代码）

用法（执行文档 4.4）：
    uv run python -m app.service.eval.runner --tag P0-baseline --retrieval-only
    uv run python -m app.service.eval.runner --tag P0-baseline --full

流程：
1. 加载评测集，按 source_file 反查 document 表填充 document_id（库重建后无需改评测集）
2. 预检：样例未成功入库的打印告警（P0 已知缺口：docx/xlsx/md 当前链路无法向量化，
   这些题文档级命中记 0，正是基线要暴露的数据）
3. 检索评测：retriever.invoke(question) → 两级命中判定 → 确定性指标聚合
4. 生成评测（--full）：同问题先独立检索拿 contexts（与链内检索同 retriever 同 query，
   结果一致），再调 rag_summarize 生成答案，LLM 裁判打分；每题独立会话
   eval_{tag}_{qid} 并在生成前 clear()，重跑同 tag 不受旧历史污染
5. 报告写入 backend/eval_reports/{时间戳}_{tag}.json/.md
'''
import argparse
import asyncio
import os
from datetime import datetime

from sqlalchemy import select

from app.modelFactory.factory import chat_model
from app.service.eval import report as report_mod
from app.service.eval.dataset import DATASET_PATH, dataset_md5, load_dataset
from app.service.eval.llm_judge import aggregate_generation, answer_relevancy, faithfulness
from app.service.eval.metrics import aggregate, aggregate_by, judge_retrieval
from app.service.history.history_store import get_chat_history
from app.service.rag.rag_service import RagSummarizeService
from app.service.rag.vector_store import VectorStoreService
from app.utils.config_handler import qdrant_conf, rag_conf
from app.utils.logger_handler import logger


def snapshot_config() -> dict:
    """链路配置快照（写入报告头部，保证各期评测可追溯）

    模式与模型名的取值优先级与 modelFactory.factory 完全一致：
    MODEL_MODE 环境变量定模式，模型名环境变量可覆盖 yml 配置。
    """
    mode = os.environ.get("MODEL_MODE", "remote").lower()
    if mode == "local":
        chat_name = os.environ.get("OLLAMA_CHAT_MODEL",
                                   rag_conf["local"]["chat_model_name"])
        embed_name = os.environ.get("OLLAMA_EMBEDDING_MODEL",
                                    rag_conf["local"]["embedding_model_name"])
    else:
        mode = "remote"
        chat_name = os.environ.get("OPENAI_CHAT_MODEL",
                                   rag_conf["remote"]["chat_model_name"])
        embed_name = rag_conf["remote"]["embedding_model_name"]
    return {
        "model_mode": mode,
        "chat_model_name": chat_name,
        "embedding_model_name": embed_name,
        "qdrant": {k: qdrant_conf.get(k) for k in
                   ("collection_name", "chunk_size", "chunk_overlap", "k", "separators")},
    }


async def _fetch_document_map_async() -> dict[str, int]:
    """查询 document 表：file_name -> document_id（仅取向量化成功的）"""
    from app.database.db import async_session
    from app.models.documents import Document
    async with async_session() as session:
        rows = (await session.execute(
            select(Document.id, Document.file_name, Document.vectorize_status)
        )).all()
    return {row.file_name: row.id for row in rows if row.vectorize_status == "success"}


def fetch_document_map() -> dict[str, int]:
    return asyncio.run(_fetch_document_map_async())


def run_eval(tag: str, mode: str, k: int | None = None, limit: int | None = None,
             dataset_path: str = DATASET_PATH) -> dict:
    """执行评测并落盘报告

    Args:
        tag: 评测标签（如 P0-baseline），用于报告文件名与会话隔离
        mode: "retrieval" 仅检索 / "full" 检索+生成
        k: 覆盖 top-k（None 时用 qdrant_config.yml 的 k）
        limit: 只评测前 N 题（调试用）
    """
    dataset = load_dataset(dataset_path)
    if limit:
        dataset = dataset[:limit]

    doc_map = fetch_document_map()
    missing = sorted({qa["source_file"] for qa in dataset if qa["source_file"] not in doc_map})
    if missing:
        logger.warning(f"[评测预检]以下样例文件未成功入库，其问题文档级命中将记 0（P0 已知格式缺口）：{missing}")

    svc = VectorStoreService()
    retriever = (svc.get_retriever() if k is None
                 else svc.vector_store.as_retriever(search_kwargs={"k": k}))
    rag = RagSummarizeService() if mode == "full" else None

    records, details = [], []
    faith_scores, relev_scores = [], []

    for i, qa in enumerate(dataset, 1):
        gt_doc_id = doc_map.get(qa["source_file"], -1)

        # ---- 检索评测（与链内检索同源：同 retriever 同 query）----
        docs = retriever.invoke(qa["question"])
        rec = judge_retrieval(qa["qid"], docs, gt_doc_id, qa["source_passage"])
        records.append(rec)

        detail = {
            "qid": qa["qid"],
            "question": qa["question"],
            "ground_truth_answer": qa["ground_truth_answer"],
            "question_type": qa["question_type"],
            "source_file": qa["source_file"],
            "document_id": gt_doc_id if gt_doc_id != -1 else None,
            "doc_hit": any(rec.doc_hits),
            "passage_hit": any(rec.passage_hits),
            "best_overlap": round(rec.best_overlap, 4),
            "retrieved": [
                {"document_id": (d.metadata or {}).get("document_id"),
                 "text": d.page_content[:80]}
                for d in docs
            ],
        }

        # ---- 生成评测（--full）----
        if mode == "full":
            session_id = f"eval_{tag}_{qa['qid']}"
            get_chat_history(session_id).clear()   # 幂等：重跑同 tag 不受旧历史污染
            contexts = [d.page_content for d in docs]
            answer = rag.rag_summarize(qa["question"], session_id=session_id)
            faith = faithfulness(chat_model, qa["question"], answer, contexts)
            relev = answer_relevancy(chat_model, qa["question"], answer)
            faith_scores.append(faith)
            relev_scores.append(relev)
            detail.update({"answer": answer, "faithfulness": faith, "answer_relevancy": relev})

        details.append(detail)
        print(f"[{i}/{len(dataset)}] {qa['qid']} doc_hit={detail['doc_hit']} "
              f"passage_hit={detail['passage_hit']}", flush=True)

    # ---- 聚合 ----
    type_map = {qa["qid"]: qa["question_type"] for qa in dataset}
    file_map = {qa["qid"]: qa["source_file"] for qa in dataset}

    result = {
        "meta": {
            "tag": tag,
            "mode": mode,
            "finished_at": datetime.now().isoformat(timespec="seconds"),
            "num_questions": len(dataset),
            "k": k if k is not None else qdrant_conf["k"],
            "config_snapshot": snapshot_config(),
            "dataset_md5": dataset_md5(dataset_path),
        },
        "missing_source_files": missing,
        "retrieval": aggregate(records),
        "retrieval_by_type": aggregate_by(records, key_of=lambda r: type_map[r.qid]),
        "retrieval_by_source_file": aggregate_by(records, key_of=lambda r: file_map[r.qid]),
    }
    if mode == "full":
        result["generation"] = {
            "faithfulness": aggregate_generation(faith_scores),
            "answer_relevancy": aggregate_generation(relev_scores),
        }
    result["details"] = details

    json_path, md_path = report_mod.save_report(result, tag)
    print(f"\n报告已生成：\n  {json_path}\n  {md_path}")
    return result


def main():
    parser = argparse.ArgumentParser(description="RAG 链路评测 CLI（P0 评测体系）")
    parser.add_argument("--tag", required=True, help="评测标签，如 P0-baseline")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--retrieval-only", action="store_true", help="仅评测检索指标（快）")
    group.add_argument("--full", action="store_true", help="评测检索+生成全量")
    parser.add_argument("--k", type=int, default=None, help="覆盖 top-k（默认取 qdrant_config.yml 的 k）")
    parser.add_argument("--limit", type=int, default=None, help="只评测前 N 题（调试用）")
    args = parser.parse_args()
    run_eval(tag=args.tag, mode="full" if args.full else "retrieval",
             k=args.k, limit=args.limit)


if __name__ == "__main__":
    main()

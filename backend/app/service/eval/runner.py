'''评测编排 CLI：直接实例化现有链路对象（不动链路一行代码）

用法（执行文档 4.4 / 6.6）：
    uv run python -m app.service.eval.runner --tag P0-baseline --retrieval-only
    uv run python -m app.service.eval.runner --tag P0-baseline --full
    uv run python -m app.service.eval.runner --tag P2-hybrid-rerank --preset hybrid-rerank --full

流程：
1. 加载评测集，按 source_file 反查 document 表填充 document_id（库重建后无需改评测集）
2. 预检：样例未成功入库的打印告警（P0 已知缺口：docx/xlsx/md 当前链路无法向量化，
   这些题文档级命中记 0，正是基线要暴露的数据）
3. 检索评测：retriever.invoke(question) → 两级命中判定 → 确定性指标聚合
   （P2 起检索链路经 build_retriever 组装；--preset 固定四组开关口径，与 --k 互斥）
4. 生成评测（--full）：同问题先独立检索拿 contexts，并将同一 retriever 注入
   RagSummarizeService（链内外同源），再调 rag_summarize 生成答案，LLM 裁判打分；
   每题独立会话 eval_{tag}_{qid} 并在生成前 clear()，重跑同 tag 不受旧历史污染
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
from app.service.rag.retrieval import bm25_retriever, fetch_chunk_documents
from app.service.rag.retrieval.hybrid_retriever import _effective_conf, build_retriever
from app.service.rag.vector_store import VectorStoreService
from app.utils.config_handler import qdrant_conf, rag_conf, retrieval_conf
from app.utils.logger_handler import logger

# P2 四组链路预设（执行文档 6.6；overrides 优先于 retrieval_config.yml）
# legacy_k 标量覆盖仅对"全关闭"组合生效 → dense-only 借此得到 k=5 的 @5 同口径
PRESETS: dict[str, dict] = {
    "legacy": {"hybrid": {"enabled": False}, "rerank": {"enabled": False}},           # 旧链路回退：dense k=legacy_k(3)
    "dense-only": {"hybrid": {"enabled": False}, "rerank": {"enabled": False}, "legacy_k": 5},  # 纯稠密 k=5
    "hybrid": {"hybrid": {"enabled": True}, "rerank": {"enabled": False}},            # dense+bm25 → RRF → top_k(5)
    "hybrid-rerank": {"hybrid": {"enabled": True}, "rerank": {"enabled": True}},      # RRF(topn) → 精排 → top_k(5)
}


def _effective_output_k(conf: dict) -> int:
    """链路最终送入生成的文档数（与 retrieval_config.yml 头部注释口径一致）"""
    if bool(conf["rerank"].get("enabled", False)):
        return int(conf["rerank"].get("top_k", 5))
    if bool(conf["hybrid"].get("enabled", False)):
        return int(conf["top_k"])
    return int(conf["legacy_k"])


def snapshot_config(overrides: dict | None = None) -> dict:
    """链路配置快照（写入报告头部，保证各期评测可追溯）

    模式与模型名的取值优先级与 modelFactory.factory 完全一致：
    MODEL_MODE 环境变量定模式，模型名环境变量可覆盖 yml 配置。
    P2 起追加 retrieval 段（hybrid/rerank 开关与口径，含 preset overrides 合并结果）。
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
    chunking = retrieval_conf.get("chunking", {})
    conf = _effective_conf(overrides)
    return {
        "model_mode": mode,
        "chat_model_name": chat_name,
        "embedding_model_name": embed_name,
        # P2 起 chunk/k 参数收敛于 retrieval_config.yml；qdrant 键保留原结构以便与 P0/P1 报告对比
        "qdrant": {
            "collection_name": qdrant_conf.get("collection_name"),
            "chunk_size": chunking.get("chunk_size"),
            "chunk_overlap": chunking.get("chunk_overlap"),
            "k": retrieval_conf.get("legacy_k"),
            "separators": chunking.get("separators"),
        },
        "retrieval": {
            "hybrid": {
                "enabled": bool(conf["hybrid"].get("enabled", False)),
                "dense_topn": conf["hybrid"].get("dense_topn"),
                "bm25_topn": conf["hybrid"].get("bm25_topn"),
                "rrf_k": conf["hybrid"].get("rrf_k"),
                "topn": conf["hybrid"].get("topn"),
            },
            "rerank": {
                "enabled": bool(conf["rerank"].get("enabled", False)),
                "remote_model": conf["rerank"].get("remote_model"),
                "local_model": conf["rerank"].get("local_model"),
                "top_k": conf["rerank"].get("top_k"),
            },
            "top_k": conf["top_k"],
            "legacy_k": conf["legacy_k"],
        },
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
             dataset_path: str = DATASET_PATH, preset: str | None = None) -> dict:
    """执行评测并落盘报告

    Args:
        tag: 评测标签（如 P0-baseline），用于报告文件名与会话隔离
        mode: "retrieval" 仅检索 / "full" 检索+生成
        k: 覆盖 top-k（直连稠密检索，与 --preset 互斥）
        limit: 只评测前 N 题（调试用）
        preset: P2 链路预设（legacy/dense-only/hybrid/hybrid-rerank），
                None 时用 retrieval_config.yml 文件配置组装
    """
    dataset = load_dataset(dataset_path)
    if limit:
        dataset = dataset[:limit]

    doc_map = fetch_document_map()
    missing = sorted({qa["source_file"] for qa in dataset if qa["source_file"] not in doc_map})
    if missing:
        logger.warning(f"[评测预检]以下样例文件未成功入库，其问题文档级命中将记 0（P0 已知格式缺口）：{missing}")

    overrides = PRESETS.get(preset) if preset else None
    conf = _effective_conf(overrides)

    # hybrid 生效时确保 BM25 内存索引就绪（CLI 无应用 lifespan，这里按 DB 全量构建）
    if bool(conf["hybrid"].get("enabled", False)):
        bm25_retriever.load_documents(asyncio.run(fetch_chunk_documents()))

    svc = VectorStoreService()
    if k is not None:
        retriever = svc.vector_store.as_retriever(search_kwargs={"k": k})
    else:
        retriever = build_retriever(svc, overrides=overrides)
    rag = RagSummarizeService(retriever=retriever) if mode == "full" else None

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
            "k": k if k is not None else _effective_output_k(conf),
            "preset": preset,
            "config_snapshot": snapshot_config(overrides),
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
    parser = argparse.ArgumentParser(description="RAG 链路评测 CLI（P0 评测体系，P2 起支持 --preset）")
    parser.add_argument("--tag", required=True, help="评测标签，如 P0-baseline / P2-hybrid-rerank")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--retrieval-only", action="store_true", help="仅评测检索指标（快）")
    group.add_argument("--full", action="store_true", help="评测检索+生成全量")
    parser.add_argument("--preset", choices=sorted(PRESETS), default=None,
                        help="P2 链路预设：legacy(旧链路回退)/dense-only(纯稠密k=5)/hybrid(RRF)/hybrid-rerank(RRF+精排)")
    parser.add_argument("--k", type=int, default=None, help="覆盖 top-k（直连稠密检索，与 --preset 互斥）")
    parser.add_argument("--limit", type=int, default=None, help="只评测前 N 题（调试用）")
    args = parser.parse_args()
    if args.preset and args.k is not None:
        parser.error("--preset 与 --k 互斥（preset 已固定各组口径，覆盖请改 retrieval_config.yml 或 preset 定义）")
    run_eval(tag=args.tag, mode="full" if args.full else "retrieval",
             k=args.k, limit=args.limit, preset=args.preset)


if __name__ == "__main__":
    main()

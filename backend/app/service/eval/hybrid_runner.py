# -*- coding: utf-8 -*-
'''A/B 对照评测：A=全直调（baseline，复现改造前行为），B=规则路由混合

用法（backend 目录）：
    uv run python -m app.service.eval.hybrid_runner --tag AB-A --group A
    uv run python -m app.service.eval.hybrid_runner --tag AB-B --group B
    uv run python -m app.service.eval.hybrid_runner --tag AB-smoke --group both \
        --limit-simple 10 --limit-complex 10

简单集 = eval_dataset_v2.json（剔除已选入复杂集的 qid）
复杂集 = complex_qids_v2.json（从 v2 人工确认）+ eval_complex_authored_v2.json（同语料补充）
输出：backend/eval_reports/{时间戳}_{tag}.json/.csv，两组时另出 {时间戳}_AB-compare.md
'''
import argparse
import csv
import json
import math
import os
import time
from collections import Counter
from datetime import datetime

from app.modelFactory.factory import get_eval_chat_model, get_eval_chat_model_name
from app.service.eval import llm_judge
from app.service.eval.complex_subset import (
    AUTHORED_PATH,
    COMPLEX_QIDS_PATH,
    DATASET_V2_PATH,
    load_complex_dataset,
)
from app.service.eval.dataset import load_dataset
from app.service.eval.metrics import judge_retrieval
from app.service.eval.report import REPORTS_DIR
from app.service.history.history_store import get_chat_history
from app.service.orchestration.hybrid_orchestrator import HybridOrchestrator
from app.service.rag.rag_service import RagSummarizeService
from app.utils.config_handler import hybrid_conf
from app.utils.logger_handler import logger

GROUP_A = "A"
GROUP_B = "B"
_UNSET = object()

CSV_FIELDS = (
    "group", "qid", "is_complex", "complex_source", "question", "source_file",
    "route", "answer_source", "fallback", "fallback_reason", "tool_calls",
    "doc_hit", "passage_hit", "correctness", "faithfulness", "answer_relevancy",
    "task_completion", "latency_ms", "answer",
)


# =====================================================================
# 聚合
# =====================================================================

def _p95(values: list[int]) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]


def _mean(values: list) -> float | None:
    items = [float(v) for v in values if v is not None]
    return sum(items) / len(items) if items else None


def _rate(values: list) -> float | None:
    items = [bool(v) for v in values if v is not None]
    return sum(items) / len(items) if items else None


def summarize_records(records: list[dict]) -> dict:
    """聚合一组明细：检索命中、正确率、忠实度、延迟、工具调用与降级分布"""
    reasons = Counter(r["fallback_reason"] for r in records if r.get("fallback_reason"))
    return {
        "num_questions": len(records),
        "doc_hit_rate": _rate([r["doc_hit"] for r in records]),
        "passage_hit_rate": _rate([r["passage_hit"] for r in records]),
        "answer_correctness": llm_judge.aggregate_correctness(
            [r["correctness"] for r in records]),
        "faithfulness": llm_judge.aggregate_generation(
            [r["faithfulness"] for r in records]),
        "answer_relevancy": llm_judge.aggregate_generation(
            [r["answer_relevancy"] for r in records]),
        "avg_latency_ms": _mean([r["latency_ms"] for r in records]),
        "p95_latency_ms": _p95([r["latency_ms"] for r in records]),
        "task_completion_rate": _rate([r.get("task_completion") for r in records]),
        "avg_tool_calls": _mean([r["tool_calls"] for r in records]),
        "fallback_rate": _rate([r.get("fallback") for r in records]),
        "fallback_reasons": dict(reasons),
    }


# =====================================================================
# 单题执行
# =====================================================================

def evaluate_question(qa: dict, is_complex: bool, group: str, tag: str,
                      rag, orchestrator, judge_model, gt_doc_id: int) -> dict:
    """执行一题并返回明细（A 组强制直调，B 组走编排器）"""
    session_id = f"eval_{tag}_{group}_{qa['qid']}"
    get_chat_history(session_id).clear()      # 幂等：重跑同 tag 不受旧历史污染

    started = time.monotonic()
    if group == GROUP_A:
        answer, docs = rag.rag_summarize(qa["question"], session_id=session_id)
        trace = {"route": "rag_direct", "route_reason": "A 组强制直调",
                 "matched_rules": [], "answer_source": "rag_direct",
                 "fallback": False, "fallback_reason": None, "tool_calls": 0}
    else:
        result = orchestrator.answer(qa["question"], session_id)
        answer, docs, trace = result.answer, result.documents, result.trace
    latency_ms = int((time.monotonic() - started) * 1000)

    retrieval = judge_retrieval(qa["qid"], docs, gt_doc_id, qa.get("source_passage", ""))
    detail = {
        "group": group,
        "qid": qa["qid"],
        "is_complex": is_complex,
        "complex_source": qa.get("complex_source"),
        "question": qa["question"],
        "source_file": qa["source_file"],
        "ground_truth_answer": qa["ground_truth_answer"],
        "document_id": gt_doc_id if gt_doc_id != -1 else None,
        "route": trace.get("route"),
        "answer_source": trace.get("answer_source"),
        "fallback": bool(trace.get("fallback")),
        "fallback_reason": trace.get("fallback_reason"),
        "tool_calls": int(trace.get("tool_calls", 0) or 0),
        "trace": {k: trace.get(k) for k in
                  ("route", "route_reason", "matched_rules", "answer_source",
                   "fallback", "fallback_reason", "tool_calls", "total_ms")},
        "doc_hit": any(retrieval.doc_hits),
        "passage_hit": any(retrieval.passage_hits),
        "best_overlap": round(retrieval.best_overlap, 4),
        "latency_ms": latency_ms,
        "answer": answer,
    }

    if judge_model is not None:
        detail["correctness"] = llm_judge.correctness(
            judge_model, qa["question"], qa["ground_truth_answer"], answer)
        detail["faithfulness"] = llm_judge.faithfulness(
            judge_model, qa["question"], answer, [d.page_content for d in docs])
        detail["answer_relevancy"] = llm_judge.answer_relevancy(
            judge_model, qa["question"], answer)
    else:
        detail.update(correctness=None, faithfulness=None, answer_relevancy=None)

    if not is_complex:
        detail["task_completion"] = None
    elif judge_model is None:
        detail["task_completion"] = bool(str(answer or "").strip())
    else:
        detail["task_completion"] = bool(
            str(answer or "").strip() and detail["correctness"] is not None
            and detail["correctness"] >= 0.5)
    return detail


def build_targets(simple_dataset: list[dict], complex_dataset: list[dict],
                  limit_simple: int | None = None,
                  limit_complex: int | None = None) -> list[tuple[dict, bool]]:
    """简单集剔除已选入复杂集的 qid；返回 [(qa, is_complex)]"""
    selected = {qa["qid"] for qa in complex_dataset
                if qa.get("complex_source") == "v2_selected"}
    simple = [qa for qa in simple_dataset if qa["qid"] not in selected]
    if limit_simple:
        simple = simple[:limit_simple]
    if limit_complex:
        complex_dataset = complex_dataset[:limit_complex]
    return [(qa, False) for qa in simple] + [(qa, True) for qa in complex_dataset]


# =====================================================================
# 报告输出
# =====================================================================

def _get(summary: dict, path: str):
    value = summary
    for key in path.split("."):
        value = value.get(key, {}) if isinstance(value, dict) else None
    return value


def _fmt(value, kind: str = "float") -> str:
    if value is None:
        return "-"
    if kind == "rate":
        return f"{float(value):.2%}"
    if kind == "int":
        return str(int(value))
    if kind == "pct":
        return f"{float(value):.2%}"
    return f"{float(value):.4f}"


_METRIC_ROWS = (
    ("num_questions", "题目数", "int"),
    ("doc_hit_rate", "文档级 HitRate", "rate"),
    ("passage_hit_rate", "片段级 HitRate", "rate"),
    ("answer_correctness.mean", "答案正确率（0/0.5/1）", "float"),
    ("faithfulness.mean", "Faithfulness", "float"),
    ("answer_relevancy.mean", "AnswerRelevancy", "float"),
    ("avg_latency_ms", "平均延迟(ms)", "int"),
    ("p95_latency_ms", "P95 延迟(ms)", "int"),
    ("task_completion_rate", "任务完成率", "rate"),
    ("avg_tool_calls", "平均工具调用次数", "float"),
    ("fallback_rate", "降级率", "rate"),
)


def render_markdown(result: dict) -> str:
    meta = result["meta"]
    groups = meta["groups"]
    lines = [f"# RAG+ReAct A/B 评测报告：{meta['tag']}", "", "## 基本信息", ""]
    lines += ["| 项 | 值 |", "|---|---|"]
    lines += [
        f"| 评测时间 | {meta['finished_at']} |",
        f"| 分组 | {'、'.join(groups)} |",
        f"| 简单集题数 | {meta['num_simple']} |",
        f"| 复杂集题数 | {meta['num_complex']} |",
        f"| 简单集 | {meta['dataset']} |",
        f"| 复杂题 qid 清单 | {meta['complex_qids']} |",
        f"| 补充复杂题集 | {meta['authored']} |",
        f"| 评测模型 | {meta['eval_chat_model']} |",
        f"| 混合开关 | {'开启' if meta['hybrid_router_enabled'] else '关闭'} |",
        f"| 文档映射 | {'可用' if meta.get('doc_map_available') else '不可用（命中率记 0，结论请看正确率/延迟）'} |",
    ]
    if meta.get("missing_complex_qids"):
        lines.append(f"| 未找到的复杂题 qid | {'、'.join(meta['missing_complex_qids'])} |")

    for scope, label in (("simple", "简单集"), ("complex", "复杂集"), ("all", "合计")):
        columns = [f"{g}-{label}" for g in groups]
        lines += ["", f"## 指标对照（{label}）", ""]
        lines.append("| 指标 | " + " | ".join(columns) + " |")
        lines.append("|---|" + "---|" * len(columns))
        for path, name, kind in _METRIC_ROWS:
            cells = [_fmt(_get(result["groups"][g]["summary"][scope], path), kind)
                     for g in groups]
            lines.append(f"| {name} | " + " | ".join(cells) + " |")

    lines += ["", "## 降级分布（复杂集）", ""]
    lines.append("| 组 | fallback_reason | 次数 |")
    lines.append("|---|---|---|")
    has_reason = False
    for g in groups:
        for reason, count in result["groups"][g]["summary"]["complex"].get(
                "fallback_reasons", {}).items():
            has_reason = True
            lines.append(f"| {g} | {reason} | {count} |")
    if not has_reason:
        lines.append("| - | 无降级 | 0 |")

    lines += ["", "## 口径说明", "",
              "- A 组强制 RAG 直调，复现改造前行为；B 组按 router_rules.yml 路由",
              "- 答案正确率：LLM 裁判对比标准答案，三档 0/0.5/1，解析失败不计均值",
              "- 任务完成率：复杂题答案非空且正确率 ≥ 0.5",
              "- 复杂集均由同一 65 份语料构造，跨文档题以主文档作为检索命中口径",
              ""]
    return "\n".join(lines)


def write_reports(result: dict, tag: str, reports_dir: str = REPORTS_DIR) -> dict:
    os.makedirs(reports_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = os.path.join(reports_dir, f"{ts}_{tag}.json")
    csv_path = os.path.join(reports_dir, f"{ts}_{tag}.csv")
    md_name = f"{ts}_AB-compare.md" if len(result["meta"]["groups"]) == 2 else f"{ts}_{tag}.md"
    md_path = os.path.join(reports_dir, md_name)

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for group in result["meta"]["groups"]:
            for row in result["groups"][group]["details"]:
                writer.writerow({k: ("" if row.get(k) is None else row.get(k))
                                 for k in CSV_FIELDS})

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(render_markdown(result))
    return {"json": json_path, "csv": csv_path, "markdown": md_path}


# =====================================================================
# 主流程
# =====================================================================

def run_ab_eval(tag: str, groups: tuple[str, ...] = (GROUP_A, GROUP_B),
                limit_simple: int | None = None, limit_complex: int | None = None,
                dataset_path: str = DATASET_V2_PATH,
                complex_qids_path: str = COMPLEX_QIDS_PATH,
                authored_path: str = AUTHORED_PATH,
                rag=_UNSET, orchestrator=_UNSET, judge_model=_UNSET,
                doc_map=_UNSET, reports_dir: str = REPORTS_DIR) -> dict:
    """执行 A/B 评测并落盘；依赖均可注入以便离线单测"""
    simple_dataset = load_dataset(dataset_path)
    complex_dataset, missing_qids = load_complex_dataset(
        dataset_path, complex_qids_path, authored_path)
    targets = build_targets(simple_dataset, complex_dataset, limit_simple, limit_complex)

    doc_map_available = doc_map is not _UNSET
    if doc_map is _UNSET:
        from app.service.eval.runner import fetch_document_map
        try:
            doc_map = fetch_document_map()
            doc_map_available = True
        except Exception as exc:      # MySQL 未启动时降级：流程可跑通，命中率记 0
            logger.warning("[A/B 评测]读取文档映射失败，文档级/片段级命中率将不可用：%s", exc)
            doc_map = {}
    if rag is _UNSET:
        rag = RagSummarizeService()
    if orchestrator is _UNSET:
        orchestrator = HybridOrchestrator()
    if judge_model is _UNSET:
        judge_model = get_eval_chat_model()
    if GROUP_B in groups and not bool(hybrid_conf.get("ENABLE_HYBRID_ROUTER", False)):
        logger.warning("[A/B 评测]ENABLE_HYBRID_ROUTER=false，B 组将退化为全直调")

    result = {
        "meta": {
            "tag": tag,
            "groups": list(groups),
            "finished_at": datetime.now().isoformat(timespec="seconds"),
            "num_simple": sum(1 for _, is_complex in targets if not is_complex),
            "num_complex": sum(1 for _, is_complex in targets if is_complex),
            "dataset": dataset_path,
            "complex_qids": complex_qids_path,
            "authored": authored_path,
            "missing_complex_qids": missing_qids,
            "eval_chat_model": get_eval_chat_model_name(),
            "hybrid_router_enabled": bool(hybrid_conf.get("ENABLE_HYBRID_ROUTER", False)),
            "judge_enabled": judge_model is not None,
            "doc_map_available": doc_map_available,
        },
        "groups": {},
    }

    for group in groups:
        records = []
        for i, (qa, is_complex) in enumerate(targets, 1):
            gt_doc_id = doc_map.get(qa["source_file"], -1)
            detail = evaluate_question(qa, is_complex, group, tag, rag, orchestrator,
                                       judge_model, gt_doc_id)
            records.append(detail)
            print(f"[{group}][{i}/{len(targets)}] {qa['qid']} complex={is_complex} "
                  f"route={detail['route']} doc_hit={detail['doc_hit']} "
                  f"correctness={detail['correctness']} {detail['latency_ms']}ms",
                  flush=True)

        simple_records = [r for r in records if not r["is_complex"]]
        complex_records = [r for r in records if r["is_complex"]]
        result["groups"][group] = {
            "summary": {
                "simple": summarize_records(simple_records),
                "complex": summarize_records(complex_records),
                "all": summarize_records(records),
            },
            "details": records,
        }

    result["meta"]["reports"] = write_reports(result, tag, reports_dir)
    print(f"\n报告已生成：\n  {result['meta']['reports']['json']}"
          f"\n  {result['meta']['reports']['csv']}"
          f"\n  {result['meta']['reports']['markdown']}")
    return result


def main():
    parser = argparse.ArgumentParser(description="RAG+ReAct A/B 对照评测 CLI")
    parser.add_argument("--tag", required=True, help="评测标签，如 AB-A / AB-B / AB-smoke")
    parser.add_argument("--group", choices=["A", "B", "both"], default="both",
                        help="A=全直调 baseline；B=规则路由混合；both=两组都跑")
    parser.add_argument("--limit-simple", type=int, default=None, help="简单集只跑前 N 题")
    parser.add_argument("--limit-complex", type=int, default=None, help="复杂集只跑前 N 题")
    parser.add_argument("--dataset", default=DATASET_V2_PATH, help="简单集路径")
    parser.add_argument("--complex-qids", default=COMPLEX_QIDS_PATH, help="复杂题 qid 清单")
    parser.add_argument("--authored", default=AUTHORED_PATH, help="补充复杂题集路径")
    args = parser.parse_args()

    groups = (GROUP_A, GROUP_B) if args.group == "both" else (args.group,)
    run_ab_eval(tag=args.tag, groups=groups,
                limit_simple=args.limit_simple, limit_complex=args.limit_complex,
                dataset_path=args.dataset, complex_qids_path=args.complex_qids,
                authored_path=args.authored)


if __name__ == "__main__":
    main()

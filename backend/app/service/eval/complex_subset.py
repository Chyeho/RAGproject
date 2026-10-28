# -*- coding: utf-8 -*-
'''复杂题筛选：用 router_rules.yml 扫描 v2 题集，输出候选清单 / 载入人工确认清单

用法（backend 目录）：
    uv run python -m app.service.eval.complex_subset scan
    uv run python -m app.service.eval.complex_subset scan --limit 40
'''
import argparse
import json
import os

from app.service.routing.rule_router import COMPLEX, RuleRouter

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATASETS_DIR = os.path.join(BASE_DIR, "datasets")
DATASET_V2_PATH = os.path.join(DATASETS_DIR, "eval_dataset_v2.json")
COMPLEX_QIDS_PATH = os.path.join(DATASETS_DIR, "complex_qids_v2.json")
AUTHORED_PATH = os.path.join(DATASETS_DIR, "eval_complex_authored_v2.json")

AUTHORED_REQUIRED = ("qid", "question", "ground_truth_answer", "source_passage", "source_file")


def load_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def scan_candidates(dataset: list[dict], router: RuleRouter | None = None) -> list[dict]:
    """按路由规则扫描题目，返回命中复杂通道的候选（含命中规则与分值，便于人工复核）"""
    router = router or RuleRouter()
    candidates = []
    for qa in dataset:
        decision = router.route(qa["question"])
        if decision.route != COMPLEX:
            continue
        candidates.append({
            "qid": qa["qid"],
            "question": qa["question"],
            "source_file": qa["source_file"],
            "matched_rules": list(decision.matched_rules),
            "score": decision.score,
            "reason": decision.reason,
        })
    return candidates


def load_complex_qids(path: str = COMPLEX_QIDS_PATH) -> list[str]:
    """读取人工确认的复杂题 qid 清单（支持 {"qids": [...]} 或纯数组）"""
    data = load_json(path)
    if isinstance(data, dict):
        data = data.get("qids", [])
    if not isinstance(data, list):
        raise ValueError(f"复杂题 qid 清单格式错误：{path} 应为数组或含 qids 数组的对象")
    return [str(q).strip() for q in data if str(q).strip()]


def load_authored(path: str = AUTHORED_PATH) -> list[dict]:
    """读取补充构造的复杂题；文件不存在时返回空列表（允许只用现有题筛选）"""
    if not os.path.exists(path):
        return []
    data = load_json(path)
    if not isinstance(data, list):
        raise ValueError(f"补充复杂题集格式错误：{path} 应为 JSON 数组")
    for i, qa in enumerate(data):
        if not isinstance(qa, dict):
            raise ValueError(f"补充复杂题第 {i} 条不是 JSON 对象")
        for field in AUTHORED_REQUIRED:
            value = qa.get(field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"补充复杂题第 {i} 条缺少必填字段或为空：{field}")
    return data


def load_complex_dataset(dataset_path: str = DATASET_V2_PATH,
                         qids_path: str = COMPLEX_QIDS_PATH,
                         authored_path: str = AUTHORED_PATH) -> tuple[list[dict], list[str]]:
    """组装复杂集：原 v2 筛选题 + 补充构造题

    Returns:
        (复杂题列表, 在 v2 中找不到的 qid 列表)；每条复杂题追加 complex_source
        （v2_selected / authored），便于报告分组分析。不修改原评测集文件。
    """
    dataset = load_json(dataset_path)
    by_qid = {qa["qid"]: qa for qa in dataset}
    qids = load_complex_qids(qids_path)
    missing = [q for q in qids if q not in by_qid]

    selected = []
    for qid in qids:
        if qid not in by_qid:
            continue
        item = dict(by_qid[qid])
        item["complex_source"] = "v2_selected"
        selected.append(item)

    for item in load_authored(authored_path):
        item = dict(item)
        item["complex_source"] = "authored"
        selected.append(item)

    seen = set()
    for qa in selected:
        if qa["qid"] in seen:
            raise ValueError(f"复杂集 qid 重复：{qa['qid']}（v2 筛选与补充题需使用不同 qid）")
        seen.add(qa["qid"])
    return selected, missing


def _print_candidates(candidates: list[dict], limit: int | None = None) -> None:
    shown = candidates[:limit] if limit else candidates
    for c in shown:
        print(f"{c['qid']}\t{c['score']}\t{','.join(c['matched_rules'])}\t{c['question']}")
    print(f"\n候选 {len(candidates)} 道（展示 {len(shown)} 道）")


def main():
    parser = argparse.ArgumentParser(description="复杂题候选筛选（按 router_rules.yml）")
    parser.add_argument("command", choices=["scan"], help="scan=扫描 v2 题集输出候选")
    parser.add_argument("--dataset", default=DATASET_V2_PATH, help="v2 评测集路径")
    parser.add_argument("--limit", type=int, default=None, help="最多展示 N 条（仅打印用）")
    args = parser.parse_args()

    _print_candidates(scan_candidates(load_json(args.dataset)), limit=args.limit)


if __name__ == "__main__":
    main()

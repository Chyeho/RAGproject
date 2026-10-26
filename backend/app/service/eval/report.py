'''评测报告生成（json+md）与多版本对比

- 单次评测报告：backend/eval_reports/{时间戳}_{tag}.json/.md（runner 调用 save_report）
- 多版本对比：python -m app.service.eval.report compare P0-baseline P1 P2 P3
  按 tag 取最新报告 json，生成指标横向对比表（检索+生成），打印并写盘
'''
import json
import os
import sys
from datetime import datetime

# eval → service → app → backend / eval_reports
REPORTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
    "eval_reports",
)

# 指标中文名（顺序即表格行序）
METRIC_LABELS = {
    "num_questions": "题目数",
    "hit_rate_doc": "文档级 HitRate@K",
    "hit_rate_passage": "片段级 HitRate@K",
    "mrr_doc": "文档级 MRR",
    "mrr_passage": "片段级 MRR",
    "precision_doc": "文档级 Precision@K",
    "precision_passage": "片段级 Precision@K",
    "recall_content": "内容召回率（重叠率均值）",
}


def _fmt(value) -> str:
    """指标值格式化：None 显示 '-'，浮点保留 4 位"""
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def save_report(result: dict, tag: str, reports_dir: str = REPORTS_DIR) -> tuple[str, str]:
    """评测结果落盘（json 全量 + md 可读），返回 (json_path, md_path)"""
    os.makedirs(reports_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = os.path.join(reports_dir, f"{ts}_{tag}.json")
    md_path = os.path.join(reports_dir, f"{ts}_{tag}.md")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(render_markdown(result))
    return json_path, md_path


def _kv_table(pairs: list[tuple[str, str]]) -> str:
    lines = ["| 项 | 值 |", "|---|---|"]
    lines.extend(f"| {k} | {v} |" for k, v in pairs)
    return "\n".join(lines)


def _metric_row_table(columns: dict[str, dict]) -> str:
    """行=指标、列=范围的指标表；columns: {列名: 指标dict}"""
    lines = ["| 指标 | " + " | ".join(columns.keys()) + " |",
             "|---|" + "---|" * len(columns)]
    for key, label in METRIC_LABELS.items():
        cells = [_fmt(col.get(key)) for col in columns.values()]
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def render_markdown(result: dict) -> str:
    """单次评测报告 markdown"""
    meta = result["meta"]
    snap = meta.get("config_snapshot", {})
    qdrant = snap.get("qdrant", {})

    lines = [f"# RAG 评测报告：{meta['tag']}", "", "## 基本信息", ""]
    lines.append(_kv_table([
        ("评测时间", meta.get("finished_at", "")),
        ("评测模式", "retrieval（仅检索）" if meta.get("mode") == "retrieval" else "full（检索+生成）"),
        ("题目数", str(meta.get("num_questions", ""))),
        ("Top-K", str(meta.get("k", ""))),
        ("模型模式", str(snap.get("model_mode", ""))),
        ("聊天模型", str(snap.get("chat_model_name", ""))),
        ("嵌入模型", str(snap.get("embedding_model_name", ""))),
        ("分块配置", f"chunk_size={qdrant.get('chunk_size')}, chunk_overlap={qdrant.get('chunk_overlap')}"),
        ("Qdrant Collection", str(qdrant.get("collection_name", ""))),
        ("评测集 MD5", str(meta.get("dataset_md5", ""))),
    ]))

    missing = result.get("missing_source_files") or []
    if missing:
        lines += ["", f"> ⚠ 未成功入库样例（其问题文档级命中记 0，为当前链路已知格式缺口）：{'、'.join(missing)}"]

    lines += ["", "## 检索指标（总体）", "",
              _metric_row_table({"总体": result["retrieval"]})]

    if result.get("retrieval_by_type"):
        lines += ["", "### 按问题类型", "",
                  _metric_row_table(result["retrieval_by_type"])]
    if result.get("retrieval_by_source_file"):
        lines += ["", "### 按样例文件", "",
                  _metric_row_table(result["retrieval_by_source_file"])]

    gen = result.get("generation")
    if gen:
        lines += ["", "## 生成指标（LLM 裁判）", ""]
        lines.append("| 指标 | 有效裁判数 | 裁判失败数 | 均值 |")
        lines.append("|---|---|---|---|")
        for key, label in (("faithfulness", "Faithfulness 忠实度"),
                           ("answer_relevancy", "AnswerRelevancy 相关性")):
            stat = gen.get(key, {})
            lines.append(f"| {label} | {stat.get('num_judged', 0)} | "
                         f"{stat.get('num_judge_error', 0)} | {_fmt(stat.get('mean'))} |")

    lines += ["", "## 口径说明", "",
              "- 文档级命中：检索结果 metadata.document_id 与 ground truth 一致",
              "- 片段级命中：chunk 与溯源段落的字符 2-gram 重叠率（包含式 |A∩B|/min(|A|,|B|)）≥ 0.6",
              "- 内容召回率：正确文档结果中最大重叠率的平均值",
              "- LLM 裁判：中文 Prompt 固定，temperature=0；失败不计入均值",
              ""]
    return "\n".join(lines)


def find_report(tag: str, reports_dir: str = REPORTS_DIR) -> str | None:
    """取指定 tag 的最新报告 json 路径（文件名时间戳前缀排序）；无则 None"""
    if not os.path.isdir(reports_dir):
        return None
    candidates = [f for f in os.listdir(reports_dir) if f.endswith(f"_{tag}.json")]
    if not candidates:
        return None
    return os.path.join(reports_dir, sorted(candidates)[-1])


def compare(tags: list[str], reports_dir: str = REPORTS_DIR) -> str:
    """多版本横向对比：生成 md（打印+写盘），返回 md 内容"""
    loaded, skipped = {}, []
    for tag in tags:
        path = find_report(tag, reports_dir)
        if not path:
            skipped.append(tag)
            continue
        with open(path, encoding="utf-8") as f:
            loaded[tag] = json.load(f)
    if skipped:
        print(f"⚠ 未找到报告（跳过）：{'、'.join(skipped)}")
    if len(loaded) < 2:
        raise SystemExit(f"可对比报告不足 2 个（仅 {list(loaded)}），请先运行评测生成报告")

    # 检索指标对比
    columns = {tag: data.get("retrieval", {}) for tag, data in loaded.items()}
    lines = ["# RAG 评测多版本对比", "",
             f"- 对比对象：{' vs '.join(loaded.keys())}",
             f"- 生成时间：{datetime.now().isoformat(timespec='seconds')}", "",
             "## 检索指标", "", _metric_row_table(columns)]

    # 生成指标对比（任一报告为 full 即展示）
    if any("generation" in data for data in loaded.values()):
        gen_rows = ["## 生成指标（LLM 裁判）", "", "| 指标 | " + " | ".join(loaded.keys()) + " |",
                    "|---|" + "---|" * len(loaded)]
        for key, label in (("faithfulness", "Faithfulness 忠实度"),
                           ("answer_relevancy", "AnswerRelevancy 相关性")):
            cells = [_fmt(data.get("generation", {}).get(key, {}).get("mean"))
                     for data in loaded.values()]
            gen_rows.append(f"| {label} | " + " | ".join(cells) + " |")
        lines += [""] + gen_rows

    # 各版本评测条件摘要（口径核对）
    lines += ["", "## 各版本评测条件", "",
              "| 版本 | 评测时间 | 模式 | 题数 | K | 聊天模型 | 嵌入模型 | chunk | 评测集MD5 |",
              "|---|---|---|---|---|---|---|---|---|"]
    for tag, data in loaded.items():
        meta = data.get("meta", {})
        snap = meta.get("config_snapshot", {})
        q = snap.get("qdrant", {})
        lines.append(
            f"| {tag} | {meta.get('finished_at')} | {meta.get('mode')} | "
            f"{meta.get('num_questions')} | {meta.get('k')} | "
            f"{snap.get('chat_model_name')} | {snap.get('embedding_model_name')} | "
            f"{q.get('chunk_size')}/{q.get('chunk_overlap')} | {meta.get('dataset_md5', '')[:8]} |")
    lines.append("")

    content = "\n".join(lines)
    os.makedirs(reports_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(reports_dir, f"{ts}_compare__{'__'.join(loaded.keys())}.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(content)
    print(f"\n对比报告已生成：{out_path}")
    return content


if __name__ == "__main__":
    # python -m app.service.eval.report compare P0-baseline P1
    argv = sys.argv[1:]
    if len(argv) < 2 or argv[0] != "compare":
        print("用法：python -m app.service.eval.report compare <tag1> <tag2> [...]")
        sys.exit(1)
    compare(argv[1:])

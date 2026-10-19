'''评测集构建（LLM 从自造样例生成 QA）与加载

构建：uv run python -m app.service.eval.dataset build --num 80
- 从 datasets/samples/ 的 5 个样例文件提取段落（txt/md/pdf/docx/xlsx 各自适配）
- 每段落由 LLM 生成若干 QA 对（问题 + 标准答案），question_type 三类分布：
  fact（量化事实）/ term（术语定义）/ longtail（长尾细节）
- 跨样例文件轮转采样至 --num 条，保证 5 种格式均衡覆盖
- 产出 datasets/eval_dataset.json，**人工校验后定稿**（执行文档 4.2）

与执行文档 4.2 schema 的差异（2026-10-18 决议）：评测集存 source_file
（样例文件名）而非写死 document_id；document_id 由 runner 运行时按
file_name 反查 document 表填充，向量库重建后评测集无需修改。
'''
import argparse
import hashlib
import json
import os
import re
from collections import Counter
from dataclasses import dataclass

import fitz                      # pymupdf：读 pdf
from docx import Document as DocxDocument
from openpyxl import load_workbook

from app.modelFactory.factory import chat_model
from app.utils.logger_handler import logger

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SAMPLES_DIR = os.path.join(BASE_DIR, "datasets", "samples")
DATASET_PATH = os.path.join(BASE_DIR, "datasets", "eval_dataset.json")

MIN_PASSAGE_CHARS = 60          # 溯源段落最短字符数（过短的标题行不作为出题依据）
QUESTION_TYPES = ("fact", "term", "longtail")
REQUIRED_FIELDS = ("qid", "question", "ground_truth_answer",
                   "source_passage", "source_file", "question_type")

QA_GEN_PROMPT = """你将获得一段企业内部文档原文，请基于该段原文生成 {n} 个用于评测知识库检索系统的问答对。

要求：
1. 问题必须能仅凭该段原文直接回答；答案中的数字、日期、金额、天数、名称等必须与原文完全一致
2. 问题措辞模拟真实员工提问口吻，不要照抄原文句式，也不要出现"根据文档/原文"之类的字眼
3. question_type 三选一：
   - fact：询问数字、日期、天数、金额、比例等量化事实
   - term：询问制度名词、系统名称、专有缩写的含义或定义
   - longtail：询问原文中仅一句带过的细节信息（如某分机号、某节点名、某期限）
4. 同一段落内生成的多个问题，question_type 尽量不同
5. 仅输出 JSON 数组，禁止输出任何其他文字，格式：
[{{"question": "……", "answer": "……", "question_type": "fact"}}]

【文档原文】（出处：{source_file}）
{passage}"""


# =====================================================================
# 段落提取（各格式独立适配，产物即 QA 的 source_passage）
# =====================================================================

@dataclass
class Passage:
    source_file: str
    text: str


def extract_txt(path: str) -> list[str]:
    """txt：按空行分段"""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def extract_md(path: str) -> list[str]:
    """md：按空行分段；连续标题行与后续正文合并为一段（保留标题上下文）"""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    raw_parts = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    parts, pending_titles = [], []
    for p in raw_parts:
        if p.startswith("#"):
            pending_titles.append(p)
            continue
        merged = ("\n".join(pending_titles) + "\n" + p) if pending_titles else p
        pending_titles = []
        parts.append(merged)
    if pending_titles:
        parts.append("\n".join(pending_titles))
    return parts


def extract_pdf(path: str) -> list[str]:
    """pdf：每页文本一段（样例 pdf 每章一页，页文本=章标题+段落）"""
    parts = []
    with fitz.open(path) as doc:
        for page in doc:
            text = page.get_text("text").strip()
            if text:
                parts.append(text)
    return parts


def extract_docx(path: str) -> list[str]:
    """docx：正文段落（跳过 Heading）+ 每张表格整体一段（单元格以、连接）"""
    doc = DocxDocument(path)
    parts = [p.text.strip() for p in doc.paragraphs
             if p.text.strip() and not (p.style and p.style.name.startswith("Heading"))]
    for table in doc.tables:
        lines = ["、".join(cell.text.strip() for cell in row.cells) for row in table.rows]
        table_text = "\n".join(l for l in lines if l)
        if table_text:
            parts.append(table_text)
    return parts


def extract_xlsx(path: str) -> list[str]:
    """xlsx：每 Sheet 首行为表头，数据行转"列名：值"句子，每 4 行拼一段"""
    wb = load_workbook(path, data_only=True)
    parts = []
    for ws in wb.worksheets:
        rows = [list(r) for r in ws.iter_rows(values_only=True)]
        if not rows:
            continue
        header = [str(c).strip() if c is not None else "" for c in rows[0]]
        sentences = []
        for row in rows[1:]:
            fields = [f"{header[i]}：{str(c).strip()}"
                      for i, c in enumerate(row)
                      if i < len(header) and header[i] and c is not None and str(c).strip()]
            if fields:
                sentences.append("；".join(fields))
        # 每 4 行拼一段，段首带 Sheet 名
        for i in range(0, len(sentences), 4):
            parts.append(f"【{ws.title}】\n" + "\n".join(sentences[i:i + 4]))
    wb.close()
    return parts


_EXTRACTORS = {".txt": extract_txt, ".md": extract_md, ".pdf": extract_pdf,
               ".docx": extract_docx, ".xlsx": extract_xlsx}


def extract_passages(samples_dir: str = SAMPLES_DIR) -> list[Passage]:
    """遍历样例目录，按扩展名分发提取，过滤过短段落"""
    if not os.path.isdir(samples_dir):
        raise FileNotFoundError(f"样例目录不存在：{samples_dir}，请先运行 python -m app.service.eval.make_samples")
    passages = []
    for fname in sorted(os.listdir(samples_dir)):
        extractor = _EXTRACTORS.get(os.path.splitext(fname)[1].lower())
        if not extractor:
            continue
        for text in extractor(os.path.join(samples_dir, fname)):
            if len(text) >= MIN_PASSAGE_CHARS:
                passages.append(Passage(source_file=fname, text=text))
    return passages


# =====================================================================
# LLM 生成 QA
# =====================================================================

def parse_qa_json(text: str) -> list[dict]:
    """解析 LLM 输出的 QA JSON 数组；容错 markdown 包裹与前后杂文，坏条目跳过"""
    if not text:
        return []
    cleaned = re.sub(r"```(?:json)?", "", text)
    match = re.search(r"\[.*\]", cleaned, re.DOTALL)
    if not match:
        return []
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []
    items = []
    if isinstance(data, list):
        for d in data:
            if not isinstance(d, dict):
                continue
            question = str(d.get("question") or "").strip()
            answer = str(d.get("answer") or "").strip()
            qtype = str(d.get("question_type") or "").strip()
            if question and answer and qtype in QUESTION_TYPES:
                items.append({"question": question, "answer": answer, "question_type": qtype})
    return items


def generate_qa_for_passage(bound_model, passage: Passage, n: int) -> list[dict]:
    """单段落生成 n 个 QA；失败记日志返回空（不中断整体构建）"""
    prompt = QA_GEN_PROMPT.format(n=n, source_file=passage.source_file, passage=passage.text)
    try:
        response = bound_model.invoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)
        return parse_qa_json(content)
    except Exception as e:
        logger.error(f"[评测集构建]{passage.source_file} QA 生成失败：{str(e)}")
        return []


def sample_balanced(qas: list[dict], num: int) -> list[dict]:
    """超出 num 时按 source_file 轮转采样，保证各格式覆盖均衡"""
    if len(qas) <= num:
        return qas
    groups: dict[str, list[dict]] = {}
    for qa in qas:
        groups.setdefault(qa["source_file"], []).append(qa)
    result, iters = [], {k: iter(v) for k, v in groups.items()}
    while len(result) < num and iters:
        for key in list(iters):
            try:
                result.append(next(iters[key]))
                if len(result) >= num:
                    break
            except StopIteration:
                del iters[key]
    return result


def build_dataset(num: int = 80, per_passage: int = 3,
                  out_path: str = DATASET_PATH, samples_dir: str = SAMPLES_DIR) -> list[dict]:
    """构建评测集并写盘，返回评测集列表（未截断前的采样结果）"""
    passages = extract_passages(samples_dir)
    if not passages:
        raise RuntimeError(f"样例目录 {samples_dir} 未提取到有效段落，请先运行 make_samples 生成样例")
    logger.info(f"[评测集构建]共提取 {len(passages)} 个有效段落，开始 LLM 生成 QA")

    model = chat_model.bind(temperature=0.2)
    qas = []
    for i, p in enumerate(passages, 1):
        items = generate_qa_for_passage(model, p, per_passage)
        for it in items:
            qas.append({
                "question": it["question"],
                "ground_truth_answer": it["answer"],
                "question_type": it["question_type"],
                "source_file": p.source_file,
                "source_passage": p.text,
            })
        print(f"[{i}/{len(passages)}] {p.source_file} 生成 {len(items)} 条", flush=True)

    if not qas:
        raise RuntimeError("LLM 未生成任何有效 QA，请检查模型配置后重试")

    qas = sample_balanced(qas, num)
    # 采样后统一编号
    for idx, qa in enumerate(qas, 1):
        qa["qid"] = f"q{idx:03d}"
    qas = [{k: qa[k] for k in ("qid", "question", "ground_truth_answer",
                               "source_passage", "source_file", "question_type")}
           for qa in qas]

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(qas, f, ensure_ascii=False, indent=2)

    by_file = Counter(qa["source_file"] for qa in qas)
    by_type = Counter(qa["question_type"] for qa in qas)
    print(f"\n评测集已生成：{out_path}")
    print(f"共 {len(qas)} 条（目标 {num}）")
    print(f"按样例文件分布：{dict(sorted(by_file.items()))}")
    print(f"按问题类型分布：{dict(sorted(by_type.items()))}")
    print("请人工校验问题与答案质量后定稿；校验通过后再用于基线评测。")
    return qas


# =====================================================================
# 加载与校验
# =====================================================================

def load_dataset(path: str = DATASET_PATH) -> list[dict]:
    """加载评测集并校验必填字段与 qid 唯一性"""
    if not os.path.exists(path):
        raise FileNotFoundError(f"评测集不存在：{path}，请先运行 python -m app.service.eval.dataset build")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list) or not data:
        raise ValueError(f"评测集格式错误：{path} 应为非空 JSON 数组")

    seen_qids = set()
    for i, qa in enumerate(data):
        if not isinstance(qa, dict):
            raise ValueError(f"第 {i} 条不是 JSON 对象")
        for field in REQUIRED_FIELDS:
            value = qa.get(field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"第 {i} 条（qid={qa.get('qid')}）缺少必填字段或为空：{field}")
        if qa["question_type"] not in QUESTION_TYPES:
            raise ValueError(f"第 {i} 条 question_type 非法：{qa['question_type']}（应为 {QUESTION_TYPES}）")
        if qa["qid"] in seen_qids:
            raise ValueError(f"qid 重复：{qa['qid']}")
        seen_qids.add(qa["qid"])
    return data


def dataset_md5(path: str = DATASET_PATH) -> str:
    """评测集文件 md5（写入报告 meta，保证跨阶段口径可追溯）"""
    with open(path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="评测集构建 CLI")
    parser.add_argument("command", choices=["build"], help="build=从样例生成评测集")
    parser.add_argument("--num", type=int, default=80, help="目标条数（默认 80）")
    parser.add_argument("--per-passage", type=int, default=3, help="每段落生成 QA 数（默认 3）")
    args = parser.parse_args()
    build_dataset(num=args.num, per_passage=args.per_passage)

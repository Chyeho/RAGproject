'''确定性检索评测指标（无 LLM 参与，纯规则计算）

命中判定两级（与执行文档 4.3 一致）：
- 文档级：检索结果 metadata.document_id == ground truth 的 document_id
- 片段级：在文档级命中基础上，chunk 文本与 source_passage 的字符 n-gram
  重叠率（包含式：|A∩B| / min(|A|,|B|)）≥ 阈值（默认 0.6）

不以 vector_id 为主键的原因：当前链路向量 ID 为随机 UUID，且 P1 重建后
chunk 边界与 ID 均会变化；文本重叠口径可让同一评测集在 P0~P3 全程复用。
'''
import re
from dataclasses import dataclass, field

# ---------- 文本归一化与 n-gram ----------

# 中文场景：仅保留汉字、字母、数字，其余（标点/空白/全角符号）全部剔除
_KEEP_PATTERN = re.compile(r"[\u4e00-\u9fffA-Za-z0-9]")


def normalize_text(text: str) -> str:
    """归一化文本：去标点、去空白，只保留汉字/字母/数字"""
    return "".join(_KEEP_PATTERN.findall(text or ""))


def char_ngrams(text: str, n: int = 2) -> set[tuple[str, ...]]:
    """字符 n-gram 集合（先归一化）；文本不足 n 字时返回单字 gram 兜底"""
    normalized = normalize_text(text)
    if not normalized:
        return set()
    if len(normalized) <= n:
        return {(normalized,)}
    return {tuple(normalized[i:i + n]) for i in range(len(normalized) - n + 1)}


def passage_overlap(chunk_text: str, source_passage: str, n: int = 2) -> float:
    """重叠率：|A∩B| / min(|A|,|B|)，A=chunk n-grams，B=溯源段落 n-grams

    包含式口径：无论 chunk 大于还是小于溯源段落（P0 chunk=150，P1 chunk=500），
    只要一方完整覆盖另一方即接近 1.0，保证跨阶段口径一致。
    任一方为空返回 0.0。
    """
    grams_a = char_ngrams(chunk_text, n)
    grams_b = char_ngrams(source_passage, n)
    if not grams_a or not grams_b:
        return 0.0
    denom = min(len(grams_a), len(grams_b))
    return len(grams_a & grams_b) / denom


# ---------- 单题命中判定 ----------

@dataclass
class QuestionRetrieval:
    """单题检索评测结果（一个问题的 Top-K 检索情况）"""
    qid: str
    doc_hits: list[bool] = field(default_factory=list)       # 各结果文档级命中
    passage_hits: list[bool] = field(default_factory=list)   # 各结果片段级命中
    best_overlap: float = 0.0                                # 正确文档结果中的最大重叠率（内容召回）


def judge_retrieval(qid: str, retrieved_docs: list, gt_document_id: int,
                    source_passage: str, threshold: float = 0.6, n: int = 2) -> QuestionRetrieval:
    """对单题的 Top-K 检索结果做两级命中判定

    Args:
        retrieved_docs: 检索器返回的 langchain Document 列表（有序）
        gt_document_id: ground truth 文档 ID
        source_passage: 溯源原文段落
        threshold: 片段级命中重叠率阈值
        n: n-gram 阶数
    """
    doc_hits: list[bool] = []
    passage_hits: list[bool] = []
    best_overlap = 0.0

    for doc in retrieved_docs:
        meta_doc_id = (getattr(doc, "metadata", {}) or {}).get("document_id")
        is_doc_hit = str(meta_doc_id) == str(gt_document_id)
        doc_hits.append(is_doc_hit)

        overlap = 0.0
        if is_doc_hit:
            overlap = passage_overlap(getattr(doc, "page_content", ""), source_passage, n)
            best_overlap = max(best_overlap, overlap)
        passage_hits.append(is_doc_hit and overlap >= threshold)

    return QuestionRetrieval(qid=qid, doc_hits=doc_hits,
                             passage_hits=passage_hits, best_overlap=best_overlap)


def first_hit_rank(hit_flags: list[bool]) -> int | None:
    """首个命中的排名（1-based）；无命中返回 None"""
    for rank, hit in enumerate(hit_flags, start=1):
        if hit:
            return rank
    return None


# ---------- 多题聚合指标 ----------

def aggregate(records: list[QuestionRetrieval]) -> dict:
    """聚合检索指标（文档级/片段级分别统计）

    返回：
        hit_rate_doc / hit_rate_passage : Top-K 出现命中的问题占比
        mrr_doc / mrr_passage           : 首个命中排名倒数的平均值
        precision_doc / precision_passage: Top-K 命中精度（命中数/K 平均）
        recall_content                  : 溯源段落内容召回率（最大重叠率平均）
    """
    if not records:
        return {
            "num_questions": 0, "hit_rate_doc": None, "hit_rate_passage": None,
            "mrr_doc": None, "mrr_passage": None,
            "precision_doc": None, "precision_passage": None, "recall_content": None,
        }

    total = len(records)
    doc_ranks = [first_hit_rank(r.doc_hits) for r in records]
    passage_ranks = [first_hit_rank(r.passage_hits) for r in records]

    def _hit_rate(flags_list: list[list[bool]]) -> float:
        return sum(1 for flags in flags_list if any(flags)) / total

    def _mrr(ranks: list[int | None]) -> float:
        return sum(1.0 / r for r in ranks if r is not None) / total

    def _precision(flags_list: list[list[bool]]) -> float:
        # 命中数 / 实际返回数（K 不足时按实际数，避免虚低）
        hits = sum(sum(1 for h in flags if h) for flags in flags_list)
        denom = sum(len(flags) for flags in flags_list)
        return hits / denom if denom else 0.0

    return {
        "num_questions": total,
        "hit_rate_doc": _hit_rate([r.doc_hits for r in records]),
        "hit_rate_passage": _hit_rate([r.passage_hits for r in records]),
        "mrr_doc": _mrr(doc_ranks),
        "mrr_passage": _mrr(passage_ranks),
        "precision_doc": _precision([r.doc_hits for r in records]),
        "precision_passage": _precision([r.passage_hits for r in records]),
        "recall_content": sum(r.best_overlap for r in records) / total,
    }


def aggregate_by(records: list[QuestionRetrieval], key_of: "callable") -> dict:
    """按维度分组聚合（如按 question_type / 样例文件分组）"""
    groups: dict[str, list[QuestionRetrieval]] = {}
    for r in records:
        groups.setdefault(key_of(r), []).append(r)
    return {key: aggregate(sub) for key, sub in sorted(groups.items())}

# -*- coding: utf-8 -*-
"""eval.metrics 确定性检索指标单元测试（构造数据，全确定性，无外部依赖）"""
from langchain_core.documents import Document

from app.service.eval.metrics import (
    QuestionRetrieval,
    aggregate,
    aggregate_by,
    char_ngrams,
    first_hit_rank,
    judge_retrieval,
    normalize_text,
    passage_overlap,
)


# ---------- 文本归一化与 n-gram ----------

class TestNormalize:
    def test_keeps_cjk_alnum_only(self):
        assert normalize_text("年假5天，含法定3天！") == "年假5天含法定3天"

    def test_empty_and_none(self):
        assert normalize_text("") == ""
        assert normalize_text(None) == ""


class TestCharNgrams:
    def test_bigrams(self):
        assert char_ngrams("abcd") == {("a", "b"), ("b", "c"), ("c", "d")}

    def test_short_text_falls_back_to_single_gram(self):
        assert char_ngrams("ab") == {("ab",)}


class TestPassageOverlap:
    def test_identical_text(self):
        assert passage_overlap("年假满十年为十五天", "年假满十年为十五天") == 1.0

    def test_chunk_contains_passage(self):
        # 长chunk完整包含短溯源段落 → 包含式口径应为 1.0
        chunk = "员工手册规定年假满一年不满五年为五天满五年不满十年为十天满十年及以上为十五天"
        passage = "年假满五年不满十年为十天"
        assert passage_overlap(chunk, passage) == 1.0

    def test_unrelated_text(self):
        assert passage_overlap("报销时效三十天", "密码长度十二位") == 0.0

    def test_empty_text(self):
        assert passage_overlap("", "任意文本") == 0.0
        assert passage_overlap("任意文本", "") == 0.0

    def test_punctuation_ignored(self):
        assert passage_overlap("年假5天。", "年假，5天") == 1.0


# ---------- 单题命中判定 ----------

class TestJudgeRetrieval:
    def test_doc_and_passage_hit(self):
        docs = [
            Document(page_content="年假满十年及以上为十五天，须当年使用", metadata={"document_id": 1}),
            Document(page_content="无关内容", metadata={"document_id": 2}),
        ]
        rec = judge_retrieval("q001", docs, gt_document_id=1,
                              source_passage="年假满十年及以上为十五天")
        assert rec.doc_hits == [True, False]
        assert rec.passage_hits == [True, False]
        assert rec.best_overlap == 1.0

    def test_doc_hit_but_low_overlap_no_passage_hit(self):
        # 文档命中但片段重叠率低 → 片段级不命中
        docs = [Document(page_content="完全不同的内容", metadata={"document_id": 1})]
        rec = judge_retrieval("q001", docs, gt_document_id=1,
                              source_passage="密码长度不得低于十二位且九十天更换")
        assert rec.doc_hits == [True]
        assert rec.passage_hits == [False]
        assert rec.best_overlap == 0.0

    def test_doc_miss_blocks_passage_hit(self):
        # 文档级未命中时，即便文本重叠也不计片段级命中
        docs = [Document(page_content="密码长度不得低于十二位", metadata={"document_id": 9})]
        rec = judge_retrieval("q001", docs, gt_document_id=1,
                              source_passage="密码长度不得低于十二位")
        assert rec.doc_hits == [False]
        assert rec.passage_hits == [False]

    def test_missing_metadata_treated_as_miss(self):
        docs = [Document(page_content="任意内容")]
        rec = judge_retrieval("q001", docs, gt_document_id=1, source_passage="任意内容")
        assert rec.doc_hits == [False]


# ---------- 排名与聚合 ----------

class TestFirstHitRank:
    def test_first_hit(self):
        assert first_hit_rank([False, True, False]) == 2

    def test_no_hit(self):
        assert first_hit_rank([False, False]) is None


class TestAggregate:
    def test_mixed_records(self):
        records = [
            QuestionRetrieval("q1", doc_hits=[True, False], passage_hits=[True, False], best_overlap=0.8),
            QuestionRetrieval("q2", doc_hits=[False, False], passage_hits=[False, False], best_overlap=0.0),
        ]
        m = aggregate(records)
        assert m["num_questions"] == 2
        assert m["hit_rate_doc"] == 0.5
        assert m["hit_rate_passage"] == 0.5
        assert m["mrr_doc"] == 0.5          # 1/1 + 0 除以 2
        assert m["mrr_passage"] == 0.5
        assert m["precision_doc"] == 0.25   # 1 命中 / 4 返回
        assert m["recall_content"] == 0.4   # (0.8 + 0) / 2

    def test_empty_records_all_none(self):
        m = aggregate([])
        assert m["num_questions"] == 0
        assert m["hit_rate_doc"] is None
        assert m["recall_content"] is None

    def test_rank2_hit_mrr(self):
        records = [QuestionRetrieval("q1", doc_hits=[False, True], passage_hits=[False, True], best_overlap=1.0)]
        m = aggregate(records)
        assert m["mrr_doc"] == 0.5
        assert m["precision_doc"] == 0.5


class TestAggregateBy:
    def test_grouping(self):
        records = [
            QuestionRetrieval("q1", doc_hits=[True], passage_hits=[True], best_overlap=1.0),
            QuestionRetrieval("q2", doc_hits=[False], passage_hits=[False], best_overlap=0.0),
        ]
        groups = aggregate_by(records, key_of=lambda r: "fact" if r.qid == "q1" else "term")
        assert set(groups) == {"fact", "term"}
        assert groups["fact"]["hit_rate_doc"] == 1.0
        assert groups["term"]["hit_rate_doc"] == 0.0

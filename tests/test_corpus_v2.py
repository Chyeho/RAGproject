# -*- coding: utf-8 -*-
"""eval.corpus_v2 语料生成器单元测试（执行文档 4.6 评测集迭代）

覆盖：
- plan_docs 分配公式：count=60 时 5 格式各 12 份、6 实体 × 10 主题全覆盖、前缀可复现
- build_doc 确定性：同 doc_idx + seed 两次构建 DocSpec 完全相等（固定种子可复现）
- 标题唯一：count=60 全部文档标题唯一（文件名 = 标题.格式）
- include_v1：count=5 追加 v1 样例后合计 10 份且文件名无冲突
- render → extract 往返：count=10 渲染后每份文件 ≥1 个有效段落（≥60 字符，
  满足 dataset.MIN_PASSAGE_CHARS 出题门槛）、5 格式齐全、各格式段落可命中实体城市锚点
"""
import os

import pytest

from app.service.eval.corpus_v2 import (
    ENTITIES,
    FORMATS,
    TOPIC_BUILDERS,
    build_all,
    build_doc,
    plan_docs,
)
from app.service.eval.dataset import MIN_PASSAGE_CHARS, extract_passages


# ---------- 分配计划 ----------

class TestPlanDocs:
    def test_count60_format_distribution(self):
        plans = plan_docs(60)
        assert len(plans) == 60
        fmt_counts = {}
        for p in plans:
            fmt_counts[p["fmt"]] = fmt_counts.get(p["fmt"], 0) + 1
        assert fmt_counts == {f: 12 for f in FORMATS}

    def test_count60_entity_topic_full_coverage(self):
        plans = plan_docs(60)
        pairs = {(p["ent"]["name"], p["t_idx"]) for p in plans}
        # 6 实体 × 10 主题，共 60 个组合无重复
        assert len(pairs) == len(ENTITIES) * len(TOPIC_BUILDERS) == 60
        assert {p["ent"]["name"] for p in plans} == {e["name"] for e in ENTITIES}
        assert {p["t_idx"] for p in plans} == set(range(len(TOPIC_BUILDERS)))

    def test_prefix_reproducible_across_count(self):
        # 任意 count 下前缀可复现：count=20 的计划与 count=60 的前 20 项一致
        assert plan_docs(20) == plan_docs(60)[:20]


# ---------- 文档构建 ----------

class TestBuildDoc:
    @pytest.mark.parametrize("t_idx", [0, 5, 9])
    def test_deterministic_same_seed(self, t_idx):
        ent = ENTITIES[0]
        assert build_doc(3, ent, t_idx) == build_doc(3, ent, t_idx)

    def test_titles_unique_count60(self):
        titles = [build_doc(i, p["ent"], p["t_idx"]).title
                  for i, p in enumerate(plan_docs(60))]
        assert len(set(titles)) == 60

    def test_doc_idx_changes_content(self):
        # 同实体同主题不同序号 → 内容不同（hard negatives 槽位数值差异）
        ent = ENTITIES[1]
        assert build_doc(0, ent, 2) != build_doc(1, ent, 2)


# ---------- 全量生成 ----------

class TestBuildAll:
    def test_include_v1_no_name_conflict(self, tmp_path):
        files = build_all(str(tmp_path), count=5, include_v1=True)
        assert len(files) == 5 + 5
        assert len(set(files)) == len(files)      # 文件名（dict key）无冲突


# ---------- 渲染 → 段落提取 往返 ----------

class TestRenderExtractRoundtrip:
    @pytest.fixture(scope="module")
    def corpus10(self, tmp_path_factory):
        """count=10：单一实体跑满 10 主题，5 格式各 2 份"""
        out = tmp_path_factory.mktemp("corpus_v2_roundtrip")
        files = build_all(str(out), count=10)
        return str(out), files

    def test_all_ten_files_rendered(self, corpus10):
        _, files = corpus10
        assert len(files) == 10
        fmt_counts = {}
        for name in files:
            fmt_counts[os.path.splitext(name)[1].lstrip(".")] = \
                fmt_counts.get(os.path.splitext(name)[1].lstrip("."), 0) + 1
        assert fmt_counts == {f: 2 for f in FORMATS}

    def test_every_file_yields_valid_passage(self, corpus10):
        out_dir, files = corpus10
        passages = extract_passages(out_dir)
        assert passages                                # 至少能提取出有效段落
        by_file = {p.source_file for p in passages}
        for name in files:                             # 每份文件都有 ≥1 个出题依据段落
            assert name in by_file, f"{name} 无有效段落（< {MIN_PASSAGE_CHARS} 字符全被过滤）"
        assert all(len(p.text) >= MIN_PASSAGE_CHARS for p in passages)

    def test_all_formats_covered_with_entity_anchor(self, corpus10):
        out_dir, _ = corpus10
        passages = extract_passages(out_dir)
        by_fmt = {}
        for p in passages:
            ext = os.path.splitext(p.source_file)[1].lstrip(".")
            by_fmt.setdefault(ext, []).append(p)
        city = ENTITIES[0]["city"]                     # count=10 全部为实体 0
        for fmt in FORMATS:
            assert by_fmt.get(fmt), f"{fmt} 格式无有效段落"
            # 实体锚点：每种格式下都有段落能命中城市名（doc_md5 语料侧可检索的前提）
            assert any(city in p.text for p in by_fmt[fmt]), f"{fmt} 段落缺少实体城市锚点"

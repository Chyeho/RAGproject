# -*- coding: utf-8 -*-
"""eval.dataset 评测集构建/加载单元测试

样例文件由 make_samples.build_all 生成到 tmp（自包含，不依赖仓库产物状态），
同时验证「样例生成 → 段落提取」全链路。
"""
import json
import os

import pytest

from app.service.eval.dataset import (
    build_dataset,
    dataset_md5,
    extract_passages,
    load_dataset,
    parse_qa_json,
    sample_balanced,
)
from app.service.eval.make_samples import build_all


@pytest.fixture(scope="module")
def samples_dir(tmp_path_factory):
    """一次性生成 5 个样例文件到 tmp 目录"""
    out = tmp_path_factory.mktemp("samples")
    build_all(str(out))
    return str(out)


def _make_qa(qid="q001", **overrides):
    qa = {
        "qid": qid,
        "question": "公司年假有几天？",
        "ground_truth_answer": "按工龄5/10/15天",
        "source_passage": "年假满一年不满五年为五天",
        "source_file": "员工手册.txt",
        "question_type": "fact",
    }
    qa.update(overrides)
    return qa


# ---------- 段落提取 ----------

class TestExtractPassages:
    def test_all_five_formats_covered(self, samples_dir):
        passages = extract_passages(samples_dir)
        by_file = {p.source_file for p in passages}
        assert any(f.endswith(".txt") for f in by_file)
        assert any(f.endswith(".pdf") for f in by_file)
        assert any(f.endswith(".docx") for f in by_file)
        assert any(f.endswith(".xlsx") for f in by_file)
        assert any(f.endswith(".md") for f in by_file)

    def test_passages_meet_min_length(self, samples_dir):
        assert all(len(p.text) >= 60 for p in extract_passages(samples_dir))

    def test_xlsx_passage_contains_sheet_and_row(self, samples_dir):
        xlsx_passages = [p for p in extract_passages(samples_dir)
                         if p.source_file.endswith(".xlsx")]
        assert xlsx_passages
        joined = "\n".join(p.text for p in xlsx_passages)
        assert "物资编码" in joined          # 表头列名进入行句子
        assert "【" in joined                # 段首带 Sheet 名

    def test_md_passage_keeps_heading_context(self, samples_dir):
        md_passages = [p for p in extract_passages(samples_dir)
                       if p.source_file.endswith(".md")]
        assert md_passages
        assert any(p.text.startswith("#") for p in md_passages)

    def test_missing_dir_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            extract_passages(str(tmp_path / "not_exist"))


# ---------- QA JSON 解析 ----------

class TestParseQaJson:
    def test_valid_array(self):
        text = '[{"question": "Q1", "answer": "A1", "question_type": "fact"}]'
        items = parse_qa_json(text)
        assert items == [{"question": "Q1", "answer": "A1", "question_type": "fact"}]

    def test_markdown_wrapped(self):
        text = '```json\n[{"question": "Q", "answer": "A", "question_type": "term"}]\n```'
        assert parse_qa_json(text)[0]["question_type"] == "term"

    def test_bad_items_filtered(self):
        text = '''[
            {"question": "Q1", "answer": "A1", "question_type": "fact"},
            {"question": "", "answer": "A2", "question_type": "fact"},
            {"question": "Q3", "answer": "A3", "question_type": "unknown"},
            {"question": "Q4", "answer": "", "question_type": "longtail"}
        ]'''
        items = parse_qa_json(text)
        assert len(items) == 1 and items[0]["question"] == "Q1"

    def test_invalid_returns_empty(self):
        assert parse_qa_json("no json here") == []
        assert parse_qa_json('{"not": "array"}') == []
        assert parse_qa_json("") == []


# ---------- 均衡采样 ----------

class TestSampleBalanced:
    def test_round_robin_across_files(self):
        qas = []
        for f in ("A.txt", "B.txt", "C.txt"):
            for i in range(5):
                qas.append({"source_file": f, "i": i})
        sampled = sample_balanced(qas, num=6)
        assert len(sampled) == 6
        counts = {}
        for qa in sampled:
            counts[qa["source_file"]] = counts.get(qa["source_file"], 0) + 1
        assert counts == {"A.txt": 2, "B.txt": 2, "C.txt": 2}

    def test_no_sampling_when_under_num(self):
        qas = [{"source_file": "A.txt"}] * 3
        assert sample_balanced(qas, num=10) == qas


# ---------- build（mock LLM，验证组装与落盘） ----------

class TestBuildDataset:
    def test_build_writes_valid_dataset(self, samples_dir, tmp_path, monkeypatch):
        from app.service.eval import dataset as dataset_mod

        calls = []

        def fake_generate(bound_model, passage, n):
            calls.append(passage.source_file)
            return [{"question": f"Q-{passage.source_file}",
                     "answer": "A",
                     "question_type": "fact"} for _ in range(n)]

        class FakeChat:
            def bind(self, **kw):
                return self

        monkeypatch.setattr(dataset_mod, "chat_model", FakeChat())
        monkeypatch.setattr(dataset_mod, "generate_qa_for_passage", fake_generate)

        out_path = str(tmp_path / "eval_dataset.json")
        result = build_dataset(num=10, out_path=out_path, samples_dir=samples_dir)

        # 全部段落都参与了生成
        assert len(calls) == len(extract_passages(samples_dir))
        # 轮转采样到 num 条且各文件均衡
        assert len(result) == 10
        counts = {}
        for qa in result:
            counts[qa["source_file"]] = counts.get(qa["source_file"], 0) + 1
        assert max(counts.values()) - min(counts.values()) <= 1
        # qid 重排为 q001 起
        assert [qa["qid"] for qa in result] == [f"q{i:03d}" for i in range(1, 11)]
        # 落盘文件可被 load_dataset 直接加载（格式自洽）
        assert load_dataset(out_path) == result


# ---------- 加载校验 ----------

class TestLoadDataset:
    def _write(self, tmp_path, data):
        path = tmp_path / "eval_dataset.json"
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return str(path)

    def test_valid(self, tmp_path):
        path = self._write(tmp_path, [_make_qa()])
        assert load_dataset(path)[0]["qid"] == "q001"

    def test_missing_file(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_dataset(str(tmp_path / "nope.json"))

    def test_not_a_list(self, tmp_path):
        path = self._write(tmp_path, {"a": 1})
        with pytest.raises(ValueError, match="非空 JSON 数组"):
            load_dataset(path)

    @pytest.mark.parametrize("field", ["qid", "question", "ground_truth_answer",
                                       "source_passage", "source_file", "question_type"])
    def test_missing_required_field(self, tmp_path, field):
        qa = _make_qa()
        qa.pop(field)
        with pytest.raises(ValueError, match=field):
            load_dataset(self._write(tmp_path, [qa]))

    def test_duplicate_qid(self, tmp_path):
        with pytest.raises(ValueError, match="重复"):
            load_dataset(self._write(tmp_path, [_make_qa("q001"), _make_qa("q001")]))

    def test_bad_question_type(self, tmp_path):
        with pytest.raises(ValueError, match="question_type 非法"):
            load_dataset(self._write(tmp_path, [_make_qa(question_type="open")]))

    def test_paraphrase_type_accepted(self, tmp_path):
        # v2 新增题型（执行文档 4.6）：同义改写题与 v1 三类一样可正常加载
        path = self._write(tmp_path, [_make_qa(question_type="paraphrase")])
        assert load_dataset(path)[0]["question_type"] == "paraphrase"


class TestDatasetMd5:
    def test_stable_and_sensitive(self, tmp_path):
        p1 = tmp_path / "a.json"
        p2 = tmp_path / "b.json"
        p1.write_text("[1]", encoding="utf-8")
        p2.write_text("[2]", encoding="utf-8")
        assert dataset_md5(str(p1)) == dataset_md5(str(p1))
        assert dataset_md5(str(p1)) != dataset_md5(str(p2))

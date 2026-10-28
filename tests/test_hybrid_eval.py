# -*- coding: utf-8 -*-
'''A/B 评测单元测试（数据集/服务/裁判全 mock，不触网不连库）'''
import json
from types import SimpleNamespace
from unittest.mock import patch

from langchain_core.documents import Document

from app.service.eval.complex_subset import load_complex_dataset, scan_candidates
from app.service.eval.hybrid_runner import (
    build_targets,
    render_markdown,
    run_ab_eval,
    summarize_records,
)
from app.service.orchestration.hybrid_orchestrator import OrchestrationResult
from app.service.routing.rule_router import RuleRouter

RULES = {"threshold": 2, "rules": [
    {"id": "compare", "pattern": "对比|比较", "weight": 2, "strong": True},
    {"id": "calc", "pattern": "计算|合计", "weight": 1, "strong": False},
]}

SIMPLE = [
    {"qid": "q1", "question": "年假多少天？", "ground_truth_answer": "5天",
     "source_passage": "年假 5 天。", "source_file": "a.txt", "question_type": "fact"},
    {"qid": "q2", "question": "对比上海和北京的住宿", "ground_truth_answer": "上海400",
     "source_passage": "上海 400。", "source_file": "b.txt", "question_type": "fact"},
    {"qid": "q3", "question": "预算几月启动？", "ground_truth_answer": "9月",
     "source_passage": "9 月启动。", "source_file": "a.txt", "question_type": "fact"},
]

AUTHORED = [
    {"qid": "c1", "question": "对比两地标准并计算差额", "ground_truth_answer": "差50元",
     "source_passage": "上海 400，北京 350。", "source_file": "b.txt",
     "question_type": "fact"},
]


class FakeRag:
    def rag_summarize(self, query, session_id=None):
        return "直调答案", [Document(page_content="上下文", metadata={"document_id": 1})]


class FakeOrchestrator:
    def answer(self, query, session_id=None):
        return OrchestrationResult(
            answer="混合答案",
            documents=[Document(page_content="上下文", metadata={"document_id": 1})],
            trace={"route": "react_complex", "answer_source": "react", "fallback": False,
                   "fallback_reason": None, "tool_calls": 2, "total_ms": 5,
                   "route_reason": "fake", "matched_rules": ["compare"]},
        )


class FakeJudge:
    def bind(self, temperature=0):
        return self

    def invoke(self, prompt):
        return SimpleNamespace(content='{"score": 1.0, "reason": "一致"}')


def _write_datasets(tmp_path):
    simple_path = tmp_path / "simple.json"
    simple_path.write_text(json.dumps(SIMPLE, ensure_ascii=False), encoding="utf-8")
    authored_path = tmp_path / "authored.json"
    authored_path.write_text(json.dumps(AUTHORED, ensure_ascii=False), encoding="utf-8")
    qids_path = tmp_path / "qids.json"
    qids_path.write_text(json.dumps({"qids": ["q2"]}, ensure_ascii=False), encoding="utf-8")
    return str(simple_path), str(qids_path), str(authored_path)


class TestComplexSubset:
    def test_scan_candidates(self):
        candidates = scan_candidates(SIMPLE, router=RuleRouter(rules_config=RULES))
        assert [c["qid"] for c in candidates] == ["q2"]

    def test_load_complex_dataset_merges_selected_and_authored(self, tmp_path):
        simple_path, qids_path, authored_path = _write_datasets(tmp_path)
        complex_set, missing = load_complex_dataset(simple_path, qids_path, authored_path)
        assert missing == []
        assert [qa["qid"] for qa in complex_set] == ["q2", "c1"]
        assert [qa["complex_source"] for qa in complex_set] == ["v2_selected", "authored"]

    def test_missing_qid_reported(self, tmp_path):
        simple_path, qids_path, authored_path = _write_datasets(tmp_path)
        qids_path = tmp_path / "qids2.json"
        qids_path.write_text(json.dumps(["q2", "q404"], ensure_ascii=False), encoding="utf-8")
        _, missing = load_complex_dataset(simple_path, str(qids_path), authored_path)
        assert missing == ["q404"]


class TestTargets:
    def test_excludes_selected_and_applies_limits(self):
        complex_set = [dict(SIMPLE[1], complex_source="v2_selected"),
                       dict(AUTHORED[0], complex_source="authored")]
        targets = build_targets(SIMPLE, complex_set, limit_simple=5, limit_complex=1)
        assert [qa["qid"] for qa, is_complex in targets if not is_complex] == ["q1", "q3"]
        assert [qa["qid"] for qa, is_complex in targets if is_complex] == ["q2"]


class TestSummary:
    def _records(self):
        return [
            {"doc_hit": True, "passage_hit": True, "correctness": 1.0,
             "faithfulness": 1.0, "answer_relevancy": 0.8, "latency_ms": 100,
             "tool_calls": 2, "fallback": False, "fallback_reason": None,
             "task_completion": True},
            {"doc_hit": False, "passage_hit": False, "correctness": 0.5,
             "faithfulness": 0.5, "answer_relevancy": 0.6, "latency_ms": 300,
             "tool_calls": 0, "fallback": True, "fallback_reason": "timeout",
             "task_completion": True},
            {"doc_hit": True, "passage_hit": False, "correctness": None,
             "faithfulness": None, "answer_relevancy": None, "latency_ms": 200,
             "tool_calls": 1, "fallback": True, "fallback_reason": "timeout",
             "task_completion": False},
        ]

    def test_aggregate(self):
        summary = summarize_records(self._records())
        assert summary["num_questions"] == 3
        assert summary["doc_hit_rate"] == 2 / 3
        assert summary["passage_hit_rate"] == 1 / 3
        assert summary["answer_correctness"]["mean"] == 0.75
        assert summary["answer_correctness"]["num_judge_error"] == 1
        assert summary["avg_latency_ms"] == 200
        assert summary["p95_latency_ms"] == 300
        assert summary["task_completion_rate"] == 2 / 3
        assert summary["fallback_rate"] == 2 / 3
        assert summary["fallback_reasons"] == {"timeout": 2}
        assert summary["avg_tool_calls"] == 1


class TestRunAB:
    def test_end_to_end_with_fakes(self, tmp_path):
        simple_path, qids_path, authored_path = _write_datasets(tmp_path)
        reports = tmp_path / "reports"

        with patch("app.service.eval.hybrid_runner.get_chat_history") as mock_history:
            result = run_ab_eval(
                tag="AB-test", groups=("A", "B"),
                dataset_path=simple_path, complex_qids_path=qids_path,
                authored_path=authored_path, rag=FakeRag(),
                orchestrator=FakeOrchestrator(), judge_model=FakeJudge(),
                doc_map={"a.txt": 1, "b.txt": 2}, reports_dir=str(reports),
            )

        assert mock_history.return_value.clear.call_count == 8  # 2 组 × 4 题
        assert result["meta"]["num_simple"] == 2
        assert result["meta"]["num_complex"] == 2

        group_a = result["groups"]["A"]["details"]
        group_b = result["groups"]["B"]["details"]
        assert all(r["route"] == "rag_direct" for r in group_a)
        assert all(r["tool_calls"] == 0 for r in group_a)
        assert group_b[0]["route"] == "react_complex"
        assert group_b[0]["tool_calls"] == 2
        assert group_a[0]["correctness"] == 1.0
        assert group_a[0]["task_completion"] is None
        # 固定返回 document_id=1：简单集（a.txt=1）命中，复杂集（b.txt=2）不命中
        assert result["groups"]["A"]["summary"]["simple"]["doc_hit_rate"] == 1.0
        assert result["groups"]["A"]["summary"]["complex"]["doc_hit_rate"] == 0.0

        paths = result["meta"]["reports"]
        assert paths["json"].endswith("_AB-test.json")
        assert paths["csv"].endswith("_AB-test.csv")
        assert paths["markdown"].endswith("_AB-compare.md")
        with open(paths["json"], encoding="utf-8") as f:
            assert json.load(f)["meta"]["tag"] == "AB-test"
        with open(paths["markdown"], encoding="utf-8") as f:
            assert "指标对照" in f.read()

    def test_judge_disabled_and_single_group(self, tmp_path):
        simple_path, qids_path, authored_path = _write_datasets(tmp_path)
        with patch("app.service.eval.hybrid_runner.get_chat_history"):
            result = run_ab_eval(
                tag="AB-nojudge", groups=("A",),
                limit_simple=1, limit_complex=1,
                dataset_path=simple_path, complex_qids_path=qids_path,
                authored_path=authored_path, rag=FakeRag(),
                orchestrator=FakeOrchestrator(), judge_model=None,
                doc_map={"a.txt": 1, "b.txt": 2},
                reports_dir=str(tmp_path / "reports2"),
            )
        assert result["meta"]["judge_enabled"] is False
        assert result["meta"]["num_simple"] == 1
        assert result["meta"]["reports"]["markdown"].endswith("_AB-nojudge.md")
        assert result["groups"]["A"]["details"][0]["correctness"] is None

    def test_render_markdown_has_metric_rows(self, tmp_path):
        simple_path, qids_path, authored_path = _write_datasets(tmp_path)
        with patch("app.service.eval.hybrid_runner.get_chat_history"):
            result = run_ab_eval(
                tag="AB-md", groups=("A", "B"),
                dataset_path=simple_path, complex_qids_path=qids_path,
                authored_path=authored_path, rag=FakeRag(),
                orchestrator=FakeOrchestrator(), judge_model=FakeJudge(),
                doc_map={"a.txt": 1, "b.txt": 2},
                reports_dir=str(tmp_path / "reports3"),
            )
        markdown = render_markdown(result)
        assert "答案正确率" in markdown
        assert "降级分布" in markdown
        assert "A-简单集" in markdown and "B-简单集" in markdown

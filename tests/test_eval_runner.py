# -*- coding: utf-8 -*-
"""eval.runner 评测编排 + eval.report 报告生成/对比单元测试

全部外部依赖 mock：VectorStoreService / RagSummarizeService / chat_model /
document 表反查 / 聊天历史 / 裁判函数 / 报告落盘，不连 Qdrant/MySQL/DashScope。
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.documents import Document

from app.service.eval import report as report_mod
from app.service.eval import runner as runner_mod


# ---------- 测试数据 ----------

def _make_dataset(path, questions):
    """写临时评测集；questions: [(qid, source_file, passage)]"""
    data = [{
        "qid": qid,
        "question": f"问题{qid}",
        "ground_truth_answer": f"答案{qid}",
        "source_passage": passage,
        "source_file": source_file,
        "question_type": "fact" if i % 2 == 0 else "longtail",
    } for i, (qid, source_file, passage) in enumerate(questions)]
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return str(path)


def _fake_retriever(responses: dict[str, list[Document]]):
    """按问题文本路由返回结果的假检索器"""
    retriever = MagicMock()

    def invoke(query):
        return responses[query]

    retriever.invoke.side_effect = invoke
    return retriever


@pytest.fixture
def eval_env(tmp_path):
    """准备评测集 + 各 mock，返回可直传 run_eval 的参数与断言用的 mock 容器"""
    q001_passage = "年假满一年不满五年为五天满五年不满十年为十天满十年及以上为十五天"
    dataset_path = _make_dataset(tmp_path / "eval_dataset.json", [
        ("q001", "A.txt", q001_passage),
        ("q002", "A.txt", "调休自产生之日起六个月内有效逾期清零"),
        ("q003", "B.txt", "密码长度不得低于十二位且每九十天更换"),
    ])

    doc_hit = Document(page_content=q001_passage, metadata={"document_id": 1})
    doc_miss = Document(page_content="无关内容", metadata={"document_id": 99})
    retriever = _fake_retriever({
        "问题q001": [doc_hit, doc_miss],
        "问题q002": [doc_miss, doc_miss],
        "问题q003": [doc_miss],
    })

    svc = MagicMock()
    svc.get_retriever.return_value = retriever

    # P2：默认路径走 build_retriever 组装链路；mock 掉以隔离真实链路
    # （否则 hybrid+rerank 开启时会触网构造精排器、连库构建 BM25 索引）
    build = MagicMock(return_value=retriever)
    bm25 = MagicMock()

    mocks = {"svc": svc, "retriever": retriever, "build_retriever": build,
             "bm25": bm25, "saved": []}

    def fake_save(result, tag, reports_dir=None):
        mocks["saved"].append(result)
        return f"/tmp/fake_{tag}.json", f"/tmp/fake_{tag}.md"

    with patch.object(runner_mod, "VectorStoreService", return_value=svc), \
         patch.object(runner_mod, "build_retriever", build), \
         patch.object(runner_mod, "fetch_chunk_documents", AsyncMock(return_value=[])), \
         patch.object(runner_mod, "bm25_retriever", bm25), \
         patch.object(runner_mod, "fetch_document_map", return_value={"A.txt": 1}), \
         patch.object(report_mod, "save_report", side_effect=fake_save):
        mocks["dataset_path"] = dataset_path
        yield mocks


# ---------- 检索模式 ----------

class TestRunEvalRetrieval:
    def test_retrieval_metrics_and_missing_warning(self, eval_env):
        result = runner_mod.run_eval(tag="t-retrieval", mode="retrieval",
                                     dataset_path=eval_env["dataset_path"])

        r = result["retrieval"]
        assert r["num_questions"] == 3
        assert r["hit_rate_doc"] == pytest.approx(1 / 3)     # 仅 q001 命中
        assert r["mrr_doc"] == pytest.approx(1 / 3)          # 首位命中
        assert r["precision_doc"] == pytest.approx(1 / 5)    # 1 命中 / 5 返回
        assert r["recall_content"] == pytest.approx(1 / 3)
        assert result["missing_source_files"] == ["B.txt"]

        # 分组聚合存在且分组键正确
        assert set(result["retrieval_by_type"]) == {"fact", "longtail"}
        assert set(result["retrieval_by_source_file"]) == {"A.txt", "B.txt"}

        # meta 口径信息
        assert result["meta"]["tag"] == "t-retrieval"
        assert result["meta"]["mode"] == "retrieval"
        assert result["meta"]["num_questions"] == 3
        assert result["meta"]["dataset_md5"]

        # 报告已落盘调用
        assert eval_env["saved"] and eval_env["saved"][0]["meta"]["tag"] == "t-retrieval"
        # 检索模式不实例化生成服务
        assert "generation" not in result

    def test_limit_takes_first_n(self, eval_env):
        result = runner_mod.run_eval(tag="t-limit", mode="retrieval", limit=1,
                                     dataset_path=eval_env["dataset_path"])
        assert result["meta"]["num_questions"] == 1

    def test_k_override_uses_vector_store_retriever(self, eval_env):
        svc = eval_env["svc"]
        custom = MagicMock()
        svc.vector_store.as_retriever.return_value = custom
        runner_mod.run_eval(tag="t-k", mode="retrieval", k=5,
                            dataset_path=eval_env["dataset_path"])
        svc.vector_store.as_retriever.assert_called_once_with(search_kwargs={"k": 5})
        assert not svc.get_retriever.called
        assert not eval_env["build_retriever"].called   # k 覆盖直连稠密检索，不走链路组装


# ---------- P2 链路预设 ----------

class TestRunEvalPreset:
    def test_preset_passes_overrides_and_meta(self, eval_env):
        build = eval_env["build_retriever"]
        result = runner_mod.run_eval(tag="t-preset", mode="retrieval", preset="hybrid-rerank",
                                     dataset_path=eval_env["dataset_path"])
        build.assert_called_once()
        kwargs = build.call_args.kwargs
        assert kwargs.get("overrides") == runner_mod.PRESETS["hybrid-rerank"]
        # rerank 开启 → meta.k 取 rerank.top_k=5
        assert result["meta"]["preset"] == "hybrid-rerank"
        assert result["meta"]["k"] == 5
        snap = result["meta"]["config_snapshot"]["retrieval"]
        assert snap["hybrid"]["enabled"] is True
        assert snap["rerank"]["enabled"] is True

    def test_preset_hybrid_loads_bm25_and_dense_only_not(self, eval_env):
        bm25 = eval_env["bm25"]
        result = runner_mod.run_eval(tag="t-h", mode="retrieval", preset="hybrid",
                                     dataset_path=eval_env["dataset_path"])
        assert bm25.load_documents.called        # hybrid 生效前确保 BM25 就绪
        assert result["meta"]["k"] == 5          # RRF → top_k

        bm25.reset_mock()
        result = runner_mod.run_eval(tag="t-d", mode="retrieval", preset="dense-only",
                                     dataset_path=eval_env["dataset_path"])
        assert not bm25.load_documents.called    # 纯稠密无需 BM25
        assert result["meta"]["k"] == 5          # legacy_k 标量覆盖=5

    def test_preset_legacy_falls_back_to_old_k(self, eval_env):
        result = runner_mod.run_eval(tag="t-l", mode="retrieval", preset="legacy",
                                     dataset_path=eval_env["dataset_path"])
        assert result["meta"]["k"] == 3          # 全关闭 → dense k=legacy_k(3)


# ---------- 全量模式 ----------

class TestRunEvalFull:
    def test_generation_and_session_isolation(self, eval_env):
        rag = MagicMock()
        rag.rag_summarize.return_value = "标准答案"
        history = MagicMock()
        sessions = []

        def fake_history(session_id):
            sessions.append(session_id)
            return history

        with patch.object(runner_mod, "RagSummarizeService", return_value=rag), \
             patch.object(runner_mod, "get_eval_chat_model", return_value=MagicMock()), \
             patch.object(runner_mod, "get_chat_history", side_effect=fake_history), \
             patch.object(runner_mod, "faithfulness", return_value=0.9), \
             patch.object(runner_mod, "answer_relevancy", return_value=0.8):
            result = runner_mod.run_eval(tag="t-full", mode="full",
                                         dataset_path=eval_env["dataset_path"])

        gen = result["generation"]
        assert gen["faithfulness"]["num_judged"] == 3
        assert gen["faithfulness"]["mean"] == pytest.approx(0.9)
        assert gen["answer_relevancy"]["mean"] == pytest.approx(0.8)

        # 每题独立会话 eval_{tag}_{qid}，且生成前清空历史（重跑同 tag 幂等）
        assert sessions == ["eval_t-full_q001", "eval_t-full_q002", "eval_t-full_q003"]
        assert history.clear.call_count == 3
        rag.rag_summarize.assert_any_call("问题q001", session_id="eval_t-full_q001")

        # detail 含答案与裁判分数
        d = result["details"][0]
        assert d["answer"] == "标准答案"
        assert d["faithfulness"] == 0.9 and d["answer_relevancy"] == 0.8


# ---------- 配置快照 ----------

class TestSnapshotConfig:
    def test_remote_default(self, monkeypatch):
        monkeypatch.delenv("MODEL_MODE", raising=False)
        monkeypatch.delenv("OPENAI_CHAT_MODEL", raising=False)
        snap = runner_mod.snapshot_config()
        assert snap["model_mode"] == "remote"
        assert snap["chat_model_name"]       # 来自 OPENAI_CHAT_MODEL 环境变量（或默认值）
        assert snap["embedding_model_name"]
        assert "chunk_size" in snap["qdrant"] and "k" in snap["qdrant"]

    def test_local_mode_and_env_override(self, monkeypatch):
        monkeypatch.setenv("MODEL_MODE", "LOCAL")          # 大小写归一
        monkeypatch.setenv("OLLAMA_CHAT_MODEL", "qwen2.5:7b-custom")
        snap = runner_mod.snapshot_config()
        assert snap["model_mode"] == "local"
        assert snap["chat_model_name"] == "qwen2.5:7b-custom"

    def test_invalid_mode_falls_back_remote(self, monkeypatch):
        monkeypatch.setenv("MODEL_MODE", "wrong")
        assert runner_mod.snapshot_config()["model_mode"] == "remote"


# ---------- 报告生成与对比 ----------

def _fake_result(tag, mode="full"):
    return {
        "meta": {
            "tag": tag, "mode": mode, "finished_at": "2026-10-18T12:00:00",
            "num_questions": 3, "k": 3,
            "config_snapshot": {"model_mode": "remote", "chat_model_name": "m",
                                "embedding_model_name": "e",
                                "qdrant": {"collection_name": "c", "chunk_size": 150,
                                           "chunk_overlap": 20}},
            "dataset_md5": "d41d8cd98f00b204e9800998ecf8427e",
        },
        "missing_source_files": [],
        "retrieval": {"num_questions": 3, "hit_rate_doc": 0.33, "hit_rate_passage": 0.33,
                      "mrr_doc": 0.33, "mrr_passage": 0.33, "precision_doc": 0.2,
                      "precision_passage": 0.2, "recall_content": 0.3},
        "retrieval_by_type": {"fact": {"num_questions": 2}},
        "retrieval_by_source_file": {"A.txt": {"num_questions": 3}},
        "generation": {
            "faithfulness": {"num_judged": 3, "num_judge_error": 0, "mean": 0.9},
            "answer_relevancy": {"num_judged": 3, "num_judge_error": 0, "mean": 0.8},
        },
        "details": [],
    }


class TestRenderMarkdown:
    def test_contains_sections(self):
        md = report_mod.render_markdown(_fake_result("P0-baseline"))
        assert "# RAG 评测报告：P0-baseline" in md
        assert "文档级 HitRate@K" in md
        assert "按问题类型" in md and "按样例文件" in md
        assert "Faithfulness 忠实度" in md and "0.9000" in md
        assert "评测集 MD5" in md

    def test_missing_files_warning(self):
        result = _fake_result("t", mode="retrieval")
        result["missing_source_files"] = ["B.txt", "C.docx"]
        md = report_mod.render_markdown(result)
        assert "未成功入库样例" in md and "B.txt" in md

    def test_retrieval_mode_has_no_generation_section(self):
        result = _fake_result("t", mode="retrieval")
        result.pop("generation")
        md = report_mod.render_markdown(result)
        assert "生成指标" not in md


class TestSaveAndFindReport:
    def test_save_writes_json_and_md(self, tmp_path):
        json_path, md_path = report_mod.save_report(_fake_result("t-save"), "t-save",
                                                    reports_dir=str(tmp_path))
        assert json_path.endswith("_t-save.json") and md_path.endswith("_t-save.md")
        assert json.load(open(json_path, encoding="utf-8"))["meta"]["tag"] == "t-save"
        assert "RAG 评测报告" in open(md_path, encoding="utf-8").read()

    def test_find_latest_by_timestamp(self, tmp_path):
        for ts in ("20260101_000000", "20260202_000000"):
            (tmp_path / f"{ts}_t-find.json").write_text("{}", encoding="utf-8")
        assert report_mod.find_report("t-find", str(tmp_path)).endswith("20260202_000000_t-find.json")

    def test_find_missing_returns_none(self, tmp_path):
        assert report_mod.find_report("nope", str(tmp_path)) is None


class TestCompare:
    def test_compare_two_tags(self, tmp_path, capsys):
        report_mod.save_report(_fake_result("P0-baseline"), "P0-baseline", reports_dir=str(tmp_path))
        p1 = _fake_result("P1")
        p1["retrieval"]["hit_rate_doc"] = 0.66
        report_mod.save_report(p1, "P1", reports_dir=str(tmp_path))

        content = report_mod.compare(["P0-baseline", "P1"], reports_dir=str(tmp_path))
        assert "P0-baseline vs P1" in content
        assert "0.3300" in content and "0.6600" in content
        assert "各版本评测条件" in content
        assert "对比报告已生成" in capsys.readouterr().out

    def test_missing_tag_skipped(self, tmp_path):
        report_mod.save_report(_fake_result("P0-baseline"), "P0-baseline", reports_dir=str(tmp_path))
        with pytest.raises(SystemExit):
            report_mod.compare(["P0-baseline", "ghost"], reports_dir=str(tmp_path))

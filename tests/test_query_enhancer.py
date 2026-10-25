# -*- coding: utf-8 -*-
"""P3 查询优化单测（执行文档 7.2 / 第 10 章 test_query_enhancer.py）

覆盖验收点：
- 两策略可配置启用：off 透传 / multi_query 多路召回+RRF 融合 / hyde 两路融合
- mock LLM（FakeChat）断言：temperature=0 绑定、多路召回查询集合、融合结果正确性
- parse_multi_queries 解析容错：编号前缀/围栏行/空行/重复/原查询过滤/cap n
- LLM 调用失败或解析为空 → 回退原查询直查（不经融合）
- build_retriever 集成：mode=multi_query 时末端包装 QueryEnhancer（注入 fake 组件）
"""
from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.retrievers import BaseRetriever
from pydantic import PrivateAttr

from app.service.rag.query import MODES, QueryEnhancer, parse_multi_queries
from app.service.rag.query.hyde import generate_hypothetical_document
from app.service.rag.query.multi_query import generate_multi_queries
from app.service.rag.retrieval.hybrid_retriever import (
    RerankRetriever,
    _effective_conf,
    build_retriever,
    effective_output_k,
)
from app.service.rag.retrieval.rrf import rrf_fuse

# ========================================
# Fake 组件
# ========================================


def _docs(prefix: str, ids: list[str]) -> list[Document]:
    """构造带确定性 vector_id 的文档（供 RRF 融合去重）"""
    return [
        Document(page_content=f"{i} 的内容（{prefix}）", metadata={"vector_id": i, "source": prefix})
        for i in ids
    ]


class FakeRetriever(BaseRetriever):
    """按查询返回预置结果并记录收到的每一路查询"""

    topn: int = 10  # 充当 bm25 角色时供 build_retriever 日志读取
    _mapping: dict = PrivateAttr(default_factory=dict)
    _queries: list = PrivateAttr(default_factory=list)

    def __init__(self, mapping: dict | None = None, **kwargs):
        super().__init__(**kwargs)
        self._mapping = mapping or {}

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> list[Document]:
        self._queries.append(query)
        # 返回副本，避免融合过程改动预置数据
        return [
            Document(page_content=d.page_content, metadata=dict(d.metadata))
            for d in self._mapping.get(query, [])
        ]


class FakeChat(BaseChatModel):
    """固定文本返回 / 可控抛错，记录 bind 参数与收到 prompt 的假聊天模型"""

    response_text: str = ""
    fail: bool = False
    _bound: list = PrivateAttr(default_factory=list)
    _prompts: list = PrivateAttr(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "fake"

    def bind(self, **kwargs):
        self._bound.append(kwargs)
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        if self.fail:
            raise RuntimeError("LLM 调用失败（测试注入）")
        self._prompts.append(messages[-1].content if messages else "")
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=self.response_text))])


class FakeReranker:
    """保序打分的假精排器（safe_rank 降级语义：异常才透传，这里恒成功）"""

    def __init__(self, top_k: int = 5):
        self.top_k = top_k

    def safe_rank(self, query, docs):
        return [(doc, 1.0 / (i + 1)) for i, doc in enumerate(docs[: self.top_k])]


class FakeVectorStoreService:
    """记录 get_retriever(k=...) 调用的假向量库服务"""

    def __init__(self, retriever: BaseRetriever):
        self._retriever = retriever
        self.ks: list[int] = []

    def get_retriever(self, k: int = 4) -> BaseRetriever:
        self.ks.append(k)
        return self._retriever


def _enhancer(mapping: dict, chat: FakeChat, mode: str, **kwargs):
    """构造 QueryEnhancer + 底层 FakeRetriever"""
    base = FakeRetriever(mapping=mapping)
    enhancer = QueryEnhancer(base=base, chat_model=chat, mode=mode, **kwargs)
    return enhancer, base


# ========================================
# parse_multi_queries 解析容错
# ========================================


def test_parse_multi_queries_strips_and_filters():
    text = (
        "1. 改写一\n"
        "2、改写二\n"
        "3) 原查询\n"
        "\n"
        "```text\n"
        "改写三\n"
        "```\n"
        "（四）改写四\n"
        "- 改写五\n"
        "* 改写六\n"
        "改写一\n"
    )
    # 编号前缀剥离 / 空行与围栏行跳过 / 原查询与重复项过滤
    assert parse_multi_queries(text, "原查询", 10) == [
        "改写一", "改写二", "改写三", "改写四", "改写五", "改写六",
    ]
    # 至多 n 条
    assert parse_multi_queries(text, "原查询", 2) == ["改写一", "改写二"]


def test_parse_multi_queries_empty_inputs():
    assert parse_multi_queries("", "原查询", 3) == []
    # 输出仅与原查询重复 → 视为解析为空
    assert parse_multi_queries("原查询", "原查询", 3) == []


# ========================================
# 变体生成层（FakeChat）
# ========================================


def test_generate_multi_queries_binds_temperature_zero():
    chat = FakeChat(response_text="改写A\n改写B")
    assert generate_multi_queries(chat, "Q", 3) == ["改写A", "改写B"]
    # temperature=0 经 bind 绑定，不改共享单例
    assert chat._bound == [{"temperature": 0}]
    assert len(chat._prompts) == 1 and "Q" in chat._prompts[0]


def test_generate_multi_queries_failure_returns_empty():
    assert generate_multi_queries(FakeChat(fail=True), "Q", 3) == []


def test_generate_hypothetical_document_roundtrip():
    chat = FakeChat(response_text="  假设文档内容  ")
    assert generate_hypothetical_document(chat, "Q") == "假设文档内容"
    assert chat._bound == [{"temperature": 0}]
    assert len(chat._prompts) == 1 and "Q" in chat._prompts[0]


def test_generate_hypothetical_document_failures():
    # 空文本（strip 后为空）与调用异常均返回 None
    assert generate_hypothetical_document(FakeChat(response_text="   "), "Q") is None
    assert generate_hypothetical_document(FakeChat(fail=True), "Q") is None


# ========================================
# QueryEnhancer 三模式行为
# ========================================


def test_mode_off_passthrough():
    docs = _docs("Q", ["a", "b"])
    enhancer, base = _enhancer({"Q": docs}, FakeChat(response_text="R1"), mode="off")
    assert enhancer.invoke("Q") == docs          # 原样透传
    assert base._queries == ["Q"]                # 底层只收到原查询
    assert enhancer._chat_model._prompts == []   # 未调用 LLM


def test_unknown_mode_treated_as_off():
    assert MODES == ("off", "multi_query", "hyde")
    docs = _docs("Q", ["a"])
    enhancer, base = _enhancer({"Q": docs}, FakeChat(response_text="R1"), mode="banana")
    assert enhancer.invoke("Q") == docs
    assert base._queries == ["Q"]


def test_mode_multi_query_multi_path_fusion():
    mapping = {
        "Q": _docs("Q", ["a", "b"]),
        "R1": _docs("R1", ["a", "c"]),
        "R2": _docs("R2", ["b", "d"]),
        "R3": _docs("R3", ["c", "e"]),
    }
    chat = FakeChat(response_text="1. R1\n2、R2\n3) R3")  # 带编号噪声，覆盖解析
    enhancer, base = _enhancer(mapping, chat, mode="multi_query", topn=3, rrf_k=60)
    result = enhancer.invoke("Q")

    # 底层收到 原查询+3 改写 共 4 路（batch 并行，顺序不保证）
    assert sorted(base._queries) == ["Q", "R1", "R2", "R3"]
    # 融合结果与对同样四路直接 rrf_fuse 完全一致（含 rrf_score 元数据）
    expected = rrf_fuse([mapping[q] for q in ["Q", "R1", "R2", "R3"]], rrf_k=60, topn=3)
    assert result == expected
    assert all("rrf_score" in d.metadata for d in result)
    # a 被两路命中分数最高，b/c 并列次之，topn=3 截断
    assert [d.metadata["vector_id"] for d in result] == ["a", "b", "c"]


def test_mode_hyde_two_path_fusion():
    hyp = "假设文档：某产品 Q3 营收 100 万元"
    mapping = {
        "Q": _docs("Q", ["a", "b"]),
        hyp: _docs("hyp", ["a", "c", "b"]),
    }
    enhancer, base = _enhancer(mapping, FakeChat(response_text=hyp), mode="hyde", topn=2, rrf_k=60)
    result = enhancer.invoke("Q")

    assert sorted(base._queries) == sorted(["Q", hyp])   # 原查询+假设文档两路
    expected = rrf_fuse([mapping["Q"], mapping[hyp]], rrf_k=60, topn=2)
    assert result == expected
    # 假设文档仅作检索输入，不进入结果内容
    assert hyp not in [d.page_content for d in result]


def test_multi_query_llm_failure_fallback():
    docs = _docs("Q", ["a", "b"])
    mapping = {"Q": docs, "R1": _docs("R1", ["x"])}  # R1 路不应被触发
    enhancer, base = _enhancer(mapping, FakeChat(fail=True), mode="multi_query")
    result = enhancer.invoke("Q")

    assert result == docs                  # 回退原查询直查
    assert base._queries == ["Q"]          # 未发起多路 batch
    assert all("rrf_score" not in d.metadata for d in result)  # 未经过融合


def test_multi_query_empty_parse_fallback():
    docs = _docs("Q", ["a", "b"])
    # 改写输出与原查询完全相同 → 解析为空 → 回退
    enhancer, base = _enhancer({"Q": docs}, FakeChat(response_text="Q"), mode="multi_query")
    assert enhancer.invoke("Q") == docs
    assert base._queries == ["Q"]


def test_hyde_llm_failure_fallback():
    docs = _docs("Q", ["a"])
    enhancer, base = _enhancer({"Q": docs}, FakeChat(fail=True), mode="hyde")
    assert enhancer.invoke("Q") == docs
    assert base._queries == ["Q"]


def test_hyde_empty_document_fallback():
    docs = _docs("Q", ["a"])
    enhancer, base = _enhancer({"Q": docs}, FakeChat(response_text="   "), mode="hyde")
    assert enhancer.invoke("Q") == docs
    assert base._queries == ["Q"]


# ========================================
# build_retriever 集成（P3 包装接线）
# ========================================


def _integration_env(mode: str, mq_count: int = 2):
    dense = FakeRetriever(mapping={
        "Q": _docs("dense-Q", ["a", "b"]),
        "R1": _docs("dense-R1", ["a", "c"]),
        "R2": _docs("dense-R2", ["b", "d"]),
    })
    bm25 = FakeRetriever(mapping={
        "Q": _docs("bm25-Q", ["a", "e"]),
        "R1": _docs("bm25-R1", ["a"]),
        "R2": _docs("bm25-R2", ["e"]),
    }, topn=5)
    svc = FakeVectorStoreService(dense)
    overrides = {
        "hybrid": {"enabled": True},
        "rerank": {"enabled": True},
        "query_optimize": {"mode": mode, "multi_query_count": mq_count},
    }
    retriever = build_retriever(
        svc, bm25=bm25, reranker=FakeReranker(top_k=5),
        overrides=overrides, chat_model=FakeChat(response_text="R1\nR2"),
    )
    return retriever, dense, bm25


def test_build_retriever_off_returns_inner_chain():
    retriever, _, _ = _integration_env("off")
    assert isinstance(retriever, RerankRetriever)       # 未被 QueryEnhancer 包装
    assert not isinstance(retriever, QueryEnhancer)


def test_build_retriever_wraps_query_enhancer_multi_query():
    retriever, dense, bm25 = _integration_env("multi_query")
    assert isinstance(retriever, QueryEnhancer)
    assert retriever.mode == "multi_query"
    assert retriever.multi_query_count == 2
    # 融合 topn 与链路有效输出 k 同口径（rerank 开 → rerank.top_k）
    assert retriever.topn == effective_output_k(_effective_conf({
        "hybrid": {"enabled": True}, "rerank": {"enabled": True},
        "query_optimize": {"mode": "multi_query", "multi_query_count": 2},
    }))

    result = retriever.invoke("Q")
    # 稠密与稀疏两路底层均实际收到 原查询+2 改写 三路查询
    assert sorted(dense._queries) == ["Q", "R1", "R2"]
    assert sorted(bm25._queries) == ["Q", "R1", "R2"]
    assert 0 < len(result) <= retriever.topn
    assert all("rrf_score" in d.metadata for d in result)

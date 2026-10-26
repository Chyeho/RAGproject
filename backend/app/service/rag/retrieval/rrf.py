# -*- coding: utf-8 -*-
'''RRF（Reciprocal Rank Fusion）多路召回融合（P2）

公式：score(d) = Σ_lists 1/(rrf_k + rank_d)，rank 从 1 开始
以 vector_id 为融合主键（依赖 P1 确定性 chunk ID），去重合并 metadata，
融合结果按分数排序取 TopN 送入精排。
'''
from collections import defaultdict

from langchain_core.documents import Document


def rrf_fuse(
    result_lists: list[list[Document]],
    rrf_k: int = 60,
    topn: int = 20,
) -> list[Document]:
    '''多路召回结果 RRF 融合

    Args:
        result_lists: 各检索路（稠密/BM25 等）的结果列表，各自已按相关性降序排列
        rrf_k: RRF 平滑常数（默认 60）
        topn: 融合后保留条数

    Returns:
        融合去重后按 RRF 分数降序的 Document 列表，metadata 附 rrf_score；
        无 vector_id 的结果无法参与去重融合，跳过
    '''
    scores: dict[str, float] = defaultdict(float)
    # 每路首个出现的文档作为底稿，后续出现的仅补齐其缺失的 metadata 键
    base: dict[str, Document] = {}
    merged_meta: dict[str, dict] = {}

    for results in result_lists:
        for rank, doc in enumerate(results, start=1):
            vector_id = doc.metadata.get("vector_id")
            if not vector_id:
                continue
            scores[vector_id] += 1.0 / (rrf_k + rank)
            if vector_id not in base:
                base[vector_id] = doc
                merged_meta[vector_id] = dict(doc.metadata)
            else:
                merged_meta[vector_id].update(
                    {k: v for k, v in doc.metadata.items() if k not in merged_meta[vector_id]}
                )

    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:topn]
    # 输出统一新建 Document，不改动入参（稠密路为查询产物，BM25 路为索引内对象）
    return [
        Document(
            page_content=base[vector_id].page_content,
            metadata={**merged_meta[vector_id], "rrf_score": round(score, 6)},
        )
        for vector_id, score in ranked
    ]

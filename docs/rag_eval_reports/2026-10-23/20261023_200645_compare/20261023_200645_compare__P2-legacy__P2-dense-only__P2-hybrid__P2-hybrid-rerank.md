# RAG 评测多版本对比

- 对比对象：P2-legacy vs P2-dense-only vs P2-hybrid vs P2-hybrid-rerank
- 生成时间：2026-10-23T20:06:45

## 检索指标

| 指标 | P2-legacy | P2-dense-only | P2-hybrid | P2-hybrid-rerank |
|---|---|---|---|---|
| 题目数 | 80 | 80 | 80 | 80 |
| 文档级 HitRate@K | 0.9250 | 0.9750 | 1.0000 | 1.0000 |
| 片段级 HitRate@K | 0.9125 | 0.9375 | 1.0000 | 1.0000 |
| 文档级 MRR | 0.8958 | 0.9071 | 0.9563 | 1.0000 |
| 片段级 MRR | 0.8396 | 0.8458 | 0.9067 | 1.0000 |
| 文档级 Precision@K | 0.7792 | 0.6525 | 0.6300 | 0.6050 |
| 片段级 Precision@K | 0.3042 | 0.1875 | 0.2000 | 0.2000 |
| 内容召回率（重叠率均值） | 0.9114 | 0.9390 | 0.9975 | 0.9975 |

## 生成指标（LLM 裁判）

| 指标 | P2-legacy | P2-dense-only | P2-hybrid | P2-hybrid-rerank |
|---|---|---|---|---|
| Faithfulness 忠实度 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| AnswerRelevancy 相关性 | 0.9500 | 0.9600 | 0.9875 | 0.9875 |

## 各版本评测条件

| 版本 | 评测时间 | 模式 | 题数 | K | 聊天模型 | 嵌入模型 | chunk | 评测集MD5 |
|---|---|---|---|---|---|---|---|---|
| P2-legacy | 2026-10-23T20:06:28 | full | 80 | 3 | qwen3.7-max | text-embedding-v4 | 500/50 | ff39e805 |
| P2-dense-only | 2026-10-23T18:38:55 | full | 80 | 5 | qwen3.7-max | text-embedding-v4 | 500/50 | ff39e805 |
| P2-hybrid | 2026-10-23T18:59:35 | full | 80 | 5 | qwen3.7-max | text-embedding-v4 | 500/50 | ff39e805 |
| P2-hybrid-rerank | 2026-10-23T19:41:44 | full | 80 | 5 | qwen3.7-max | text-embedding-v4 | 500/50 | ff39e805 |

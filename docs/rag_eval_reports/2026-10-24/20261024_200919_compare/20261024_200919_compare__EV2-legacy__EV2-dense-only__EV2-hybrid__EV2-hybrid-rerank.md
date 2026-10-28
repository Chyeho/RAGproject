# RAG 评测多版本对比

- 对比对象：EV2-legacy vs EV2-dense-only vs EV2-hybrid vs EV2-hybrid-rerank
- 生成时间：2026-10-24T20:09:19

## 检索指标

| 指标 | EV2-legacy | EV2-dense-only | EV2-hybrid | EV2-hybrid-rerank |
|---|---|---|---|---|
| 题目数 | 260 | 260 | 260 | 260 |
| 文档级 HitRate@K | 0.6000 | 0.6923 | 0.7462 | 0.8115 |
| 片段级 HitRate@K | 0.4615 | 0.5115 | 0.6231 | 0.7846 |
| 文档级 MRR | 0.4949 | 0.5152 | 0.5389 | 0.5873 |
| 片段级 MRR | 0.3551 | 0.3662 | 0.4512 | 0.5675 |
| 文档级 Precision@K | 0.3218 | 0.2900 | 0.2646 | 0.3092 |
| 片段级 Precision@K | 0.1590 | 0.1054 | 0.1308 | 0.1623 |
| 内容召回率（重叠率均值） | 0.4847 | 0.5441 | 0.6441 | 0.7881 |

## 各版本评测条件

| 版本 | 评测时间 | 模式 | 题数 | K | 聊天模型 | 嵌入模型 | chunk | 评测集MD5 |
|---|---|---|---|---|---|---|---|---|
| EV2-legacy | 2026-10-24T19:49:59 | retrieval | 260 | 3 | qwen-plus | text-embedding-v4 | 500/50 | 9b68db07 |
| EV2-dense-only | 2026-10-24T19:54:37 | retrieval | 260 | 5 | qwen-plus | text-embedding-v4 | 500/50 | 9b68db07 |
| EV2-hybrid | 2026-10-24T19:59:27 | retrieval | 260 | 5 | qwen-plus | text-embedding-v4 | 500/50 | 9b68db07 |
| EV2-hybrid-rerank | 2026-10-24T20:08:50 | retrieval | 260 | 5 | qwen-plus | text-embedding-v4 | 500/50 | 9b68db07 |

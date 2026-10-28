# RAG 评测多版本对比

- 对比对象：P3-off vs P3-multi-query vs P3b-off vs P3b-multi-query vs P3b-multi-query-fuse
- 生成时间：2026-10-26T14:47:22

## 检索指标

| 指标 | P3-off | P3-multi-query | P3b-off | P3b-multi-query | P3b-multi-query-fuse |
|---|---|---|---|---|---|
| 题目数 | 260 | 260 | 260 | 260 | 260 |
| 文档级 HitRate@K | 0.8115 | 0.8115 | 0.8115 | 0.8192 | 0.8115 |
| 片段级 HitRate@K | 0.7846 | 0.7808 | 0.7846 | 0.7808 | 0.7808 |
| 文档级 MRR | 0.5813 | 0.5744 | 0.5813 | 0.5817 | 0.5806 |
| 片段级 MRR | 0.5615 | 0.5527 | 0.5615 | 0.5595 | 0.5595 |
| 文档级 Precision@K | 0.3092 | 0.3046 | 0.3092 | 0.3115 | 0.3138 |
| 片段级 Precision@K | 0.1623 | 0.1623 | 0.1623 | 0.1615 | 0.1615 |
| 内容召回率（重叠率均值） | 0.7881 | 0.7850 | 0.7881 | 0.7865 | 0.7851 |

## 各版本评测条件

| 版本 | 评测时间 | 模式 | 题数 | K | 聊天模型 | 嵌入模型 | chunk | 评测集MD5 |
|---|---|---|---|---|---|---|---|---|
| P3-off | 2026-10-25T16:24:18 | retrieval | 260 | 5 | qwen-plus | text-embedding-v4 | 500/50 | 9b68db07 |
| P3-multi-query | 2026-10-25T17:00:01 | retrieval | 260 | 5 | qwen-plus | text-embedding-v4 | 500/50 | 9b68db07 |
| P3b-off | 2026-10-26T13:52:32 | retrieval | 260 | 5 | deepseek-flash | text-embedding-v4 | 500/50 | 9b68db07 |
| P3b-multi-query | 2026-10-26T14:21:47 | retrieval | 260 | 5 | deepseek-flash | text-embedding-v4 | 500/50 | 9b68db07 |
| P3b-multi-query-fuse | 2026-10-26T14:46:47 | retrieval | 260 | 5 | deepseek-flash | text-embedding-v4 | 500/50 | 9b68db07 |

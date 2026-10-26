# RAG 评测实验时间线

> PrivRAG「RAG 链路升级」过程全部评测实验按时间排列的清单与演进脉络（2026-10-19 → 2026-10-26）。
> 整理时间：2026-10-26。报告文件位于 `backend/eval_reports/`（同目录《RAG评测实验总结报告.md》含各实验动机、完整指标与结论）。
>
> 口径说明：v1 = 80 题 / 5 文档库（MD5 `ff39e805…`）；v2 = 260 题 / 65 文档库（MD5 `9b68db07…`）。两口径不可混比。

## 总览

| 日期 | 事件 | 报告数 |
|---|---|---|
| 2026-10-19 | 评测集 v1 构建；P0 基线（retrieval + full） | 2 + 1 份构建 |
| 2026-10-20 | P1 格式感知分块（full + compare） | 1 + 1 |
| 2026-10-23 | P2 混合检索/精排四组 A/B（full × 4 + compare） | 4 + 1 |
| 2026-10-24 | 评测集 v2 迭代（扩库 65 份 + 260 题）；EV2 四组基线（retrieval-only × 4 + compare） | 4 + 1 |
| 2026-10-25 | P3 查询优化三组 A/B（retrieval-only × 3 + compare） | 3 + 1 |
| 2026-10-26 | P3b fuse_then_rerank 变体补测三组（retrieval-only × 3 + compare） | 3 + 1 |

## 2026-10-19 · 评测集 v1 构建 + P0 基线

| 时间 | 报告 | 模式 | 题数/口径 | 关键结果 |
|---|---|---|---|---|
| — | 评测集 v1 构建（`dataset build`） | — | 80 题 / v1（fact 31 / term 24 / longtail 25） | MD5 `ff39e805…`，人工抽查通过 |
| 01:00 | `20261019_010016_P0-baseline` | retrieval | 80 / v1 | 与 full 版数值一致（互相验证） |
| 01:51 | `20261019_015104_P0-baseline` | full | 80 / v1 | **基线口径**：doc HitRate/MRR 0.2000，Faithfulness 1.0000，AR 0.2925；格式缺口天花板 0.20（仅 txt 入库） |

## 2026-10-20 · P1 格式感知分块

| 时间 | 报告 | 模式 | 题数/口径 | 关键结果 |
|---|---|---|---|---|
| 23:48 | `20261020_234801_P1` | full | 80 / v1 | 5 格式全入库（chunk 500/50）：doc HitRate 0.2000→**0.9250**，MRR 0.8958，AR 0.9338，Faithfulness 保持 1.0 |
| 23:48 | `20261020_234830_compare__P0-baseline__P1` | compare | — | P0 vs P1 横向对比 |

## 2026-10-23 · P2 混合检索 + 精排（四组 A/B）

| 时间 | 报告 | 模式 | 题数/口径 | 关键结果 |
|---|---|---|---|---|
| 18:38 | `20261023_183855_P2-dense-only` | full | 80 / v1 @5 | doc HitRate 0.9750（隔离"纯调大 k"效应） |
| 18:59 | `20261023_185935_P2-hybrid` | full | 80 / v1 @5 | +BM25/RRF：HitRate **1.0000** 双满分，doc MRR 0.9563 |
| 19:41 | `20261023_194144_P2-hybrid-rerank` | full | 80 / v1 @5 | +gte-rerank-v2：MRR **双满分 1.0000**，AR 0.9875（当期最优配置） |
| 20:06 | `20261023_200628_P2-legacy` | full | 80 / v1 @3 | 开关全关回退，与 P1 逐项一致（回退等价验证） |
| 20:06 | `20261023_200645_compare__P2-legacy__P2-dense-only__P2-hybrid__P2-hybrid-rerank` | compare | — | 四组横向对比 |

## 2026-10-24 · 评测集 v2 迭代 + EV2 基线

**当日非评测动作**：corpus_v2 生成 60 份语料入库（全库 68 份 / 499 chunks）→ `dataset build --v2` 生成 260 题新评测集（动机：P2 在 v1 双满分天花板）。附带修复 BM25 增量失效 bug（Document import 遮蔽）与 ingest 旧快照问题。

| 时间 | 报告 | 模式 | 题数/口径 | 关键结果 |
|---|---|---|---|---|
| 19:49 | `20261024_194959_EV2-legacy` | retrieval | 260 / v2 | doc HitRate 0.6000（旧链路 k=3 在难集上的真实水平） |
| 19:54 | `20261024_195437_EV2-dense-only` | retrieval | 260 / v2 @5 | 0.6923 |
| 19:59 | `20261024_195927_EV2-hybrid` | retrieval | 260 / v2 @5 | 0.7462 |
| 20:08 | `20261024_200850_EV2-hybrid-rerank` | retrieval | 260 / v2 @5 | **0.8115**（doc）/ 0.7846（passage），召回 0.7881——后续所有 v2 评测的对照基准 |
| 20:09 | `20261024_200919_compare__EV2-legacy__EV2-dense-only__EV2-hybrid__EV2-hybrid-rerank` | compare | — | 四组横向对比；四组单调递进，召回/排序增益可分离 |

## 2026-10-25 · P3 查询优化 A/B

| 时间 | 报告 | 模式 | 题数/口径 | 关键结果 |
|---|---|---|---|---|
| 16:24 | `20261025_162418_P3-off` | retrieval | 260 / v2 | 对照组：doc 0.8115 / passage 0.7846 / doc MRR 0.5813（约 9 分钟） |
| 17:00 | `20261025_170001_P3-multi-query` | retrieval | 260 / v2 | 4 路改写 + 每路精排 + RRF：doc 持平，passage/MRR 微降（约 35 分钟；改写模型 qwen-plus） |
| 17:32 | `20261025_173253_P3-hyde` | retrieval | 260 / v2 | 假设文档双路：全面下降（passage -7.69pp，longtail 重灾区） |
| 17:33 | `20261025_173326_compare__P3-off__P3-multi-query__P3-hyde` | compare | — | 三组对比；**决策 mode=off** |

## 2026-10-26 · P3b fuse_then_rerank 变体补测

**当日非评测动作**：实现 `fuse_then_rerank` 变体（`RerankRetriever(QueryEnhancer(HybridRetriever))` 融合后统一精排）+ `multi-query-fuse` preset + 配置项（默认 false）+ 单测 2 例，全量回归 417 passed。动机：验证 P3 multi_query 下降是否因「每路精排→末端 RRF」的链路顺序。

| 时间 | 报告 | 模式 | 题数/口径 | 关键结果 |
|---|---|---|---|---|
| 13:52 | `20261026_135232_P3b-off` | retrieval | 260 / v2 | 对照组：与 P3-off 逐项一致（跨日口径稳定验证） |
| 14:21 | `20261026_142147_P3b-multi-query` | retrieval | 260 / v2 | 每路精排+末端 RRF：doc 0.8192（+2 题）/ passage 0.7808（改写模型 deepseek-flash） |
| 14:46 | `20261026_144647_P3b-multi-query-fuse` | retrieval | 260 / v2 | 融合后统一精排：doc 0.8115 / passage 0.7808 / doc MRR 0.5806——无净收益 |
| 14:47 | `20261026_144722_compare__P3-off__P3-multi-query__P3b-off__P3b-multi-query__P3b-multi-query-fuse` | compare | — | 五组对比；**决策 fuse_then_rerank=false，链路顺序非 P3 下降主因** |

## 演进脉络

```
v1 口径（80 题，doc 级 HitRate 主线）
P0 基线 0.2000（格式缺口天花板）
  └─ P1 格式感知分块 0.9250（chunk 500/50 + [section_path] 前缀）
       └─ P2 hybrid 1.0000（BM25 补召回）
            └─ P2 hybrid+rerank 1.0000 + MRR 双满分 ──→ 天花板效应
                                                      │
v2 口径（260 题难集，doc 级 HitRate / passage 级 HitRate 主线）│
EV2-legacy 0.6000/0.4615 ←────────────────────────────┘
  └─ dense-only 0.6923/0.5115
       └─ hybrid 0.7462/0.6231
            └─ hybrid+rerank 0.8115/0.7846（v2 最优检索配置 = 生产默认）
                 ├─ P3 multi_query 0.8115/0.7808（持平/微降，弃用）
                 ├─ P3 hyde 0.7769/0.7077（明显下降，弃用）
                 └─ P3b multi-query 0.8192/0.7808、multi-query-fuse 0.8115/0.7808
                    （改写模型 deepseek-flash 复测：差异 ≤2 题属噪声，fuse 无净收益，均不启用）

生产链路定格：dense(20)+bm25(20) → RRF(20) → gte-rerank-v2 top5，query_optimize.mode=off，fuse_then_rerank=false
全程 Faithfulness 1.0000（零幻觉）
```

## 待办（后续评测）

- P4（多轮对话/引用溯源等，视项目推进）完成后的 v2 口径评测与对比，回填执行文档附录 A 并更新本目录两份报告。

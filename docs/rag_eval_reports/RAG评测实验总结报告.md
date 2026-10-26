# RAG 评测实验总结报告

> 本报告汇总 PrivRAG 项目「RAG 链路升级」（P0→P4）过程中已执行的全部评测实验：各阶段实验的动机、配置、指标与结论。
> 整理时间：2026-10-26。
>
> - 评测框架说明（模块组成、运行命令、指标口径）：见 `backend/app/service/eval/README.md`
> - 原始单次/对比报告（json + md，含每题明细）：`backend/eval_reports/`
> - 按时间排列的全部报告清单与演进脉络：见同目录《RAG评测实验时间线.md》
> - 升级方案与阶段验收：见项目根目录《RAG链路升级执行文档.md》

## 1. 评测体系与口径速览

| 口径 | 定义 |
|---|---|
| 文档级命中 | 检索结果 `metadata.document_id` == ground truth |
| 片段级命中 | chunk 与溯源段落字符 2-gram 重叠率（包含式 \|A∩B\|/min(\|A\|,\|B\|)）≥ 0.6 |
| 内容召回率 | 正确文档结果中最大重叠率的均值 |
| Faithfulness | 答案论断被检索上下文支持的程度（LLM 裁判 0~1） |
| AnswerRelevancy | 答案与问题的相关性（LLM 裁判 0~1）。⚠ 度量主题相关而非事实正确 |

- ground truth 采用「document_id + 溯源原文段落」而非 vector_id（向量 ID 为随机 UUID，且重建后 chunk 边界与 ID 均会变化），保证同一份评测集全程复用。
- **两套评测口径**：v1（80 题 / 5 文档库，MD5 `ff39e805…`）用于 P0/P1/P2；v2（260 题 / 65 文档库，MD5 `9b68db07…`，fact 118 / paraphrase 60 / term 54 / longtail 28）用于 EV2/P3/P3b/P4 起的所有评测。两口径不可直接混比。

## 2. 实验总览

### 2.1 v1 口径主线（80 题，P0→P1→P2）

| 指标 | P0 基线(@3) | P1(@3) | P2-hybrid-rerank(@5) |
|---|---|---|---|
| HitRate（文档级/片段级） | 0.2000 / 0.2000 | 0.9250 / 0.9125 | **1.0000 / 1.0000** |
| MRR（文档级/片段级） | 0.2000 / 0.1812 | 0.8958 / 0.8396 | **1.0000 / 1.0000** |
| Precision（文档级/片段级） | 0.2000 / 0.0667 | 0.7792 / 0.3042 | 0.6050 / 0.2000 |
| 内容召回率 | 0.2000 | 0.9114 | **0.9975** |
| Faithfulness | 1.0000 | 1.0000 | 1.0000 |
| AnswerRelevancy | 0.2925 | 0.9338 | **0.9875** |

> P2 在 v1 口径双满分出现天花板效应 → 触发评测集 v2 迭代（见 3.5）。

### 2.2 v2 口径主线（260 题，EV2→P3→P3b→P4）

| 指标 | EV2-legacy(k=3) | EV2-dense-only(k=5) | EV2-hybrid | EV2-hybrid-rerank | P3-off（=生产默认） | P3b 补测组 | P4 收尾验证 |
|---|---|---|---|---|---|---|---|
| HitRate（文档级/片段级） | 0.6000 / 0.4615 | 0.6923 / 0.5115 | 0.7462 / 0.6231 | **0.8115 / 0.7846** | **0.8115 / 0.7846** | 见 3.7（无净收益，不入主线） | **0.8115 / 0.7846**（≡P3-off） |
| MRR（文档级/片段级） | 0.4949 / 0.3551 | 0.5152 / 0.3662 | 0.5389 / 0.4512 | **0.5873 / 0.5675** | 0.5813 / 0.5615 | 同上 | 0.5813 / 0.5615（≡P3-off） |
| 内容召回率 | 0.4847 | 0.5441 | 0.6441 | **0.7881** | **0.7881** | 同上 | **0.7881**（≡P3-off） |

> 生产链路最终形态（P2 起）：`dense(20) + bm25(20) → RRF(topn=20) → gte-rerank-v2 精排 top 5`，`query_optimize.mode=off`、`fuse_then_rerank=false`。

## 3. 各阶段实验详情

### 3.1 评测集构建 v1（2026-10-19）

- 80 题 = 5 文件 × 16；类型分布 fact 31 / term 24 / longtail 25；人工抽查通过
- 数据集 MD5：`ff39e8051a07422862206a02d07e0de9`（写入每份报告头，改评测集即失配，便于发现口径漂移）

### 3.2 P0 基线（tag：`P0-baseline`，2026-10-19）

| 报告 | 时间 | 模式 | 说明 |
|---|---|---|---|
| `20261019_010016_P0-baseline` | 01:00 | retrieval | 仅检索，先行完成 |
| `20261019_015104_P0-baseline` | 01:51 | full | 最终基线口径；首次运行 q035 因 DashScope 欠费中断，充值后重跑成功 |

**检索指标（总体，Top-K=3）**：文档级/片段级 HitRate 0.2000/0.2000、MRR 0.2000/0.1812、Precision@3 0.2000/0.0667、内容召回率 0.2000。
**生成指标（80/80）**：Faithfulness 1.0000、AnswerRelevancy 0.2925。

**解读要点**：

1. 总体 0.20 = 格式缺口天花板：仅 txt 入库（16 分块），16/80 题有命中机会且全部命中；xlsx/md/docx/pdf 未入库的 64 题记 0。
2. txt 内部链路质量健康（文档级 HitRate/MRR 1.0）；短板是片段级 Precision@3 仅 0.3333（chunk_size=150 粒度粗）。
3. Faithfulness 1.0：64 题未命中时模型全部如实拒答，零幻觉；后续任何阶段若该指标下滑即引入幻觉。
4. AnswerRelevancy 0.2925 的构成：16 命中题全部 1.0、7 题未命中但拒答话题相关得 1.0、56 题 0 分。

### 3.3 P1：格式感知分块 + 结构化元数据（tag：`P1`，2026-10-20）

| 报告 | 时间 | 模式 | 说明 |
|---|---|---|---|
| `20261020_234801_P1` | 23:48 | full | 80/80；存量 5 文档先 `rebuild --all` 重建（chunk 500/50，共 32 块）；MD5 与 P0 一致 |
| `20261020_234830_compare__P0-baseline__P1` | 23:48 | compare | P0 vs P1 横向对比 |

**检索指标（Top-K=3，P1 / P0 / Δ）**：

| 指标 | P1 | P0 | Δ |
|---|---|---|---|
| 文档级 HitRate@3 | 0.9250 | 0.2000 | +0.7250 |
| 片段级 HitRate@3 | 0.9125 | 0.2000 | +0.7125 |
| 文档级 MRR | 0.8958 | 0.2000 | +0.6958 |
| 片段级 MRR | 0.8396 | 0.1812 | +0.6584 |
| 内容召回率 | 0.9114 | 0.2000 | +0.7114 |

**生成指标**：Faithfulness 1.0000（保持零幻觉）、AnswerRelevancy 0.9338。

**解读要点**：

1. 格式缺口修复兑现：5 文档全部入库（32 块），74/80 题文档级命中。
2. term 类 0.1667→0.9167：嵌入增强（`[section_path]` 前缀随正文一起嵌入）对专有名词/缩写类问题提升显著。
3. 按文件：pdf/xlsx 1.0000、docx 0.9375、txt 0.8750、md 0.8125。
4. 遗留：片段级 Precision@3 仅 0.3042——top-3 中混入其他文档 chunk，为 P2 精排的量化目标。

### 3.4 P2：混合检索 + 精排重排（tag：`P2-*` 四组，2026-10-23）

| 报告 | 时间 | 模式 | 说明 |
|---|---|---|---|
| `20261023_183855_P2-dense-only` | 18:38 | full | dense-only k=5（隔离"纯调大 k"效应的对照组） |
| `20261023_185935_P2-hybrid` | 18:59 | full | RRF 融合：dense(20) + bm25(20) → top 5 |
| `20261023_194144_P2-hybrid-rerank` | 19:41 | full | RRF(topn=20) → gte-rerank-v2 精排 → top 5（修复 langchain model 覆盖 bug 后重跑） |
| `20261023_200628_P2-legacy` | 20:06 | full | 开关全关回退旧链路（K=3），与 P1 逐项一致（回退等价验证） |
| `20261023_200645_compare__P2-legacy__P2-dense-only__P2-hybrid__P2-hybrid-rerank` | 20:06 | compare | 四组横向对比 |

**检索指标（总体；legacy 组 K=3，其余 K=5）**：

| 指标 | P2-legacy(=P1) | P2-dense-only | P2-hybrid | P2-hybrid-rerank |
|---|---|---|---|---|
| 文档级 HitRate@K | 0.9250 | 0.9750 | 1.0000 | 1.0000 |
| 片段级 HitRate@K | 0.9125 | 0.9375 | 1.0000 | 1.0000 |
| 文档级 MRR | 0.8958 | 0.9071 | 0.9563 | 1.0000 |
| 片段级 MRR | 0.8396 | 0.8458 | 0.9067 | 1.0000 |
| 文档级 Precision@K | 0.7792 | 0.6525 | 0.6300 | 0.6050 |
| 片段级 Precision@K | 0.3042 | 0.1875 | 0.2000 | 0.2000 |
| 内容召回率 | 0.9114 | 0.9390 | 0.9975 | 0.9975 |

**生成指标**：Faithfulness 四组均 1.0000；AnswerRelevancy legacy 0.9500 → hybrid / hybrid-rerank 0.9875。

**解读要点**：

1. BM25 补召回兑现：dense-only 遗留 miss 在 hybrid 组全部补齐，HitRate 双满分；内容召回 0.9390→0.9975。
2. 精排价值量化：hybrid-rerank 文档/片段 MRR 双满分（正确片段全部置顶）。
3. Precision@K 下滑属口径效应：K=5 分母变大叠加精排聚焦 top1，P2 以 HitRate/MRR 为主指标。
4. term 类 0.9167→1.0000：BM25 字面精确匹配 + 精排组合生效。

### 3.5 评测集迭代 v2 + EV2 基线（tag：`EV2-*` 四组，2026-10-24）

**动机**：P2 在 v1 口径双满分，天花板效应，无法度量后续增量。

**迭代动作**：

1. `corpus_v2.py` 生成 60 份语料（10 主题 × 6 实体，固定种子；同主题跨实体近似参数制造干扰项），与 v1 样例合计 65 份
2. `ingest.py` 批量入库（复用上传链路，md5 幂等）；全库 68 份 / 499 chunks
3. `dataset build --v2`：806 段落 → LLM 每段 3~4 题 → 采样 260 题；新增 paraphrase 口语改写题型；MD5 `9b68db07…`
4. `runner --dataset app/service/eval/datasets/eval_dataset_v2.json --retrieval-only` 重跑四组基线

**EV2 四组基线（260 题，retrieval-only）**：

| 指标 | EV2-legacy(k=3) | EV2-dense-only(k=5) | EV2-hybrid | EV2-hybrid-rerank |
|---|---|---|---|---|
| 文档级 HitRate | 0.6000 | 0.6923 | 0.7462 | **0.8115** |
| 片段级 HitRate | 0.4615 | 0.5115 | 0.6231 | **0.7846** |
| 文档级 MRR | 0.4949 | 0.5152 | 0.5389 | **0.5873** |
| 片段级 MRR | 0.3551 | 0.3662 | 0.4512 | **0.5675** |
| 内容召回率 | 0.4847 | 0.5441 | 0.6441 | **0.7881** |

| 报告 | 时间 | 说明 |
|---|---|---|
| `20261024_194959_EV2-legacy` | 19:49 | 旧链路回退（k=3） |
| `20261024_195437_EV2-dense-only` | 19:54 | dense k=5 |
| `20261024_195927_EV2-hybrid` | 19:59 | RRF 融合 top5 |
| `20261024_200850_EV2-hybrid-rerank` | 20:08 | RRF + 精排 top5 |
| `20261024_200919_compare__EV2-legacy__EV2-dense-only__EV2-hybrid__EV2-hybrid-rerank` | 20:09 | 四组横向对比 |

**结论**：天花板效应消除（双满分 → 最高 0.8115），四组单调递进；hybrid 召回增益与精排排序增益在难集上首次可分离。后续评测以 v2 口径为准。

**迭代期间 bug 修复**：`documents.py` langchain/SQLModel `Document` import 遮蔽（P2 起新上传文档 BM25 增量实际失效，改别名 `LCDocument`）；`ingest.py` REPEATABLE READ 旧快照与 md5 幂等缺口。

### 3.6 P3：查询优化 A/B（tag：`P3-off` / `P3-multi-query` / `P3-hyde`，2026-10-25）

**动机**：multi_query（LLM 改写 N 路 + RRF 融合）与 hyde（假设文档 embedding 双路融合）对 v2 难集是否有增量，用数据定默认 mode。原计划 `P3-final`（最优配置）即结论本身——最优 = mode=off，无需单跑。

**评测方式**：v2 口径 260 题 retrieval-only，三组同底座（hybrid + rerank，等价 EV2-hybrid-rerank），仅 `query_optimize.mode` 不同（`--preset off/multi-query/hyde`）；multi_query_count=3（原查询 + 3 改写共 4 路并行检索）；改写模型 qwen-plus。

| 报告 | 时间 | 说明 |
|---|---|---|
| `20261025_162418_P3-off` | 16:24 | 对照组（mode=off 透传，约 9 分钟） |
| `20261025_170001_P3-multi-query` | 17:00 | 4 路并行检索 + RRF 融合（约 35 分钟） |
| `20261025_173253_P3-hyde` | 17:32 | 原查询 + 假设文档双路融合（约 32 分钟） |
| `20261025_173326_compare__P3-off__P3-multi-query__P3-hyde` | 17:33 | 三组横向对比 |

**检索指标（总体）**：

| 指标 | P3-off | P3-multi-query | P3-hyde |
|---|---|---|---|
| 文档级 HitRate@K | **0.8115** | 0.8115（持平） | 0.7769（-3.46pp） |
| 片段级 HitRate@K | **0.7846** | 0.7808（-0.38pp） | 0.7077（-7.69pp） |
| 文档级 MRR | **0.5813** | 0.5744 | 0.5683 |
| 片段级 MRR | **0.5615** | 0.5527 | 0.5220 |
| 文档级 Precision@K | 0.3092 | 0.3046 | 0.3254 |
| 内容召回率 | **0.7881** | 0.7850 | 0.7193 |

**按问题类型（文档级 HitRate，off → multi-query → hyde）**：fact 0.8220→0.8220→0.8051；longtail 0.8214→0.8214→0.7143；paraphrase 0.7667→0.7500→0.7167；term 0.8333→0.8519→0.8148。

**结论与决策**：**默认 mode 维持 `off`**（已回写 retrieval_config.yml 注释）：

1. **multi_query 无净收益**：文档级持平，片段级/MRR 微降（4 路结果 RRF 融合稀释精排排序）；term +1.9pp 与 paraphrase -1.7pp 相抵；每题多 1 次 LLM + 3 次 rerank 调用，性价比为负。
2. **hyde 明显负收益**：假设文档 embedding 把召回拉向 LLM 想象内容，longtail（细节参数题）最差；全题型无一获益。

### 3.7 P3b：fuse_then_rerank 变体补测（tag：`P3b-*` 三组，2026-10-26）

**动机**：P3 中 multi_query 相对 off 的片段级/MRR 下降，是否因链路顺序不当——即「每路各自精排 → 末端 RRF 融合」会稀释精排排序。假设改为「每路仅混合检索 → 全路 RRF 融合 → 最后统一精排」可恢复排序质量。

**实现**（不改生产默认，作为可选变体）：

- `build_retriever` 新增 `fuse_then_rerank` 开关（`retrieval_config.yml` 默认 `false`），开启时包装序反转：`RerankRetriever(QueryEnhancer(HybridRetriever))`
- 每路（原查询 + 3 改写）仅做混合检索 dense(20)+bm25(20)；全路 RRF 融合 topn=20（=hybrid.topn，作为精排候选数）；最后**用原查询**统一精排取 top 5，最终序 = 精排序
- runner 新增 `multi-query-fuse` preset；补 2 个单测（包装顺序断言 + mode=off 时开关无效），全量回归 417 passed

**评测方式**：v2 口径 260 题 retrieval-only，三组同日同环境对照（改写模型 deepseek-flash，注：与 P3 组的 qwen-plus 不同，故以 P3b 三组内部对比为主、P3 两组作跨日参照）。

| 报告 | 时间 | 说明 |
|---|---|---|
| `20261026_135232_P3b-off` | 13:52 | 对照组（与 P3-off 逐项一致，验证跨日口径稳定） |
| `20261026_142147_P3b-multi-query` | 14:21 | 每路精排 + 末端 RRF（原链路） |
| `20261026_144647_P3b-multi-query-fuse` | 14:46 | 融合后统一精排（新变体） |
| `20261026_144722_compare__P3-off__P3-multi-query__P3b-off__P3b-multi-query__P3b-multi-query-fuse` | 14:47 | 五组横向对比 |

**检索指标（总体）**：

| 指标 | P3b-off | P3b-multi-query（每路精排） | P3b-multi-query-fuse（融合后精排） |
|---|---|---|---|
| 文档级 HitRate@K | 0.8115 | **0.8192** | 0.8115 |
| 片段级 HitRate@K | **0.7846** | 0.7808 | 0.7808 |
| 文档级 MRR | 0.5813 | **0.5817** | 0.5806 |
| 片段级 MRR | **0.5615** | 0.5595 | 0.5595 |
| 文档级 Precision@K | 0.3092 | 0.3115 | **0.3138** |
| 片段级 Precision@K | **0.1623** | 0.1615 | 0.1615 |
| 内容召回率 | **0.7881** | 0.7865 | 0.7851 |

**按问题类型（文档级 HitRate，off → multi-query → fuse）**：fact 0.8220→0.8390→0.8220；longtail 0.8214→0.8214→0.8214；paraphrase 0.7667→0.7667→0.7667；term 0.8333→0.8333→0.8333。

**结论与决策**：**链路顺序非 P3 下降主因，`fuse_then_rerank` 无净收益，维持 `false`**：

1. 融合后统一精排未恢复也未提升指标：doc HitRate 回落至与 off 持平（比每路精排少 2 题）、MRR 微降，唯一微升项 doc Precision@5 0.3138（+0.46pp）幅度极小。
2. 全部组间差异折合 1~2 题（260 题中 1 题 ≈ 0.38pp），属噪声区间，无统计显著性。
3. 改写模型影响大于链路顺序：P3（qwen-plus 改写）multi_query 全面微降，P3b（deepseek-flash 改写）multi_query doc 级微升/片段级微降——未来若优化多路改写，优先方向是改写质量（提示词/模型），而非链路顺序。
4. P3b-off 与 P3-off 指标逐项一致（0.8115/0.7846/0.5813/0.5615/0.7881），验证 v2 口径跨日复跑稳定。

### 3.8 P4：热更新收尾验证（tag：`P4`，2026-10-26）

**动机**：P4 为工程收尾阶段（参数热更新 + 引用合并 + 注册表单例 + 前端设置区块），未改动检索/分块链路。评测目的：① 工程改造**零回归**；② **热更新前后同口径等价**——热更新重建所用的配置源正是 `retrieval_config.yml`，需验证「文件配置直组链路 ≡ preset 口径链路」。

**评测方式**：

1. **不使用 `--preset`**，直接以 `retrieval_config.yml` 当前内容（hybrid + rerank + mode=off，即生产定格配置）组链，260 题 retrieval-only，v2 口径——与 P3-off（preset 口径）对比，等价即同时证明上述两点。
2. **接口级热更新验证**：起服务后 PUT `hybrid.bm25Topn` 20→15→20 全程不重启，GET 即时反映新值，响应「保存成功，检索链路已重建即时生效」，审计日志记录 `[热更新]用户更新 RAG 参数` + `[热更新]RAG 链路已按新配置重建生效`。

| 报告 | 时间 | 说明 |
|---|---|---|
| `20261026_183124_P4` | 18:31 | P4 主评测（文件配置直组，无 preset） |
| `20261026_183233_compare__P0-baseline__P1__P2-legacy__P2-dense-only__P2-hybrid__P2-hybrid-rerank` | 18:32 | v1 口径终局总对比（P0→P2） |
| `20261026_183236_compare__EV2-legacy__EV2-dense-only__EV2-hybrid__EV2-hybrid-rerank__P3-off__P4` | 18:32 | v2 口径终局总对比（EV2→P4） |

**P3-off vs P4 七项检索指标对照**（逐项一致）：

| 指标 | P3-off | P4 |
|---|---|---|
| 文档级 HitRate@K | 0.8115 | 0.8115 |
| 片段级 HitRate@K | 0.7846 | 0.7846 |
| 文档级 MRR | 0.5813 | 0.5813 |
| 片段级 MRR | 0.5615 | 0.5615 |
| 文档级 Precision@K | 0.3092 | 0.3092 |
| 片段级 Precision@K | 0.1623 | 0.1623 |
| 内容召回率 | 0.7881 | 0.7881 |

**结论**：文件配置直组链路 ≡ preset 口径链路，热更新重建路径行为等价，P4 工程改造（注册表单例 / tuple 返回 / 引用合并 / settings API）**零回归**。至此 **P0→P4 全阶段收官**：v1 口径文档级 HitRate 0.2000→**1.0000**、AnswerRelevancy 0.2925→**0.9875**；v2 口径（65 份近似语料难集）文档级/片段级 HitRate 0.6000/0.4615→**0.8115/0.7846**、内容召回率 0.4847→**0.7881**；且检索参数全量可热更新（settings API + 设置页，不重启即时生效）。报告头聊天模型字段为 deepseek-flash（retrieval-only 不调用，仅元数据差异）。

## 4. 阶段决策汇总

| 阶段 | 实验问题 | 决策 | 生产配置落点 |
|---|---|---|---|
| P0 | 基线现状 | 格式缺口是首要瓶颈（仅 txt 入库，天花板 0.20） | — |
| P1 | 格式感知分块 + 元数据增强 | **启用**：HitRate 0.20→0.925，term 类大幅提升 | chunk 500/50、`[section_path]` 嵌入前缀 |
| P2 | 混合检索 + 精排 | **启用**：v1 双满分；BM25 补召回 + 精排置顶 | `hybrid.enabled=true`、`rerank.enabled=true`（top_k=5） |
| EV2 | 评测集天花板 | v1 双满分 → 扩库 65 份 + 260 题 v2 口径 | 后续评测统一 `--dataset eval_dataset_v2.json` |
| P3 | 查询优化模式选择 | **mode=off**：multi_query 无净收益、hyde 负收益 | `query_optimize.mode: off` |
| P3b | 融合后统一精排变体 | **fuse_then_rerank=false**：无净收益，作为可选变体保留 | `query_optimize.fuse_then_rerank: false` |
| P4 | 热更新收尾（工程改造）是否影响链路 | **零回归**：七项指标与 P3-off 逐项一致；热更新重建行为等价 | 检索参数全量可热更新（settings API + 设置页） |

**Faithfulness 全程 1.0000**（P0/P1/P2 全量口径）：各阶段升级均未引入幻觉，未命中时模型保持如实拒答。

## 5. 环境与排障备忘（评测相关）

| 现象 | 原因 | 处置 |
|---|---|---|
| 评测中途 `Arrearage` 中断 | DashScope 欠费（`--full` 约 320+ 次调用） | 充值后重跑（幂等） |
| 精排全量降级 `'NoneType' object has no attribute 'results'` | langchain_community DashScopeRerank 无条件覆盖 model 为已下线的 gte-rerank(v1) | `rerank_factory.py` 构造后回写 `compressor.model`（2026-10-23） |
| 改写/嵌入调用 401（key ****a392 invalid） | User 作用域/进程残留失效 API key，env_loader 仅注入缺失键导致失效 key 优先 | 从 `docker/env/.env.dev` 显式注入有效值；根因清理：`[Environment]::SetEnvironmentVariable('DASHSCOPE_API_KEY', $null, 'User')`（2026-10-26） |
| 嵌入偶发 403（空 message） | DashScope 偶发限流 | 冒烟验证后重跑即过；单次失败会中断评测进程，建议失败后整组重跑 |
| ingest 汇总误报「向量化失败：None」 | MySQL REPEATABLE READ 旧快照 | 状态核对改用新 session（2026-10-24） |

> 完整排障记录（含基础设施类）见 `backend/app/service/eval/README.md` 第 7 章。

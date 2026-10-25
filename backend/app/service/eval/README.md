# RAG 链路评测框架（P0 评测体系）

> 定位：在**不改动现有 RAG 链路代码**的前提下，对「上传 → 向量化 → 检索 → 生成」全链路做可重复的量化评测，为 P1~P4 各阶段升级提供前后对比数据。设计依据见根目录《RAG链路升级执行文档.md》第 4 章。

## 1. 模块组成

| 模块 | 职责 |
|---|---|
| `metrics.py` | 确定性检索指标（HitRate@K / MRR / Precision@K / 内容召回率，文档级与片段级双口径），纯函数、无外部依赖 |
| `llm_judge.py` | 生成指标 LLM 裁判（Faithfulness / AnswerRelevancy），中文 Prompt 固定、temperature=0 |
| `make_samples.py` | 自造 5 格式样例文档（txt/pdf/docx/xlsx/md，"宸甄科技"企业制度语料） |
| `corpus_v2.py` | 评测集 v2 语料生成器（10 主题 × 6 实体 = 60 份，固定种子，跨实体近似干扰项） |
| `dataset.py` | 评测集构建与加载校验（v1 `datasets/eval_dataset.json`；v2 `datasets/eval_dataset_v2.json`，`build --v2`） |
| `ingest.py` | 评测语料批量入库 CLI（复用上传链路；md5 幂等：success 跳过 / failed 复用原 id 重试） |
| `runner.py` | 评测主入口：反查 document_id → 预检 → 逐题检索/生成 → 汇总 → 报告落盘 |
| `report.py` | 单次报告读写 + 多版本横向对比（`compare` 子命令） |

数据流（一次性步骤 vs 每阶段重跑）：

```
make_samples（一次性）→ 样例经前端/API 上传入库 → dataset build（一次性，耗 LLM tokens）
    → runner（P0/P1/P2/P3 每阶段完成后重跑）→ report compare（阶段间横向对比）

评测集迭代 v2（2026-10-24，消除 P2 双满分天花板，详见 6.5）：
corpus_v2（60 份）→ ingest 批量入库 → dataset build --v2（260 题）
    → runner --dataset eval_dataset_v2.json（EV2-* 系列基线）
```

## 2. 目录与产物

```
backend/app/service/eval/          # 本包
├── datasets/
│   ├── eval_dataset.json          # 评测集 v1（80 题，MD5 写入报告头保证口径可追溯）
│   ├── eval_dataset_v2.json       # 评测集 v2（260 题，2026-10-24 迭代，详见 6.5）
│   ├── samples/                   # 5 格式自造样例（上传入库用）
│   └── corpus_v2/                 # v2 扩容语料 60 份（10 主题 × 6 实体，ingest 批量入库用）

backend/eval_reports/              # 报告输出（不在本包内）
├── {时间戳}_{tag}.json            # 含每题明细（检索结果、答案、裁判分）
├── {时间戳}_{tag}.md              # 人读版汇总报告
└── {时间戳}_compare__{tags}.md    # report compare 生成的横向对比表
```

## 3. 运行前置条件

1. **基础设施在跑**：MySQL + Qdrant 容器已启动（`docker compose up -d`）。全新空库需先 `uv run uvicorn app.main:app` 启动一次触发建表（lifespan → `init_db()`），再 Ctrl+C 退出。
2. **宿主机 CLI 环境变量**（⚠ `MYSQL_PORT` 每次新开终端都要重设，`$env:` 仅当前会话有效）：

   ```powershell
   cd backend
   $env:MYSQL_PORT='6666'      # docker 映射端口；不设则默认 3306 拒连
   ```

   模型环境变量无需手工设置：后端启动时自动按白名单从 `docker/env/.env.dev` 加载
   （`DASHSCOPE_API_KEY` / `OPENAI_*` 等，仅注入缺失键）。评测裁判/评测集生成固定走
   DashScope（默认 `qwen-plus`，可用 `EVAL_CHAT_MODEL` 覆盖），与业务聊天模型
   （如 DeepSeek）解耦，保证与历史报告口径可比。

3. **样例文档已入库**：5 个样例已通过上传接口完成向量化。未入库文件的题目记 0（报告头会有 missing 警告）——P0 基线期即此状态，属预期格式缺口。
4. **评测集已构建**：`datasets/eval_dataset.json` 存在且通过加载校验。
5. **DashScope 余额充足**：`--full` 全量约 320+ 次调用（每题 1 嵌入 + 1 生成 + 2 裁判）；余额不足会中途报 `Arrearage`（欠费）。`--retrieval-only` 仅约 80 次嵌入。

## 4. 常用命令

（全部在 `backend/` 目录执行；tag 规范：`P0-baseline` / `P1` / `P2-<配置名>` / `P3-<配置名>` / `EV2-<配置名>`（v2 口径 260 题））

```powershell
# 0)（一次性）生成 5 格式样例文件
uv run python -m app.service.eval.make_samples

# 1)（一次性）构建评测集（消耗 LLM tokens）
uv run python -m app.service.eval.dataset build --num 80

# 2) 仅检索评测（快，检索类升级对比用）
uv run python -m app.service.eval.runner --tag P0-baseline --retrieval-only

# 3) 全量评测（检索+生成）
uv run python -m app.service.eval.runner --tag P0-baseline --full
#    可选参数：--k 5 覆盖 top-k（默认取 qdrant_config.yml 的 k=3）
#             --limit 10 只跑前 10 题调试

# 4) 多版本横向对比（按 tag 自动取各自最新报告）
uv run python -m app.service.eval.report compare P0-baseline P1 P2 P3
```

说明：

- **重跑幂等**：每题独立、先清理旧记录；报告按时间戳生成新文件，`compare` 自动取各 tag 最新一份。
- **单元测试**（全 mock、离线可跑）：`uv run pytest tests/test_eval_metrics.py tests/test_eval_llm_judge.py tests/test_eval_dataset.py tests/test_eval_runner.py`

### 4.1 每阶段标准评测流程（SOP，P2/P3/P4 直接照此执行）

> **统一评测命令就是 `runner` 这一条**：`uv run python -m app.service.eval.runner --tag <tag> --full`（或 `--retrieval-only`）。入口固定为 `app.service.eval.runner`，**不存在** `scripts.evaluate` 之类的其他入口（`python -m scripts.evaluate` 会报 No module named）。

```powershell
# ── 第 0 步：环境准备（MYSQL_PORT 每次新开终端都要重设，$env: 仅当前会话有效）──
cd backend
$env:MYSQL_PORT='6666'
# 模型变量（DASHSCOPE_API_KEY 等）启动时自动从 docker/env/.env.dev 白名单加载，无需手工设置
# 前置：MySQL/Qdrant 容器已启动（docker compose --env-file docker/env/.env.dev up -d）
# 注意：中文控制台输出乱码时命令前加 -X utf8，如 uv run python -X utf8 -m ...

# ── 第 1 步：跑本阶段评测（--tag 按下表命名）──
uv run python -X utf8 -m app.service.eval.runner --tag P2-hybrid-rerank --full
#   检索类升级可先快跑 --retrieval-only（约 80 次嵌入，不耗生成/裁判 tokens）
#   调试可加 --limit 10 只跑前 10 题；--k 5 覆盖 top-k

# ── 第 2 步：与历史阶段横向对比（按需增删参与对比的 tag）──
uv run python -X utf8 -m app.service.eval.report compare P0-baseline P1 P2-hybrid-rerank
```

**tag 命名规范与归档进度**：

| 阶段 | tag 格式 | 已归档 |
|---|---|---|
| P0 基线 | `P0-baseline` | 2026-10-19（retrieval + full 两份） |
| P1 | `P1` | 2026-10-20（full） |
| P2 四组对比 | `P2-dense-only` / `P2-hybrid` / `P2-hybrid-rerank` / `P2-legacy`（旧链路回退） | 2026-10-23（四组 + compare，见 6.4） |
| P3 策略对比 | `P3-off` / `P3-multi-query` / `P3-hyde` | 2026-10-25（三组 + compare，v2 口径 260 题，结论 mode=off，见 6.6） |
| 评测集 v2 基线 | `EV2-legacy` / `EV2-dense-only` / `EV2-hybrid` / `EV2-hybrid-rerank` | 2026-10-24（四组 + compare，v2 口径 260 题，见 6.5） |

补充：

- 若本阶段**改动了分块/入库链路**（如 P1、P4），评测前先执行存量重建：`uv run python -X utf8 -m app.service.rag.rebuild --all`；纯检索/重排改动（P2/P3）无需重建。
- 评测完成后将关键指标回填根目录《RAG链路升级执行文档.md》附录 A 表格，并保留 eval_reports 目录下的 json/md 报告归档。

## 5. 指标口径速览

| 口径 | 定义 |
|---|---|
| 文档级命中 | 检索结果 `metadata.document_id` == ground truth |
| 片段级命中 | chunk 与溯源段落字符 2-gram 重叠率（包含式）≥ 0.6 |
| 内容召回率 | 正确文档结果中最大重叠率的均值 |
| Faithfulness | 答案论断被检索上下文支持的程度（LLM 裁判 0~1） |
| AnswerRelevancy | 答案与问题的相关性（LLM 裁判 0~1）。⚠ 度量主题相关而非事实正确：基线中 7 题检索未命中、模型如实拒答，仍因话题相关得 1.0 |

> ground truth 采用「document_id + 溯源原文段落」而非 vector_id：当前向量 ID 为随机 UUID，且 P1 重建后 chunk 边界与 ID 均会变化；此口径保证同一份评测集在 P0~P3 全程复用。

## 6. 已跑实验记录

### 6.1 评测集构建（2026-10-19）

- 80 题 = 5 文件 × 16；类型分布 fact 31 / term 24 / longtail 25；人工抽查通过
- 数据集 MD5：`ff39e8051a07422862206a02d07e0de9`（写入每份报告头，改评测集即失配，便于发现口径漂移）

### 6.2 P0 基线（tag：`P0-baseline`）

| 报告 | 时间 | 模式 | 说明 |
|---|---|---|---|
| `20261019_010016_P0-baseline` | 2026-10-19 01:00 | retrieval | 仅检索，先行完成 |
| `20261019_015104_P0-baseline` | 2026-10-19 01:51 | full | 最终基线口径；首次运行在 q035 因 DashScope 欠费中断，充值后重跑成功 |

**检索指标（总体，Top-K=3）**：

| 指标 | 总体 | 员工手册.txt（16 题） |
|---|---|---|
| 文档级 HitRate@3 | 0.2000 | 1.0000 |
| 片段级 HitRate@3 | 0.2000 | 1.0000 |
| 文档级 MRR | 0.2000 | 1.0000 |
| 片段级 MRR | 0.1812 | 0.9062 |
| 文档级 Precision@3 | 0.2000 | 1.0000 |
| 片段级 Precision@3 | 0.0667 | 0.3333 |
| 内容召回率 | 0.2000 | 1.0000 |

**生成指标（LLM 裁判，80/80 成功）**：Faithfulness **1.0000**、AnswerRelevancy **0.2925**

**按类型（文档级 HitRate）**：fact 0.2258 / longtail 0.2000 / term 0.1667

**解读要点**：

1. 总体 0.20 = 格式缺口天花板：仅 txt 入库（16 分块），16/80 题有命中机会且全部命中（16×1.0/80）；xlsx/md/docx/pdf 未入库的 64 题记 0。P1 补齐格式后预期文档级 HitRate 回到 0.9+。
2. txt 内部链路质量健康：文档级命中/MRR 1.0、内容召回 1.0、片段级 MRR 0.9062；短板是片段级 Precision@3 仅 0.3333（chunk_size=150 粒度粗，top-3 中平均仅 1 块命中目标片段）——P2/P3 重排与分块调优的量化空间。
3. Faithfulness 1.0：64 题未命中时模型全部如实拒答（"参考资料中未提及……"），零幻觉；后续任何阶段若该指标下滑即引入幻觉，需立即回查。
4. AnswerRelevancy 0.2925 构成：16 命中题全部 1.0（检索→回答全链路正确 16/16）；7 题未命中但拒答话题相关得 1.0；q014 得 0.4；56 题 0 分。真实答对率 ≈ 0.20，纵向对比口径一致即可。

### 6.3 P1：格式感知分块 + 结构化元数据（tag：`P1`）

| 报告 | 时间 | 模式 | 说明 |
|---|---|---|---|
| `20261020_234801_P1` | 2026-10-20 23:48 | full | 80/80；存量 5 文档先经 `rebuild --all` 按新链路重建（chunk 500/50，共 32 块）；评测集 MD5 与 P0 一致 |
| `20261020_234830_compare__P0-baseline__P1` | 2026-10-20 23:48 | compare | P0 vs P1 横向对比 |

**检索指标（总体，Top-K=3，P1 总体 / P0 基线 / Δ）**：

| 指标 | P1 | P0 | Δ |
|---|---|---|---|
| 文档级 HitRate@3 | 0.9250 | 0.2000 | +0.7250 |
| 片段级 HitRate@3 | 0.9125 | 0.2000 | +0.7125 |
| 文档级 MRR | 0.8958 | 0.2000 | +0.6958 |
| 片段级 MRR | 0.8396 | 0.1812 | +0.6584 |
| 文档级 Precision@3 | 0.7792 | 0.2000 | +0.5792 |
| 片段级 Precision@3 | 0.3042 | 0.0667 | +0.2375 |
| 内容召回率 | 0.9114 | 0.2000 | +0.7114 |

**生成指标（LLM 裁判，80/80 成功）**：Faithfulness **1.0000**（与 P0 持平，零幻觉）、AnswerRelevancy **0.9338**（P0 0.2925）

**按类型（文档级 HitRate，括号内为 P0）**：fact 0.9355（0.2258）/ longtail 0.9200（0.2000）/ term 0.9167（0.1667）

**按文件（文档级 HitRate）**：pdf 1.0000 / xlsx 1.0000 / docx 0.9375 / txt 0.8750 / md 0.8125

**解读要点**：

1. 格式缺口修复兑现：5 文档全部入库（32 块），74/80 题文档级命中，总体 HitRate 从基线天花板 0.20 回到 0.9+，与 P0 基线期预判一致。
2. term 类 0.1667→0.9167：嵌入增强（`[section_path]` 前缀随正文一起嵌入）对专有名词/缩写类问题提升显著。
3. Faithfulness 保持 1.0000：分块改造未引入幻觉，未命中的 6 题模型仍如实拒答。
4. 遗留优化空间：片段级 Precision@3 仅 0.3042——top-3 中平均混入其他文档的 chunk，精确片段排序是 P2 精排的直接量化目标；txt 0.8750 / md 0.8125 存在少量失配（chunk 边界与提问粒度不一致），留待 P2/P3 观察。

### 6.4 P2：混合检索 + 精排重排（tag：`P2-*` 四组）

| 报告 | 时间 | 模式 | 说明 |
|---|---|---|---|
| `20261023_183855_P2-dense-only` | 2026-10-23 18:38 | full | dense-only k=5（隔离"纯调大 k"效应的对照组） |
| `20261023_185935_P2-hybrid` | 2026-10-23 18:59 | full | RRF 融合：dense(20) + bm25(20) → top 5 |
| `20261023_194144_P2-hybrid-rerank` | 2026-10-23 19:41 | full | RRF(topn=20) → gte-rerank-v2 精排 → top 5（修复 langchain model 覆盖 bug 后重跑） |
| `20261023_200628_P2-legacy` | 2026-10-23 20:06 | full | 开关全关回退旧链路（K=3），总体指标与 P1 逐项一致（回退等价验证） |
| `20261023_200645_compare__P2-legacy__P2-dense-only__P2-hybrid__P2-hybrid-rerank` | 2026-10-23 20:06 | compare | 四组横向对比 |

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

**生成指标（LLM 裁判，均 80/80 成功）**：Faithfulness 四组均 **1.0000**；AnswerRelevancy legacy 0.9500 → hybrid / hybrid-rerank **0.9875**

**按类型（文档级 HitRate@K，hybrid-rerank，括号内为 P1）**：fact 1.0000（0.9355）/ longtail 1.0000（0.9200）/ term 1.0000（0.9167）

**解读要点**：

1. BM25 补召回兑现：dense-only 遗留的 doc miss（q013 等）在 hybrid 组全部补齐，HitRate 双满分；内容召回 0.9390→0.9975。
2. 精排价值量化：hybrid-rerank 文档/片段 MRR 双满分（正确片段全部置于第 1 位），AnswerRelevancy 同步 0.9875；Faithfulness 四组保持 1.0000。
3. Precision@K 下滑属口径效应：K=5 分母变大叠加精排聚焦 top1，P2 以 HitRate/MRR 为主指标（P1 报告预告的"top-3 混入其他文档 chunk"问题以 MRR 满分形式解决）。
4. term 类（专有名词/缩写）0.9167→1.0000：BM25 字面精确匹配 + 精排组合生效。

### 6.5 评测集迭代 v2：库扩容 65 份 + 260 题新基线（tag：`EV2-*` 四组，2026-10-24）

**动机**：P2 在 v1 口径（80 题 / 5 文档库）HitRate/MRR 双满分，天花板效应，无法度量后续增量（对应执行文档 4.6 节）。

**迭代动作**：

1. `corpus_v2.py` 生成 60 份语料（10 主题 × 6 实体，固定种子；同主题跨实体近似参数制造干扰项，如北京分机 6501 / 成都 6301），与 v1 样例合计 65 份（5 格式 × 13）
2. `ingest.py` 批量入库 65 份（复用上传链路，md5 幂等）；实测全库 68 份 / 499 chunks，幂等重跑 65 全跳过
3. `dataset build --v2`：806 段落 → LLM 每段 3~4 题 → 按 source_file 轮转采样 260 题（fact 118 / paraphrase 60 / term 54 / longtail 28，每文件恰 4 题）；新增 paraphrase 口语改写题型（如"没走OA审批，这笔费用能报销吗"）；MD5 `9b68db07…`
4. `runner --dataset app/service/eval/datasets/eval_dataset_v2.json --retrieval-only` 重跑四组基线（报告头记录 dataset 路径与 MD5）

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
| `20261024_194959_EV2-legacy` | 2026-10-24 19:49 | 旧链路回退（k=3） |
| `20261024_195437_EV2-dense-only` | 2026-10-24 19:54 | dense k=5 |
| `20261024_195927_EV2-hybrid` | 2026-10-24 19:59 | RRF 融合 top5 |
| `20261024_200850_EV2-hybrid-rerank` | 2026-10-24 20:08 | RRF + gte-rerank-v2 精排 top5 |
| `20261024_200919_compare__EV2-legacy__EV2-dense-only__EV2-hybrid__EV2-hybrid-rerank` | 2026-10-24 20:09 | 四组横向对比 |

**结论**：天花板效应消除（v1 双满分 → v2 最高 0.8115），四组单调递进（文档级 HitRate 0.60→0.81）；hybrid 召回增益与精排排序增益在难集上首次可分离。后续 P3/P4 评测以 v2 口径为准（`--dataset eval_dataset_v2.json`）。

**迭代期间 bug 修复**（详见执行文档 4.6）：`documents.py` langchain/SQLModel `Document` import 遮蔽（P2 起新上传文档 BM25 增量实际失效，改别名 `LCDocument`）；`ingest.py` 状态核对 REPEATABLE READ 旧快照（改新 session）与 md5 幂等缺口（区分跳过/重试）。

### 6.6 P3：查询优化 A/B（tag：`P3-off` / `P3-multi-query` / `P3-hyde`，2026-10-25）

**动机**：multi_query（LLM 改写 N 路 + RRF 融合）与 hyde（假设文档 embedding + 原查询双路融合）对 v2 难集是否有增量，用数据定默认 mode（执行文档 7.2）。原计划的 `P3-final`（最优配置）即结论本身——最优 = 对照组 mode=off，无需单跑。

**评测方式**：v2 口径 260 题 retrieval-only，三组同底座（hybrid + rerank，等价 EV2-hybrid-rerank），仅 `query_optimize.mode` 不同（runner `--preset off/multi-query/hyde`）；multi_query_count=3（原查询 + 3 改写共 4 路并行检索）。

| 报告 | 时间 | 说明 |
|---|---|---|
| `20261025_162418_P3-off` | 2026-10-25 16:24 | 对照组（mode=off 透传，约 9 分钟） |
| `20261025_170001_P3-multi-query` | 2026-10-25 17:00 | 4 路并行检索 + RRF 融合 topn=5（约 35 分钟） |
| `20261025_173253_P3-hyde` | 2026-10-25 17:32 | 原查询 + 假设文档双路融合（约 32 分钟） |
| `20261025_173326_compare__P3-off__P3-multi-query__P3-hyde` | 2026-10-25 17:33 | 三组横向对比 |

**检索指标（总体）**：

| 指标 | P3-off | P3-multi-query | P3-hyde |
|---|---|---|---|
| 文档级 HitRate@K | **0.8115** | 0.8115（持平） | 0.7769（-3.46pp） |
| 片段级 HitRate@K | **0.7846** | 0.7808（-0.38pp） | 0.7077（-7.69pp） |
| 文档级 MRR | **0.5813** | 0.5744 | 0.5683 |
| 片段级 MRR | **0.5615** | 0.5527 | 0.5220 |
| 文档级 Precision@K | 0.3092 | 0.3046 | 0.3254 |
| 内容召回率 | **0.7881** | 0.7850 | 0.7193 |

**按问题类型（文档级 HitRate，off → multi-query → hyde）**：fact 0.8220 → 0.8220 → 0.8051；longtail 0.8214 → 0.8214 → **0.7143**；paraphrase 0.7667 → 0.7500 → 0.7167；term 0.8333 → 0.8519 → 0.8148。

**结论与决策**：**默认 mode 维持 `off`**（已回写 retrieval_config.yml 注释）：

1. **multi_query 无净收益**：文档级 HitRate 持平，片段级/MRR 微降（4 路结果 RRF 融合稀释精排排序，个别题被改写变体带偏）；term +1.9pp 与 paraphrase -1.7pp 基本相抵。成本侧每题多 1 次 LLM（改写）+ 3 次 rerank API（评测耗时 9→35 分钟），性价比为负。
2. **hyde 明显负收益**：假设文档 embedding 把召回拉向 LLM 想象内容——longtail 类（细节参数题）最差（文档级 0.8214→0.7143、片段级 0.7857→0.6071），fact 题假设文档常编造具体参数导致 embedding 偏移；全题型无一获益。
3. 与 7.1 调研结论印证：HyDE 对表述类/术语类查询的理论收益，在本企业制度语料（短查询 + 跨实体近似干扰项）上不成立。

## 7. 基线期排障记录（复现参考）

| 现象 | 原因 | 处置 |
|---|---|---|
| `ConnectionRefusedError 127.0.0.1:3306` | db.py 默认 3306，docker 映射 6666 | `$env:MYSQL_PORT='6666'` |
| `Table 'privrag_dev.document' doesn't exist` | 全新空库未建表 | 启动一次 uvicorn 触发 lifespan `init_db()` |
| 模型调用全部超时，日志 `模型名 @ None` | 历史原因：缺 `OPENAI_BASE_URL` 回落 api.openai.com | 已修复：模型变量自动从 `docker/env/.env.dev` 白名单加载（业务聊天走 `OPENAI_BASE_URL`，评测裁判走 DashScope 兼容端点）；仍超时则检查对应 env 文件配置 |
| uvicorn 绑定 8000 报 winerror 10013 | Windows Hyper-V 端口保留 | 管理员执行 `net stop winnat` → 起服务 → `net start winnat` |
| 中途 `code: Arrearage` 中断 | DashScope 欠费（`--full` 约 320+ 次调用） | 充值后直接重跑（幂等） |
| PDF 向量化报 `surrogates not allowed (\udc80)` | pypdf 提取中文 PDF 产出代理字符，Qdrant 序列化崩溃 | **基线期保留不修**（属 P1 格式解析修复范围）；已装 pypdf 依赖 |
| 精排全量降级 `'NoneType' object has no attribute 'results'` | langchain_community DashScopeRerank 的 model_validator 无条件覆盖 model 为已下线的 `gte-rerank`(v1)，API 403 AccessDenied 且 output=None，SDK 不抛异常 | `rerank_factory.py` RemoteReranker 构造后回写 `compressor.model = model`（P2 实测于 2026-10-23） |
| ingest 汇总误报「向量化失败：None」（DB 实为 success） | MySQL REPEATABLE READ：主 session 在 `refresh(doc)` 后的事务快照早于 vectorize_document（独立 session）的提交，状态 SELECT 读旧快照 `processing` | 状态核对改用新 session（`async with async_session() as check:`，2026-10-24 实测） |

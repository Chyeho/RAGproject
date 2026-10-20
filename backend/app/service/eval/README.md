# RAG 链路评测框架（P0 评测体系）

> 定位：在**不改动现有 RAG 链路代码**的前提下，对「上传 → 向量化 → 检索 → 生成」全链路做可重复的量化评测，为 P1~P4 各阶段升级提供前后对比数据。设计依据见根目录《RAG链路升级执行文档.md》第 4 章。

## 1. 模块组成

| 模块 | 职责 |
|---|---|
| `metrics.py` | 确定性检索指标（HitRate@K / MRR / Precision@K / 内容召回率，文档级与片段级双口径），纯函数、无外部依赖 |
| `llm_judge.py` | 生成指标 LLM 裁判（Faithfulness / AnswerRelevancy），中文 Prompt 固定、temperature=0 |
| `make_samples.py` | 自造 5 格式样例文档（txt/pdf/docx/xlsx/md，"宸甄科技"企业制度语料） |
| `dataset.py` | 评测集构建与加载校验（`datasets/eval_dataset.json`） |
| `runner.py` | 评测主入口：反查 document_id → 预检 → 逐题检索/生成 → 汇总 → 报告落盘 |
| `report.py` | 单次报告读写 + 多版本横向对比（`compare` 子命令） |

数据流（一次性步骤 vs 每阶段重跑）：

```
make_samples（一次性）→ 样例经前端/API 上传入库 → dataset build（一次性，耗 LLM tokens）
    → runner（P0/P1/P2/P3 每阶段完成后重跑）→ report compare（阶段间横向对比）
```

## 2. 目录与产物

```
backend/app/service/eval/          # 本包
├── datasets/
│   ├── eval_dataset.json          # 评测集（80 题，MD5 写入报告头保证口径可追溯）
│   └── samples/                   # 5 格式自造样例（上传入库用）

backend/eval_reports/              # 报告输出（不在本包内）
├── {时间戳}_{tag}.json            # 含每题明细（检索结果、答案、裁判分）
├── {时间戳}_{tag}.md              # 人读版汇总报告
└── {时间戳}_compare__{tags}.md    # report compare 生成的横向对比表
```

## 3. 运行前置条件

1. **基础设施在跑**：MySQL + Qdrant 容器已启动（`docker compose up -d`）。全新空库需先 `uv run uvicorn app.main:app` 启动一次触发建表（lifespan → `init_db()`），再 Ctrl+C 退出。
2. **宿主机 CLI 环境变量**（⚠ 每次新开终端都要重设，`$env:` 仅当前会话有效）：

   ```powershell
   cd backend
   $env:MYSQL_PORT='6666'      # docker 映射端口；不设则默认 3306 拒连
   $env:OPENAI_BASE_URL='https://dashscope.aliyuncs.com/compatible-mode/v1'
                               # 不设则 ChatOpenAI 回落 api.openai.com，全部超时（日志特征：qwen3.7-max @ None）
   # DASHSCOPE_API_KEY 已在 backend/.env 中
   ```

3. **样例文档已入库**：5 个样例已通过上传接口完成向量化。未入库文件的题目记 0（报告头会有 missing 警告）——P0 基线期即此状态，属预期格式缺口。
4. **评测集已构建**：`datasets/eval_dataset.json` 存在且通过加载校验。
5. **DashScope 余额充足**：`--full` 全量约 320+ 次调用（每题 1 嵌入 + 1 生成 + 2 裁判）；余额不足会中途报 `Arrearage`（欠费）。`--retrieval-only` 仅约 80 次嵌入。

## 4. 常用命令

（全部在 `backend/` 目录执行；tag 规范：`P0-baseline` / `P1` / `P2-<配置名>` / `P3-<配置名>`）

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
# ── 第 0 步：环境准备（每次新开终端都要重设，$env: 仅当前会话有效）──
cd backend
$env:MYSQL_PORT='6666'
$env:OPENAI_BASE_URL='https://dashscope.aliyuncs.com/compatible-mode/v1'
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
| P2 四组对比 | `P2-dense-only` / `P2-hybrid` / `P2-hybrid-rerank` / `P2-legacy`（旧链路回退） | 待跑 |
| P3 策略对比 | `P3-multi-query` / `P3-hyde` / `P3-final`（最优配置） | 待跑 |

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

## 7. 基线期排障记录（复现参考）

| 现象 | 原因 | 处置 |
|---|---|---|
| `ConnectionRefusedError 127.0.0.1:3306` | db.py 默认 3306，docker 映射 6666 | `$env:MYSQL_PORT='6666'` |
| `Table 'privrag_dev.document' doesn't exist` | 全新空库未建表 | 启动一次 uvicorn 触发 lifespan `init_db()` |
| 模型调用全部超时，日志 `qwen3.7-max @ None` | 缺 `OPENAI_BASE_URL`，回落 api.openai.com | `$env:OPENAI_BASE_URL='https://dashscope.aliyuncs.com/compatible-mode/v1'` |
| uvicorn 绑定 8000 报 winerror 10013 | Windows Hyper-V 端口保留 | 管理员执行 `net stop winnat` → 起服务 → `net start winnat` |
| 中途 `code: Arrearage` 中断 | DashScope 欠费（`--full` 约 320+ 次调用） | 充值后直接重跑（幂等） |
| PDF 向量化报 `surrogates not allowed (\udc80)` | pypdf 提取中文 PDF 产出代理字符，Qdrant 序列化崩溃 | **基线期保留不修**（属 P1 格式解析修复范围）；已装 pypdf 依赖 |

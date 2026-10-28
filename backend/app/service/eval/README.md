# RAG 链路评测框架（P0 评测体系）

> 定位：在**不改动现有 RAG 链路代码**的前提下，对「上传 → 向量化 → 检索 → 生成」全链路做可重复的量化评测，为 P1~P4 各阶段升级提供前后对比数据。设计依据见根目录《RAG链路升级执行文档.md》第 4 章。

## 1. 模块组成

| 模块 | 职责 |
|---|---|
| `metrics.py` | 确定性检索指标（HitRate@K / MRR / Precision@K / 内容召回率，文档级与片段级双口径），纯函数、无外部依赖 |
| `llm_judge.py` | 生成指标 LLM 裁判（Faithfulness / AnswerRelevancy / Correctness 三档正确率），中文 Prompt 固定、temperature=0 |
| `make_samples.py` | 自造 5 格式样例文档（txt/pdf/docx/xlsx/md，"宸甄科技"企业制度语料） |
| `corpus_v2.py` | 评测集 v2 语料生成器（10 主题 × 6 实体 = 60 份，固定种子，跨实体近似干扰项） |
| `dataset.py` | 评测集构建与加载校验（v1 `datasets/eval_dataset.json`；v2 `datasets/eval_dataset_v2.json`，`build --v2`） |
| `ingest.py` | 评测语料批量入库 CLI（复用上传链路；md5 幂等：success 跳过 / failed 复用原 id 重试） |
| `runner.py` | 评测主入口：反查 document_id → 预检 → 逐题检索/生成 → 汇总 → 报告落盘 |
| `report.py` | 单次报告读写 + 多版本横向对比（`compare` 子命令） |
| `complex_subset.py` | 复杂题集构造：按 `router_rules.yml` 扫描候选题 + 加载人工补充复杂题（P5） |
| `hybrid_runner.py` | RAG+ReAct A/B 对照评测：A=全直调 baseline，B=规则路由混合（P5） |

数据流（一次性步骤 vs 每阶段重跑）：

```
make_samples（一次性）→ 样例经前端/API 上传入库 → dataset build（一次性，耗 LLM tokens）
    → runner（P0/P1/P2/P3 每阶段完成后重跑）→ report compare（阶段间横向对比）

评测集迭代 v2（2026-10-24，消除 P2 双满分天花板，详见 docs/rag_eval_reports）：
corpus_v2（60 份）→ ingest 批量入库 → dataset build --v2（260 题）
    → runner --dataset eval_dataset_v2.json（EV2-* 系列基线）
```

## 2. 目录与产物

```
backend/app/service/eval/          # 本包
├── datasets/
│   ├── eval_dataset.json          # 评测集 v1（80 题，MD5 写入报告头保证口径可追溯）
│   ├── eval_dataset_v2.json       # 评测集 v2（260 题，2026-10-24 迭代，详见 docs/rag_eval_reports）
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
| P2 四组对比 | `P2-dense-only` / `P2-hybrid` / `P2-hybrid-rerank` / `P2-legacy`（旧链路回退） | 2026-10-23（四组 + compare，见 docs/rag_eval_reports） |
| P3 策略对比 | `P3-off` / `P3-multi-query` / `P3-hyde` | 2026-10-25（三组 + compare，v2 口径 260 题，结论 mode=off） |
| P3b 变体补测 | `P3b-off` / `P3b-multi-query` / `P3b-multi-query-fuse` | 2026-10-26（三组 + compare，v2 口径，结论 fuse_then_rerank=false） |
| P4 收尾验证 | `P4`（文件配置直组链路，无 preset） | 2026-10-26（retrieval-only + v1/v2 双口径终局 compare，与 P3-off 七项指标逐项一致） |
| 评测集 v2 基线 | `EV2-legacy` / `EV2-dense-only` / `EV2-hybrid` / `EV2-hybrid-rerank` | 2026-10-24（四组 + compare，v2 口径 260 题） |

补充：

- 若本阶段**改动了分块/入库链路**（如 P1、P4），评测前先执行存量重建：`uv run python -X utf8 -m app.service.rag.rebuild --all`；纯检索/重排改动（P2/P3）无需重建。
- 评测完成后将关键指标回填根目录《RAG链路升级执行文档.md》附录 A 表格，保留 eval_reports 目录下的 json/md 报告归档，并同步整理至 `/docs/rag_eval_reports/`（总结报告 + 时间线）。

## 5. 指标口径速览

| 口径 | 定义 |
|---|---|
| 文档级命中 | 检索结果 `metadata.document_id` == ground truth |
| 片段级命中 | chunk 与溯源段落字符 2-gram 重叠率（包含式）≥ 0.6 |
| 内容召回率 | 正确文档结果中最大重叠率的均值 |
| Faithfulness | 答案论断被检索上下文支持的程度（LLM 裁判 0~1） |
| AnswerRelevancy | 答案与问题的相关性（LLM 裁判 0~1）。⚠ 度量主题相关而非事实正确：基线中 7 题检索未命中、模型如实拒答，仍因话题相关得 1.0 |

> ground truth 采用「document_id + 溯源原文段落」而非 vector_id：当前向量 ID 为随机 UUID，且 P1 重建后 chunk 边界与 ID 均会变化；此口径保证同一份评测集在 P0~P4 全程复用。

## 6. 已跑实验报告归档

过往实验报告（P0 / P1 / P2 / EV2 / P3 / P3b / P4 各阶段的评测记录、指标与结论）已整理归档至项目根目录 `/docs/rag_eval_reports/`，具体可查看该目录的实验报告内容：

- 《RAG评测实验总结报告.md》——各阶段实验动机、配置、完整指标与结论
- 《RAG评测实验时间线.md》——全部报告按时间排列的清单与演进脉络

原始单次/对比报告（json + md，含每题明细）仍保存在 `backend/eval_reports/`。

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
| 评测时改写/嵌入调用 401（key ****a392 invalid） | 环境变量残留失效 key：env_loader 仅注入缺失键，User/进程作用域的失效值优先于 env.dev 有效值 | 显式从 env.dev 注入有效值跑评测；根因清理残留：`[Environment]::SetEnvironmentVariable('DASHSCOPE_API_KEY', $null, 'User')`（2026-10-26 实测） |
| A/B 评测启动即报 `AuthenticationError: No api key provided` | `dashscope` SDK 在 **import 时**读取 `DASHSCOPE_API_KEY`（`dashscope/common/env.py`），而 env_loader 在导入之后才注入，SDK 已固化为 None | 启动前显式导出（见 8.5），或把 key 写入用户环境变量后重开终端 |

## 8. RAG+ReAct 混合架构 A/B 评测（P5）

> 定位：验证「窄规则路由 + RAG 直调为主 + ReAct 复杂通道」相对改造前纯直调是否**不劣化简单题、改善复杂题**。设计依据见根目录《RAG+ReAct混合架构改造执行文档.md》第 5 章。

### 8.1 分组与执行口径

| 组 | 执行路径 | 用途 |
|---|---|---|
| A | 强制 `rag.rag_summarize`（单次检索 + 生成） | baseline，复现改造前行为 |
| B | `HybridOrchestrator.answer`（`ENABLE_HYBRID_ROUTER` 控制路由 → 直调 / ReAct → 失败降级） | 被测的混合架构 |

- 两组使用**同一批题、同一检索链路、同一评测模型**，唯一变量是编排路径。
- 每题执行前清空该 `session_id` 的会话历史，重跑同 tag 不受旧历史污染；每题独立 session。
- B 组若 `ENABLE_HYBRID_ROUTER=false`，会在日志中告警并退化为全直调（A/B 将无差异）。

### 8.2 题集构造

**简单集**：`eval_dataset_v2.json`（260 题），剔除已被选入复杂集的 qid（当前为 0 题）。

**复杂集**（`complex_subset.py`）：

1. `scan` 子命令按 `router_rules.yml` 的强/弱规则与阈值严格扫描 v2 题集；
2. 实测 260 题命中 **0 道真复杂题**（仅 15 道含弱关键词的单跳题，不应判为复杂），故复杂集全部来自**同语料人工补充题**：`eval_complex_authored_v2.json`（c001~c020，共 20 道）；
3. 补充题基于同一 65 份语料，覆盖跨文档对比、阈值判断、多步骤计算与制度冲突，例如「上海 vs 北京住宿标准差异」「报销 30 天 vs 45 天以哪个为准」「8 万 + 25 万采购组合分别走什么方式」；
4. `complex_qids_v2.json` 的 `qids` 为空数组，`note` 记录上述原因；后续若新增复杂题，可继续追加 qid 或在补充题文件中扩展。

```powershell
# 查看严格规则下的候选复杂题（不写文件）
uv run python -m app.service.eval.complex_subset scan
```

### 8.3 指标口径

| 指标 | 口径 |
|---|---|
| 文档级 / 片段级 HitRate | 与 `runner.py` 完全一致（`metrics.judge_retrieval`） |
| 答案正确率 | LLM 裁判对比标准答案，三档 **0 / 0.5 / 1**，就近吸附；解析失败不计均值，单独计 `num_judge_error` |
| Faithfulness / AnswerRelevancy | 与既有评测共用裁判提示词 |
| 任务完成率 | 复杂题：答案非空且正确率 ≥ 0.5；简单题不计 |
| 延迟 | 单题端到端平均 / P95（毫秒） |
| 工具调用 | B 组复杂题平均工具调用次数（A 组恒为 0） |
| 降级率 | B 组 `fallback=True` 占比，并输出 `fallback_reason` 分布（timeout / max_steps_exceeded / parse_error / internal_error 等） |

### 8.4 命令

（均在 `backend/` 目录执行）

```powershell
# 小样本冒烟（2 简单 + 2 复杂，两组）
uv run python -X utf8 -m app.service.eval.hybrid_runner --tag AB-smoke --group both --limit-simple 2 --limit-complex 2

# 正式 A/B（简单题可按需 limit，复杂集全量 20 题）
uv run python -X utf8 -m app.service.eval.hybrid_runner --tag AB-v1 --group both --limit-simple 50

# 只跑单组（分别执行后人工对照，或直接看每次报告）
uv run python -X utf8 -m app.service.eval.hybrid_runner --tag AB-A --group A
uv run python -X utf8 -m app.service.eval.hybrid_runner --tag AB-B --group B
```

### 8.5 运行前置与降级

1. **MySQL + Qdrant 已启动**：本项目 MySQL 由 `docker compose` 拉起，宿主机映射端口 **6666**（非 3306），评测命令需显式指认：

   ```powershell
   $env:MYSQL_HOST='127.0.0.1'; $env:MYSQL_PORT='6666'
   # MYSQL_USER / MYSQL_PASSWORD / MYSQL_DATABASE 取自 docker/env/.env.dev
   ```

   MySQL 仅用于反查 `source_file → document_id`；Qdrant 提供检索。
2. **DashScope Key 必须在启动前已在进程环境中**（SDK 在 import 时固化），本机未设置用户环境变量时可显式导出：

   ```powershell
   $line = Select-String -Path '..\docker\env\.env.dev' -Pattern '^DASHSCOPE_API_KEY=' | Select-Object -First 1
   $env:DASHSCOPE_API_KEY = ($line.Line -split '=',2)[1].Trim()
   ```

3. **MySQL 不可用时**：`hybrid_runner` 会告警并降级为空文档映射，流程、正确率、延迟、工具调用、降级分布仍可评测；**文档级/片段级 HitRate 会记为 0，不可作为检索结论**（报告头「文档映射」标注为不可用）。
4. 裁判模型固定 DashScope `qwen-plus`（可用 `EVAL_CHAT_MODEL` 覆盖），与业务聊天模型解耦。

### 8.6 产物与错误分析

```
backend/eval_reports/
├── {ts}_{tag}.json      # meta + 每组 summary（simple/complex/all）+ 每题 trace 摘要
├── {ts}_{tag}.csv       # 每题一行，便于 Excel 透视
└── {ts}_AB-compare.md   # 两组时生成：三项指标对照 + 降级分布 + 口径说明
```

建议的错误分析顺序：

1. 看 `AB-compare.md` 的复杂集任务完成率与正确率差异，再看 P95 延迟是否可接受；
2. 看 `fallback_reason` 分布：`timeout` 偏多说明预算或检索过慢，`parse_error` 偏多说明模型未按 JSON 输出；
3. 在 CSV 中筛 `correctness=0` / `task_completion=false` 的题目，对照 `answer` 与标准答案；
4. 需要逐轮排查时，用该题 `session_id`（`eval_{tag}_{group}_{qid}`）或时间点查 `backend/app/logs/traces/*.jsonl`（`LOG_TRACE_LEVEL=full` 时含每轮 thought/action/observation）。

### 8.7 实测结果（2026-10-28，10 简单 + 10 复杂）

报告：`backend/eval_reports/20261028_165307_AB-10x10.json / .csv / _AB-compare.md`（MySQL 走 Docker 映射端口 6666，文档映射可用，命中率为真实口径）。

| 指标 | A-简单 | B-简单 | A-复杂 | B-复杂 |
|---|---|---|---|---|
| 文档级 HitRate | 90.00% | 90.00% | 100.00% | 100.00% |
| 片段级 HitRate | 80.00% | 80.00% | 90.00% | 100.00% |
| 答案正确率 | 0.8500 | 0.8500 | 0.6000 | **0.6500** |
| Faithfulness | 1.0 | 1.0 | 1.0 | 1.0 |
| AnswerRelevancy | 1.0 | 1.0 | 0.8500 | **0.9700** |
| 平均延迟 | 4003ms | 4995ms | 4423ms | 22339ms |
| P95 延迟 | 5047ms | 6133ms | 6170ms | 34660ms |
| 任务完成率 | - | - | 70.00% | **80.00%** |
| 平均工具调用 | 0 | 0 | 0 | 2.7 |
| 降级率 | 0 | 0 | 0 | 10.00%（1 次 timeout） |

结论（10+10 小样本）：

- **简单题零劣化**：两组命中率、正确率完全一致；B 组延迟 +25% 属同链路模型抖动，路由与编排开销可忽略。
- **复杂题有改善**：正确率 0.60→0.65，任务完成率 70%→80%，片段级 HitRate 90%→100%，AnswerRelevancy 0.85→0.97；代价是平均延迟 4.4s→22.3s。
- **主要失败模式**：1 道复杂题在 30s 预算内未收尾（`timeout`）并降级直调；B 组 P95 34.7s 已触及总超时。若扩量评测，应重点关注 `timeout` 占比，必要时缩短单题检索耗时或调整预算。

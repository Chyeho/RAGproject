# RAG 链路评测框架

> 对「上传 → 向量化 → 检索 → 生成」做可重复的量化评测，并支持 RAG 与 RAG+ReAct 混合架构的 A/B 对照。设计依据见 `docs/development_docs/4_RAG链路升级执行文档.md` 与 `3_RAG+ReAct混合架构改造执行文档.md`。

## 1. 模块组成

| 模块 | 职责 |
|---|---|
| `metrics.py` | 确定性检索指标（HitRate / MRR / Precision / 内容召回率），文档级与片段级双口径，纯函数 |
| `llm_judge.py` | LLM 裁判：Faithfulness / AnswerRelevancy / Correctness（0 / 0.5 / 1 三档） |
| `make_samples.py` | 生成 5 格式样例文档（txt / pdf / docx / xlsx / md） |
| `corpus_v2.py` | v2 语料生成器（10 主题 × 6 实体，固定种子，含近似干扰项） |
| `dataset.py` | 评测集构建与加载校验（v1 80 题 / v2 260 题） |
| `ingest.py` | 评测语料批量入库（复用上传链路，按 MD5 幂等） |
| `runner.py` | 检索链路评测主入口（支持 `--preset` 切换链路，输出 json / md） |
| `report.py` | 报告读写与多版本横向对比 |
| `complex_subset.py` | 复杂题构造：按 `router_rules.yml` 扫描候选 + 加载人工补充题 |
| `hybrid_runner.py` | A/B 评测：A = 全直调 baseline，B = 规则路由混合架构 |

```
一次性：make_samples → 上传入库 → dataset build
每次评测：runner（检索 / 全量）→ report compare
A/B：hybrid_runner（两组）→ 自动生成 AB-compare.md
```

## 2. 目录与产物

```
backend/app/service/eval/
├── datasets/
│   ├── eval_dataset.json          # v1：80 题 / 5 文档库
│   ├── eval_dataset_v2.json       # v2：260 题 / 65 文档库（当前主口径）
│   ├── samples/                   # 5 格式样例
│   ├── corpus_v2/                 # v2 语料 60 份
│   ├── complex_qids_v2.json       # 复杂题 qid（严格规则筛选结果，当前为空）
│   └── eval_complex_authored_v2.json  # 人工补充复杂题 20 道
backend/eval_reports/              # 新评测运行输出（运行后生成）
docs/rag_eval_reports/             # 历史实验归档：按日期分组，每份报告一个文件夹
├── RAG评测实验总结报告.md
├── RAG评测实验时间线.md
├── 2026-10-19/
│   ├── 20261019_010016_P0-baseline/   # 内含同名 json + md
│   └── 20261019_015104_P0-baseline/
├── 2026-10-23/
│   ├── 20261023_194144_P2-hybrid-rerank/
│   └── 20261023_200645_compare/       # 对比报告
└── ...
```

- 单次报告：`{时间戳}_{tag}.json`（逐题明细）与 `.md`（人读汇总）。
- A/B 报告：`{时间戳}_{tag}.json / .csv`，两组时另有 `{时间戳}_AB-compare.md`。
- 归档规则：先按实验日期建 `YYYY-MM-DD/`，其下每份报告一个文件夹（`<报告名>/`，内含同名 json / md / csv）；compare 报告文件夹统一用 `{时间戳}_compare`，报告文件名保持不变。

## 3. 运行前置

1. **基础设施**：MySQL + Qdrant 已启动；全新空库先启动一次后端触发建表（`scripts/start-backend.ps1`，lifespan → `init_db()`）。
2. **宿主机端口**：MySQL `16666`、Qdrant `16333`（容器内仍为 3306 / 6333，详见根目录 README 3.4.4）。
3. **环境变量**（每次新开终端需重设，`$env:` 仅当前会话有效）：

   ```powershell
   cd backend
   $env:MYSQL_HOST='127.0.0.1'; $env:MYSQL_PORT='16666'
   # MYSQL_USER / MYSQL_PASSWORD / MYSQL_DATABASE 取自 docker/env/.env.dev
   ```

   - 模型变量（`DASHSCOPE_API_KEY` / `OPENAI_*`）启动时按白名单从 `docker/env/.env.dev` 自动注入缺失键，无需手工设置。
   - **A/B 评测例外**：`dashscope` SDK 在 import 时读取 Key，必须先导出再启动：

     ```powershell
     $line = Select-String -Path '..\docker\env\.env.dev' -Pattern '^DASHSCOPE_API_KEY=' | Select-Object -First 1
     $env:DASHSCOPE_API_KEY = ($line.Line -split '=',2)[1].Trim()
     ```
4. **数据就绪**：语料已入库（`ingest`），评测集已构建（`dataset build`）；未入库文档对应题目记 0。
5. **费用**：`--full` 每题约 4 次调用（1 嵌入 + 1 生成 + 2 裁判）；`--retrieval-only` 仅 1 次嵌入。裁判与评测集生成固定走 DashScope（默认 `qwen-plus`，可用 `EVAL_CHAT_MODEL` 覆盖）。

## 4. 常用命令

> 全部在 `backend/` 目录执行；中文乱码时加 `-X utf8`。

### 4.1 检索链路评测（runner）

`--preset` 用于切换链路开关，报告头部会写入当时的配置快照：

| 链路对象 | preset | 开关 / 口径 | 适用场景 |
|---|---|---|---|
| 旧链路回退 | `legacy` | 混合检索 off、精排 off，dense `k=3` | 改造前基线 |
| 纯稠密 @5 | `dense-only` | 混合 off、精排 off，`k=5` | 隔离「调大 K」的收益 |
| 混合检索 | `hybrid` | dense + BM25 → RRF → top5，精排 off | 验证 BM25 补召回 |
| 混合 + 精排 | `hybrid-rerank` | RRF → gte-rerank-v2 → top5 | **当前生产默认** |
| 查询优化对照组 | `off` | hybrid+rerank，`query_optimize.mode=off` | P3 对照 |
| 多路改写 | `multi-query` | 每路改写+精排，末端 RRF | 异构语料/脏查询 |
| HyDE | `hyde` | 假设文档双路检索 | 实验性 |
| 融合后精排 | `multi-query-fuse` | 多路混合后统一精排 | 验证链路顺序 |

```powershell
# 当前生产配置（v2，仅检索，快）
uv run python -X utf8 -m app.service.eval.runner --tag EV2-hybrid-rerank `
  --preset hybrid-rerank --retrieval-only --dataset datasets/eval_dataset_v2.json

# 全量（检索 + 生成 + 裁判）
uv run python -X utf8 -m app.service.eval.runner --tag EV2-hybrid-rerank --preset hybrid-rerank --full `
  --dataset datasets/eval_dataset_v2.json

# 不加 preset：完全按 retrieval_config.yml 当前配置跑
uv run python -X utf8 -m app.service.eval.runner --tag P4 --retrieval-only --dataset datasets/eval_dataset_v2.json

# 只测「提高 K」：--k 直接覆盖稠密检索 K（与 --preset 互斥）
uv run python -X utf8 -m app.service.eval.runner --tag K8 --retrieval-only --k 8

# 调试：只跑前 10 题
uv run python -X utf8 -m app.service.eval.runner --tag debug --preset hybrid-rerank --retrieval-only --limit 10
```

### 4.2 混合架构 A/B（hybrid_runner）

- **A 组**：强制 `rag_summarize`（单次检索 + 生成），复现改造前行为。
- **B 组**：`HybridOrchestrator.answer`（规则路由 → 直调 / ReAct → 失败降级）。
- 两组同题、同检索链路、同评测模型；每题独立 session 并清空历史。

```powershell
# 冒烟（2 简单 + 2 复杂）
uv run python -X utf8 -m app.service.eval.hybrid_runner --tag AB-smoke --group both --limit-simple 2 --limit-complex 2

# 正式：简单题取 50，复杂题全量 20
uv run python -X utf8 -m app.service.eval.hybrid_runner --tag AB-v1 --group both --limit-simple 50

# 只跑单组
uv run python -X utf8 -m app.service.eval.hybrid_runner --tag AB-A --group A
uv run python -X utf8 -m app.service.eval.hybrid_runner --tag AB-B --group B
```

```powershell
# 查看严格规则命中的复杂候选（不写文件）
uv run python -X utf8 -m app.service.eval.complex_subset scan
```

复杂集口径：v2 严格规则实测 0 道真复杂题，故使用同语料人工补充题 `eval_complex_authored_v2.json`（c001~c020）；`complex_qids_v2.json` 的 `qids` 为空。新增复杂题可追加 qid 或扩充补充题文件。

### 4.3 结果对比

```powershell
# RAG 链路多版本对比（按 tag 取各自最新报告）
uv run python -X utf8 -m app.service.eval.report compare P0-baseline P1 P2-hybrid-rerank EV2-hybrid-rerank

# A/B：--group both 会自动生成 AB-compare.md；单组运行则人工对照
```

## 5. 指标口径

| 类别 | 指标 | 定义 |
|---|---|---|
| 检索 | 文档级 HitRate | Top-K 中 `document_id` == ground truth 的题目占比 |
| 检索 | 片段级 HitRate | 在文档命中基础上，chunk 与溯源段落 2-gram 重叠率 ≥ 0.6 |
| 检索 | MRR / Precision | 首个命中排名倒数均值 / Top-K 命中比例 |
| 检索 | 内容召回率 | 正确文档结果中最大重叠率的均值 |
| 生成 | Faithfulness | 答案论断被检索上下文支持的程度（0~1） |
| 生成 | AnswerRelevancy | 答案与问题的相关性（0~1，主题相关≠事实正确） |
| 生成 | 答案正确率 | 裁判对比标准答案，三档 0 / 0.5 / 1；解析失败单独计 `num_judge_error` |
| A/B | 任务完成率 | 复杂题：答案非空且正确率 ≥ 0.5 |
| A/B | 延迟 / 工具调用 | 单题端到端平均与 P95 / B 组复杂题平均工具调用次数 |
| A/B | 降级率 | B 组 `fallback=True` 占比，并输出 `fallback_reason` 分布 |

> ground truth 用「document_id + 溯源段落」而非 vector_id：向量 ID 随重建变化，文本口径可让同一评测集跨阶段复用。

## 6. 报告归档与结果解读

### 6.1 归档与查找

- 历史实验按 `docs/rag_eval_reports/YYYY-MM-DD/<报告名>/` 存放，索引见同目录《RAG评测实验时间线.md》，完整指标与结论见《RAG评测实验总结报告.md》。
- 新跑的评测先落在 `backend/eval_reports/`，确认无误后按同一规则移动到 `docs/rag_eval_reports/YYYY-MM-DD/<报告名>/`（compare 用 `{时间戳}_compare`）。
- 报告头部包含配置快照（preset、hybrid/rerank 开关、模型、评测集 MD5），跨报告对比前先确认口径一致（v1 与 v2 不可混比）。

### 6.2 阅读顺序

1. 先看 `.md` 汇总的 HitRate / 正确率 / P95，确认是否达到预期；
2. A/B 看 `AB-compare.md` 的复杂题任务完成率与正确率差异，再看延迟是否可接受；
3. 看 `fallback_reason` 分布：`timeout` 偏多说明预算或检索过慢，`parse_error` 偏多说明模型未按 JSON 输出；
4. CSV 中筛 `correctness=0` / `task_completion=false`，对照 `answer` 与标准答案；
5. 需要逐轮排查时，用 `session_id`（`eval_{tag}_{group}_{qid}`）查 `backend/app/logs/traces/*.jsonl`（`LOG_TRACE_LEVEL=full` 含每轮 thought/action/observation）。

### 6.3 A/B 实测结论（2026-10-28，10 简单 + 10 复杂）

报告：`docs/rag_eval_reports/2026-10-28/20261028_165307_AB-10x10/` 与 `docs/rag_eval_reports/2026-10-28/20261028_165307_AB-compare/`。

| 指标 | A-简单 | B-简单 | A-复杂 | B-复杂 |
|---|---|---|---|---|
| 答案正确率 | 0.85 | 0.85 | 0.60 | **0.65** |
| 任务完成率 | - | - | 70% | **80%** |
| 平均延迟 | 4003ms | 4995ms | 4423ms | 22339ms |
| 降级率 | 0 | 0 | 0 | 10%（1 次 timeout） |

- 简单题零劣化（路由全部 `rag_direct`），复杂题正确率 +0.05、完成率 +10pp。
- 代价是复杂题约 5 倍延迟；扩量时重点监控 `timeout` 降级占比。

## 7. 排障速查

| 现象 | 原因 | 处置 |
|---|---|---|
| `ConnectionRefusedError 127.0.0.1:3306` | 未设宿主机映射端口 | `$env:MYSQL_PORT='16666'` |
| `Table 'privrag_dev.document' doesn't exist` | 空库未建表 | 启动一次后端触发 `init_db()` |
| uvicorn 绑定 18000 报 `WinError 10013` | Windows 端口保留段 | 管理员 `net stop winnat` → 启动服务 → `net start winnat` |
| 模型调用超时且日志 `模型名 @ None` | 缺 `OPENAI_BASE_URL` | 确认 `docker/env/.env.dev` 配置；模型变量会自动加载 |
| 评测中途 `code: Arrearage` | DashScope 欠费 | 充值后直接重跑（幂等） |
| A/B 启动报 `AuthenticationError: No api key provided` | `dashscope` 在 import 时读取 Key | 启动前显式导出（见第 3 节第 3 条），或写入用户环境变量后重开终端 |
| 改写/嵌入 401（key invalid） | 用户/进程作用域残留旧 Key 覆盖 env 文件 | 清理残留：`[Environment]::SetEnvironmentVariable('DASHSCOPE_API_KEY', $null, 'User')` |
| 精排全量降级 `'NoneType' object has no attribute 'results'` | 旧版 DashScopeRerank 强制覆盖为已下线的 `gte-rerank` v1 | 使用 `gte-rerank-v2`；`rerank_factory` 已回写模型名 |
| ingest 汇总误报「向量化失败：None」 | MySQL REPEATABLE READ 读到旧快照 | 状态核对使用独立 session（已修复） |
| PDF 向量化 `surrogates not allowed` | pypdf 提取中文 PDF 产生代理字符 | P1 已修；旧报告保留此现象 |
| `Event loop is closed` Traceback（退出时） | aiomysql 析构噪音 | 退出码 0 即非致命 |
| 中文输出乱码 | 控制台编码 | 命令前加 `-X utf8` |

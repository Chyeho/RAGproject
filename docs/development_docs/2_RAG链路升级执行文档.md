# RAG 链路升级执行文档

> 状态：**待确认**（确认后按本文档开发，开发过程以本文档为唯一执行依据）
> 范围：RAG 评测体系 + 格式感知解析与智能分块 + 混合检索与精排重排 + 查询优化 + 参数热更新与收尾
> 原则：**评测驱动升级**——先建评测体系跑出基线，每个阶段升级后重新评测，用数据对比体现升级成果

---

## 1. 背景与现状分析

### 1.1 当前链路（升级前）

```
上传文档 → file_handler 加载(txt/pdf) → RecursiveCharacterTextSplitter 固定切分(150/20)
        → DashScope/Ollama 嵌入 → Qdrant(纯稠密) → top-k=3 直接返回
        → 拼接 Prompt + 历史 → LLM 生成回答
```

### 1.2 现存问题清单（代码级定位）

| # | 问题 | 位置 | 影响 |
|---|---|---|---|
| 1 | 上传放行 `pdf/docx/doc/txt/md/xlsx`，但解析器仅支持 txt/pdf，docx/md/xlsx 向量化必然失败 | `routers/documents.py` 的 `ALLOWED_TYPES` vs `utils/file_handler.py` 的 `get_file_documents` | 格式缺口，上传即失败 |
| 2 | `chunk_size=150` 对中文过小，且固定切分不感知文档结构 | `config/qdrant_config.yml` | 语义被切碎，检索上下文不足 |
| 3 | `doc.metadata = {"document_id": ...}` 直接**覆盖**原有 metadata（页码等全丢） | `service/rag/vector_store.py` upload_file | 引用来源信息丢失 |
| 4 | 纯稠密向量检索，无混合检索/精排/查询优化 | `vector_store.py` get_retriever | 专有名词、缩写、长尾查询召回差 |
| 5 | 回答检索与引用检索是**两次独立检索**（重复计算，且两者结果可能不一致） | `routers/chat.py` build_citations | 算力浪费 + 引用与回答来源脱节 |
| 6 | RAG 参数修改需重启后端才生效 | `routers/settings.py` | 调参迭代效率低 |
| 7 | 无任何评测手段，链路改动效果无法量化 | 全局 | 本次升级要解决的核心前置问题 |

### 1.3 与《技术文档.md》规划项的对应结论

| 技术文档规划项 | 本次是否实施 | 落点 |
|---|---|---|
| a. 扩展文档格式（docx/xlsx/md） | ✅ 实施 | P1 |
| b. 增强解析（章节树/智能切分/元数据） | ✅ 实施 | P1 |
| c. 混合检索 + 精排 + 查询改写 | ✅ 实施 | P2/P3 |
| RAG 参数实时生效（检索参数部分） | ✅ 实施 | P4 |
| 引用与回答合并为一次检索 | ✅ 实施 | P4 |
| 短信服务接入 | ❌ 不在本次范围 | — |
| 权限/部门级隔离、可观测性、CI/CD、多模态 | ❌ 不在本次范围 | — |

---

## 2. 技术选型结论

| 决策点 | 结论 | 理由 |
|---|---|---|
| 评测框架 | **自研轻量评测框架** | 检索指标确定性计算，生成指标 LLM 裁判（中文 Prompt 可控）；无重依赖、单测 mock 友好、对比报告直观 |
| 混合检索 | **rank_bm25 + jieba + RRF** | BM25 内存索引从 `document_chunk` 表构建；中文分词准确；不依赖 Qdrant 版本特性、无需重建 collection |
| 精排重排 | **工厂模式双通道** | 跟随现有 `MODEL_MODE`：remote=DashScope gte-rerank-v2（langchain DashScopeRerank），local=bge-reranker-v2-m3（sentence-transformers）；失败自动降级跳过 |
| 查询优化 | **multi-query + HyDE 都实现、可配置** | 均做成配置开关，默认关闭；由评测体系 A/B 对比后决定默认值，temperature=0 |

### 2.1 新增依赖清单

| 包 | 用途 | 备注 |
|---|---|---|
| rank_bm25 | BM25 稀疏检索 | 轻量纯 Python |
| jieba | 中文分词（BM25 分词器） | — |
| pymupdf | PDF 章节树（目录 outline）解析 | 现有 pypdf 保留做兜底 |
| python-docx | docx 解析 | — |
| openpyxl | xlsx 解析 | — |
| sentence-transformers (+torch) | 本地 Cross-Encoder 重排 | **作为可选依赖组** `local-rerank`，未安装自动降级跳过重排，避免主环境过重 |

---

## 3. 升级后总体架构

```
                                   ┌─────────────── 查询优化(P3) ───────────────┐
                                   │ mode: off / multi_query / hyde            │
                                   │ (temperature=0，失败回退原始查询)           │
                                   └──────────────────┬────────────────────────┘
用户提问 ──→ RagSummarizeService ──→ HybridRetriever(P2)
                                   ├─ DenseRetriever(Qdrant, topN=20)
                                   ├─ BM25Retriever(document_chunk表+jieba, topN=20)
                                   │        └── RRF 融合(rrf_k=60)
                                   └─→ Reranker(工厂双通道, topN→topK=5)
                                              ↓
                                   TopK chunks(含章节/页码/Sheet元数据)
                                              ↓
                                   Prompt(参考资料带章节路径) → LLM → 回答 + citations(同一次检索)

上传文档 ──→ 格式感知解析(P1) ──→ 智能切分 ──→ 确定性ID入Qdrant + document_chunk表 ──→ BM25索引增量更新
```

### 3.1 新增代码结构规划

```
backend/app/
├─ service/
│  ├─ rag/
│  │  ├─ rag_service.py            # 改造：接入新检索器，返回(回答,来源)
│  │  ├─ vector_store.py           # 改造：格式感知分块接入、metadata合并、确定性ID
│  │  ├─ chunking/                 # P1 新增
│  │  │  ├─ strategy.py            #   格式→策略路由 + 智能切分规则(小合并/长再分)
│  │  │  ├─ pdf_chunker.py         #   章节树：outline→字体启发式→常规兜底
│  │  │  ├─ docx_chunker.py        #   标题层级切分 + 表格序列化
│  │  │  ├─ markdown_chunker.py    #   MarkdownHeaderTextSplitter(h1~h3)
│  │  │  ├─ excel_chunker.py       #   Sheet→行组块(携带表头上下文)
│  │  │  └─ text_chunker.py        #   中文感知常规切分(参数调优)
│  │  ├─ retrieval/                # P2 新增
│  │  │  ├─ bm25_retriever.py      #   BM25Retriever(BaseRetriever) 内存索引
│  │  │  ├─ rrf.py                 #   RRF 融合算法
│  │  │  ├─ hybrid_retriever.py    #   HybridRetriever = dense+bm25+RRF
│  │  │  └─ rerank.py              #   重排包装器(统一接口+降级)
│  │  └─ query/                    # P3 新增
│  │     ├─ enhancer.py            #   QueryEnhancer 模式路由(off/multi_query/hyde)
│  │     ├─ multi_query.py         #   多查询扩展
│  │     └─ hyde.py                #   假设文档嵌入
│  └─ eval/                        # P0 新增
│     ├─ dataset.py                #   评测集构建(LLM生成)+加载
│     ├─ metrics.py                #   确定性检索指标(HitRate@K/MRR/P@K/R@K)
│     ├─ llm_judge.py              #   LLM裁判指标(忠实度/答案相关性, 中文Prompt)
│     ├─ runner.py                 #   评测编排 CLI(__main__可执行)
│     ├─ report.py                 #   报告生成(md+json)与多版本对比表
│     └─ datasets/                 #   评测集与自造样例文件（eval_dataset.json + samples/，不进 app/data）
├─ modelFactory/
│  └─ rerank_factory.py            # P2 新增：重排模型工厂(双通道+降级)，与chat/embed工厂并列
```

---

## 4. 阶段 P0：RAG 评测体系（先于一切升级）

### 4.1 目标

- 在**不动现有链路一行代码**的前提下，构建可重复运行的评测 CLI，产出当前链路基线报告
- 后续每阶段完成后重跑评测，报告自动生成横向对比表
- **评测对象即现有链路本身**：runner 直接实例化 `VectorStoreService().get_retriever()` 与 `RagSummarizeService`（与 chat.py 相同对象），不包装、不代理、不改动

### 4.2 评测集构建

- 样例文档：全部**开发自造**（员工手册 txt 亦为自造样例，可修改或删除），pdf / docx / xlsx / md 各至少 1 个 + 员工手册 txt；统一样例存放于 `backend/app/service/eval/datasets/samples/`，通过现有上传接口入库（**不放 `backend/app/data`**，避免与企业正式文档混淆）
- 生成方式：`uv run python -m app.service.eval.dataset build --num 80`，LLM 从样例文档的章节/段落生成 QA 对（问题 + 标准答案 + 溯源原文段落），**人工校验后定稿**
- 规模：≥ 50 条（含事实型/术语型/长尾型问题分布），覆盖全部格式
- 存储：`backend/app/service/eval/datasets/eval_dataset.json`，格式：

```json
[{
  "qid": "q001",
  "question": "公司年假有几天？",
  "ground_truth_answer": "……",
  "document_id": 1,
  "source_passage": "生成该问题所依据的原文段落（命中判定依据）",
  "question_type": "fact|term|longtail"
}]
```

> **不以 vector_id 作为 ground truth 主键的原因**：当前链路向量 ID 为随机 UUID，且 P1 重建后 chunk 边界与 ID 均会变化；以「溯源原文段落 + document_id」做命中判定，可让**同一份评测集在 P0~P3 全程稳定复用**，保证各期数据口径一致。

### 4.3 指标定义

**检索指标（确定性计算，无需 LLM）**

命中判定两级（均为确定性规则）：
- **文档级**：检索结果的 `metadata.document_id` == ground truth 的 `document_id`
- **片段级**：检索 chunk 文本与 `source_passage` 的字符 n-gram 重叠率 ≥ 阈值（默认 0.6，归一化后计算）

| 指标 | 定义 |
|---|---|
| HitRate@K | Top-K 中出现命中的问题占比（文档级/片段级分别统计） |
| MRR | 首个命中结果排名倒数的平均值（文档级/片段级分别统计） |
| Precision@K / Recall@K | Top-K 命中精度 / 溯源段落内容召回率 |

> P1 落地确定性 vector_id 后，可切换为 ID 精确匹配模式（更快更严格）；文本重叠模式保留为跨阶段兜底口径。

**生成指标（LLM 裁判，中文 Prompt 固定，temperature=0）**

| 指标 | 定义 |
|---|---|
| Faithfulness | 答案中的论断是否被检索上下文支持（0~1） |
| AnswerRelevancy | 答案与问题的相关性（0~1） |

### 4.4 评测流程与 CLI

```powershell
# 仅检索指标（快，用于 P1/P2 检索类升级对比）
uv run python -m app.service.eval.runner --tag P0-baseline --retrieval-only
# 全量（检索+生成）
uv run python -m app.service.eval.runner --tag P0-baseline --full
# 生成多版本对比表
uv run python -m app.service.eval.report compare P0-baseline P1 P2 P3
```

- 报告输出：`backend/eval_reports/{时间戳}_{tag}.json/.md`；评测参数（当时的链路配置快照）写入报告头部，保证可追溯
- 运行前提：模式 A 基础设施（MySQL + Qdrant 容器运行、DashScope key 可用），样例文档已通过现有上传接口完成向量化
- 注意：P0 基线必须在**任何链路代码改动之前**完成评测并归档

### 4.5 交付物与验收标准

- [x] eval 包 5 个模块 + CLI 可重复运行
- [x] 评测集 ≥50 条，人工校验通过
- [x] P0 基线报告（retrieval + generation 全量）归档
- [x] 单元测试：metrics 确定性指标用构造数据全 mock；llm_judge mock chat_model（遵循 tests/README.md 文化）

### 4.6 评测集迭代（v2 口径，2026-10-24）

> 背景：P2 完成后，v1 评测集（80 题 / 5 文档库）HitRate/MRR 双满分，出现天花板效应，无法继续度量 P3/P4 的增量收益。本轮对评测集本身迭代，恢复区分度。

**语料库扩容（`corpus_v2.py`）**

- 新增 60 份企业制度语料：10 主题 × 6 实体，固定随机种子可复现；与 v1 自造样例合计 65 份，5 格式均衡（每格式 13 份）
- 跨实体近似设计：同主题不同实体承载相近但不同的参数（如北京分机 6501 / 成都分机 6301），制造天然干扰项，专测片段级区分能力
- 产物：`datasets/corpus_v2/`

**评测集 v2（`dataset.py build --v2`）**

- 构建链路：65 份文档 → 806 个有效段落 → LLM 每段生成 3~4 题 → 按 source_file 轮转采样至 260 题
- 题量与分布：260 题 = 65 文件 × 恰好 4 题；fact 118 / paraphrase 60 / term 54 / longtail 28
- 新增 **paraphrase 题型**：口语化改写模拟真实提问（如「没走OA审批，这笔费用能报销吗」），直指 dense 向量检索的改写鲁棒性短板
- 产物：`datasets/eval_dataset_v2.json`，MD5 `9b68db07…`（前 8 位，全量写入报告头保证口径可追溯）

**批量入库（`ingest.py`，本轮新增 CLI）**

- 复用现有「上传→分块→向量化→BM25 增量」链路批量入库 65 份评测语料；实测全库 68 份 / 499 chunks
- 幂等语义：md5 查重，`success` 跳过；`failed` / 残留 `processing` 复用原 id+file_path 重试（重试前清理旧 chunk 行；Qdrant chunk_id 为确定性 uuid5，upsert 天然幂等，向量库无需清理）
- 验证：幂等重跑 65 全跳过、0 失败

**EV2 四组基线（260 题，retrieval-only，2026-10-24）**

| 指标 | EV2-legacy(k=3) | EV2-dense-only(k=5) | EV2-hybrid | EV2-hybrid-rerank |
|---|---|---|---|---|
| 文档级 HitRate | 0.6000 | 0.6923 | 0.7462 | **0.8115** |
| 片段级 HitRate | 0.4615 | 0.5115 | 0.6231 | **0.7846** |
| 文档级 MRR | 0.4949 | 0.5152 | 0.5389 | **0.5873** |
| 片段级 MRR | 0.3551 | 0.3662 | 0.4512 | **0.5675** |
| 内容召回率 | 0.4847 | 0.5441 | 0.6441 | **0.7881** |

报告（均在 `backend/eval_reports/`）：`20261024_194959_EV2-legacy` / `20261024_195437_EV2-dense-only` / `20261024_195927_EV2-hybrid` / `20261024_200850_EV2-hybrid-rerank`（各含 json+md）+ `20261024_200919_compare__EV2-*` 四组横向对比。

**结论**

1. 天花板效应消除：v1 双满分 → v2 最高文档级 HitRate 0.8115，区分度恢复，可继续度量 P3/P4 增量
2. 四组单调递进且间距拉开：hybrid 相对 dense-only 的**召回增益**（文档级 HitRate 0.6923→0.7462）与精排的**排序增益**（片段级 MRR 0.4512→0.5675）在难集上首次可分离量化
3. 口径约定：EV2 为 v2 口径独立基线，与 v1 的 80 题口径不可直接混比（附录 A 已加注记）；P3/P4 后续评测以 v2 口径为准（`--dataset eval_dataset_v2.json`）

**迭代期间发现并修复的 bug**

1. （P2 遗留）`documents.py` import 遮蔽：langchain `Document` 被 SQLModel `Document` 遮蔽，`bm25_retriever.add` 构造错类型，P2 起**新上传文档的 BM25 增量索引实际失效**（评测期因 runner 每次全量构建 BM25 未暴露）→ 改别名 `LCDocument` 引入
2. （ingest 新代码）MySQL REPEATABLE READ 快照陷阱：主 session 在 `refresh(doc)` 后开启的事务快照早于 `vectorize_document`（独立 session）的提交，状态核对读到旧快照 `processing`，误报「向量化失败：None」→ 核对改用新 session
3. （ingest 新代码）md5 幂等缺口：原仅按 md5 查 id 存在性、failed 重试不清旧 chunk 行 → 改查 `(id, vectorize_status, file_path)` 并区分跳过/重试（即上文「幂等语义」）

**交付物**

- [x] `corpus_v2.py` + `tests/test_corpus_v2.py`（全量回归 381 项全绿）
- [x] `dataset.py --v2` / `runner --dataset` / `ingest.py` 三个 CLI
- [x] 65 份语料入库（全库 68 份 / 499 chunks），幂等重跑验证通过
- [x] 评测集 v2（260 题）构建 + 人工抽查通过
- [x] EV2 四组基线 + compare 归档，指标回填附录 A

---

## 5. 阶段 P1：格式感知解析与智能分块

### 5.1 各格式策略（对应需求：按格式自动选择向量化策略）

| 格式 | 解析策略 | 切分策略 | chunk 元数据 |
|---|---|---|---|
| **pdf（结构化）** | PyMuPDF `get_toc()` 提取章节树 | 按章节切分；超长章节按段落边界再分 | `section_path`（如"第三章 > 3.2 考勤"）、`page` |
| **pdf（无目录）** | 字体大小启发式识别标题层级 | 同上；识别失败兜底常规切分 | `page` |
| **docx** | python-docx 按 Heading 样式构建层级；表格序列化为文本 | 按标题层级切分 + 表格独立成块 | `section_path`、`table_index` |
| **md** | MarkdownHeaderTextSplitter（h1~h3） | 按标题切分 | `section_path` |
| **xlsx** | openpyxl 按 Sheet 读取，每行转"列名: 值"文本 | 每 N 行（默认 20）一组，**不做语义切分**；每块携带表头行上下文 | `sheet_name`、`row_range` |
| **txt** | 现有 TextLoader | RecursiveCharacterTextSplitter 参数调优（见 5.2） | `paragraph_range` |
| **doc（旧格式）** | 尝试按 docx 解析，失败则明确报错提示转换 | — | 已知限制，写入上传提示 |

> 路由入口：`chunking/strategy.py` 按扩展名分发，同步修复问题 #1（上传白名单与解析器对齐）。

### 5.2 智能切分规则（在格式结构解析之后统一应用）

1. **小章节合并**：结构单元 < `min_chunk_size`（默认 100 字）→ 与同级相邻单元合并，避免碎片
2. **超长章节再分**：结构单元 > `max_chunk_size`（默认 800 字）→ 按段落边界递归二分，不在句中截断
3. **常规单元保持原样**
4. **默认参数**：`chunk_size` 150→**500**、`chunk_overlap` 20→**50**（经 P0 评测基线验证后可调）
5. **嵌入增强**：chunk 的 `page_content = "[{section_path}]\n{正文}"`，标题上下文随正文一起嵌入（低成本提升检索质量，存储展示两不误）

### 5.3 向量化工程改造（vector_store.py）

- **确定性 chunk ID**：`uuid5(NAMESPACE, f"{document_id}:{chunk_index}")`，写入 `metadata.vector_id` 并作为 Qdrant point id（`add_documents(ids=...)`）——BM25/稠密/citations 三方对齐的基石，重复向量化幂等覆盖
- **metadata 合并修复**（问题 #3）：`doc.metadata = {**doc.metadata, "document_id": ..., "chunk_index": ..., "total_chunks": ...}`，不再覆盖
- **存量重建**：`uv run python -m app.service.rag.rebuild --all | --doc-id N`——删除旧向量 + 重跑新链路 + 重建 document_chunk 表；P1 完成后执行 `--all`

### 5.4 交付物与验收标准

- [x] 各格式样例文件上传→向量化→检索全链路成功（docx/md/xlsx 缺口修复）
- [x] chunk 元数据包含 section_path/page/sheet_name 等（抽查 Qdrant payload 验证）
- [x] 重建脚本执行后存量文档全部按新策略入库
- [x] 跑评测 `--tag P1`，HitRate/MRR 相对 P0 基线**不劣化**（结构化解析预期有提升，以报告数据为准）
- [x] 单测：各 chunker 用本地固定样例文件断言切分结构；全部离线可跑

---

## 6. 阶段 P2：混合检索 + 精排重排

### 6.1 BM25Retriever 设计

- 数据源：MySQL `document_chunk` 表（content 字段），启动时全量构建内存索引；上传向量化/删除文档事件**增量更新**；提供 `rebuild()` 全量重建
- 分词：`jieba.lcut_for_search`（搜索模式，兼顾新词发现）
- 实现：继承 `langchain_core.retrievers.BaseRetriever`，返回 Document（metadata 含 `vector_id`/`document_id`），topN 默认 20

### 6.2 RRF 融合

- 公式：`score(d) = Σ_lists 1/(rrf_k + rank_d)`，`rrf_k=60`
- 以 `vector_id` 为融合主键（依赖 P1 确定性 ID），去重合并 metadata
- 融合结果按分数排序取 TopN 送入精排

### 6.3 重排工厂（modelFactory/rerank_factory.py）

| 模式 | 实现 | 说明 |
|---|---|---|
| remote | `langchain_community.document_compressors.dashscope_rerank.DashScopeRerank(model="gte-rerank-v2")` | 阿里云商业 Cross-Encoder |
| local | sentence-transformers `BAAI/bge-reranker-v2-m3` | 可选依赖组 `local-rerank`，未安装则跳过 |

- 统一接口：`rank(query, docs) -> list[(doc, score)]`；精排后取 `top_k`（默认 5）
- **降级策略**：任何异常（网络/限额/依赖缺失）→ 记 warning 日志 + 返回 RRF 排序前 top_k，链路不中断

### 6.4 链路集成

- `HybridRetriever`（dense + bm25 → RRF）+ rerank 包装成最终 retriever，替换 `RagSummarizeService` 与 `chat.py` 中的 `get_retriever()`
- 开关可配置（见 6.5），全关闭时行为等价旧链路（保证可回退对比）

### 6.5 新增配置（config/retrieval_config.yml，参数统一收敛于此）

```yaml
hybrid:
  enabled: true
  dense_topn: 20
  bm25_topn: 20
  rrf_k: 60
rerank:
  enabled: true
  remote_model: gte-rerank-v2
  local_model: BAAI/bge-reranker-v2-m3
  top_k: 5
query_optimize:          # P3 使用，本阶段先落配置骨架
  mode: off              # off / multi_query / hyde
  multi_query_count: 3
chunking:
  chunk_size: 500
  chunk_overlap: 50
  min_chunk_size: 100
  max_chunk_size: 800
```

> `qdrant_config.yml` 保留连接类配置（host/port/collection_name/data_path/allow_knowledge_file_type），chunk/k 参数迁移至本文件（settings 路由读取来源同步调整）。

### 6.6 交付物与验收标准

- [x] BM25/RRF/重排模块单测全 mock（索引用内存数据、rerank mock 工厂）——51 passed（test_rrf 8 + test_bm25_retriever 13 + test_rerank 13 + test_hybrid 17），全量回归 368 passed
- [x] 评测四组对比：dense-only / +hybrid / +hybrid+rerank / 旧链路（开关回退）——tag 按 eval/README 命名表展开为 P2-dense-only / P2-hybrid / P2-hybrid-rerank / P2-legacy，均 80/80 完成；横向对比 `backend/eval_reports/20261023_200645_compare__P2-legacy__P2-dense-only__P2-hybrid__P2-hybrid-rerank.md`
- [x] MRR、HitRate@5 相对 P1 报告**可量化提升**（数值以报告为准）——hybrid-rerank：文档级 HitRate 0.9250→1.0000、片段级 0.9125→1.0000；MRR 0.8958/0.8396→**双满分 1.0000/1.0000**
- [x] 断网/依赖缺失场景降级可用（手动演练 + 单测覆盖）——safe_rank 降级单测覆盖；首跑期间精排曾因 langchain model 覆盖 bug 全量 403，链路全程降级不中断（修复后重跑），等价一次真实降级演练
- [x] 专有名词/缩写类问题（评测集 term 类）检索提升明显——term 类文档级 HitRate 0.9167→1.0000、文档级/片段级 MRR 均 1.0000（BM25 字面匹配补召回 + 精排置顶）

---

## 7. 阶段 P3：查询优化（multi-query + HyDE）

### 7.1 设计

| 策略 | 流程 | 细节 |
|---|---|---|
| multi_query | LLM 生成 N 个改写查询（temperature=0）→ 原查询+N 改写**并行**多路检索 → RRF 融合 | 融合复用 P2 的 rrf.py；改写失败回退原查询 |
| hyde | LLM 生成假设答案段落（temperature=0）→ 用假设文档 embedding 做稠密检索 → 与原查询检索 RRF 融合 | 假设文档仅用于检索，不进入生成上下文 |

- 模式路由：`QueryEnhancer(mode=off/multi_query/hyde)`，作为 HybridRetriever 前置包装
- 工程注意（调研结论）：HyDE 对表述类/术语类查询收益大，但对明确短查询反而增加延迟成本——**默认关闭，由评测数据决定默认值**

### 7.2 交付物与验收标准

- [x] 两种策略均可配置启用，单测 mock LLM 断言多路召回与融合正确性——`tests/test_query_enhancer.py` 16 用例全过（改写解析容错/三模式路由/多路 RRF 融合排序/build_retriever 集成），全量回归 397 passed
- [x] 评测矩阵：`off / multi_query / hyde` 三组 `--tag P3-*` 报告归档，含分问题类型（fact/term/longtail）的细分对比——三组均 260 题（v2 口径 retrieval-only，MD5 9b68db07），单组报告含 fact/longtail/paraphrase/term 细分；横向对比 `backend/eval_reports/20261025_173326_compare__P3-off__P3-multi-query__P3-hyde.md`
- [x] 根据数据确定默认 mode 并更新配置，报告中记录决策依据——**决策：mode 维持 `off`**（已回写 retrieval_config.yml 注释）。multi_query 文档级 HitRate 持平（0.8115）但片段级 -0.38pp、MRR 微降（term +1.9pp 与 paraphrase -1.7pp 相抵），每题多 1 次 LLM + 3 次 rerank 调用（评测耗时 9→35 分钟），性价比为负；hyde 全面下降（片段级 HitRate -7.69pp），longtail 类最差（0.8214→0.7143，假设文档 embedding 拉向 LLM 编造参数）
- [x] LLM 调用失败回退原查询（单测覆盖）——4 个回退用例：multi_query LLM 失败/解析为空、hyde LLM 失败/生成空文档，均断言直查内层链路且结果无 rrf_score

---

## 8. 阶段 P4：集成收尾（参数热更新 + 引用合并）

### 8.1 内容

1. **参数热更新**（技术文档"RAG 参数实时生效"落地）：settings API 扩展读写 `retrieval_config.yml` 全部参数；保存后**线程安全重建检索器/RAG 链单例**（chat.py 懒加载单例改造为注册表模式），无需重启；参数变更写审计日志
2. **引用合并**（问题 #5）：`rag_summarize` 升级返回 `(answer, retrieved_docs)`；chat.py 用同一次检索结果拼装 citations，删除 `build_citations` 二次检索；引用展示增加 `section_path`/页码信息
3. **终局报告**：`report compare P0-baseline P1 P2 P3` 生成升级前后总对比，写入本执行文档附录
4. **前端设置页「检索增强」区块**（2026-10-26 移回 P4，原附录 C 第 1 条）：在设置页 RAG 参数卡片中新增 hybrid/rerank/query_optimize 开关与 topK/topN 等参数控件，对接第 1 项产出的新 settings API，保存即触发热更新

### 8.2 交付物与验收标准

- [x] 修改 topK/开关后**不重启**即时生效（接口级验证 + 单测）
- [x] citations 与回答来自同一次检索，引用含章节路径
- [x] 总对比报告归档并附结论
- [x] 前端设置页「检索增强」区块可读写全部检索参数，保存后不重启生效

---

## 9. 开发顺序与依赖关系

```
P0 评测体系（不动现有代码，先出基线）
 └→ P1 解析分块（依赖评测验证；为 P2 提供确定性 vector_id 与元数据）
     └→ P2 混合检索+精排（依赖 P1 的 chunk 对齐与 document_chunk 数据）
         └→ P3 查询优化（复用 P2 检索与 RRF；LLM 裁决由 P0 评测）
             └→ P4 收尾（依赖前面全部模块稳定）
```

> 每阶段完成 = 功能 + 单测 + 评测报告归档 + 与上一阶段对比结论，四者齐备才进入下一阶段。

## 10. 测试计划

- 遵循项目现有测试文化（见 `tests/README.md`）：绝大多数用例全程 mock 外部依赖（MySQL/DashScope/LLM/Ollama/Qdrant），离线可跑
- 新增用例：`test_metrics.py`、`test_llm_judge.py`、`test_chunkers.py`（各格式）、`test_bm25_retriever.py`、`test_rrf.py`、`test_rerank.py`、`test_query_enhancer.py`、`test_retrieval_config.py`、`test_settings_router.py`（扩展）
- 需要 Qdrant/真实样例文件的集成用例单独标记（参考现有 test_agent_tools 模式）
- 验收时全量 `uv run pytest` 通过（外部依赖用例按现有约定处理）

## 11. 风险与对策

| 风险 | 对策 |
|---|---|
| 新旧 chunk 混存导致检索口径不一致 | P1 重建脚本全量重建 + 评测前后 collection 状态一致 |
| BM25 索引与 DB 不一致（上传/删除并发） | 事件增量更新 + 启动全量构建 + `rebuild()` 兜底；索引仅作召回源，以 DB 为准 |
| 本地重排依赖 torch 过重 | optional 依赖组，未安装自动降级；文档明确安装指引 |
| DashScope rerank 限额/网络抖动 | 降级跳过重排 + warning 日志 |
| LLM 裁判打分波动 | Prompt 固定 + temperature=0 + 报告记录模型与参数快照 |
| 查询优化增加延迟（多一次 LLM 调用） | 默认关闭；评测给出延迟-效果权衡数据后决策 |
| chunk 参数调整影响可比性 | 评测报告头部记录配置快照，对比只在同口径下进行 |

## 12. 里程碑检查总表

| 阶段 | 核心产出 | 评测报告 tag | 完成判定 |
|---|---|---|---|
| P0 | 评测体系 + 基线 | `P0-baseline` | 基线归档，评测集≥50条 |
| P1 | 格式感知解析分块 + 重建 | `P1` | 全格式可用，指标不劣化 |
| P2 | 混合检索 + 精排 | `P2`(多组) | 检索指标可量化提升 |
| P3 | 查询优化可配置 | `P3-*`(三组) | A/B 数据定默认值 |
| P4 | 热更新 + 引用合并 | 总对比 | 不重启生效，总报告归档 |
| 评测集迭代 | 语料库扩容 65 份 + 评测集 v2（260 题）+ 批量入库 CLI + EV2 四组基线 | `EV2-*`(四组) | 天花板效应消除，四组单调递进（v2 口径） |

---

## 附录 A：升级前后预期对比维度（以最终评测报告数据填充）

> P0 基线实测于 2026-10-19（Top-K=3，当前链路默认配置），数据来源：`backend/eval_reports/20261019_015104_P0-baseline.md`（full 全量版；`20261019_010016` retrieval 版数值一致，两次运行互相验证）。
> 基线期仅「员工手册.txt」成功入库（16/80 题有命中机会），文档级指标天花板即 0.20——格式缺口是主要瓶颈，也是 P1 的直接提升空间。
> P1 实测于 2026-10-20（Top-K=3，chunk 500/50），数据来源：`backend/eval_reports/20261020_234801_P1.md`（full 全量版，评测集 MD5 与 P0 一致）；横向对比：`backend/eval_reports/20261020_234830_compare__P0-baseline__P1.md`。

| 指标 | P0 基线 | P1 | P2 | P3（最优配置） |
|---|---|---|---|---|
| HitRate@3（文档级 / 片段级） | **0.2000 / 0.2000** | **0.9250 / 0.9125** | **1.0000 / 1.0000**（@5） | —（v2 口径） |
| MRR（文档级 / 片段级） | **0.2000 / 0.1812** | **0.8958 / 0.8396** | **1.0000 / 1.0000**（双满分） | —（v2 口径） |
| Precision@3（文档级 / 片段级） | **0.2000 / 0.0667** | **0.7792 / 0.3042** | 0.6050 / 0.2000（@5） | —（v2 口径） |
| 内容召回率（重叠率均值） | **0.2000** | **0.9114** | **0.9975** | —（v2 口径） |
| Faithfulness | **1.0000**（80/80 裁判成功，零幻觉） | **1.0000**（80/80，保持零幻觉） | **1.0000**（80/80，保持零幻觉） | —（v2 口径） |
| AnswerRelevancy | **0.2925**（16 命中题全部 1.0；7 题未命中因拒答话题相关得 1.0，q014 得 0.4） | **0.9338**（真实答对率大幅回升） | **0.9875** | —（v2 口径） |

> txt 内部真实检索质量（16 题子集）：文档级 HitRate/MRR 1.0000、片段级 MRR 0.9062、片段级 Precision 0.3333（chunk 粒度粗，P2/P3 优化点）、term 类最弱（0.1667）。
> P1 解读：格式补齐后 term 类文档级 HitRate 0.1667→0.9167（嵌入增强 `[section_path]` 前缀生效）；按文件 pdf/xlsx 1.0000、docx 0.9375、txt 0.8750、md 0.8125（txt/md 遗留少量失配）；片段级 Precision@3 仅 0.3042——top-3 中混入其他文档 chunk，为 P2 混合检索+精排的量化空间。
> P2 实测于 2026-10-23，取最优配置 hybrid-rerank（dense 20 + bm25 20 → RRF topn=20 → gte-rerank-v2 精排 top 5），P2 列为 **@5 口径**（P2 起生效 top_k=5）；数据来源：`backend/eval_reports/20261023_194144_P2-hybrid-rerank.md`，四组横向对比：`backend/eval_reports/20261023_200645_compare__P2-legacy__P2-dense-only__P2-hybrid__P2-hybrid-rerank.md`。
> P2 解读：BM25 补召回使 dense-only 遗留 miss 全部补齐（HitRate 双满分）；精排将正确片段全部置顶（MRR 双满分）；Precision@5 低于 P1 的 @3 属口径效应（k 分母变大 + 精排聚焦 top1），P2 主指标为 HitRate/MRR；legacy 回退组（K=3）总体指标与 P1 逐项一致，验证开关回退等价。
> 后续各阶段完成重跑评测后回填本表，并用 `report compare` 生成横向对比报告归档。

> **评测集 v2（EV2）口径注记（2026-10-24）**：P2 在上表 v1 口径（80 题 / 5 文档库）双满分出现天花板效应后，执行评测集迭代（详见 4.6 节）：语料库扩至 65 份（corpus_v2 新增 60 份，10 主题 × 6 实体、跨实体近似干扰），评测集 v2 共 260 题（fact 118 / paraphrase 60 / term 54 / longtail 28，新增 paraphrase 题型）。EV2 为 **v2 口径独立基线**，与上表 v1 口径不可直接混比；P3/P4 起以 v2 口径为准（指标回填下表而非 v1 主表）。
> 数据来源：`backend/eval_reports/20261024_200919_compare__EV2-legacy__EV2-dense-only__EV2-hybrid__EV2-hybrid-rerank.md`（实测 2026-10-24，260 题，retrieval-only，评测集 MD5 `9b68db07…`）。

| 指标（v2 口径，260 题） | EV2-legacy(k=3) | EV2-dense-only(k=5) | EV2-hybrid | EV2-hybrid-rerank | P3（v2 口径） | P4（v2 口径） |
|---|---|---|---|---|---|---|
| HitRate@K（文档级 / 片段级） | 0.6000 / 0.4615 | 0.6923 / 0.5115 | 0.7462 / 0.6231 | **0.8115 / 0.7846** | **0.8115 / 0.7846**（mode=off） | **0.8115 / 0.7846**（≡P3-off） |
| MRR（文档级 / 片段级） | 0.4949 / 0.3551 | 0.5152 / 0.3662 | 0.5389 / 0.4512 | **0.5873 / 0.5675** | **0.5813 / 0.5615**（mode=off） | **0.5813 / 0.5615**（≡P3-off） |
| 内容召回率 | 0.4847 | 0.5441 | 0.6441 | **0.7881** | **0.7881**（mode=off） | **0.7881**（≡P3-off） |

> EV2 解读：65 份近似语料 + paraphrase 改写 + longtail 细节题显著抬高任务难度，四组单调递进且间距拉开；hybrid 的召回增益与精排的排序增益在难集上首次可分离量化。生成指标（Faithfulness / AnswerRelevancy）EV2 未跑（retrieval-only），P3/P4 视需要补全量。
> P3 实测于 2026-10-25（260 题 retrieval-only，v2 口径）：三组 A/B 同底座（hybrid + rerank，等价 EV2-hybrid-rerank），仅变 `query_optimize.mode`（runner `--preset off/multi-query/hyde`）；数据来源：`backend/eval_reports/20261025_173326_compare__P3-off__P3-multi-query__P3-hyde.md`。**决策：mode 维持 `off`**——multi_query 文档级持平（0.8115）但片段级/MRR 微降且每题多 4 次外部调用；hyde 全面下降（片段级 HitRate -7.69pp，longtail 文档级 0.8214→0.7143，假设文档 embedding 拉向 LLM 编造参数）。P3 列取 P3-off 值：HitRate/召回率与 EV2-hybrid-rerank 完全一致，MRR 微差（0.5813 vs 0.5873）属嵌入/精排 API 非确定性；multi-query/hyde 数值不入表（决策为不启用）。
> **P3b 补测注记（2026-10-26，fuse_then_rerank 变体验证）**：针对「P3 multi_query 下降是否因链路顺序（每路各自精排→末端 RRF 融合稀释排序）」的疑问，实现 `fuse_then_rerank` 变体（每路仅混合检索→全路 RRF 融合 topn=20→**原查询统一精排** top 5，即 `RerankRetriever(QueryEnhancer(HybridRetriever))` 包装序反转），同日重跑三组对照（P3b-off / P3b-multi-query / P3b-multi-query-fuse，260 题 retrieval-only，v2 口径，改写模型 deepseek-flash）；数据来源：`backend/eval_reports/20261026_144722_compare__P3-off__P3-multi-query__P3b-off__P3b-multi-query__P3b-multi-query-fuse.md`。**结论：链路顺序非主因，fuse 变体无净收益**——doc HitRate 0.8115（=off，比每路精排的 0.8192 少 2 题）、doc MRR 0.5806 微降、唯一微升项 doc Precision@5 0.3138（+0.46pp），全部差异折合 1~2 题属噪声区间；P3b-off 与 P3-off 逐项一致（0.8115/0.7846/0.5813/0.5615/0.7881），验证跨日口径稳定。**决策：`fuse_then_rerank` 维持 `false`**（实现与 `multi-query-fuse` preset 保留为可选变体，默认 mode=off 不变；单测补充后全量回归 417 passed）。
> **P4 实测注记（2026-10-26，热更新收尾验证）**：P4 未改动检索/分块链路（仅工程收尾：参数热更新、引用合并、注册表单例、前端设置区块），评测目的为验证「改造零回归 + 热更新前后同口径等价」。本次不使用 `--preset`，直接以 `retrieval_config.yml` 文件配置组链（即热更新重建所用的同一配置源），260 题 retrieval-only，v2 口径；数据来源：`backend/eval_reports/20261026_183124_P4.md`、v2 总对比 `backend/eval_reports/20261026_183236_compare__EV2-legacy__EV2-dense-only__EV2-hybrid__EV2-hybrid-rerank__P3-off__P4.md`、v1 终局总对比 `backend/eval_reports/20261026_183233_compare__P0-baseline__P1__P2-legacy__P2-dense-only__P2-hybrid__P2-hybrid-rerank.md`（§8.1 第 3 项终局报告）。**结论：与 P3-off 七项检索指标逐项一致**（含 Precision 0.3092/0.1623）——文件配置直组链路 ≡ preset 口径链路，热更新重建路径行为等价；接口级验证另证：PUT `hybrid.bm25Topn` 20→15→20 全程不重启即时生效（GET 即时反映、响应「保存成功，检索链路已重建即时生效」、审计日志 `[热更新]用户更新 RAG 参数` + `[热更新]RAG 链路已按新配置重建生效`）。报告头聊天模型字段为 deepseek-flash（retrieval-only 不调用，无影响）。

## 附录 B：确认决议（2026-10-18）

原"待确认事项"3 条已全部确认，决议如下，全文正文已按决议更新：

| # | 原待确认事项 | 决议 | 落实位置 |
|---|---|---|---|
| 1 | 评测集补充样例文档（pdf/docx/xlsx/md）来源？ | **全部开发自造**。现有"员工手册 txt"亦为自造样例，可直接删除或修改，无需真实企业数据 | 4.2 节；样例存 `backend/app/service/eval/datasets/samples/` |
| 2 | P4 前端"检索增强"设置区块是否本轮必做？ | 原决议（2026-10-18）**本轮不做**；**2026-10-26 移回 P4 实施**（§8.1 第 4 项） | §8.1 第 4 项、§8.2 |
| 3 | 评测集生成 tokens 走 DashScope 现有 key？ | **接受（默认方案）**。生成+校验约 80 条 QA 的 tokens 消耗走现有 key | 4.2 节 |
| 4 | （新增）评测集存放位置 | 不放 `backend/app/data`（避免与企业文档混合），统一存 `backend/app/service/eval/datasets/`，评测集为 `eval_dataset.json` | 4.2 节；3.1 目录结构 |

## 附录 C：后续待办（本轮不做）

以下事项经讨论确认**本轮不实施**，留待后续迭代，不阻塞本轮任何阶段验收：

1. **《技术文档.md》"项目期望"中未纳入本轮范围的方向**（详见 docs/技术文档.md）：
   - 评估类：更多评测维度（如上下文利用率、噪声鲁棒性）、评测报告前端可视化看板
   - 检索类：多租户/按文档权限过滤检索、父子块（parent-child chunk）检索、图 RAG
   - 工程类：模型服务降级熔断、批量导入性能优化、增量重建索引任务化
   - 其他：短信/邮件通知渠道、Agent 工具链扩展
2. **本地重排模型（bge-reranker-v2-m3）的镜像预热**：本轮仅实现代码通道与可选依赖组 `local-rerank`，首次拉取模型权重较大，是否预置到部署镜像待定。

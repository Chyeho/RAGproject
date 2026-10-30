# 宸甄 PrivRAG 企业私有知识库问答系统

## 第一章 项目介绍

企业在日常运营中沉淀了大量非结构化内部文档（制度规范、产品手册、培训资料等），传统文件管理与关键词检索方式查阅效率低下；同时通用大模型无法加载企业私有数据，回答易产生幻觉，而直接调用公有大模型接口又存在数据泄密隐患。

**宸甄 PrivRAG** 是一套面向企业的私有化知识库问答系统。基于 RAG（检索增强生成）技术，将企业私有文档向量化后存入本地向量数据库，问答时先从私有知识库中语义检索相关片段，再交由大模型生成回答，从而实现：

- **私有数据安全**：文档与向量库均部署在企业内网，数据不出域；
- **回答精准可溯源**：基于检索到的文档片段作答，减少幻觉，并提供引用来源；
- **双模型模式**：支持远程 API（通义/DeepSeek 等）与本地 Ollama 模型一键切换，兼顾性能与数据合规；
- **完整业务闭环**：涵盖用户认证、文档管理、知识入库、多轮问答、会话管理、统计分析、系统设置等全功能。

系统采用前后端分离架构，前端基于 Vue 3 + Element Plus，后端基于 FastAPI + LangChain，数据层使用 MySQL（关系型）与 Qdrant（向量库），并提供 Docker 容器化一键部署能力。

## 第二章 技术架构

### 2.1 项目技术栈

- **前端框架**：Vue 3 + Vite + Element Plus + ECharts + Vue Router + Axios
- **后端框架**：FastAPI（含认证/会话/文档/统计/设置全部业务接口）
- **关系型数据库**：MySQL 8.4（SQLModel + aiomysql 异步）
- **向量数据库**：Qdrant v1.16
- **本地大模型服务**：Ollama（本地模式下运行聊天与嵌入模型，支持自动拉取）
- **ORM**：SQLModel + SQLAlchemy（异步）
- **AI问答服务框架**：LangChain
- **测试框架**：pytest + anyio（532 个单元测试，详见 `tests/README.md`）

### 2.2 项目结构

```plaintext
RAGproject_demo/
├── docker/                              # 部署配置（nginx / 环境变量 / 中间件）
│   ├── env/
│   │   ├── .env.dev                     # 开发环境变量
│   │   ├── .env.prod                    # 生产环境变量
│   │   └── *.example                    # 变量模板（仓库内置，供复制使用）
│   ├── middleware/
│   │   ├── my.cnf                       # MySQL 自定义配置
│   │   └── qdrant_config.yaml           # Qdrant 向量库配置
│   └── nginx/
│       ├── conf.d/
│       │   └── default.conf             # Nginx 虚拟主机 & 反向代理规则
│       └── nginx.conf                   # Nginx 主配置
├── backend/                             # 后端（FastAPI + LangChain）
│   ├── Dockerfile                       # 后端容器构建文件
│   ├── app/
│   │   ├── config/                      # 业务配置文件目录
│   │   │   ├── agent_config.yml         # Agent 配置
│   │   │   ├── cache_config.yml         # 缓存配置
│   │   │   ├── prompts_config.yml       # 提示词配置
│   │   │   ├── qdrant_config.yml        # Qdrant 连接与集合配置
│   │   │   ├── rag_config.yml           # 模型配置（聊天 / 嵌入，remote / local 分组）
│   │   │   └── retrieval_config.yml     # 检索链路配置（分块 / hybrid / rerank / 查询优化）
│   │   ├── core/                        # 核心模块
│   │   │   ├── permissions.py           # 权限矩阵（角色/等级 → 权限，唯一判定源）
│   │   │   ├── response.py              # 统一响应 {code, message, data}
│   │   │   └── security.py              # 密码哈希 / JWT 签发与校验 / 随机密码生成
│   │   ├── data/                        # 上传文件落盘目录（文件名前缀时间戳）
│   │   ├── database/                    # 数据库连接层
│   │   │   └── db.py                    # 环境变量连接 / get_session / init_db 建表
│   │   ├── dependencies.py              # 全局依赖（get_current_user / require_permission）
│   │   ├── logs/                        # 运行日志
│   │   ├── modelFactory/                # 模型工厂（本地 / 远程双模式）
│   │   │   ├── factory.py               # 聊天 / 嵌入模型实例化
│   │   │   └── rerank_factory.py        # 精排模型实例化（远端 / 本地，含降级）
│   │   ├── models/                      # SQLModel 数据模型（6 张表）
│   │   │   ├── __init__.py
│   │   │   ├── audit_log.py             # 账号管理操作审计表
│   │   │   ├── chat_conversation.py     # 会话表
│   │   │   ├── chat_message.py          # 消息表（含 citations）
│   │   │   ├── document_chunk.py        # 文档分块表（含章节 / 页码元数据）
│   │   │   ├── documents.py             # 文档表（含 md5 去重）
│   │   │   └── users.py                 # 用户表
│   │   ├── prompts/                     # 提示词模板
│   │   │   ├── rag_summarize.txt        # RAG 总结提示词
│   │   │   ├── system_prompt.txt
│   │   │   ├── multi_query.txt          # 多查询改写（可选链路）
│   │   │   ├── hyde.txt                 # HyDE 假设文档（可选链路）
│   │   │   ├── faithfulness_judge.txt   # 评测：忠实度裁判
│   │   │   └── relevancy_judge.txt      # 评测：相关性裁判
│   │   ├── routers/                     # FastAPI 路由层
│   │   │   ├── admin.py                 # 账号管理（列表/新建/改等级状态/重置密码/软删除，仅管理员）
│   │   │   ├── auth.py                  # 认证（登录/退出/当前用户/改密）
│   │   │   ├── chat.py                  # 会话 CRUD + 问答 + 引用来源
│   │   │   ├── documents.py             # 文档上传/列表/预览/下载/删除
│   │   │   ├── settings.py              # RAG 全参数读写与热更新
│   │   │   └── statistics.py            # 统计数据查询
│   │   ├── service/                     # 业务服务层
│   │   │   ├── account_service.py       # 账号服务（管理员初始化/建号/重置密码/审计）
│   │   │   ├── agent/                   # Agent 服务
│   │   │   │   ├── react_agent.py
│   │   │   │   └── tools/               # Agent 工具与中间件
│   │   │   ├── eval/                    # RAG 评测框架
│   │   │   │   ├── runner.py            # 检索评测运行器（链路组合 / preset）
│   │   │   │   ├── metrics.py           # HitRate / 召回率等指标
│   │   │   │   ├── llm_judge.py         # LLM 裁判
│   │   │   │   ├── dataset.py           # 评测集加载
│   │   │   │   ├── corpus_v2.py         # v2 语料与评测集生成
│   │   │   │   ├── ingest.py            # 评测语料入库
│   │   │   │   ├── report.py            # 报告输出与对比
│   │   │   │   ├── make_samples.py      # 样例文档生成
│   │   │   │   ├── datasets/            # 评测集（v1 80 题 / v2 260 题）与语料
│   │   │   │   └── README.md            # 评测框架使用说明
│   │   │   ├── history/                 # 对话历史管理（按会话隔离）
│   │   │   │   └── history_store.py
│   │   │   └── rag/                     # RAG 问答核心
│   │   │       ├── chunking/            # 格式感知分块（pdf/docx/md/xlsx/txt）
│   │   │       │   ├── strategy.py      # 分块策略入口（按格式分发）
│   │   │       │   ├── pdf_chunker.py
│   │   │       │   ├── docx_chunker.py
│   │   │       │   ├── markdown_chunker.py
│   │   │       │   ├── excel_chunker.py
│   │   │       │   └── text_chunker.py
│   │   │       ├── retrieval/           # 检索层
│   │   │       │   ├── bm25_retriever.py    # BM25 稀疏检索
│   │   │       │   ├── rrf.py               # RRF 融合
│   │   │       │   └── hybrid_retriever.py  # 混合检索链路工厂
│   │   │       ├── query/              # 查询优化（可选，默认关闭）
│   │   │       │   ├── enhancer.py      # 查询增强总入口
│   │   │       │   ├── multi_query.py   # 多查询改写
│   │   │       │   └── hyde.py          # HyDE
│   │   │       ├── rag_service.py       # RAG 总结服务（检索与生成分离）
│   │   │       ├── registry.py          # RAG 单例注册表（线程安全 + 热更新重建）
│   │   │       ├── rebuild.py           # 存量文档向量重建脚本
│   │   │       └── vector_store.py      # Qdrant 向量库服务
│   │   ├── utils/                       # 工具模块
│   │   │   ├── config_handler.py        # 配置加载器
│   │   │   ├── env_loader.py            # docker/env 环境变量白名单加载
│   │   │   ├── file_handler.py          # 文件 MD5 / 文档读取
│   │   │   ├── logger_handler.py        # 日志配置
│   │   │   ├── path_tool.py             # 路径工具（绝对路径计算）
│   │   │   └── prompt_loader.py         # 提示词模板加载
│   │   └── main.py                      # FastAPI 应用入口（lifespan 建表 + 路由注册）
│   ├── chat_history/                    # 用户对话历史持久化（按会话独立文件）
│   ├── eval_reports/                    # 评测运行输出（JSON / 报告）
│   ├── pyproject.toml                   # 项目依赖配置
│   └── uv.lock
├── frontend/                            # 前端（Vue 3 + Element Plus + ECharts）
│   ├── Dockerfile                       # 前端容器构建文件
│   └── src/
│       ├── api/                         # 接口层（axios 请求）
│       ├── assets/
│       │   ├── images/                  # Logo 等静态资源
│       │   └── styles/                  # 全局样式（蓝紫渐变设计变量）
│       ├── layout/                      # 主框架布局（顶部导航 + 侧边菜单 + 内容区）
│       ├── router/                      # 路由配置 + 登录守卫
│       ├── utils/                       # 工具模块（登录态 / 格式化）
│       └── views/                       # 页面视图
│           ├── admin/                   # 账号管理页（仅管理员）
│           ├── chat/                    # Bot 问答页（会话管理 + 引用溯源）
│           ├── knowledge/               # 知识库页（文档表格 + 上传/预览/删除）
│           ├── statistics/              # 统计数据页（ECharts 图表）
│           ├── settings/                # 系统设置页（账号信息 + 修改密码 + RAG 参数）
│           └── LoginRegister.vue        # 登录页（不提供自助注册）
├── scripts/                             # 启动脚本
│   ├── start-backend.ps1                # Windows 后端一键启动脚本
│   └── start-backend.sh                 # Linux 后端一键启动脚本
├── tests/                               # 单元测试（532 个，运行方式见 tests/README.md）
├── docker-compose.yml                   # Docker Compose 编排文件
├── .dockerignore                        # Docker 构建忽略规则
├── .gitattributes
├── .gitignore
├── docs/                                # 项目开发文档目录
│   ├── 技术文档.md                       # 项目阶段、期望与部署设计说明
│   ├── 接口JSON契约文档.md                # 前后端接口契约（联调依据）
│   ├── 账号管理说明文档.md                 # 角色/等级权限、管理员初始化、账号运维
│   ├── 常见报错问题解决方案速查.md         # 高频报错与排查速查
│   ├── development_docs/                # 各阶段开发执行文档
│   │   ├── 前后端开发执行文档.md
│   │   ├── 模型加载双模式改造执行文档.md
│   │   └── RAG链路升级执行文档.md
│   └── rag_eval_reports/                # RAG 评测实验报告归档
│       ├── RAG评测实验总结报告.md
│       └── RAG评测实验时间线.md
└── README.md
```

### 2.3 Docker 架构概览

```
互联网用户 → Nginx(:18080) → Frontend Vue(:13000)  静态页面
                          → Backend API(:18000)  数据处理
                                   ↓
                          MySQL(:16666→3306)   关系型数据库
                          Qdrant(:16333→6333)  向量数据库
                          Ollama(:21434→11434) 本地模型服务（MODEL_MODE=local 时使用）
```

> 用高位端口是为了预防端口占用问题，详见文档 [`docs/常见报错问题解决方案速查.md`](docs/常见报错问题解决方案速查.md)。容器内部端口保持不变，仅宿主机映射/本地启动端口改为高位；完整清单见 3.4.4 节。

### 2.4 RAG 检索链路架构

系统经过 P0→P4 五个阶段升级，当前生产链路为「双路召回 → RRF 融合 → 精排截断」，最终只把 **5 个**最相关片段送入大模型生成回答：

```
用户提问
   │
   ▼
[查询优化]  mode=off（multi_query / HyDE 为可选实验开关）
   │
   ├──────────────────┐
   ▼                  ▼
[稠密召回]          [稀疏召回]
Qdrant 向量检索      BM25 倒排索引
dense_topn=20       bm25_topn=20
   └────────┬─────────┘
            ▼
[RRF 融合]  rrf_k=60，两路按排名融合，保留 topn=20
            ▼
[精排]      gte-rerank-v2 逐条打分，取 top_k=5（异常自动降级）
            ▼
[生成]      5 个片段拼入提示词 → 大模型回答 + 引用溯源
```

| 环节 | 关键参数 | 说明 |
|---|---|---|
| 格式感知分块 | `chunk_size=500` / `chunk_overlap=50` | pdf/docx/md/xlsx/txt 分别用专用分块器，保留章节路径与页码 |
| 稠密召回 | `hybrid.dense_topn=20` | Qdrant 语义向量检索 |
| 稀疏召回 | `hybrid.bm25_topn=20` | BM25 关键词检索，文档入库时增量维护索引 |
| RRF 融合 | `hybrid.rrf_k=60` / `hybrid.topn=20` | 两路排名融合去重，作为精排候选 |
| 精排 | `rerank.remote_model=gte-rerank-v2` / `rerank.top_k=5` | 精排不可用时自动降级，链路不中断 |
| 查询优化 | `query_optimize.mode=off` | multi_query / HyDE 已实现，实测无净收益故默认关闭 |

**四组合链路语义**（可在设置页或 `retrieval_config.yml` 切换）：

| 混合检索 | 精排 | 链路行为 | 最终条数 |
|---|---|---|---|
| 关 | 关 | 纯稠密检索（等价升级前旧链路） | `legacy_k=3` |
| 开 | 关 | dense + bm25 → RRF | `hybrid.topn` |
| 关 | 开 | dense 候选 → 精排 | `rerank.top_k` |
| 开 | 开（**当前默认**） | dense + bm25 → RRF(20) → 精排 | `rerank.top_k=5` |

**评测结论**（retrieval-only，v2 评测集 260 题）：

- v1 集（80 题）：P0 基线因仅 txt 入库、文档级 HitRate 仅 0.2000，逐步升级至 P1 的 0.9250、P2 hybrid+rerank 的 **1.0000**；
- v2 集（68 份高度近似制度文档、260 题）文档级 HitRate **0.8115**、片段级 HitRate **0.7846**、内容召回率 **0.7881**，全程零幻觉；
- multi-query、HyDE 等查询优化在该语料下无净收益，故默认关闭，仅作可选实验变体保留。

> 检索参数支持**热更新**：设置页保存后写入 `retrieval_config.yml`、同步内存配置并重建检索单例，无需重启服务；分块参数在下次上传向量化时生效。

#### 2.4.1 RAG+ReAct 混合架构

在上述检索链路之上增加一层**窄规则路由**：绝大多数问题仍走 RAG 直调（行为与改造前一致），只有命中"多实体对比 / 多步计算"等明确规则的问题才进入 ReAct 复杂通道，失败自动降级回直调。

```
用户提问
   │
   ▼
[规则路由]  config/router_rules.yml（强规则直接命中；弱规则累计 ≥ 阈值 2）
   │
   ├── rag_direct（默认，占绝大多数）──→ [RAG 直调] 见 2.4 检索链路
   │
   └── react_complex（多实体/多步骤/对比计算）
             ▼
       [ReAct Agent] 最多 3 轮工具调用 + 1 次收尾总结（总超时 30s，单工具 10s）
             工具：rag_search（检索 + 片段摘要）
                   compare_calc（compare / diff / sum / condition_check）
             ▼
       成功 → 回答 + 引用来源；失败/超时 → 自动降级 RAG 直调（用户无感）
```

| 配置项（`backend/app/config/hybrid_config.yml`） | 默认值 | 说明 |
|---|---|---|
| `ENABLE_HYBRID_ROUTER` | `true` | 总开关；置 `false` 时全部走 RAG 直调，行为与改造前一致 |
| `REACT_MAX_STEPS` | `3` | ReAct 最大工具轮次（用尽后追加一次纯总结，仍不产生新工具调用） |
| `REACT_TIMEOUT_MS` / `TOOL_TIMEOUT_MS` | `30000` / `10000` | ReAct 总超时 / 单次工具超时 |
| `ENABLE_REACT_FALLBACK` | `true` | ReAct 失败时是否降级回 RAG 直调 |
| `ROUTER_RULES_PATH` | `config/router_rules.yml` | 路由规则文件（强/弱规则、权重、阈值） |
| `LOG_TRACE_LEVEL` | `summary` | trace 级别：`off` / `summary` / `full`（full 含每轮 thought/action/observation） |
| `ENABLE_TRACE_API` | `false` | 是否开放 `/api/debug/trace` 调试查询接口 |

> **一键关闭**：设置环境变量 `ENABLE_HYBRID_ROUTER=false`（优先级高于 YAML）或直接改 YAML，即可完全回到纯 RAG 直调，无需改代码。

## 第三章 安装运行指南

本章介绍如何在本地快速把项目跑起来。根据使用场景选择以下两种启动方式之一。

### 3.1 环境准备

#### 3.1.1 依赖版本说明

| 依赖 | 版本要求 | 说明 |
|---|---|---|
| Docker Desktop | ≥ 4.x（Windows 需启用 WSL2 后端） | 提供 MySQL / Qdrant / 完整容器化部署的运行环境；镜像源可配置加速 |
| Python | ≥ 3.10（推荐 3.12+） | 方式二本地运行后端所需；项目已提供 `pyproject.toml` / `uv.lock` |
| uv | 最新版（推荐安装） | **推荐的 Python 包管理器**：统一管理虚拟环境与依赖，支持 `uv sync` / `uv run`；安装见 [uv 官方文档](https://docs.astral.sh/uv/) |
| Node.js | ≥ 18 | 方式二本地运行前端所需 |
| Git | 任意 | 拉取/管理项目代码 |

> Windows 提示：执行下述命令前，请确认 **Docker Desktop 已启动**（任务栏图标处于运行状态），否则 `docker compose` 会报连接错误。

#### 3.1.2 环境变量文件配置

环境变量统一放在 `docker/env/` 目录，仓库已提供模板文件，复制一份即可：

```bash
cp docker/env/.env.dev.example docker/env/.env.dev    # 开发环境（快速启动用它）
cp docker/env/.env.prod.example docker/env/.env.prod  # 生产环境（可选）
```

复制后只需填写以下 **6 个必填项**即可启动，其余变量均有默认值，无需改动：

| 必填项 | 说明 |
|--------|------|
| `OPENAI_CHAT_MODEL` | 业务聊天模型名，随所选供应商填写（如 `deepseek-flash`、`qwen-plus`） |
| `OPENAI_API_KEY` | 业务聊天模型的 API Key |
| `OPENAI_BASE_URL` | 业务聊天模型端点（如 `https://api.deepseek.com/v1`） |
| `DASHSCOPE_API_KEY` | DashScope API Key：嵌入 / 精排 / 评测模型共用 |
| `ADMIN1_USERNAME` | 内置管理员登录账号（首次启动时自动创建，建议改掉默认值） |
| `ADMIN1_PASSWORD` | 内置管理员初始密码（≥12 位，首次启动时写入；账号已存在则不会覆盖） |

> 嵌入、精排、评测等其他远程模型默认走 DashScope，配好 `DASHSCOPE_API_KEY` 即可，无需额外配置。生产环境还需将 `.env.prod` 中 `<strong_production_password>` 等 MySQL 密码占位符替换为强密码（开发模板已内置默认密码）。各变量完整说明见 3.4 节。

> **账号说明**：系统不提供自助注册。内置管理员由服务启动时按 `ADMIN1_*`~`ADMIN3_*` 自动初始化；普通账号由管理员登录后在「账号管理」页创建（账号名 `czzsk` + 6 位补零 ID，初始密码仅显示一次）。详见 [`docs/账号管理说明文档.md`](docs/账号管理说明文档.md)。

### 3.2 启动方式一：Docker 一键容器化部署（便捷，但较慢）

**前置准备**：仅需 Docker Desktop；无需本地安装 Python / Node.js。

```bash
# 1. 首次使用：从模板复制环境变量文件并编辑
cp docker/env/.env.dev.example docker/env/.env.dev
#    只需填写 3.1.2 所列 6 个必填项（聊天模型三件套 + DASHSCOPE_API_KEY + 管理员账号密码）

# 2. 构建并一键启动全部服务（mysql / qdrant / backend / frontend / nginx / ollama）
docker compose --env-file docker/env/.env.dev up -d --build

# 3. 查看运行状态与日志
docker compose ps                 # 5 个服务均应为 Up (healthy)[本地模式为6个服务]
docker compose logs -f backend    # 查看后端日志（Ctrl+C 退出）

# 4. 访问应用
#    Nginx 入口：http://localhost:18080
#    后端 API：  http://localhost:18000/docs
#    前端页面：  http://localhost:13000

# 日常停止（仅删除容器，数据卷保留，数据不丢失）
docker compose --env-file docker/env/.env.dev down

# 再次启动（已构建且代码无修改：不加 --build，直接复用镜像，秒级启动）
docker compose --env-file docker/env/.env.dev up -d

# 重新构建启动（代码有修改：必须加 --build，否则改动不会生效）
docker compose --env-file docker/env/.env.dev up -d --build
```

> ⚠️ **注意**：每一条 `docker compose` 命令（包括 `down`）都必须带 `--env-file` 参数。本项目环境变量位于 `docker/env/` 而非项目根目录，Compose 不会自动加载；漏掉该参数会导致数据库密码、库名等被置空，后端连不上 MySQL 而启动失败（容器显示 unhealthy）。若启动时终端出现 `WARN: The "XXX" variable is not set` 提示，即说明漏带了该参数。

**说明**：一条命令拉起全部服务，环境一致、无需本地装依赖，适合演示与部署；但**首次启动较慢**——需拉取 MySQL/Qdrant/Nginx 基础镜像并构建前后端镜像（安装 Python / Node 依赖），且代码修改后需重新构建镜像才能生效。

### 3.3 启动方式二：仅基础设施 + 本地启动前后端（推荐开发调试）

**前置准备**：Docker Desktop + Python（可选 uv）+ Node.js。

```bash
# 1. 仅启动基础设施（MySQL + Qdrant + Ollama）
# 1.1 remote 模式
docker compose --env-file docker/env/.env.dev up -d mysql qdrant
# 1.2 local 模式
docker compose --env-file docker/env/.env.dev up -d mysql qdrant ollama
# 1.3 查看运行状态与日志
docker compose ps    # 预期：mysql 和 qdrant 状态为 Up (healthy)

# 2. 本地启动后端服务（新终端窗口，在项目根目录执行）
# 直接运行一键启动脚本，脚本会自动读取 docker/env/.env.dev 并做本地连接覆盖
# （MySQL/Qdrant 主机名改为 127.0.0.1，端口改用宿主机映射端口 MYSQL_HOST_PORT / QDRANT_HOST_PORT）
# 注意：脚本路径是相对于项目根目录的；若当前在 backend 目录，改用 ..\scripts\start-backend.ps1

# Windows PowerShell:
.\scripts\start-backend.ps1

# Linux / macOS / Git Bash:
chmod +x scripts/start-backend.sh   # 首次需加执行权限
./scripts/start-backend.sh

# 如需指定其他 env 文件（如生产环境）：
#   .\scripts\start-backend.ps1 docker/env/.env.prod
#   ./scripts/start-backend.sh docker/env/.env.prod

# 启动时自动建表（幂等）；访问 http://localhost:18000/docs 查看全部接口

# 3. 本地启动前端服务（新终端窗口）
cd frontend
npm install  # 首次运行
npm run dev
# 访问 http://localhost:13000 查看前端页面（已对接后端真实接口）
# 测试账号：使用 docker/env/.env.dev 中的 ADMIN1_USERNAME / ADMIN1_PASSWORD 登录；
# 普通账号由管理员在「账号管理」页创建（无自助注册）

# 4. 停止基础设施
docker compose down
```

**说明**：仅运行 MySQL/Qdrant 两个容器（local模式为加上ollama的共计三个容器），资源占用少、启动快；前后端在本机运行，支持热重载与 IDE 断点调试，代码修改即时生效，适合开发阶段；代价是需要本机安装 Python / Node.js 依赖。

### 3.4 模型配置与环境变量说明

  快速上手只需配置 3.1.2 中的 6 个必填项，本节为完整参考。变量按用途分为两类：**可自主配置的模型项**（模型名 / API Key / base_url，可按需替换供应商）与**保留在原位置的编排项**（Docker 容器编排注入信息、模型加载模式等，一般无需改动）。

#### 3.4.1 模型加载模式说明

通过环境变量 **`MODEL_MODE`** 一键切换，无需改代码：

| 模式 | 聊天模型（LLM） | 嵌入模型（Embed） | 适用场景 |
|------|----------------|-------------------|----------|
| `remote`（默认） | `langchain_openai.ChatOpenAI`，兼容任意 OpenAI 协议模型（通义/DeepSeek/月之暗面等） | DashScope `text-embedding-v4` | 有 API Key、低延迟需求 |
| `local` | `langchain_ollama.ChatOllama`，本地 Ollama | `langchain_ollama.OllamaEmbeddings`，本地 Ollama | 私有化部署、数据不出域 |

##### 切换方法

修改 `.env` 文件中的 `MODEL_MODE` 值即可：

```ini
# 远程模式（默认）：聊天模型指向任意 OpenAI 协议供应商
MODEL_MODE=remote
OPENAI_CHAT_MODEL=deepseek-flash
OPENAI_API_KEY=your_deepseek_api_key
OPENAI_BASE_URL=https://api.deepseek.com
DASHSCOPE_API_KEY=your_dashscope_api_key   # 嵌入/精排/评测模型仍走 DashScope

# 本地模式
MODEL_MODE=local
OLLAMA_BASE_URL=http://ollama:11434
```

##### 本地模式首次使用：Ollama 模型自动拉取

Docker Compose 已内置 `ollama` 服务。切换为 `MODEL_MODE=local` 后，后端启动时会**自动检测** `qwen2.5:7b`（聊天）和 `bge-m3`（嵌入）两个模型是否存在，缺失则自动 `pull`，无需手动执行：

```bash
# 首次使用本地模式时，后端启动日志会显示：
# [模型工厂]Ollama 模型缺失: qwen2.5:7b，开始自动拉取（可能耗时较长）...
```

> **注意**：模型体积较大（qwen2.5:7b 约 4.7GB，bge-m3 约 1.2GB），首次拉取耗时取决于网络，需耐心等待。

如需自定义本地模型，可在 `rag_config.yml` 中修改 `local` 分组，或通过环境变量覆盖：

```bash
OLLAMA_CHAT_MODEL=qwen2.5:14b
OLLAMA_EMBEDDING_MODEL=nomic-embed-text
```

##### 远程模式兼容的模型端点（业务聊天模型）

| 服务商               | `OPENAI_BASE_URL`                                   | 模型名示例       |
| -------------------- | --------------------------------------------------- | ---------------- |
| 通义千问（兼容端点） | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-plus`      |
| DeepSeek             | `https://api.deepseek.com/v1`                       | `deepseek-flash` |
| 月之暗面             | `https://api.moonshot.cn/v1`                        | `moonshot-v1-8k` |

#### 3.4.2 配置项说明

##### .env 需自主配置的模型项

| 变量 | 必填 | 说明 |
|------|------|------|
| `OPENAI_CHAT_MODEL` | 是 | 业务聊天模型名，随所选供应商填写 |
| `OPENAI_API_KEY` | 是 | 业务聊天模型的 API Key |
| `OPENAI_BASE_URL` | 是 | 业务聊天模型端点，见下方兼容端点表 |
| `DASHSCOPE_API_KEY` | 是 | DashScope API Key：嵌入 / 精排 / 评测模型共用 |

> **供应商策略**：只有业务聊天模型（`OPENAI_*` 三件套）可指向任意 OpenAI 协议供应商；**聊天模型除外的其他远程模型（嵌入、精排、评测）默认走 DashScope 供应商**，仅需配好 `DASHSCOPE_API_KEY` 即可，无需其他配置。

##### 可选覆盖项（默认值即可用，无需配置）

| 变量 | 默认值（均为 DashScope） | 说明 |
|------|--------------------------|------|
| `TEXT_EMBEDDING_MODEL` | `rag_config.yml` 的 `remote.embedding_model_name`（text-embedding-v4） | 覆盖嵌入模型名 |
| `RERANK_MODEL` | `retrieval_config.yml` 的 `rerank.remote_model`（gte-rerank-v2） | 覆盖精排模型名 |
| `EVAL_CHAT_MODEL` | `qwen-plus` | 覆盖评测模型名（裁判/评测集生成）。固定走 DashScope，与业务聊天模型解耦，保证与历史评测报告口径可比 |
| `DASHSCOPE_BASE_URL` | `https://dashscope.aliyuncs.com/compatible-mode/v1` | 覆盖 DashScope OpenAI 协议端点（仅评测模型使用） |

> **注意**：切换嵌入模型后向量维度会变化，需删除旧 Qdrant collection 并重新入库文档。系统会在 collection 不存在时按新维度自动创建。

##### 账号与登录安全变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `SECRET_KEY` | 开发模板内置 | JWT 签名密钥；**生产环境必须替换为随机长字符串**，更换后已签发 token 全部失效 |
| `ADMIN1_USERNAME` / `ADMIN1_PASSWORD` | `admin` / 开发模板内置 | 内置管理员账号；服务启动时若不存在则创建，已存在不覆盖密码 |
| `ADMIN2_*` / `ADMIN3_*` | 空 | 可选的第 2、3 个内置管理员，未配置则跳过 |
| `LOGIN_MAX_FAILURES` | `5` | 连续登录失败多少次后锁定账号 |
| `LOGIN_LOCK_MINUTES` | `15` | 账号锁定时长（分钟） |

> 管理员密码仅在首次创建时写入数据库（bcrypt 哈希），因此**启动日志不会打印密码**；忘记密码可在宿主机执行 `python -m app.cli.reset_password --username <账号>` 重置，或直接修改 env 后手工删除该账号记录再重启（不推荐）。

##### 保留在原位置的编排项（不要在 .env 之外自定义）

以下变量由 Docker Compose / 启动脚本按部署形态注入，属于编排信息，**不属于模型自定义项**：

- `MODEL_MODE`：模型加载模式（remote/local），见上表
- `MYSQL_HOST` / `MYSQL_PORT` / `MYSQL_*`：容器编排内为服务名 `mysql`；本地直跑由 `scripts/start-backend.ps1` 自动覆盖为 `127.0.0.1` + `MYSQL_HOST_PORT`
- `QDRANT_HOST` / `QDRANT_PORT` / `QDRANT_COLLECTION`：编排内为 `qdrant:6333`；本地直跑由脚本覆盖为 `127.0.0.1` + `QDRANT_HOST_PORT`
- `MYSQL_HOST_PORT` / `QDRANT_HOST_PORT` / `QDRANT_GRPC_HOST_PORT` / `OLLAMA_PORT`：仅宿主机映射端口，见 3.4.4
- `OLLAMA_BASE_URL` / `OLLAMA_PORT`：编排内为 `http://ollama:11434`；本地直连为 `http://localhost:21434`
- `ENV` / `DEBUG` / `LOG_LEVEL`：后端服务运行参数

##### RAG+ReAct 混合架构配置（可选）

路由与 ReAct 参数集中在 `backend/app/config/hybrid_config.yml`，**均可用同名环境变量覆盖**（环境变量 > YAML > 代码默认值），完整键说明见 2.4.1。最常用的是 `ENABLE_HYBRID_ROUTER`：设为 `false` 即完全回到纯 RAG 直调，无需改代码或改规则文件。

#### 3.4.3 本地直跑时 .env 如何生效

- **Docker 部署**：Compose 自动把 env 文件注入容器环境。
- **本地启动后端**：`scripts/start-backend.ps1` / `start-backend.sh` 解析 `.env.dev` 注入（并自动做本地连接覆盖）。
- **`uv run` 直跑脚本/评测**：后端启动时会自动按白名单从 `docker/env/.env.dev` 加载**模型相关变量**（仅注入缺失键，已注入的真实环境变量优先；可用 `PRIVRAG_ENV_FILE` 指定其他 env 文件）。白名单只含模型项，`MYSQL_HOST=mysql` 等编排值不会被误注入本地进程。

#### 3.4.4 端口清单（高位端口）

| 服务 | 宿主机 / 本地端口 | 容器内端口 | 配置位置 |
|---|---|---|---|
| Nginx 入口 | `18080`（HTTP）/ `18443`（HTTPS） | `80` / `443` | `docker-compose.yml` |
| Frontend（Vite / 容器） | `13000` | `80` | `frontend/vite.config.js`、`docker-compose.yml` |
| Backend API | `18000` | `18000` | `backend/Dockerfile`、`scripts/start-backend.*` |
| MySQL | `16666` | `3306` | `docker/env/.env.dev` → `MYSQL_HOST_PORT` |
| Qdrant HTTP / gRPC | `16333` / `16334` | `6333` / `6334` | `.env.dev` → `QDRANT_HOST_PORT` / `QDRANT_GRPC_HOST_PORT` |
| Ollama | `21434` | `11434` | `.env.dev` → `OLLAMA_PORT` |

> 用高位端口是为了预防端口占用问题，详见 [`docs/常见报错问题解决方案速查.md`](docs/常见报错问题解决方案速查.md)。本地直跑脚本会自动把 `MYSQL_PORT` / `QDRANT_PORT` 覆盖为上述宿主机端口，无需手工设置。

## 第四章 团队信息

- 学校：东莞理工学院
- 指导老师：无
- 团队名：207
- 队员信息：
  1. 队长：程迪宏
  2. 队员：李仕远

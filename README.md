# 宸甄 PrivRAG 企业私有知识库问答系统

## 1 项目概述

### 1-1 项目背景

​	企业沉淀大量非结构化内部文档，传统文件管理与关键词检索查阅效率低下；通用大模型无法加载私有数据，回答易产生幻觉，公有接口存在数据泄密隐患。为此基于 RAG 技术开发私有化知识库问答系统，依托本地向量库实现私有文档语义检索，赋能大模型精准作答，保障数据安全。

### 1-2 项目技术栈

- **前端框架**：Vue 3 + Vite + Element Plus + ECharts + Vue Router + Axios
- **后端框架**：FastAPI（含认证/会话/文档/统计/设置全部业务接口）
- **关系型数据库**：MySQL 8.4（SQLModel + aiomysql 异步）
- **向量数据库**：Qdrant v1.16
- **ORM**：SQLModel + SQLAlchemy（异步）
- **AI问答服务框架**：Langchain
- **测试框架**：pytest + anyio（202 个单元测试，详见 `tests/README.md`）

### 1-3 项目结构

```plaintext
RAGproject_demo/
├── docker/                              # 部署配置（nginx / 环境变量 / 中间件）
│   ├── env/
│   │   ├── .env.dev                     # 开发环境变量
│   │   └── .env.prod                    # 生产环境变量
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
│   │   │   ├── qdrant_config.yml        # Qdrant 向量库 + RAG 参数配置
│   │   │   └── rag_config.yml           # RAG 服务配置
│   │   ├── core/                        # 核心模块
│   │   │   ├── response.py              # 统一响应 {code, message, data}
│   │   │   └── security.py              # 密码哈希 / JWT 签发与校验
│   │   ├── data/                        # 私有知识库原始文件（上传落盘目录）
│   │   │   └── 员工手册.txt
│   │   ├── database/                    # 数据库连接层
│   │   │   └── db.py                    # 环境变量连接 / get_session / init_db 建表
│   │   ├── dependencies.py              # 全局依赖（get_current_user）
│   │   ├── logs/                        # 运行日志
│   │   ├── modelFactory/                # 模型工厂
│   │   │   └── factory.py               # 聊天模型 / 嵌入模型实例化
│   │   ├── models/                      # SQLModel 数据模型（5 张表）
│   │   │   ├── __init__.py
│   │   │   ├── chat_conversation.py     # 会话表
│   │   │   ├── chat_message.py          # 消息表（含 citations）
│   │   │   ├── document_chunk.py        # 文档分块表
│   │   │   ├── documents.py             # 文档表（含 md5 去重）
│   │   │   └── users.py                 # 用户表
│   │   ├── prompts/                     # 系统提示词模板
│   │   │   ├── rag_summarize.txt
│   │   │   └── system_prompt.txt
│   │   ├── routers/                     # FastAPI 路由层
│   │   │   ├── auth.py                  # 认证（登录/注册/个人信息/改密）
│   │   │   ├── chat.py                  # 会话 CRUD + 问答 + 引用来源
│   │   │   ├── documents.py             # 文档上传/列表/预览/下载/删除
│   │   │   ├── settings.py              # RAG 参数配置读写
│   │   │   └── statistics.py            # 统计数据查询
│   │   ├── service/                     # 业务服务层
│   │   │   ├── agent/                   # Agent 服务
│   │   │   │   └── react_agent.py
│   │   │   ├── history/                 # 对话历史管理（按会话隔离）
│   │   │   │   └── history_store.py
│   │   │   └── rag/                     # RAG 问答核心
│   │   │       ├── rag_service.py       # RAG 总结服务（支持多会话历史隔离）
│   │   │       └── vector_store.py      # Qdrant 向量库服务
│   │   ├── utils/                       # 工具模块
│   │   │   ├── config_handler.py        # 配置加载器
│   │   │   ├── file_handler.py          # 文件 MD5 / 文档读取
│   │   │   ├── logger_handler.py        # 日志配置
│   │   │   ├── path_tool.py             # 路径工具（绝对路径计算）
│   │   │   └── prompt_loader.py         # 提示词模板加载
│   │   └── main.py                      # FastAPI 应用入口（lifespan 建表 + 路由注册）
│   ├── chat_history/                    # 用户对话历史持久化（按会话独立文件）
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
│           ├── chat/                    # Bot 问答页（会话管理 + 引用溯源）
│           ├── knowledge/               # 知识库页（文档表格 + 上传/预览/删除）
│           ├── statistics/              # 统计数据页（ECharts 图表）
│           ├── settings/                # 系统设置页（个人信息 + RAG 参数）
│           └── LoginRegister.vue        # 登录注册页
├── tests/                               # 单元测试（202 个，运行方式见 tests/README.md）
├── docker-compose.yml                   # Docker Compose 编排文件
├── .dockerignore                        # Docker 构建忽略规则
├── .gitattributes
├── .gitignore
├── docs/                                # 项目开发文档目录
│   ├── 前后端开发执行文档.md               # 前后端开发计划与实施记录
│   └── 接口JSON契约文档.md                # 前后端接口契约（联调依据）
└── README.md
```

## 2 项目阶段

目前阶段完成情况：

1. **RAG 检索服务与 Agent 问答**：已完成基础架构开发（Qdrant 向量库服务、RAG 总结服务、ReAct Agent、按会话隔离的对话历史管理）；
2. **前端页面**：已完成全部页面开发（登录注册、主框架、Bot 问答、知识库、统计数据、系统设置），采用蓝紫渐变科技风格，已对接后端真实接口；
3. **后端业务服务**：已完成（认证、会话、文档、统计、设置全部接口），接入 MySQL 8.4 + Qdrant v1.16，复用现有 RAG/Agent 服务；前后端联调通过；
4. **单元测试**：已为后端新增与更新 202 个单元测试（工具/模型/核心/数据/依赖/服务/路由/Agent 各层），全程 mock 外部依赖（MySQL/Qdrant/DashScope/LLM），不连真实库、无网络调用；运行方式详见 `tests/README.md`；
5. **后续可迭代**：详见下一章「项目期望」。

## 3 项目期望

基于当前的代码架构，做企业级迭代。当前版本的已完成能力之外，规划以下优化方向（按优先级排列）：

### 3-1 升级 RAG 检索体系

**a. 扩展支持更多文档格式**

目前仅支持 `txt` / `pdf` 两种格式（由 `file_handler.py` 的文件加载器决定）。后续按文档类型逐类接入加载器，并同步放开 `allow_knowledge_file_type` 白名单：

- Office 系：`docx` / `doc`（python-docx / 转换工具）
- 表格与演示：`xlsx` / `pptx`（openpyxl / python-pptx）
- Web 与标记：`md` / `html`（Markdown 解析 / BeautifulSoup）
- 图片与扫描件：`png` / `jpg`（OCR 文本提取）

**b. 增强文档解析能力**

当前按固定 `chunk_size` / `chunk_overlap` 均匀切分，未感知文档结构。后续升级为结构化解析：

- **章节树构建**：解析文档标题层级（H1→Hn），生成章节树，检索时可按章节定位引用来源，回答展示更精准；
- **智能切分规则**：根据章节/段落语义自定义切分策略——小章节合并进邻近 chunk（避免碎片化）、超长章节按段落边界再分割（避免截断语义）、常规段落保持原样不处理；
- **元数据增强**：chunk 携带章节号、标题、页码等元数据，供检索过滤与引用展示使用。

**c. 检索侧升级（混合检索 + 精排）**

当前为纯稠密向量检索（`topK` 直接返回）。后续升级为两级检索架构：

- **混合检索**：BM25 稀疏检索与稠密向量检索并行召回，按权重融合（如 RRF 融合算法），提升专有名词/缩写/长尾查询的召回率；
- **精排重排**：召回 TopN 后使用 Cross-Encoder 或大模型打分重排，取精排后的 TopK 作为最终上下文，提升回答相关性与引用准确度；
- **检索调优**：支持查询改写（Query Rewriting）、上下文压缩（Contextual Compression）等后处理。

### 3-2 RAG 参数实时生效

当前系统设置中的 RAG 参数（chunkSize / topK 等）写入 `qdrant_config.yml`，**重启后端后生效**。后续升级为实时生效：

- 参数热更新：设置保存时同步刷新内存中的运行参数（如线程安全的配置快照）；
- 可观测：参数变更记录日志，便于追溯配置调整时间线与影响范围。

### 3-3 验证码可随时接入短信服务

当前开发环境验证码固定为 `123456`（`/api/auth/sms-code` 仅写日志，不真实下发）。后续抽象短信发送接口，接入真实服务商（阿里云短信 / 腾讯云 SMS 等），通过配置切换：

- 开发环境：保留固定验证码兜底；
- 生产环境：走真实短信通道，增加发送频率限制、验证码有效期与防爆破策略。

### 3-4 其他可补充方向

- **权限与数据隔离**：知识库支持按用户/部门授权，文档与会话数据严格按用户隔离（当前会话已按用户隔离，可进一步细化到知识库级别）；
- **引用来源展示增强**：citations 支持高亮命中片段、跳转到原文位置；合并「回答检索」与「引用检索」为一次检索两处使用，降低重复计算；
- **系统可观测性**：接入指标采集（请求量/时延/错误率）、链路追踪与日志可视化（Prometheus + Grafana / ELK）；
- **部署与运维**：补充 CI/CD 流水线（自动测试 + 镜像构建 + 发布）、Kubernetes 编排与水平扩展、数据备份恢复策略；
- **多模态与语音**：支持图片/表格多模态问答、语音提问与播报等交互形态。

---

## 4 快速启动

本节介绍如何在本地快速把项目跑起来。根据使用场景选择以下两种启动方式之一。

### 4-1 环境准备

| 依赖 | 版本要求 | 说明 |
|---|---|---|
| Docker Desktop | ≥ 4.x（Windows 需启用 WSL2 后端） | 提供 MySQL / Qdrant / 完整容器化部署的运行环境；镜像源可配置加速 |
| Python | ≥ 3.10（推荐 3.12+） | 方式二本地运行后端所需；可选 `uv` 作为包管理器（项目已提供 `pyproject.toml` / `uv.lock`） |
| Node.js | ≥ 18 | 方式二本地运行前端所需（`npm` 随 Node 附带） |
| Git | 任意 | 拉取/管理项目代码 |

> Windows 提示：执行下述命令前，请确认 **Docker Desktop 已启动**（任务栏图标处于运行状态），否则 `docker compose` 会报连接错误。

### 4-2 启动方式一：Docker 一键容器化部署（便捷，但较慢）

**前置准备**：仅需 Docker Desktop；无需本地安装 Python / Node.js。

```bash
# 1. 首次使用：从模板复制环境变量文件并编辑
cp docker/env/.env.dev.example docker/env/.env.dev
#    至少需填写：DASHSCOPE_API_KEY（问答与向量化必需）、MYSQL_ROOT_PASSWORD 等

# 2. 构建并一键启动全部服务（mysql / qdrant / backend / frontend / nginx）
docker compose --env-file docker/env/.env.dev up -d --build

# 3. 查看运行状态与日志
docker compose ps                 # 5 个服务均应为 Up (healthy)
docker compose logs -f backend    # 查看后端日志（Ctrl+C 退出）

# 4. 访问应用
#    Nginx 入口：http://localhost
#    后端 API：  http://localhost:8000/docs
#    前端页面：  http://localhost:3000

# 停止 / 重新构建（代码更新后）
docker compose down
docker compose --env-file docker/env/.env.dev up -d --build
```

**说明**：一条命令拉起全部服务，环境一致、无需本地装依赖，适合演示与部署；但**首次启动较慢**——需拉取 MySQL/Qdrant/Nginx 基础镜像并构建前后端镜像（安装 Python / Node 依赖），且代码修改后需重新构建镜像才能生效。

### 4-3 启动方式二：仅基础设施 + 本地启动前后端（推荐开发调试）

**前置准备**：Docker Desktop + Python（可选 uv）+ Node.js。

```bash
# 1. 仅启动基础设施（MySQL + Qdrant）
docker compose --env-file docker/env/.env.dev up -d mysql qdrant
docker compose ps    # 预期：mysql 和 qdrant 状态为 Up (healthy)

# 2. 本地启动后端服务（新终端窗口）
# 2.1 进入后端目录
cd backend
# 2.2 读取 docker/env/.env.dev 中的 DASHSCOPE_API_KEY（问答与向量化必需）

# 2.2.1 Windows PowerShell:
$env:DASHSCOPE_API_KEY = ((Get-Content ../docker/env/.env.dev | Select-String '^DASHSCOPE_API_KEY=').Line -split '=',2)[1]

# 2.2.2 Linux / macOS / Git Bash:
export DASHSCOPE_API_KEY=$(grep '^DASHSCOPE_API_KEY=' ../docker/env/.env.dev | cut -d'=' -f2)

# 2.3 启动后端服务
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
# 启动时自动建表（幂等）；访问 http://localhost:8000/docs 查看全部接口

# 3. 本地启动前端服务（新终端窗口）
cd frontend
npm install  # 首次运行
npm run dev
# 访问 http://localhost:3000 查看前端页面（已对接后端真实接口）
# 测试账号：注册后登录（注册验证码固定为 123456）

# 4. 停止基础设施
docker compose down
```

**说明**：仅运行 MySQL/Qdrant 两个容器，资源占用少、启动快；前后端在本机运行，支持热重载与 IDE 断点调试，代码修改即时生效，适合开发阶段；代价是需要本机安装 Python / Node.js 依赖。

---

## 5 Docker 容器化部署

### 5-1 架构概览

```
互联网用户 → Nginx(:80) → Frontend Vue(:3000)  静态页面
                          → Backend API(:8000)  数据处理
                                   ↓
                          MySQL(:3306)   关系型数据库
                          Qdrant(:6333)  向量数据库
```

### 5-2 两种使用模式

本项目支持两种 Docker 使用模式，启动步骤已在上章「快速启动」中给出，此处仅说明两种模式的特点与适用场景：

#### 模式 A：基础设施模式（推荐开发阶段使用）

- 只启动 MySQL 和 Qdrant 两个基础服务，前后端在本地（Windows）运行；
- 代码修改即时生效（后端热重载 + 前端 HMR），支持 IDE 断点调试；
- 资源占用少、启动速度快；需本机安装 Python / Node.js 依赖。

#### 模式 B：完整容器化模式（部署/演示阶段使用）

- 一键启动全部 5 个服务（MySQL、Qdrant、Backend、Frontend、Nginx），环境一致性高；
- 无需本机安装 Python / Node.js 依赖，适合演示、测试环境与生产部署；
- 修改代码后需重新构建镜像，构建/拉取耗时较长。

#### 模式对比

| 对比项 | 模式 A：基础设施模式 | 模式 B：完整容器化模式 |
|---|---|---|
| 启动服务 | MySQL、Qdrant | 全部 5 个服务 |
| 代码运行位置 | 本地（Windows） | 容器内 |
| 代码修改生效 | 即时（热重载） | 需重新构建 |
| 调试支持 | IDE 断点调试 | 日志查看 |
| 适用阶段 | 开发调试 | 部署/演示/生产 |
| 资源占用 | 较低 | 较高 |
| 依赖安装 | 需本地安装 | 无需本地安装 |

### 5-3 关键设计说明

| 设计点 | 说明 |
|---|---|
| 业务配置 vs 部署配置 | `backend/app/config/` 存放业务级 YAML 配置，`docker/` 存放部署级配置，职责分离 |
| 独立 Dockerfile | `backend/Dockerfile` 和 `frontend/Dockerfile` 各自管理构建，不混入 docker 目录 |
| 多阶段构建 | 后端使用 `uv` 官方镜像构建虚拟环境后复制到 slim 运行镜像；前端使用 Node 构建后由 Nginx 托管 |
| 健康检查 | 所有服务均配置 healthcheck，后端依赖 MySQL/Qdrant 健康状态后才启动 |
| 环境隔离 | 通过 `--env-file` 切换 `.env.dev` / `.env.prod` 实现开发/生产环境分离 |
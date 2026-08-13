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
├── tests/                               # 测试代码
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
4. **后续可迭代**：完整容器化部署（模式 B）、citations 检索合并优化、RAG 参数热生效等（详见前后端开发执行文档 4.5）。

## 3 项目期望

基于当前的代码架构，做企业级迭代

---

## 4 Docker 容器化部署

### 4-1 架构概览

```
互联网用户 → Nginx(:80) → Frontend Vue(:3000)  静态页面
                          → Backend API(:8000)  数据处理
                                   ↓
                          MySQL(:3306)   关系型数据库
                          Qdrant(:6333)  向量数据库
```

### 4-2 两种使用模式

本项目支持两种 Docker 使用模式，根据开发阶段和需求选择：

---

#### 模式 A：基础设施模式（推荐开发阶段使用）

**适用场景**：后端/前端代码开发调试阶段，需要频繁修改代码

**特点**：
- 只启动 MySQL 和 Qdrant 两个基础服务
- 后端通过 `uvicorn` 在本地运行，代码修改即时生效（支持热重载）
- 前端通过 `npm run dev` 本地启动，支持 HMR 热更新
- 调试方便，可直接在 IDE 中打断点
- 资源占用少，启动速度快

```bash
# 1. 从模板复制环境变量文件（首次使用）
cp docker/env/.env.dev.example docker/env/.env.dev
# 编辑 docker/env/.env.dev 文件，修改数据库密码、API Key 等变量

# 2. 仅启动基础设施（MySQL + Qdrant）
docker compose --env-file docker/env/.env.dev up -d mysql qdrant

# 3. 验证基础设施是否就绪
docker compose ps
# 预期输出：mysql 和 qdrant 状态为 Up (healthy)

# 4. 本地启动后端服务（新终端窗口）
cd backend
# 读取 docker/env/.env.dev 中的 DASHSCOPE_API_KEY（问答与向量化必需）
export DASHSCOPE_API_KEY=$(grep '^DASHSCOPE_API_KEY=' ../docker/env/.env.dev | cut -d'=' -f2)
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
# 启动时自动建表（幂等）；访问 http://localhost:8000/docs 查看全部接口

# 5. 本地启动前端服务（新终端窗口）
cd frontend
npm install  # 首次运行
npm run dev
# 访问 http://localhost:3000 查看前端页面（已对接后端真实接口）
# 测试账号：注册后登录（注册验证码固定为 123456）

# 停止基础设施
docker compose down
```

---

#### 模式 B：完整容器化模式（部署/演示阶段使用）

**适用场景**：功能开发完成后，需要验证容器内运行或进行部署

**特点**：
- 一键启动所有服务（MySQL、Qdrant、Backend、Frontend、Nginx）
- 环境一致性，避免"在我机器上能跑"的问题
- 无需本地安装 Python/Node.js 等依赖
- 适合演示、测试环境、生产部署
- 修改代码后需要重新构建镜像

```bash
# 1. 从模板复制环境变量文件（首次使用）
cp docker/env/.env.dev.example docker/env/.env.dev
# 编辑 docker/env/.env.dev 文件，修改数据库密码、API Key 等变量

# 2. 开发环境：构建并启动所有服务
docker compose --env-file docker/env/.env.dev up -d --build

# 3. 生产环境：构建并启动所有服务
docker compose --env-file docker/env/.env.prod up -d --build

# 4. 查看运行状态
docker compose ps
# 预期输出：5 个服务均为 Up 状态

# 5. 查看服务日志
docker compose logs -f
# 查看特定服务日志：docker compose logs -f backend

# 6. 访问应用
# Nginx 入口：http://localhost
# Backend API：http://localhost:8000/docs
# Frontend 页面：http://localhost:3000

# 停止所有服务
docker compose down

# 重新构建并启动（代码更新后）
docker compose --env-file docker/env/.env.dev up -d --build
```

---

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

### 4-3 docker-compose.yml 模板

```yaml
# ======================================================================
# 宸甄 PrivRAG — Docker Compose 编排文件
# ======================================================================
# 包含服务: nginx, frontend(Vue), backend(FastAPI), MySQL, Qdrant

services:
  # ======================== MySQL 关系型数据库 ========================
  mysql:
    image: mysql:8.4
    container_name: privrag-mysql
    restart: unless-stopped
    environment:
      MYSQL_ROOT_PASSWORD: ${MYSQL_ROOT_PASSWORD}
      MYSQL_DATABASE: ${MYSQL_DATABASE}
      MYSQL_USER: ${MYSQL_USER}
      MYSQL_PASSWORD: ${MYSQL_PASSWORD}
    ports:
      - "${MYSQL_PORT:-3306}:3306"
    volumes:
      - mysql_data:/var/lib/mysql
      - ./docker/middleware/my.cnf:/etc/mysql/conf.d/my.cnf:ro
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "localhost", "-u", "root", "-p${MYSQL_ROOT_PASSWORD}"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s
    networks:
      - privrag-network

  # ======================== Qdrant 向量数据库 ========================
  qdrant:
    image: qdrant/qdrant:v1.16
    container_name: privrag-qdrant
    restart: unless-stopped
    ports:
      - "${QDRANT_PORT:-6333}:6333"
      - "6334:6334"
    volumes:
      - qdrant_data:/qdrant/storage
      - ./docker/middleware/qdrant_config.yaml:/qdrant/config/config.yaml:ro
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:6333/health"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 15s
    networks:
      - privrag-network

  # ======================== FastAPI 后端服务 ========================
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: privrag-backend
    restart: unless-stopped
    depends_on:
      mysql:
        condition: service_healthy
      qdrant:
        condition: service_healthy
    environment:
      ENV: ${ENV:-development}
      DEBUG: ${DEBUG:-true}
      LOG_LEVEL: ${LOG_LEVEL:-DEBUG}
      MYSQL_HOST: ${MYSQL_HOST:-mysql}
      MYSQL_PORT: ${MYSQL_PORT:-3306}
      MYSQL_USER: ${MYSQL_USER:-privrag}
      MYSQL_PASSWORD: ${MYSQL_PASSWORD}
      MYSQL_DATABASE: ${MYSQL_DATABASE:-privrag}
      QDRANT_HOST: ${QDRANT_HOST:-qdrant}
      QDRANT_PORT: ${QDRANT_PORT:-6333}
      QDRANT_COLLECTION: ${QDRANT_COLLECTION:-privrag}
      DASHSCOPE_API_KEY: ${DASHSCOPE_API_KEY}
    ports:
      - "8000:8000"
    volumes:
      - ./backend/app/config:/app/app/config:ro
      - ./backend/app/data:/app/app/data
      - chat_history:/app/chat_history
    networks:
      - privrag-network
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/docs"]
      interval: 15s
      timeout: 5s
      retries: 3
      start_period: 30s

  # ======================== Vue 前端服务 ========================
  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    container_name: privrag-frontend
    restart: unless-stopped
    depends_on:
      backend:
        condition: service_healthy
    ports:
      - "3000:80"
    networks:
      - privrag-network
    healthcheck:
      test: ["CMD", "wget", "-q", "--spider", "http://localhost:80/"]
      interval: 15s
      timeout: 5s
      retries: 3

  # ======================== Nginx 反向代理 ========================
  nginx:
    image: nginx:stable-alpine
    container_name: privrag-nginx
    restart: unless-stopped
    depends_on:
      - frontend
      - backend
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./docker/nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./docker/nginx/conf.d:/etc/nginx/conf.d:ro
    networks:
      - privrag-network
    healthcheck:
      test: ["CMD", "nginx", "-t"]
      interval: 30s
      timeout: 5s
      retries: 3

# ======================== 数据卷 ========================
volumes:
  mysql_data:
    name: privrag_mysql_data
  qdrant_data:
    name: privrag_qdrant_data
  chat_history:
    name: privrag_chat_history

# ======================== 网络 ========================
networks:
  privrag-network:
    name: privrag-network
    driver: bridge
```

### 4-4 关键设计说明

| 设计点 | 说明 |
|---|---|
| 业务配置 vs 部署配置 | `backend/app/config/` 存放业务级 YAML 配置，`docker/` 存放部署级配置，职责分离 |
| 独立 Dockerfile | `backend/Dockerfile` 和 `frontend/Dockerfile` 各自管理构建，不混入 docker 目录 |
| 多阶段构建 | 后端使用 `uv` 官方镜像构建虚拟环境后复制到 slim 运行镜像；前端使用 Node 构建后由 Nginx 托管 |
| 健康检查 | 所有服务均配置 healthcheck，后端依赖 MySQL/Qdrant 健康状态后才启动 |
| 环境隔离 | 通过 `--env-file` 切换 `.env.dev` / `.env.prod` 实现开发/生产环境分离 |
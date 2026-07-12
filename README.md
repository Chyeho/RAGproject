# 宸甄 PrivRAG 企业私有知识库问答系统

## 1 项目概述

### 1-1 项目背景

​	企业沉淀大量非结构化内部文档，传统文件管理与关键词检索查阅效率低下；通用大模型无法加载私有数据，回答易产生幻觉，公有接口存在数据泄密隐患。为此基于 RAG 技术开发私有化知识库问答系统，依托本地向量库实现私有文档语义检索，赋能大模型精准作答，保障数据安全。

### 1-2 项目技术栈

- **前端框架**：Vue（待开发）
- **后端框架**：FastAPI（待开发）
- **关系型数据库**：MySQL（待接入）
- **向量数据库**：Chroma（后面将升级为Milvus）
- **ORM**：SQLAlchemy（异步）
- **AI问答服务框架**：Langchain

### 1-3 项目结构

```plaintext
RAGproject_demo/
├── backend/                             # 后端（FastAPI + LangChain）
│   ├── app/
│   │   ├── config/                      # 配置文件目录
│   │   │   ├── agent_config.yml         # Agent 配置
│   │   │   ├── cache_config.yml         # 缓存配置
│   │   │   ├── chroma_config.yml        # 向量库配置
│   │   │   ├── db_config.yml            # 关系数据库配置
│   │   │   ├── prompts_config.yml       # 提示词配置
│   │   │   └── rag_config.yml           # RAG 服务配置
│   │   ├── data/                        # 私有知识库原始文件
│   │   │   └── 员工手册.txt
│   │   ├── logs/                        # 运行日志
│   │   ├── modelFactory/                # 模型工厂
│   │   │   └── factory.py               # 聊天模型 / 嵌入模型实例化
│   │   ├── models/                      # SQLAlchemy 数据模型
│   │   │   ├── document_chunk.py
│   │   │   ├── documents.py
│   │   │   └── users.py
│   │   ├── prompts/                     # 系统提示词模板
│   │   │   ├── rag_summarize.txt
│   │   │   └── system_prompt.txt
│   │   ├── routers/                     # FastAPI 路由层
│   │   │   └── documents.py             # 文档上传 / 检索接口
│   │   ├── service/                     # 业务服务层
│   │   │   ├── agent/                   # Agent 服务
│   │   │   │   └── react_agent.py
│   │   │   ├── history/                 # 对话历史管理
│   │   │   │   └── history_store.py
│   │   │   └── rag/                     # RAG 问答核心
│   │   │       ├── rag_service.py       # RAG 总结服务
│   │   │       └── vector_store.py      # 向量库服务
│   │   ├── utils/                       # 工具模块
│   │   │   ├── config_handler.py        # 配置加载器
│   │   │   ├── file_handler.py          # 文件 MD5 / 文档读取
│   │   │   ├── logger_handler.py        # 日志配置
│   │   │   ├── path_tool.py             # 路径工具（绝对路径计算）
│   │   │   └── prompt_loader.py         # 提示词模板加载
│   │   ├── main.py                      # FastAPI 应用入口
│   │   └── md5.txt                      # 知识库文件去重记录
│   ├── chat_history/                    # 用户对话历史持久化
│   ├── chroma_db/                       # Chroma 向量数据库
│   ├── pyproject.toml                   # 项目依赖配置
│   └── uv.lock
├── oldProject/                          # 旧版本脚本代码归档
├── frontend/                            # 前端（待开发）
└── README.md
```

## 2 项目阶段

目前阶段项目尚未完善，仅完成rag服务和agent的基本架构的开发；下一阶段将会开发fastAPI后端和前端服务。

## 3 项目期望

基于当前的代码架构，做企业级迭代
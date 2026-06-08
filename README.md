# 宸甄 PrivRAG 企业私有知识库问答系统

## 1 项目概述

### 1-1 项目背景

​	企业沉淀大量非结构化内部文档，传统文件管理与关键词检索查阅效率低下；通用大模型无法加载私有数据，回答易产生幻觉，公有接口存在数据泄密隐患。为此基于 RAG 技术开发私有化知识库问答系统，依托本地向量库实现私有文档语义检索，赋能大模型精准作答，保障数据安全。

### 1-2 项目技术栈

- **前端框架**：Vue
- **后端框架**：FastAPI
- **关系型数据库**：MySQL
- **向量数据库**：Chroma（后面升级为Milvus）
- **ORM**：SQLAlchemy（异步）
- **AI问答服务框架**：Langchain

### 1-3 项目结构

```plaintext
project_root/
├── chat_history/
├── chroma_db/
├── data/
│   ├── 尺码推荐.txt
│   ├── 洗涤养护.txt
│   └── 颜色选择.txt
├── app_file_upload.py
├── app_qa.py
├── config_data.py
├── file_history_store.py
├── knowledge_base.py
├── rag.py
└── vector_stores.py
```



## 2 如何使用

**快速开始**

1.创建并激活并激活虚拟环境(Windows)[可选]

```powershell
# 1.创建虚拟环境
python -m venv .venv

# 2.激活虚拟环境
.venv/Scripts/activate
```

2.安装`pyproject.toml`的所有依赖

```powershell
pip install -e .
```

3.退出虚拟环境(Windows)[可选]

```powershell
deactivate
```

4.在线流程代码运行

```powershell
streamlit run app_qa.py
```

5.离线流程代码运行

```python
streamlit run file_app_upload.py
```

## 3 项目期望

基于当前的代码架构，做企业级迭代
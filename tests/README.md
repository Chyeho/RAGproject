# 单元测试说明文档

## 测试结构

> **为什么测试文件不分子目录？**
>
> Python / pytest 社区的标准实践是 tests 目录保持扁平结构。分子目录会引入额外复杂度：
> - 每个子目录需要 `__init__.py`
> - `conftest.py` 的作用域和 fixture 共享会变得复杂
> - 跨模块导入路径需要额外配置
>
> 当前平铺结构已通过**命名约定**（`test_{模块名}.py`）清晰地标识了每个测试文件的被测模块。

## 测试目录一览

```
tests/
├── __init__.py
├── conftest.py                  # 共享 fixtures（路径配置、临时文件、anyio backend）
│
├── test_path_tool.py            # 工具层 · 路径计算工具
├── test_config_handler.py       # 工具层 · YAML 配置加载与校验（含 Qdrant 配置）
├── test_file_handler.py         # 工具层 · MD5、文件读写、目录遍历
├── test_logger_handler.py       # 工具层 · 日志器创建与管理
├── test_prompt_loader.py        # 工具层 · 提示词模板加载
├── test_env_loader.py           # 工具层 · 模型环境变量白名单加载器（parse/load/默认文件）
│
├── test_factory.py              # 模型层 · 模型工厂双模式（remote/local）+ 嵌入模型封装
├── test_models.py               # 模型层 · SQLModel 五张表定义（字段/外键/默认值）
│
├── test_security.py             # 核心层 · bcrypt 密码哈希 + JWT 签发/解析
├── test_response.py             # 核心层 · 统一响应 {code, message, data}
├── test_db.py                   # 数据层 · 连接串 / get_session / init_db 建表
├── test_dependencies.py         # 依赖层 · get_current_user 认证鉴权
│
├── test_history_store.py        # 服务层 · 对话历史存储
├── test_vector_store.py         # 服务层 · Qdrant 向量库（P1 改造：确定性 chunk ID + metadata 合并 + chunking 接入）
├── test_rag_service.py          # 服务层 · RAG 总结服务（含多会话历史隔离）
├── test_chunking.py             # 服务层 · 格式感知分块（P1：strategy 路由/智能切分/五格式 chunker，样例动态生成全离线）
├── test_bm25_retriever.py       # 服务层 · BM25 稀疏检索器（P2：内存索引全离线，rebuild 用 mock 数据源）
├── test_rrf.py                  # 服务层 · RRF 多路召回融合（P2：纯函数，无外部依赖）
├── test_hybrid.py               # 服务层 · 混合检索/精排包装/链路工厂（P2：稠密路与精排器全 mock）
├── test_rerank.py               # 服务层 · 精排器工厂（P2：remote/local 构造与 rank 全 mock，不触网不下载模型）
├── test_query_enhancer.py       # 服务层 · 查询优化器（P3：mode 路由/多查询改写/HyDE/fuse_then_rerank）
├── test_registry.py             # 服务层 · RAG 服务注册表单例（P4：线程安全懒加载 + 配置变更重建）
├── test_citations.py            # 服务层 · 引用同源拼装（P4：build_citations_from_docs，回答与引用同一次检索）
│
├── test_auth_router.py          # 路由层 · /api/auth 认证接口（TestClient + mock 会话）
├── test_settings_router.py      # 路由层 · /api/settings RAG 参数读写（P4：全参数读写 + 热更新重建 + 审计日志）
│
├── test_agent_tools.py          # Agent 层 · 工具注册
├── test_middleware.py           # Agent 层 · 中间件（监控、日志）
├── test_react_agent.py          # Agent 层 · ReAct Agent 主体
│
├── test_eval_metrics.py         # 评测层 · 确定性检索指标（归一化/2-gram 重叠/命中判定/聚合）
├── test_eval_llm_judge.py       # 评测层 · LLM 裁判（分数解析/忠实度/相关性/聚合）
├── test_eval_dataset.py         # 评测层 · 评测集构建（5 格式段落提取/QA 解析/均衡采样/加载校验）
├── test_corpus_v2.py            # 评测层 · v2 语料生成器（EV2：10 主题 × 6 实体、跨实体近似干扰）
└── test_eval_runner.py          # 评测编排 + 报告生成/对比（全 mock，不连 Qdrant/MySQL）
```

### 测试覆盖层级

| 层级 | 测试文件 | 说明 |
|------|---------|------|
| **工具层** | `test_path_tool` ~ `test_env_loader`（6 个，54 用例） | 纯函数、无外部依赖，最快、最稳定；含模型环境变量白名单加载器 |
| **模型层** | `test_factory.py`、`test_models.py`（66 用例） | 模型工厂双模式分发（`MODEL_MODE` remote/local）、DashScope 嵌入封装、Ollama 模型自动拉取；SQLModel 表定义 |
| **核心层** | `test_security.py`、`test_response.py`（19 用例） | 密码哈希/JWT、统一响应包裹（纯函数） |
| **数据/依赖层** | `test_db.py`、`test_dependencies.py`（11 用例） | 连接串与建表、JWT 认证依赖（mock 会话） |
| **服务层** | `test_history_store` ~ `test_citations`（11 个，152 用例） | 文件读写、Qdrant 向量库（P1：uuid5 确定性 ID/metadata 合并）、RAG 链与历史隔离；格式感知分块（P1：22 用例全离线）；检索链路（P2：BM25/RRF/hybrid/精排工厂，P3：查询优化器）；P4：注册表单例重建 + 引用同源拼装 |
| **路由层** | `test_auth_router.py`、`test_settings_router.py`（27 用例） | FastAPI TestClient + dependency_overrides（不连真实 DB）；P4 settings 全参数读写与热更新重建 |
| **Agent 层** | `test_agent_tools` ~ `test_react_agent`（3 个，16 用例） | Agent 初始化、工具注册、流式输出 |
| **评测层** | `test_eval_metrics` ~ `test_eval_runner`（5 个，87 用例，P0 新增 / EV2 补语料生成） | 检索指标纯函数、LLM 裁判、评测集构建（样例自包含生成）、v2 语料生成器、评测编排与报告（全 mock） |

> 异步测试（`test_db`、`test_dependencies` 中带 `@pytest.mark.anyio` 的用例）由 anyio 的 pytest 插件执行，backend 统一使用 asyncio（见 conftest.py 的 `anyio_backend` fixture）。

## 运行测试

**注意事项（重要）**

- 如果在虚拟环境下跑测试命令，则需要在命令前加`.\.venv\Scripts\python.exe -m`
- 如果在虚拟环境下并且使用uv作为包管理器跑测试命令，则需要在命令前加`uv run`

### 前置条件

```powershell
# 1. 确保在正确的目录
cd backend

# 2. 确认 pytest 已安装
pytest --version
# 或：.\.venv\Scripts\python.exe -m pytest --version
# 或：uv run pytest --version
# 后面的类似
```

### 常用命令

```powershell
# ─── 运行全部测试 ──────────────────────────────
pytest ..\tests\ -v                       # 详细输出
pytest ..\tests\ -v --tb=short            # 详细 + 简洁错误回溯
pytest ..\tests\ -q                       # 安静模式（只显示结果）


# ─── 按层级运行 ────────────────────────────────
# 工具层
pytest ..\tests\test_path_tool.py ..\tests\test_config_handler.py ..\tests\test_file_handler.py ..\tests\test_logger_handler.py ..\tests\test_prompt_loader.py ..\tests\test_env_loader.py -v

# 模型层
pytest ..\tests\test_factory.py ..\tests\test_models.py -v

# 核心/数据/依赖层
pytest ..\tests\test_security.py ..\tests\test_response.py ..\tests\test_db.py ..\tests\test_dependencies.py -v

# 服务层
pytest ..\tests\test_history_store.py ..\tests\test_vector_store.py ..\tests\test_rag_service.py ..\tests\test_chunking.py ..\tests\test_bm25_retriever.py ..\tests\test_rrf.py ..\tests\test_hybrid.py ..\tests\test_rerank.py ..\tests\test_query_enhancer.py ..\tests\test_registry.py ..\tests\test_citations.py -v

# 路由层
pytest ..\tests\test_auth_router.py ..\tests\test_settings_router.py -v

# Agent 层
pytest ..\tests\test_agent_tools.py ..\tests\test_middleware.py ..\tests\test_react_agent.py -v

# 评测层
pytest ..\tests\test_eval_metrics.py ..\tests\test_eval_llm_judge.py ..\tests\test_eval_dataset.py ..\tests\test_corpus_v2.py ..\tests\test_eval_runner.py -v


# ─── 运行单个文件 ──────────────────────────────
pytest ..\tests\test_factory.py -v


# ─── 运行单个测试类 ────────────────────────────
pytest ..\tests\test_factory.py::TestDashScopeTextEmbeddingsCallApi -v


# ─── 运行单个测试方法 ──────────────────────────
pytest ..\tests\test_factory.py::TestDashScopeTextEmbeddingsCallApi::test_batch_splits_when_exceeds_max -v


# ─── 运行匹配关键词的测试 ─────────────────────
pytest ..\tests\ -v -k "history"          # 所有包含 "history" 的测试
pytest ..\tests\ -v -k "config"           # 所有包含 "config" 的测试


# ─── 输出测试覆盖率报告 ────────────────────────
uv add --dev pytest-cov
pytest ..\tests\ --cov=app --cov-report=term-missing


# ─── 失败时立即停止 ────────────────────────────
pytest ..\tests\ -v -x                    # 第一个失败就停
pytest ..\tests\ -v --maxfail=3           # 最多 3 个失败就停


# ─── 只运行上次失败的测试 ─────────────────────
pytest ..\tests\ --lf                     # --last-failed

# ─── 先运行上次失败的，再运行全部 ─────────────
pytest ..\tests\ --ff                     # --failed-first
```

## 已知警告说明

运行全部测试时会出现 **1 条警告**（第三方库内部问题，**不影响测试结果**，无需处理）：

```
DeprecationWarning: datetime.datetime.utcfromtimestamp() is deprecated
  _EPOCH_DATETIME_NAIVE = datetime.datetime.utcfromtimestamp(0)
```

**来源**：`protobuf`（项目依赖）使用了 Python 3.12+ 已弃用的 `utcfromtimestamp()` API，发生在模块导入阶段（早于任何测试代码执行）。

**如需手动抑制**（可选）：

```powershell
pytest ..\tests\ -q -W "ignore::DeprecationWarning"
```

---

## 测试设计原则

1. **不修改业务代码**：所有测试只读被测模块，通过 mock 隔离外部依赖（DashScope API、Qdrant、MySQL、ChatOpenAI / ChatOllama / Ollama）
2. **快速执行**：避免网络调用和磁盘 I/O 密集型操作，使用 `tempfile` 和 `unittest.mock`；路由测试使用 TestClient + `dependency_overrides`，不连接真实数据库
3. **独立性**：每个测试独立运行，不依赖其他测试的执行顺序或副作用
4. **清晰命名**：测试方法名精确描述被测行为和预期结果

## 当前测试统计

### 标准环境：已启动 Qdrant 容器

最近一次验证：**2026-10-26**（MySQL/Qdrant 容器运行中，`pytest ..\tests\ -q`，34.37s）

```
platform: win32
python:   3.13.0（backend/.venv）
pytest:   9.1.1
tests:    432 passed, 0 failed
```

输出中的 `1 warning` 为 `protobuf` 库内部告警（见上文「已知警告说明」），不影响测试结果。

### 未启动 Qdrant 容器时

**实测同样全绿：432 passed, 0 failed**（2026-10-26，停掉 `privrag-qdrant` 后跑 `pytest ..\tests\ -q`，26.68s）。

P2 检索链路与 P4 注册表单例的单测均已 mock Qdrant 访问，此前文档记录的 10 个 Agent 层真实依赖用例（`test_agent_tools` 4 个、`test_react_agent` 6 个）现已全部隔离，无需 Qdrant 服务即可通过。

如需按标准环境复现（可选）：

```powershell
# 在项目根目录执行（--env-file 避免 MYSQL_DATABASE 等变量未设置的警告）
docker compose --env-file docker/env/.env.dev up -d qdrant
docker compose --env-file docker/env/.env.dev ps    # 确认 privrag-qdrant 状态为 Up
```

> 全部 432 个用例均通过 mock 隔离外部依赖（MySQL / DashScope / ChatOpenAI / ChatOllama / Ollama / Qdrant），实测 Qdrant 停止时仍全绿（其中评测层 87 个、P1 分块 22 个、P2/P3 检索链路 69 个、P4 热更新与引用 10 个，见上表「评测层」「服务层」）。

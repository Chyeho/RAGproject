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
│
├── test_factory.py              # 模型层 · 嵌入模型 & 工厂模式
├── test_models.py               # 模型层 · SQLModel 五张表定义（字段/外键/默认值）
│
├── test_security.py             # 核心层 · bcrypt 密码哈希 + JWT 签发/解析
├── test_response.py             # 核心层 · 统一响应 {code, message, data}
├── test_db.py                   # 数据层 · 连接串 / get_session / init_db 建表
├── test_dependencies.py         # 依赖层 · get_current_user 认证鉴权
│
├── test_history_store.py        # 服务层 · 对话历史存储
├── test_vector_store.py         # 服务层 · Qdrant 向量库（含 upload/delete/md5 去重）
├── test_rag_service.py          # 服务层 · RAG 总结服务（含多会话历史隔离）
│
├── test_auth_router.py          # 路由层 · /api/auth 认证接口（TestClient + mock 会话）
├── test_settings_router.py      # 路由层 · /api/settings RAG 参数读写
│
├── test_agent_tools.py          # Agent 层 · 工具注册
├── test_middleware.py           # Agent 层 · 中间件（监控、日志）
└── test_react_agent.py          # Agent 层 · ReAct Agent 主体
```

### 测试覆盖层级

| 层级 | 测试文件 | 说明 |
|------|---------|------|
| **工具层** | `test_path_tool` ~ `test_prompt_loader`（5 个） | 纯函数、无外部依赖，最快、最稳定 |
| **模型层** | `test_factory.py`、`test_models.py` | 嵌入模型 API 封装（mock DashScope）；SQLModel 表定义 |
| **核心层** | `test_security.py`、`test_response.py` | 密码哈希/JWT、统一响应包裹（纯函数） |
| **数据/依赖层** | `test_db.py`、`test_dependencies.py` | 连接串与建表、JWT 认证依赖（mock 会话） |
| **服务层** | `test_history_store` ~ `test_rag_service`（3 个） | 文件读写、Qdrant 向量库、RAG 链与历史隔离 |
| **路由层** | `test_auth_router.py`、`test_settings_router.py` | FastAPI TestClient + dependency_overrides（不连真实 DB） |
| **Agent 层** | `test_agent_tools` ~ `test_react_agent`（3 个） | Agent 初始化、工具注册、流式输出 |

> 异步测试（`test_db`、`test_dependencies` 中带 `@pytest.mark.anyio` 的用例）由 anyio 的 pytest 插件执行，backend 统一使用 asyncio（见 conftest.py 的 `anyio_backend` fixture）。

## 运行测试

### 前置条件

```powershell
# 1. 确保在正确的目录
cd "d:\Microsoft VS Code\pyAdCode\7.rag_agent_project\02_RAG项目\RAGproject_demo\backend"

# 2. 确认 pytest 已安装
python -m pytest --version
```

### 常用命令

```powershell
# ─── 运行全部测试 ──────────────────────────────
python -m pytest ..\tests\ -v                    # 详细输出（推荐）
python -m pytest ..\tests\ -v --tb=short         # 详细 + 简洁错误回溯
python -m pytest ..\tests\ -q                    # 安静模式（只显示结果）


# ─── 按层级运行 ────────────────────────────────
python -m pytest ..\tests\test_path_tool.py ..\tests\test_config_handler.py ..\tests\test_file_handler.py ..\tests\test_logger_handler.py ..\tests\test_prompt_loader.py -v  # 工具层
python -m pytest ..\tests\test_factory.py ..\tests\test_models.py -v                                                                                                                                                              # 模型层
python -m pytest ..\tests\test_security.py ..\tests\test_response.py ..\tests\test_db.py ..\tests\test_dependencies.py -v                                                                                                         # 核心/数据/依赖层
python -m pytest ..\tests\test_history_store.py ..\tests\test_vector_store.py ..\tests\test_rag_service.py -v                                                                                                                      # 服务层
python -m pytest ..\tests\test_auth_router.py ..\tests\test_settings_router.py -v                                                                                                                                                 # 路由层
python -m pytest ..\tests\test_agent_tools.py ..\tests\test_middleware.py ..\tests\test_react_agent.py -v                                                                                                                          # Agent 层


# ─── 运行单个文件 ──────────────────────────────
python -m pytest ..\tests\test_factory.py -v


# ─── 运行单个测试类 ────────────────────────────
python -m pytest ..\tests\test_factory.py::TestDashScopeTextEmbeddingsCallApi -v


# ─── 运行单个测试方法 ──────────────────────────
python -m pytest ..\tests\test_factory.py::TestDashScopeTextEmbeddingsCallApi::test_batch_splits_when_exceeds_max -v


# ─── 运行匹配关键词的测试 ─────────────────────
python -m pytest ..\tests\ -v -k "history"       # 所有包含 "history" 的测试
python -m pytest ..\tests\ -v -k "config"        # 所有包含 "config" 的测试


# ─── 输出测试覆盖率报告 ───────────────────────
pip install pytest-cov
python -m pytest ..\tests\ --cov=app --cov-report=term-missing


# ─── 失败时立即停止 ────────────────────────────
python -m pytest ..\tests\ -v -x                 # 第一个失败就停
python -m pytest ..\tests\ -v --maxfail=3        # 最多 3 个失败就停


# ─── 只运行上次失败的测试 ─────────────────────
python -m pytest ..\tests\ --lf                  # --last-failed


# ─── 先运行上次失败的，再运行全部 ─────────────
python -m pytest ..\tests\ --ff                  # --failed-first
```

## 已知警告说明

运行全部测试时，你可能看到如下警告（均为第三方库内部问题，**不影响测试结果**，无需处理）：

```
DeprecationWarning: datetime.datetime.utcfromtimestamp() is deprecated
  _EPOCH_DATETIME_NAIVE = datetime.datetime.utcfromtimestamp(0)
```

**来源**：`protobuf==3.20.3`（项目依赖）使用了 Python 3.12+ 已弃用的 `utcfromtimestamp()` API，发生在模块导入阶段（早于任何测试代码执行）。

```
StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
```

**来源**：`fastapi.testclient`（TestClient）底层依赖 `httpx`，新版 starlette 推荐使用 `httpx2`，属框架演进提示，当前功能不受影响。

**如需手动抑制**（可选）：

```powershell
python -m pytest ..\tests\ -q -W "ignore::DeprecationWarning"
```

---

## 测试设计原则

1. **不修改业务代码**：所有测试只读被测模块，通过 mock 隔离外部依赖（DashScope API、Qdrant、MySQL、ChatTongyi）
2. **快速执行**：避免网络调用和磁盘 I/O 密集型操作，使用 `tempfile` 和 `unittest.mock`；路由测试使用 TestClient + `dependency_overrides`，不连接真实数据库
3. **独立性**：每个测试独立运行，不依赖其他测试的执行顺序或副作用
4. **清晰命名**：测试方法名精确描述被测行为和预期结果

## 当前测试统计

```
platform: win32
python:   3.13.0
pytest:   9.0.2
tests:    202 passed, 0 failed
```

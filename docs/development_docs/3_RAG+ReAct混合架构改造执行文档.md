# RAG + ReAct 混合架构改造执行文档

> 状态：**已确认，待实施**（第 12 节决策已由用户确认，按本文档实施）
> 范围：窄规则路由 + RAG 直调主路径 + 极简 ReAct 复杂任务通道 + 降级 + 可回放 trace + A/B 评测
> 原则：**最小侵入、可回滚、配置开关控制、不重写检索/精排核心算法**

---

## 0. 结论摘要

1. 当前主路径已核实：`POST /api/chat/messages` → `chat.send_message()` → `registry.get_rag_service().rag_summarize()`，**没有调用任何 ReAct Agent**。
2. 现有 ReAct 代码（`service/agent/react_agent.py`）基于 LangChain `create_agent`，仅被单元测试引用，属死代码；其工具 `rag_summarize` 只返回答案、丢弃检索片段，无法支撑“证据可追溯”的 ReAct。
3. 因此本次**不强行复用** `create_agent` 死代码，改为新写一个 200 行以内的极简 `while` 循环，复用现有 RAG 服务、检索链、模型工厂、历史存储与评测框架。
4. 评测集 v2 的真实结构是 260 道**单跳题**（fact 118 / term 54 / paraphrase 60 / longtail 28），多实体题 0 道，按复杂关键词粗筛仅 31 道且多为单跳。**不能假装从 260 题里直接标注出 20~30 道真复杂题**；本方案改为“从现有题中筛候选 + 基于同一 65 份语料补充构造 20~30 道复杂题（人工校验）”，并单列复杂集，避免污染原 260 题基线口径。
5. 对外 API 的请求/响应结构保持不变；仅新增可选 `traceId` 字段与受开关保护的调试 trace 接口。

---

## 1. 现状扫描（基于代码核实）

### 1.1 问答主链路

```
前端 ChatView.vue
  └─ POST /api/chat/messages  {conversationId, content}
       └─ backend/app/routers/chat.py::send_message
            ├─ 入库 user 消息、更新会话标题
            ├─ asyncio.to_thread(registry.get_rag_service().rag_summarize, content, session_id)
            │    └─ RagSummarizeService.rag_summarize
            │         ├─ get_chat_history(session_id).messages
            │         ├─ self.retriever.invoke(query)          # 混合检索 + 精排
            │         ├─ prompt_template | chat_model | StrOutputParser
            │         └─ 追加 Human/AI 历史，返回 (answer, retrieved_docs)
            ├─ build_citations_from_docs(docs)                 # 回答与引用同源
            └─ 入库 assistant 消息，返回 msg_to_dict(assistant_msg)
```

关键代码位置：

| 能力 | 文件 | 说明 |
|---|---|---|
| 问答入口 | `backend/app/routers/chat.py` | `send_message` 约 L184-L245；直调 RAG 在 L217-L221 |
| RAG 总结服务 | `backend/app/service/rag/rag_service.py` | `rag_summarize()` L52-L80，返回 `(answer, docs)` |
| RAG 单例注册表 | `backend/app/service/rag/registry.py` | 线程安全懒加载；settings 保存后可热重建 |
| 检索链路工厂 | `backend/app/service/rag/retrieval/hybrid_retriever.py` | `build_retriever()` L159-L236 |
| 当前检索参数 | `backend/app/config/retrieval_config.yml` | hybrid=true、rerank=true、top_k=5、legacy_k=3 |
| 模型工厂 | `backend/app/modelFactory/factory.py` | `chat_model` / `embed_model` 模块级单例 |
| 历史存储 | `backend/app/service/history/history_store.py` | 按 session_id 独立 JSON 文件 |
| 统一响应 | `backend/app/core/response.py` | `{code, message, data}` |

### 1.2 现有 ReAct 死代码

| 文件 | 内容 | 现状 |
|---|---|---|
| `backend/app/service/agent/react_agent.py` | `ReActAgent`，`create_agent(model, system_prompt, tools, middleware)`，`execute_stream()` | 全项目仅测试引用，业务入口未引用 |
| `backend/app/service/agent/tools/agent_tools.py` | 单工具 `rag_summarize(query)`，只返回 answer，丢弃 docs | 无法支撑多轮证据链 |
| `backend/app/service/agent/tools/middleware.py` | `monitor_tool` / `log_before_model` | 仅服务于死代码 |
| `backend/app/prompts/system_prompt.txt` | 旧 ReAct 系统提示词 | 仅被死代码加载，主路径未使用 |
| `tests/test_react_agent.py`、`tests/test_agent_tools.py`、`tests/test_middleware.py` | 死代码单测 | 保留，不做破坏性修改 |

结论：旧 ReAct 的 `create_agent` 封装较重、工具契约不满足“返回证据片段”，且当前主路径完全未接入。为满足“不引入重型 Agent 框架、最小侵入”，本次新写极简循环，**旧代码原样保留**，避免破坏既有 432 个单测。

### 1.3 评测框架现状

| 能力 | 文件 | 说明 |
|---|---|---|
| 评测编排 | `backend/app/service/eval/runner.py` | CLI；`--retrieval-only` / `--full`、`--preset`、`--limit`、`--dataset` |
| 评测集加载 | `backend/app/service/eval/dataset.py` | 字段：qid/question/ground_truth_answer/source_passage/source_file/question_type |
| 检索指标 | `backend/app/service/eval/metrics.py` | 文档级/片段级 HitRate、MRR、Precision、内容召回率 |
| 生成指标 | `backend/app/service/eval/llm_judge.py` | Faithfulness、AnswerRelevancy，固定评测模型、temperature=0 |
| 报告 | `backend/app/service/eval/report.py` | JSON + Markdown，输出 `backend/eval_reports/` |
| v2 评测集 | `backend/app/service/eval/datasets/eval_dataset_v2.json` | 260 题，65 份语料 |
| 当前基线 | `backend/eval_reports/20261026_183124_P4.md` | 文档级 HitRate 0.8115 / 片段级 0.7846 / 内容召回 0.7881（retrieval-only） |

**v2 题型分布（实测）**：fact 118、term 54、paraphrase 60、longtail 28。
**复杂度筛查（实测）**：`对比|比较|差异|分别|各自|预算|判断|计算|汇总` 等关键词仅命中 31 题，且多为“预算编制几月启动”这类单跳事实；同时包含两个及以上分支机构名的题 **0 道**。因此复杂集必须补充构造。

### 1.4 配置与运行方式

- 配置形态：YAML 文件 + 模块级加载（`backend/app/utils/config_handler.py`），环境变量用于模型凭据与模式。
- RAG 参数热更新：`routers/settings.py` 写 `retrieval_config.yml` 后同步内存并重建 RAG 单例。
- 启动：`backend` 目录下 `uv run`；测试在项目根目录 `pytest tests`（`tests/conftest.py` 自动加入 backend 路径）。
- 前端问答超时 300 秒（`frontend/src/api/chat.js`），新增 ReAct 延迟不会触发前端超时。

### 1.5 可复用的检索元数据

检索结果 `Document.metadata` 已有：`document_id`、`vector_id`（确定性 chunk ID）、`chunk_index`、`section_path`、`page_start`、`page_end`、`rerank_score` 或 `bm25_score`。工具契约中的 `doc_id/chunk_id/score` 可直接映射，无需改检索层。

### 1.6 现状改造风险

| 风险 | 说明 | 对策 |
|---|---|---|
| 历史被污染 | `rag_summarize` 每次调用都会写会话历史；ReAct 内部多次检索会把子查询写进历史 | 给 `rag_summarize` 增加可选 `write_history=True` 参数，工具调用传 `False`；外部默认行为不变 |
| 简单问题误触发 | 规则过宽会让 FAQ 也进 ReAct，延迟退化 | 规则分级（强/弱），默认阈值；简单查询默认 `rag_direct`；单测覆盖 |
| 超时无法强杀线程 | 同步 LLM/工具调用在线程中无法被强制终止 | 用 deadline + `future.result(timeout)` 控制等待；超时立即降级，后台线程自行结束；文档明确限制 |
| 多进程 trace 不共享 | 调试接口若用内存缓存，多 worker 下可能查不到 | trace 同步落 JSONL，内存缓存仅作加速；文档说明 |
| 评测成本 | 260 题全量生成评测耗时 | A/B 支持 `--limit`、分层子集、先跑 10+10 smoke |

---

## 2. 目标架构

### 2.1 总体链路

```
用户问题 + 会话上下文
        │
        ▼
┌───────────────────┐    ENABLE_HYBRID_ROUTER=false
│  Router（规则）    │──────────────────────────────┐
└─────────┬─────────┘                              │
          │ route=rag_direct                       │
          │ route=react_complex                    │
          ▼                                        ▼
┌───────────────────┐                    ┌───────────────────┐
│ RAG 直调路径       │                    │ 极简 ReAct 循环    │
│ 现有 rag_summarize │                    │ max_steps=3        │
│ 行为完全不变        │                    │ 超时/超轮次/工具失败│
└─────────┬─────────┘                    │ → 降级回 RAG 直调  │
          │                              └─────────┬─────────┘
          └──────────────┬─────────────────────────┘
                         ▼
              答案 + 引用 + trace
```

### 2.2 设计边界（明确不做）

- 不做多 Agent 协作、长期记忆、复杂规划、自动工具发现。
- 不做 LLM 路由分类器 / 向量路由，路由只用可配置规则。
- 不让所有请求进 ReAct；简单/单跳/FAQ 默认直调。
- 不改检索、精排核心算法；只做编排层与工具层接入。
- 不引入新的重型 Agent 框架；不改造旧 `react_agent.py`。

---

## 3. 关键设计

### 3.1 Router（窄规则路由）

**输入**：`query`，可选 `context`（当前会话最近若干条消息，仅用于规则判断，不改变检索）。
**输出**：

```json
{
  "route": "rag_direct | react_complex",
  "reason": "命中 compare + multi_entity，总分 3 ≥ 阈值 2",
  "matched_rules": ["compare", "multi_entity"],
  "score": 3
}
```

**规则配置**：`backend/app/config/router_rules.yml`，不硬编码在业务代码中。

```yaml
version: 1
threshold: 2                 # 弱规则累计达到该分值才进 ReAct
rules:
  - id: compare
    description: 对比/比较/差异类
    pattern: '对比|比较|差异|区别|分别|各自|哪个更|哪一个更|结合.*和|相比'
    weight: 2
    strong: true
  - id: multi_entity
    description: 多实体/多文档
    pattern: '(上海|北京|成都|深圳|苏州|杭州|南京|武汉|西安|重庆|广州|天津).*(上海|北京|成都|深圳|苏州|杭州|南京|武汉|西安|重庆|广州|天津)|《[^》]+》.*《[^》]+》|第[一二三四五六七八九十0-9]+条.*第[一二三四五六七八九十0-9]+条'
    weight: 2
    strong: true
  - id: condition_calc
    description: 条件组合/计算
    pattern: '是否满足|能否|根据.*和.*判断|计算|预算|差值|汇总|合计|加总|折算|占比'
    weight: 1
    strong: false
  - id: tool_chain
    description: 明确要求多步工具链
    pattern: '先.*再.*(判断|建议|给建议)|查.*再.*判断|分别查|逐一核对|交叉校验'
    weight: 2
    strong: true
  - id: conflict
    description: 制度冲突判断
    pattern: '冲突|矛盾|不一致|以哪个为准|哪个优先|是否违背'
    weight: 2
    strong: true
```

**判定逻辑**：
1. 遍历启用的规则，正则命中则累加 `weight` 并记录 `matched_rules`。
2. 任一 `strong=true` 规则命中，或总分 ≥ `threshold`，则 `route=react_complex`。
3. 否则 `route=rag_direct`，`reason` 记录“未命中复杂规则”。
4. 规则文件加载失败时，**保守回退** `rag_direct` 并记录告警，保证可用性。
5. 规则支持环境变量 `ROUTER_RULES_PATH` 覆盖路径。

**为什么这样能避免误触发**：单跳题如“公司年假多少天”不命中任何规则；单命中“预算”这类弱规则（1 分）低于阈值 2；只有“对比 + 多实体”或明确的“先查再判断”才进 ReAct。

### 3.2 RAG 直调路径（保持现状）

- 继续调用 `RagSummarizeService.rag_summarize(query, session_id)`，检索、生成、历史写入行为不变。
- 仅在编排层加埋点：route、route_reason、耗时、是否降级。
- `ENABLE_HYBRID_ROUTER=false` 时，编排器直接走该路径，trace 仍记录 `route=rag_direct`，**答案、引用、历史副作用与改造前一致**。

### 3.3 极简 ReAct 循环

**位置**：`backend/app/service/agent/simple_react.py`（与现有 agent 包同风格）。
**提示词**：`backend/app/prompts/react_complex.txt`。
**解析器**：`backend/app/service/agent/react_parser.py`。

**循环伪代码**：

```python
deadline = now + timeout_ms
for step in range(1, max_steps + 1):
    if now > deadline: fallback("timeout")
    raw = chat_model.invoke(prompt_with_history_and_observations)
    decision = parse_json(raw)            # 失败即 fallback("parse_error")
    if decision.action == "final_answer":
        if not decision.answer: fallback("empty_answer")
        if not has_evidence(): fallback("no_evidence")
        return answer
    if decision.action not in tools:      # 不允许的 action
        observations.append(error_observation); continue
    result = call_tool_with_timeout(...)  # 失败累计，连续 2 次失败 fallback
    observations.append(result)
fallback("max_steps_exceeded")
```

**每轮模型输出结构**（严格 JSON，解析器容错 markdown 代码块）：

```json
{
  "thought": "需要先查出差旅报销标准，再与招待费标准对比",
  "action": "rag_search",
  "action_input": {"query": "差旅费用报销标准", "top_k": 5}
}
```

最终轮：

```json
{"thought": "已获得两边标准，可以给出对比结论", "action": "final_answer", "action_input": {"answer": "..."}}
```

**硬约束**：
- `max_steps=3`，包含工具调用轮；第 3 轮仍无 `final_answer` 即降级。
- 总超时 `REACT_TIMEOUT_MS`，默认 30000（30s）；每次模型/工具调用前检查剩余时间。
- 空 action、未知 action、参数非法、工具异常：记为 observation 并计数；连续 2 次工具失败降级。
- 模型输出无法解析：直接降级（不猜测、不重试，避免额外延迟）。
- 最终答案必须非空，且**至少有一次成功工具 observation**，否则视为“无证据”降级。
- 提示词明确要求：优先用工具取证，不得编造；最终答案只基于 observation。

### 3.4 工具契约

#### Tool 1：`rag_search`

```json
输入: {"query": "string", "top_k": 5}
输出: {
  "passages": [{"doc_id": 3, "chunk_id": "uuid5...", "text": "...", "score": 0.83}],
  "summary": "..."
}
```

- 实现：复用现有 `RagSummarizeService` 的检索链与生成链。
- 新增 `RagSummarizeService.retrieve(query)`：只检索，返回 `list[Document]`。
- 新增 `RagSummarizeService.summarize(query, docs, session_id=None, write_history=False)`：只生成。
- `rag_search` 调用 `retrieve` + `summarize`，**不写会话历史**，避免子查询污染多轮对话。
- `doc_id` 取 `metadata.document_id`；`chunk_id` 取 `metadata.vector_id`；`score` 依次取 `rerank_score` → `bm25_score` → 无则 `null`。
- `top_k` 限制在 1~10，默认取当前链路有效输出 k（当前 5）。
- 统一超时 `TOOL_TIMEOUT_MS`，异常包装为 `{"error": "...", "passages": []}`，不向循环抛未捕获异常。

#### Tool 2：`compare_calc`

```json
输入: {
  "operation": "compare | diff | sum | condition_check",
  "items": [
    {"label": "上海差旅标准", "text": "...", "value": 500, "source": "doc:3#chunk:..."}
  ],
  "criteria": {"field": "value", "operator": "gt", "value": 300}
}
输出: {
  "result": {...},
  "evidence": [{"label": "...", "text": "...", "source": "..."}],
  "explanation": "..."
}
```

- 最小实现，不接 LLM：
  - `compare`：按 `criteria.field` 比较各 item；输出差异表与极值。
  - `diff`：对两个 `text` 使用 `difflib.SequenceMatcher`，输出相似度与差异片段。
  - `sum`：对 `value` 求和，支持 `criteria.unit` 仅作回显。
  - `condition_check`：支持 `gt/gte/lt/lte/eq/ne/contains`，逐项返回 `pass/fail`。
- 参数非法返回结构化错误；不做自然语言理解，自然语言到结构化 items 的转换由 ReAct 模型完成。
- 纯函数实现，便于单测，无外部依赖。

### 3.5 降级策略

路由到 `react_complex` 后，以下任一情况降级回 RAG 直调：

| 触发条件 | `fallback_reason` |
|---|---|
| 超过 `max_steps` | `max_steps_exceeded` |
| 总超时 | `timeout` |
| 连续 2 次工具失败 | `tool_failed` |
| 模型输出无法解析 / 非法 action 且无法继续 | `parse_error` |
| 最终答案为空 | `empty_answer` |
| 最终答案无任何工具证据 | `no_evidence` |
| ReAct 内部未捕获异常 | `internal_error` |

- 降级时调用 `rag_summarize(query, session_id)`，用户拿到与改造前一致的答案与引用。
- 降级不向用户抛错；trace 记录 `fallback=true`、原因、降级耗时。
- `ENABLE_REACT_FALLBACK=false` 时，降级只记录错误并返回“当前无法完成复杂分析”，**默认 true**。

### 3.6 trace 与可观测性

**trace 结构**（同步返回给编排器，不依赖全局状态）：

```json
{
  "trace_id": "8f3c...",
  "query": "...",
  "route": "react_complex",
  "route_reason": "...",
  "matched_rules": ["compare", "multi_entity"],
  "steps": [
    {
      "step": 1,
      "thought": "...",
      "action": "rag_search",
      "action_input": {"query": "..."},
      "observation": {"passages": [{"doc_id": 3, "chunk_id": "...", "text_preview": "..."}]},
      "elapsed_ms": 1234
    }
  ],
  "tool_calls": 2,
  "fallback": false,
  "fallback_reason": null,
  "answer_source": "react | rag_direct | rag_direct_fallback",
  "total_ms": 5678,
  "started_at": "2026-10-28T12:00:00+08:00"
}
```

**记录方式**：
- `backend/app/service/observability/trace.py`：`Trace` 数据类 + `TraceRecorder`。
- 每次请求生成 `trace_id`；步骤级记录 thought/action/action_input/observation/耗时。
- `LOG_TRACE_LEVEL=off|summary|full`：`summary` 只记录路由、工具次数、降级、总耗时；`full` 记录每轮细节。
- 文档正文截断：observation 中 `text` 最多保留 `OBS_TEXT_MAX_CHARS`（默认 200）字符，避免日志泄露全文。
- 落盘：`backend/logs/traces/YYYYMMDD.jsonl`，每行一条 JSON，便于回放。
- 内存环形缓存（默认 200 条）供调试接口快速查询；多 worker 下以 JSONL 为准。
- 调试接口：`GET /api/debug/trace/{trace_id}`，仅 `ENABLE_TRACE_API=true` 时注册/可用；生产默认 false。
- 用户响应默认不返回 trace；`RETURN_TRACE_TO_CLIENT=true` 时在 assistant 消息对象中附加 `traceId`（可选字段，不破坏旧前端）。

### 3.7 配置项

新增 `backend/app/config/hybrid_config.yml`（所有配置有默认值与注释）：

```yaml
ENABLE_HYBRID_ROUTER: true        # 总开关；false 时全部走 RAG 直调，行为与改造前一致
REACT_MAX_STEPS: 3                # ReAct 最大轮次
REACT_TIMEOUT_MS: 30000           # ReAct 总超时（30s，已确认）
TOOL_TIMEOUT_MS: 10000            # 单次工具超时（10s，已确认）
ENABLE_REACT_FALLBACK: true       # 失败是否降级回 RAG 直调
ROUTER_RULES_PATH: config/router_rules.yml
LOG_TRACE_LEVEL: summary          # off | summary | full
OBS_TRACE_DIR: logs/traces        # trace JSONL 落盘目录
OBS_TEXT_MAX_CHARS: 200           # observation 文本截断长度
ENABLE_TRACE_API: false           # 是否开放调试 trace 接口
RETURN_TRACE_TO_CLIENT: false     # 是否在用户响应中返回 traceId
COMPARE_CALC_MAX_ITEMS: 20        # compare_calc 最大 item 数
```

- 环境变量同名覆盖 YAML（便于容器部署），读取优先级：环境变量 > YAML > 代码默认值。
- 配置加载集中在 `backend/app/utils/config_handler.py` 新增 `load_hybrid_config()` 与 `hybrid_conf`，沿用现有风格。
- 代码兜底默认 `ENABLE_HYBRID_ROUTER=false`（配置缺失时安全回退）；随仓库提供的 `hybrid_config.yml` 默认 `true`，便于开发/演示。
- `ENABLE_HYBRID_ROUTER` 在每次请求时读取生效值（支持测试 monkeypatch），不依赖重启。

---

## 4. 对外 API 兼容性

### 4.1 保持不变

- `POST /api/chat/messages` 请求体仍是 `{conversationId, content}`。
- 响应仍是 `{code, message, data: {id, role, content, citations, createdAt}}`。
- 引用来源字段、会话 CRUD、文档接口、设置接口、评测 CLI 参数全部不变。

### 4.2 可选新增

| 新增项 | 默认 | 说明 |
|---|---|---|
| `data.traceId` | 不返回 | `RETURN_TRACE_TO_CLIENT=true` 时附加；旧前端忽略未知字段即可 |
| `GET /api/debug/trace/{trace_id}` | 不开放 | `ENABLE_TRACE_API=true` 时可用；返回内存/JSONL 中的 trace |
| `GET /api/debug/hybrid-config` | 不开放 | 可选，返回当前 hybrid 配置快照，便于答辩演示 |

### 4.3 关闭开关时的等价性

`ENABLE_HYBRID_ROUTER=false`：

- 不加载路由规则、不构建 ReAct 循环、不触发工具。
- `chat.send_message` 走与当前完全相同的 `rag_summarize` 调用，返回结构与历史写入一致。
- trace 仍记录 `route=rag_direct`、`answer_source=rag_direct`、总耗时，但 `LOG_TRACE_LEVEL` 可设为 `off` 完全静默。

---

## 5. 文件变更清单

### 5.1 新增文件

| 文件 | 作用 | 关键内容 |
|---|---|---|
| `backend/app/config/hybrid_config.yml` | 混合架构配置 | 开关、轮次、超时、trace、工具限制 |
| `backend/app/config/router_rules.yml` | 路由规则 | 规则 id/pattern/weight/strong/threshold |
| `backend/app/prompts/react_complex.txt` | ReAct 提示词 | 只允许 2 个工具 + final_answer；强制 JSON；禁止编造 |
| `backend/app/prompts/correctness_judge.txt` | 答案正确率裁判提示词 | 输入问题/标准答案/模型答案，输出 0/0.5/1 三档 JSON |
| `backend/app/service/routing/__init__.py` | 路由包 | 导出 `RuleRouter`、`RouteDecision` |
| `backend/app/service/routing/rule_router.py` | 规则路由 | 加载 YAML、正则匹配、强/弱规则判定、失败保守回退 |
| `backend/app/service/agent/react_parser.py` | ReAct 输出解析 | 容错 markdown/前后杂文，校验 action 与 action_input |
| `backend/app/service/agent/simple_react.py` | 极简 ReAct 循环 | while + 工具字典 + deadline + 降级信号 |
| `backend/app/service/agent/tools/tool_registry.py` | 工具注册表 | 名称→可调用对象的白名单注册，统一超时/异常包装 |
| `backend/app/service/agent/tools/rag_search_tool.py` | RAG 检索/总结工具 | 复用 `RagSummarizeService`，返回 passages + summary，不写历史 |
| `backend/app/service/agent/tools/compare_calc_tool.py` | 对比/计算工具 | compare/diff/sum/condition_check 纯函数 |
| `backend/app/service/observability/__init__.py` | 可观测包 | 导出 `Trace`、`TraceRecorder` |
| `backend/app/service/observability/trace.py` | trace 记录 | trace_id、步骤、截断、JSONL 落盘、内存缓存 |
| `backend/app/service/orchestration/__init__.py` | 编排包 | 导出 `HybridOrchestrator`、`OrchestrationResult` |
| `backend/app/service/orchestration/hybrid_orchestrator.py` | 混合编排入口 | route → 直调/ReAct → 降级 → trace；开关关闭时纯直调 |
| `backend/app/routers/debug.py` | 调试接口（可选） | `GET /api/debug/trace/{trace_id}`，受开关保护 |
| `backend/app/service/eval/complex_subset.py` | 复杂题筛选辅助 | 按规则从 v2 题集筛候选、读取人工确认的 qid 列表 |
| `backend/app/service/eval/datasets/complex_qids_v2.json` | 复杂题 qid 清单 | 人工确认 20~30 条（从现有题筛 + 补充题） |
| `backend/app/service/eval/datasets/eval_complex_authored_v2.json` | 补充复杂题集 | 若现有题不足，新增 20~30 道跨文档/条件/计算题 |
| `backend/app/service/eval/hybrid_runner.py` | A/B 对照评测 | A=全直调，B=路由混合；输出 JSON/CSV/Markdown |
| `tests/test_rule_router.py` | 路由单测 | 四类规则、阈值、误触发、配置加载失败回退 |
| `tests/test_react_parser.py` | 解析单测 | 正常 JSON、markdown、非法 action、空输入 |
| `tests/test_simple_react.py` | 循环单测 | final_answer、超轮次、超时、工具失败、无证据 |
| `tests/test_compare_calc_tool.py` | 工具单测 | 四种操作、非法参数、证据回传 |
| `tests/test_rag_search_tool.py` | 工具单测 | passages 映射、不写历史、超时/异常包装 |
| `tests/test_hybrid_orchestrator.py` | 编排/降级单测 | 开关关闭等价、简单直调、复杂成功、各降级原因 |
| `tests/test_trace.py` | trace 单测 | 字段完整性、截断、JSONL 写入 |
| `tests/test_hybrid_eval.py` | A/B 评测单测 | 分组选择、指标聚合、CSV 输出（全 mock） |
| `docs/development_docs/RAG+ReAct混合架构说明.md` | 比赛/答辩版架构说明 | 架构图、配置、demo、已知限制；评测细节引用 eval README |

### 5.2 修改文件（最小改动）

| 文件 | 修改点 | 兼容性 |
|---|---|---|
| `backend/app/service/rag/rag_service.py` | 抽出 `retrieve()` / `summarize()`；`rag_summarize()` 改为组合调用，新增可选 `write_history=True` | 默认参数不变，现有调用与单测不受影响 |
| `backend/app/routers/chat.py` | 直调改为 `HybridOrchestrator.answer()`；仍在线程池执行；可选附加 `traceId` | 响应结构不变；无新增必填字段 |
| `backend/app/utils/config_handler.py` | 新增 `load_hybrid_config()` / `hybrid_conf` | 纯新增 |
| `backend/app/main.py` | 按开关注册 debug 路由（可选） | 默认不注册，不影响现有路由 |
| `backend/app/service/eval/runner.py` | 可选：复用新 `dataset_md5` 等，不改变现有 CLI | 不改行为 |
| `backend/app/service/eval/llm_judge.py` | 新增 `correctness()` 与 `aggregate_correctness()` | 纯新增，不影响 faithfulness/relevancy |
| `backend/app/config/prompts_config.yml` | 新增 `correctness_judge_prompt_path` | 纯新增键 |
| `README.md` | **仅**新增 RAG+ReAct 混合架构图与新增配置项简述；不写评测方法/指标/对照实验 | 不改变现有章节结构 |
| `backend/app/service/eval/README.md` | 新增 A/B 分层评测说明、复杂集构造、命令、指标、错误分析 | 评测信息统一归口 |
| `tests/README.md` | 更新测试目录一览、覆盖层级、测试统计与运行命令（新增 8 个测试文件） | 同步真实用例数 |
| `docs/接口JSON契约文档.md` | 补充可选 `traceId` 与 debug 接口 | 可选字段 |

### 5.3 明确不改动

- `backend/app/service/agent/react_agent.py`、`agent_tools.py`、`middleware.py`：保留为历史代码，不删除、不改造，避免破坏既有测试。
- `backend/app/service/rag/retrieval/**`：检索、融合、精排核心算法一行不改。
- `backend/app/service/eval/metrics.py`、`report.py`：指标口径不改，A/B 复用。
- `backend/app/service/eval/llm_judge.py`：只新增 `correctness()`，现有 faithfulness/relevancy 逻辑不改。
- `frontend/**`：不改前端；`traceId` 是可选字段。
- 现有 260 题评测集：不修改，复杂集单列，保证基线口径可追溯。

### 5.4 文档更新分工

| 文档 | 允许写入 | 禁止写入 |
|---|---|---|
| 根目录 `README.md` | 更新现有 2.4「RAG 检索链路架构」图（增加窄路由/ReAct 分支）与 3.4.2 配置项简述、一键关闭方式；**不新增章节** | 评测方法、A/B 指标、复杂集构造、错误分析等评测内容；不改动现有 2.4 的评测结论段落 |
| `backend/app/service/eval/README.md` | A/B 分层评测流程、复杂集筛选与补充、命令、指标口径、降级分布、5 类错误分析 | 与评测无关的架构说明 |
| `tests/README.md` | 新增测试文件清单、层级归属、用例统计、运行命令 | 评测实验结论 |
| `docs/development_docs/RAG+ReAct混合架构说明.md` | 架构图、配置、demo 步骤、已知限制 | 详细评测数据（引用 eval README 即可） |

---

## 6. 实施步骤

### 阶段 P0：骨架与配置（不改主路径）

1. 新增 `hybrid_config.yml`、`router_rules.yml`、`react_complex.txt`。
2. 新增 `rule_router.py` 与 `test_rule_router.py`，先跑通规则单测。
3. 新增 `trace.py` 与 `test_trace.py`，明确字段结构。

### 阶段 P1：RAG 服务拆分（保持外部行为）

1. `RagSummarizeService` 抽出 `retrieve()`、`summarize()`，`rag_summarize()` 组合调用。
2. 新增 `write_history` 可选参数，默认 True。
3. 跑 `tests/test_rag_service.py`、`tests/test_citations.py`，确认零回归。

### 阶段 P2：工具层

1. `rag_search_tool.py`：复用 registry 取服务，映射 doc_id/chunk_id/score，不写历史。
2. `compare_calc_tool.py`：四种操作 + 参数校验。
3. `tool_registry.py`：白名单注册 + 统一超时/异常包装。
4. 完成工具单测。

### 阶段 P3：极简 ReAct 循环

1. `react_parser.py`：严格 JSON 解析 + 校验。
2. `simple_react.py`：轮次、deadline、工具失败计数、证据检查、返回结构化结果或降级信号。
3. 完成循环单测（mock 模型与工具，不触网）。

### 阶段 P4：编排与主路径接入

1. `hybrid_orchestrator.py`：开关判断 → 路由 → 直调/ReAct → 降级 → trace。
2. `chat.py` 改调用编排器；保留线程池；保证响应结构。
3. 完成编排/降级单测与开关等价性测试。

### 阶段 P5：评测与文档

1. 复杂题筛选与补充；生成 `complex_qids_v2.json`。
2. `hybrid_runner.py`：A/B 分组、指标、CSV/JSON、报告。
3. 跑 smoke：10 简单 + 10 复杂；能跑全量则跑全量。
4. 按 5.4 更新文档：README（仅架构图+配置简述）、eval README（A/B 评测）、tests README（新测试），另输出答辩版架构说明与已知限制。

### 回滚策略

- 一键关闭：`ENABLE_HYBRID_ROUTER=false`，行为回到改造前。
- 代码回滚：新增文件独立，主路径仅 `chat.py` 一处调用变更 + `rag_service.py` 可选参数；回滚只需还原这两个文件。
- 配置回滚：删除 `hybrid_config.yml` 时加载器使用代码默认值，默认 `ENABLE_HYBRID_ROUTER=false`（安全兜底），部署时显式开启。

---

## 7. 测试计划

### 7.1 单元测试（离线，不依赖 Qdrant/MySQL/LLM）

| 测试文件 | 覆盖点 | 关键断言 |
|---|---|---|
| `tests/test_rule_router.py` | 四类规则、阈值、强规则、误触发 | 简单 FAQ → `rag_direct`；“上海和北京的差旅标准对比” → `react_complex`；仅“预算” → `rag_direct`；规则文件缺失 → `rag_direct` |
| `tests/test_react_parser.py` | JSON、markdown 包裹、前后杂文、非法 action、空输入 | 正常解析；非法输出返回 `None`；`action_input` 类型校验 |
| `tests/test_simple_react.py` | 成功、超轮次、超时、工具失败、无证据、解析失败 | 每种情况返回正确的 `fallback_reason`；max_steps=3 生效 |
| `tests/test_compare_calc_tool.py` | compare/diff/sum/condition_check、非法参数、超 item 数 | 结果与 evidence 正确；非法 operation 返回结构化错误 |
| `tests/test_rag_search_tool.py` | passages 映射、top_k 边界、不写历史、异常包装 | `doc_id/chunk_id/score` 映射正确；`write_history=False` 被传入 |
| `tests/test_hybrid_orchestrator.py` | 开关关闭等价、简单直调、复杂成功、各降级原因 | 关闭时只调用一次 `rag_summarize`；降级后仍返回答案；trace 字段完整 |
| `tests/test_trace.py` | 字段完整性、文本截断、JSONL 落盘、缓存淘汰 | 不含超长正文；trace_id 唯一 |
| `tests/test_hybrid_eval.py` | A/B 分组、指标聚合、CSV 输出 | 复杂题走 B 组 ReAct，简单题两组都直调 |

### 7.2 回归测试

- 全量运行现有 432 个单测：`pytest tests -q`。
- 重点回归：`test_rag_service.py`、`test_citations.py`、`test_react_agent.py`、`test_agent_tools.py`、`test_middleware.py`、`test_eval_runner.py`。
- 验收“关闭开关等价”：单测中固定 `ENABLE_HYBRID_ROUTER=false`，断言 `chat.send_message` 的 RAG 调用参数与改造前一致。

### 7.3 集成/smoke 测试（需要真实服务）

前置：MySQL、Qdrant、模型 API 可用，65 份语料已入库。

1. 简单 query（如“公司的年假有多少天？”）→ 断言 `route=rag_direct`，响应结构不变，延迟与基线同量级。
2. 复杂 query（如“对比上海总部和北京分公司的差旅住宿标准，并计算 3 天出差两地差额”）→ 断言 `route=react_complex`，trace 含至少 2 次工具调用与 `final_answer`。
3. 降级演示：将 `REACT_TIMEOUT_MS` 临时调为 1，或 mock 工具抛错 → 断言 `fallback=true`、`fallback_reason` 有值、用户仍收到 RAG 答案。

---

## 8. A/B 对照评测方案

### 8.1 复杂集构建（基于真实数据情况的调整）

**实测结论**：v2 的 260 题中，多实体题 0 道；复杂关键词仅粗筛出 31 道，人工复核后预计真复杂题不足 20 道。因此采用两步：

1. **从现有题筛候选**：`complex_subset.py` 用 `router_rules.yml` 规则扫描 260 题，输出候选清单（预计 20~31 道），人工复核，保留真正的多跳/对比/条件/计算题。
2. **补充构造复杂题**：若现有题不足 20 道，基于**同一 65 份语料**补充 15~20 道，人工校验后写入 `eval_complex_authored_v2.json`，题型示例如下：
   - 跨文档对比：上海总部与北京分公司的差旅住宿标准差异；
   - 条件组合：某员工同时满足出差 3 天、住宿 2 晚、餐补标准，合计可报销多少；
   - 制度冲突：两版信息安全制度对“机密级”定义是否一致，以哪个为准；
   - 数值计算：采购金额分档与审批权限组合判断；
   - 多跳：先查某制度适用范围，再判断某类人员是否适用。
3. 复杂集合计 20~30 道，单列文件，**不修改原 260 题**；简单集使用原 260 题（或剔除已选复杂题的剩余题），保证基线口径不变。

### 8.2 分组

| 组 | 路由 | 用途 |
|---|---|---|
| A（baseline） | 强制 `rag_direct` | 复现改造前行为，作为对照 |
| B（hybrid） | 规则路由：简单直调、复杂 ReAct | 验证混合架构收益 |

### 8.3 指标

| 指标 | 简单集 | 复杂集 |
|---|---|---|
| 文档级/片段级 HitRate@K | ✅ | ✅ |
| 答案正确率（LLM 裁判对比标准答案） | ✅ | ✅ |
| 平均延迟 / P95 延迟 | ✅ | ✅ |
| 任务完成率（复杂题是否给出完整结论） | — | ✅ |
| 平均工具调用次数 | — | ✅ |
| 降级率 / `fallback_reason` 分布 | — | ✅ |
| Faithfulness / AnswerRelevancy | ✅ | ✅ |

> 答案正确率：新增 `prompts/correctness_judge.txt` 与 `llm_judge.correctness()`，输入问题、标准答案、模型答案，输出 0/0.5/1 三档；复用现有“解析失败不计均值”的口径。该改动为纯新增，不影响现有 faithfulness/relevancy 指标。

### 8.4 输出与命令

```bash
# 在 backend 目录下；runner 默认读取：
#   simple  = datasets/eval_dataset_v2.json
#   complex = datasets/complex_qids_v2.json（从 260 题筛出）
#             + datasets/eval_complex_authored_v2.json（补充构造）
# A 组：全部直调（baseline）
uv run python -m app.service.eval.hybrid_runner --tag AB-A --group A

# B 组：混合路由
uv run python -m app.service.eval.hybrid_runner --tag AB-B --group B

# 快速 smoke（10 简单 + 10 复杂，不跑全量）
uv run python -m app.service.eval.hybrid_runner --tag AB-smoke --group both --limit-simple 10 --limit-complex 10
```

输出：
- `backend/eval_reports/{时间戳}_{tag}.json`：逐题明细（route、trace 摘要、答案、指标、延迟）。
- `backend/eval_reports/{时间戳}_{tag}.csv`：便于比赛材料做表。
- `backend/eval_reports/{时间戳}_AB-compare.md`：A/B 指标对照、降级分布、错误分析。

### 8.5 错误分析（至少 5 条）

按以下类别各给真实例子与改法，写入 A/B 报告：

| 类别 | 记录内容 | 可能改法 |
|---|---|---|
| 检索未命中 | query、gold doc、Top-K 文档 | 规则未触发/召回不足，调整 Router 或检索参数（不改算法） |
| 排序靠后 | 命中但排名 > K | 精排候选数/查询措辞，或 ReAct 二次检索 |
| 片段噪声 | 命中文档但片段无关 | 提示词约束、top_k、chunk 参数 |
| 多跳未分解 | 只查到一个实体 | 改进 ReAct 提示词与规则，强制分步检索 |
| 答案幻觉 | 答案含 observation 外内容 | 强化提示词“仅基于 observation”，失败即降级 |

### 8.6 时间不足时的最低验收

- 1 条复杂 query 触发 ReAct 并输出完整 trace；
- 1 条简单 query 走直调且延迟与基线同量级；
- 降级路径可演示（超时/超轮次/工具失败任一）。

---

## 9. 验收标准

| # | 验收项 | 判定方式 |
|---|---|---|
| 1 | 关闭 `ENABLE_HYBRID_ROUTER` 行为与改造前一致 | 单测 + 手工对比响应/历史文件 |
| 2 | 简单查询默认 `rag_direct` | 路由单测 + smoke |
| 3 | 复杂查询进入 ReAct，最多 3 轮，工具调用有日志 | trace/smoke |
| 4 | 超时/超轮次/工具失败降级，用户无感 | 降级单测 + smoke |
| 5 | 展示完整 trace：route_reason → thought → action → observation → final_answer | debug 接口或 JSONL |
| 6 | 路由、解析、降级、工具契约单测齐全 | `pytest tests -q` |
| 7 | A/B 对照或 10+10 smoke 跑通 | 报告 JSON/CSV/Markdown |
| 8 | 文档更新到位：README 仅含架构图+配置简述；eval README 含 A/B；tests README 含新测试 | 文档 review |

---

## 10. 交付物

1. 本执行文档（已输出到项目根目录）。
2. 代码实现：配置、路由、ReAct、工具、编排、trace、测试。
3. 一条简单 query 与一条复杂 query 的运行示例 + 完整 trace（JSONL/控制台输出）。
4. A/B 对照结果；若时间不足则 10+10 smoke 结果。
5. 答辩版架构说明：`docs/development_docs/RAG+ReAct混合架构说明.md`，核心表述为：
   > RAG 直调为主路径，ReAct 为复杂任务可选增强，设轮次上限、超时降级与可回放 trace。
6. 文档同步：
   - 根目录 `README.md`：仅混合架构图 + 新增配置项简述；
   - `backend/app/service/eval/README.md`：A/B 评测方案、命令、指标与错误分析；
   - `tests/README.md`：新增测试文件与用例统计。
7. 已知限制与后续改进建议（见第 11 节）。

---

## 11. 已知限制与后续改进

### 11.1 已知限制

1. **复杂评测集不是原生基准**：v2 以单跳题为主，复杂题包含人工补充，需在报告中明确标注来源，不能宣称是官方 260 题原生结果。
2. **规则路由的覆盖有限**：正则无法理解所有语义变体；规则文件需随业务语料迭代。未采用 LLM/向量路由是刻意选择（成本、可解释性、稳定性）。
3. **超时不能强杀线程**：同步 LLM/工具调用超时后主流程立即降级，但后台线程可能继续运行至自然结束，存在少量资源占用。
4. **trace 多进程不共享**：内存缓存只在单 worker 内有效；多 worker 部署以 JSONL 回放为准。
5. **ReAct 依赖模型 JSON 输出稳定性**：解析失败即降级，复杂题可能因此回退到直调。
6. **compare_calc 不做自然语言理解**：复杂语义到结构化 items 的转换由模型完成，模型抽取错误会导致计算结果偏差。
7. **引用来源范围**：ReAct 路径的引用来自各次 `rag_search` 的成功证据片段并去重，不保证覆盖最终答案的每一句。

### 11.2 后续改进

- 规则路由增加同义词/实体词典配置，降低维护成本。
- 引入“路由结果离线回放”脚本，用历史 query 评估误触发率。
- 为复杂集建立人工标注规范与双人复核，逐步扩展。
- 在不引入重型框架的前提下，增加工具调用结果缓存，降低重复检索成本。
- 若未来要上语义路由，先离线对比规则路由的误触发率与延迟，再决定是否替换。

---

## 12. 已确认事项（2026-10-28）

1. **复杂集方案：同意**。采用“现有题筛候选 + 同一 65 份语料补充构造 20~30 道”，单列复杂集，不修改原 260 题。
2. **默认开关：同意**。随仓库的 `hybrid_config.yml` 默认 `ENABLE_HYBRID_ROUTER=true`；代码兜底默认 `false`；生产可通过环境变量关闭。
3. **trace 暴露：同意**。调试接口默认关闭；答辩/演示环境显式开启 `ENABLE_TRACE_API=true`，并按需开启 `RETURN_TRACE_TO_CLIENT=true`。
4. **答案正确率裁判：同意**。新增 `correctness_judge.txt` 与 `llm_judge.correctness()`，三档 0/0.5/1，仅用于 A/B 报告，不改现有指标口径。
5. **超时参数：已调整**。`REACT_TIMEOUT_MS=30000`（30s）、`TOOL_TIMEOUT_MS=10000`（10s）。

### 12.1 文档更新口径（已确认）

- 根目录 `README.md` **只**更新 RAG+ReAct 混合架构图与新增配置项简单说明，不写入评测方法、A/B 指标、复杂集构造、错误分析等内容。
- 所有评测相关内容统一写入 `backend/app/service/eval/README.md`。
- `tests/README.md` 同步更新新增测试文件、所属层级、用例统计与运行命令。

---

> 本文档已按上述决策更新，**尚未修改任何业务代码**。下一步按第 6 节 P0→P5 阶段实施。




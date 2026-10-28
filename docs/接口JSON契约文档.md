# 宸甄 PrivRAG 接口 JSON 契约文档

> 版本：v2.0 ｜ 更新日期：2026-10-26
> 作用：**前端与后端真实接口之间的对接依据**。前端 `src/api/` 与后端 `app/routers/` 严格按本契约的字段、类型、嵌套结构实现；两侧任何一方改动字段，必须同步更新本文档。
> v2.0 变更：RAG 检索链路升级（P0→P4）完成后的接口同步——`citations` 增加章节路径/页码、`/api/settings/rag-config` 扩展为全参数读写与热更新、移除未实现的流式问答章节。
> 配套文档：[前后端开发执行文档.md](./development_docs/前后端开发执行文档.md)

---

## 0. 通用约定

### 0.1 基础信息

- 基础路径：`/api`（前端 Vite 已配置 `/api` 代理到后端）
- 数据格式：请求与响应均为 `application/json`（上传接口除外，使用 `multipart/form-data`）
- 登录态：除登录/注册/验证码外，请求头需携带 `Authorization: Bearer <token>`；未携带或 token 失效 → **HTTP 401**，响应体 `code=3001`，前端统一清除本地登录态并跳转登录页
- 时间格式：`YYYY-MM-DD HH:mm:ss`（如 `2026-08-13 09:30:00`）
- 文件大小：数值类型，单位 **字节**（前端展示时自行格式化）

### 0.2 统一响应包裹

所有接口（文件流接口除外）返回统一结构：

```json
{
  "code": 0,
  "message": "success",
  "data": {}
}
```

| code | 含义 | 前端处理 |
|---|---|---|
| 0 | 成功 | 取 `data` |
| 1001 | 参数校验失败 | 展示 `message` |
| 2001 | 账号或密码错误 | 展示 `message` |
| 2002 | 验证码错误 | 展示 `message` |
| 2003 | 手机号已注册 | 展示 `message` |
| 3001 | 未登录 / token 失效（HTTP 401） | 清除登录态并跳转登录页 |
| 4001 | 文档不存在 | 展示 `message` |
| 4002 | 文件类型不支持 | 展示 `message` |
| 4003 | 文件超过大小限制 | 展示 `message` |
| 5001 | 会话不存在 | 展示 `message` |
| 5000 | 服务器内部错误 | 通用错误提示 |

失败示例：

```json
{
  "code": 2001,
  "message": "手机号或密码错误",
  "data": null
}
```

### 0.3 接口一览

| 模块 | 方法 | 路径 | 鉴权 | 说明 |
|---|---|---|---|---|
| 健康检查 | GET | `/api/health` | 否 | 返回 `{status: "ok"}` |
| 认证 | POST | `/api/auth/login` | 否 | 手机号+密码登录，签发 JWT |
| 认证 | POST | `/api/auth/register` | 否 | 注册（开发环境验证码固定 `123456`） |
| 认证 | POST | `/api/auth/sms-code` | 否 | 发送验证码（开发环境仅写日志） |
| 认证 | POST | `/api/auth/logout` | 否 | JWT 无状态，前端清除本地 token |
| 认证 | GET | `/api/auth/me` | 是 | 当前用户信息 |
| 认证 | PUT | `/api/auth/profile` | 是 | 修改昵称/头像 |
| 认证 | PUT | `/api/auth/password` | 是 | 修改密码 |
| 会话 | GET | `/api/chat/conversations` | 是 | 当前用户会话列表 |
| 会话 | POST | `/api/chat/conversations` | 是 | 新建会话 |
| 会话 | DELETE | `/api/chat/conversations/{id}` | 是 | 删除会话（级联消息） |
| 会话 | GET | `/api/chat/conversations/{id}/messages` | 是 | 消息列表 |
| 会话 | DELETE | `/api/chat/conversations/{id}/messages` | 是 | 清空消息 |
| 会话 | POST | `/api/chat/messages` | 是 | 发送消息，RAG 生成回答 + 引用 |
| 文档 | POST | `/api/documents/upload` | 是 | 多文件上传（异步向量化） |
| 文档 | GET | `/api/documents` | 是 | 分页 + 搜索 + 排序 |
| 文档 | GET | `/api/documents/{id}/preview` | 是 | 纯文本预览（截断 10000 字符） |
| 文档 | GET | `/api/documents/{id}/download` | 是 | 文件流下载 |
| 文档 | DELETE | `/api/documents/{id}` | 是 | 删除（向量/DB/物理文件三方同步） |
| 统计 | GET | `/api/statistics/overview` | 是 | 总览统计 |
| 统计 | GET | `/api/statistics/file-type-distribution` | 是 | 文件类型占比 |
| 统计 | GET | `/api/statistics/daily-trend` | 是 | 近 N 天入库趋势 |
| 统计 | GET | `/api/statistics/vectorization-status` | 是 | 向量化成功/失败数 |
| 设置 | GET | `/api/settings/rag-config` | 是 | 获取全部 RAG 参数 |
| 设置 | PUT | `/api/settings/rag-config` | 是 | 保存并热更新（不重启生效） |

> 当前版本不提供流式（SSE）问答接口，前端问答统一走 `POST /api/chat/messages`。

---

## 1. 认证模块（/api/auth）

### 1.1 登录

`POST /api/auth/login`

请求：

```json
{
  "phone": "13800138000",
  "password": "123456",
  "remember": true
}
```

响应 `data`：

```json
{
  "token": "eyJhbGciOiJIUzI1NiIs...",
  "user": {
    "id": 1,
    "phone": "13800138000",
    "nickname": "宸甄管理员",
    "avatar": "",
    "createdAt": "2026-06-01 10:00:00"
  }
}
```

### 1.2 注册

`POST /api/auth/register`

请求：

```json
{
  "phone": "13800138000",
  "smsCode": "123456",
  "password": "123456",
  "confirmPassword": "123456"
}
```

响应 `data`：`null`（`message="注册成功"`）

校验规则：验证码须为开发环境固定值 `123456`（否则 `2002`）；两次密码一致且长度 ≥ 6（否则 `1001`）；手机号已存在返回 `2003`。注册后默认昵称为手机号。

### 1.3 发送短信验证码

`POST /api/auth/sms-code`

请求：

```json
{
  "phone": "13800138000",
  "scene": "register"
}
```

`scene` 取值：`register` | `login`（非法值返回 `1001`）。响应 `data`：`null`（开发环境验证码固定 `123456`，仅记录日志、不真实下发）

### 1.4 退出登录

`POST /api/auth/logout`

请求体：空。响应 `data`：`null`（JWT 无状态，后端不维护会话，前端清除本地 token 即完成退出）

### 1.5 获取当前用户信息

`GET /api/auth/me`

响应 `data`（与 1.1 中 `user` 结构一致）：

```json
{
  "id": 1,
  "phone": "13800138000",
  "nickname": "宸甄管理员",
  "avatar": "",
  "createdAt": "2026-06-01 10:00:00"
}
```

### 1.6 修改个人信息

`PUT /api/auth/profile`

请求：

```json
{
  "nickname": "宸甄管理员",
  "avatar": "data:image/png;base64,..."
}
```

响应 `data`（更新后的用户对象，与 1.1 中 `user` 结构一致）

### 1.7 修改密码

`PUT /api/auth/password`

请求：

```json
{
  "oldPassword": "123456",
  "newPassword": "654321",
  "confirmPassword": "654321"
}
```

响应 `data`：`null`

---

## 2. 会话模块（/api/chat）

### 2.1 会话对象模型

```json
{
  "id": 1,
  "title": "考勤制度咨询",
  "createdAt": "2026-08-12 10:00:00",
  "updatedAt": "2026-08-12 11:30:00"
}
```

### 2.2 消息对象模型

```json
{
  "id": 101,
  "role": "assistant",
  "content": "根据知识库资料，公司考勤制度规定……",
  "citations": [
    {
      "documentId": 1,
      "documentName": "员工手册.pdf",
      "sectionPath": "第三章 考勤制度 > 3.2 打卡规定",
      "pageStart": 12,
      "pageEnd": 12,
      "snippet": "第三章 考勤制度：员工每日上下班需打卡……"
    }
  ],
  "createdAt": "2026-08-12 11:30:00"
}
```

- `role` 取值：`user` | `assistant`
- `citations`：引用知识库来源，**AI 消息必须携带**（可空数组表示未命中）；`user` 消息 `citations` 恒为空数组
- `citations` 与回答来自**同一次检索**（不再二次检索），按文档去重（每篇文档取排序最靠前的命中块），`snippet` 截取命中块正文前 200 字
- `sectionPath` / `pageStart` / `pageEnd`：命中块的章节路径与页码区间，缺失时可为 `null`（txt/md 等无页码格式 `pageStart` 为空）

### 2.3 获取会话列表

`GET /api/chat/conversations`

响应 `data`：

```json
{
  "list": [
    {
      "id": 3,
      "title": "报销流程",
      "createdAt": "2026-08-13 09:00:00",
      "updatedAt": "2026-08-13 09:30:00"
    },
    {
      "id": 2,
      "title": "考勤制度咨询",
      "createdAt": "2026-08-12 10:00:00",
      "updatedAt": "2026-08-12 11:30:00"
    }
  ]
}
```

按 `updatedAt` 降序返回。

### 2.4 新建会话

`POST /api/chat/conversations`

请求：

```json
{
  "title": "考勤制度咨询"
}
```

`title` 可省略，后端默认使用第一条用户消息作为标题。响应 `data`：会话对象（同 2.1）。

### 2.5 删除会话

`DELETE /api/chat/conversations/{id}`

响应 `data`：`null`

### 2.6 获取会话消息列表

`GET /api/chat/conversations/{id}/messages`

响应 `data`：

```json
{
  "list": [
    {
      "id": 101,
      "role": "user",
      "content": "公司考勤制度是什么？",
      "citations": [],
      "createdAt": "2026-08-12 11:29:00"
    },
    {
      "id": 102,
      "role": "assistant",
      "content": "根据知识库资料，公司考勤制度规定……",
      "citations": [
        {
          "documentId": 1,
          "documentName": "员工手册.pdf",
          "sectionPath": "第三章 考勤制度 > 3.2 打卡规定",
          "pageStart": 12,
          "pageEnd": 12,
          "snippet": "第三章 考勤制度：员工每日上下班需打卡……"
        }
      ],
      "createdAt": "2026-08-12 11:30:00"
    }
  ]
}
```

### 2.7 发送消息

`POST /api/chat/messages`

请求：

```json
{
  "conversationId": 1,
  "content": "公司考勤制度是什么？"
}
```

响应 `data`：AI 消息对象（同 2.2，`role=assistant`）。

执行顺序：校验会话归属 → 入库 user 消息 → 会话标题为空/「新会话」时取首条消息前 20 字 → 调用 RAG（会话级历史隔离，历史文件按 `user_{uid}_conv_{cid}`） → 用同一次检索结果拼装 `citations` → 入库 assistant 消息。

错误：内容为空 `1001`；会话不存在或不属于当前用户 `5001`；生成失败 `5000`（message 含原因）。

> **可选字段 `traceId`**：仅当后端环境变量 `RETURN_TRACE_TO_CLIENT=true` 时，响应 `data` 追加 `traceId`（字符串），前端可忽略；默认不返回，响应结构与改造前一致。

### 2.8 清空会话消息

`DELETE /api/chat/conversations/{id}/messages`

响应 `data`：`null`

### 2.9 调试 trace 查询（可选）

`GET /api/debug/trace/{trace_id}`

- 仅当 `ENABLE_TRACE_API=true` 时开放；否则返回 `4044`「调试 trace 接口未开启」。
- `traceId` 不存在或已过期返回 `4045`。

响应 `data`：

```json
{
  "trace_id": "a21bfe20260a486d862f131cc8cd2014",
  "query": "对比上海和北京的住宿标准差异",
  "route": "react_complex",
  "route_reason": "命中强规则 compare",
  "matched_rules": ["compare"],
  "route_score": 2,
  "tool_calls": 3,
  "fallback": false,
  "fallback_reason": null,
  "answer_source": "react",
  "total_ms": 18698,
  "started_at": "2026-10-28T16:21:51.123",
  "steps": [
    {
      "step": 1,
      "thought": "先查上海住宿标准",
      "action": "rag_search",
      "action_input": {"query": "上海 住宿标准", "top_k": 5},
      "observation": {"passages": [], "summary": "..."},
      "elapsed_ms": 4693
    }
  ]
}
```

> `LOG_TRACE_LEVEL=summary` 时落盘不含 `steps`，接口仍返回内存缓存中的完整 trace（进程内最近 200 条）；`off` 时不缓存也不落盘。

---

## 3. 文档模块（/api/documents）

### 3.1 文档对象模型

```json
{
  "id": 1,
  "name": "员工手册.pdf",
  "type": "pdf",
  "size": 2097152,
  "uploadedAt": "2026-08-01 10:00:00",
  "vectorizeStatus": "success",
  "vectorizeMessage": ""
}
```

- `type` 取值：`pdf` | `docx` | `doc` | `txt` | `md` | `xlsx`
- `vectorizeStatus` 取值：`success`（绿色标签） | `failed`（红色标签）
- `vectorizeMessage`：向量化失败时填写原因，成功为空字符串

### 3.2 上传文档

`POST /api/documents/upload`

请求：`multipart/form-data`，字段 `files`（可多文件）。支持格式 `pdf、docx、doc、txt、md、xlsx`；单个文件最大 100MB，批量总大小不超过 125MB。

响应 `data`：本次新增的文档对象列表

```json
{
  "list": [
    {
      "id": 6,
      "name": "员工手册.pdf",
      "type": "pdf",
      "size": 2097152,
      "uploadedAt": "2026-08-13 10:00:00",
      "vectorizeStatus": "processing",
      "vectorizeMessage": ""
    }
  ]
}
```

> `vectorizeStatus` 新增 `processing`（向量化中，异步执行）；前端列表可显示为「向量化中」灰色标签或轮询刷新。

补充：后端按文件内容 MD5 去重，**内容已存在的文件会被跳过且不出现在本次 `list` 中**；向量化在后台任务中执行（格式感知分块 → 嵌入 → 写入 Qdrant / `document_chunk`，hybrid 开启时同步增量更新 BM25 索引），完成后状态置 `success`，失败写 `failed` 并在 `vectorizeMessage` 记录原因（截断 500 字）。

### 3.3 获取文档列表（分页 + 搜索 + 排序）

`GET /api/documents?page=1&size=10&keyword=员工&sortBy=uploadedAt&sortOrder=desc`

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| page | int | 否 | 页码，默认 1 |
| size | int | 否 | 每页条数，默认 10（后端限制 1~100） |
| keyword | string | 否 | 文档名称模糊搜索 |
| sortBy | string | 否 | `uploadedAt`（入库时间，默认）\| `name`（文档名称）\| `size`（文档大小）\| `type`（文档类型） |
| sortOrder | string | 否 | `asc` \| `desc`，默认 `desc` |

响应 `data`：

```json
{
  "list": [
    {
      "id": 1,
      "name": "员工手册.pdf",
      "type": "pdf",
      "size": 2097152,
      "uploadedAt": "2026-08-01 10:00:00",
      "vectorizeStatus": "success",
      "vectorizeMessage": ""
    }
  ],
  "total": 5,
  "page": 1,
  "size": 10
}
```

### 3.4 文档预览

`GET /api/documents/{id}/preview`

响应 `data`：

```json
{
  "id": 1,
  "name": "员工手册.pdf",
  "type": "pdf",
  "size": 2097152,
  "uploadedAt": "2026-08-01 10:00:00",
  "vectorizeStatus": "success",
  "vectorizeMessage": "",
  "content": "员工手册\n第一章 总则……（预览用纯文本内容，超长截断）"
}
```

> 预览为服务端按 UTF-8 读取文件前 10000 字符（`errors="ignore"`）；pdf/docx/xlsx 等二进制格式通常只能得到少量可读文本或空串，完整内容请走下载接口。

### 3.5 文档下载

`GET /api/documents/{id}/download`

响应：`application/octet-stream` 文件流，`Content-Disposition: attachment; filename="员工手册.pdf"`

### 3.6 删除文档

`DELETE /api/documents/{id}`

响应 `data`：`null`

---

## 4. 统计模块（/api/statistics）

### 4.1 总览统计

`GET /api/statistics/overview`

响应 `data`：

```json
{
  "totalDocuments": 5,
  "totalSize": 10485760,
  "vectorizeSuccess": 4,
  "vectorizeFailed": 1
}
```

| 字段 | 含义 | 前端卡片 |
|---|---|---|
| totalDocuments | 文档总数量 | 文档总数量 |
| totalSize | 全部文档总占用大小（字节） | 全部文档总占用大小 |
| vectorizeSuccess | 向量化成功文档数 | 向量化成功文档数 |
| vectorizeFailed | 向量化失败文档数 | 向量化失败文档数 |

### 4.2 文件类型占比

`GET /api/statistics/file-type-distribution`

响应 `data`：

```json
{
  "list": [
    { "type": "pdf", "count": 2 },
    { "type": "docx", "count": 1 },
    { "type": "txt", "count": 1 },
    { "type": "md", "count": 1 },
    { "type": "xlsx", "count": 0 }
  ]
}
```

饼图按此渲染，`count` 为 0 的类型可省略或显示为 0。

### 4.3 近 30 天每日入库趋势

`GET /api/statistics/daily-trend?days=30`

响应 `data`：

```json
{
  "list": [
    { "date": "2026-07-15", "count": 1 },
    { "date": "2026-08-01", "count": 2 },
    { "date": "2026-08-13", "count": 1 }
  ]
}
```

柱状图 X 轴为 `date`（`YYYY-MM-DD`），未入库日期可不返回或补 0（前端按 `days` 补全）。

### 4.4 向量化成功/失败占比

`GET /api/statistics/vectorization-status`

响应 `data`：

```json
{
  "success": 4,
  "failed": 1
}
```

环形图按此渲染。

### 4.5 空状态约定

当 `totalDocuments === 0` 时，前端图表区域整体展示「暂无文档统计数据，请前往知识库上传文档」，不渲染图表。后端仍返回上述结构（各值均为 0）。

---

## 5. 系统设置模块（/api/settings）

### 5.1 获取 RAG 参数配置

`GET /api/settings/rag-config`

响应 `data`（v1 平铺字段 + P4 分组字段全量返回）：

```json
{
  "chunkSize": 500,
  "topK": 5,
  "chunkOverlap": 50,
  "separators": ["\n\n", "\n", ".", "!", "?", "。", "！", "？", " ", ""],
  "legacyK": 3,
  "hybrid": {
    "enabled": true,
    "denseTopn": 20,
    "bm25Topn": 20,
    "rrfK": 60,
    "topn": 20
  },
  "rerank": {
    "enabled": true,
    "remoteModel": "gte-rerank-v2",
    "localModel": "BAAI/bge-reranker-v2-m3",
    "topK": 5
  },
  "queryOptimize": {
    "mode": "off",
    "multiQueryCount": 3,
    "fuseThenRerank": false
  },
  "chunking": {
    "chunkSize": 500,
    "chunkOverlap": 50,
    "minChunkSize": 100,
    "maxChunkSize": 800,
    "excelRowsPerChunk": 20,
    "separators": ["\n\n", "\n", ".", "!", "?", "。", "！", "？", " ", ""]
  }
}
```

| 字段 | 含义 | 取值域 |
|---|---|---|
| `chunkSize` / `chunkOverlap` | v1 平铺分块大小 / 重叠（与 `chunking.*` 同源） | 10~2000 / 0~1000 |
| `topK` | 最终送入生成的文档数（与 `top_k` 同源；rerank 开启时同步写 `rerank.topK`） | 1~20 |
| `legacyK` | 混合与精排**全关闭**时的稠密检索 k | 1~20 |
| `hybrid.enabled` | 混合检索（dense + BM25）开关 | bool |
| `hybrid.denseTopn` / `bm25Topn` | 稠密 / 稀疏每路召回候选数 | 1~100 |
| `hybrid.rrfK` / `topn` | RRF 平滑常数 / 融合后保留条数 | 1~500 / 1~100 |
| `rerank.enabled` | 精排开关（模型不可用时链路自动降级关闭） | bool |
| `rerank.remoteModel` / `localModel` | 远端 / 本地精排模型名 | string |
| `rerank.topK` | 精排后保留条数 | 1~20 |
| `queryOptimize.mode` | 查询优化模式 | `off` \| `multi_query` \| `hyde` |
| `queryOptimize.multiQueryCount` | multi_query 变体查询数 | 2~5 |
| `queryOptimize.fuseThenRerank` | 「融合后统一精排」变体开关 | bool |
| `chunking.*` | 格式感知分块参数（上传向量化时按次读取） | 见上表 |

### 5.2 保存 RAG 参数配置

`PUT /api/settings/rag-config`

请求：平铺字段与分组字段可**任意组合**，仅提交需要修改的字段（未提交的字段保持原值）：

```json
{
  "topK": 5,
  "hybrid": { "enabled": true, "denseTopn": 20, "bm25Topn": 20, "rrfK": 60, "topn": 20 },
  "rerank": { "enabled": true, "topK": 5 },
  "queryOptimize": { "mode": "off" },
  "chunking": { "chunkSize": 500, "chunkOverlap": 50 }
}
```

响应 `data`：保存后的完整配置（同 5.1 结构）。

- 同键冲突时**平铺字段优先**（如同时传 `chunkSize` 与 `chunking.chunkSize`，以平铺为准）
- 传 `topK` 且 `rerank.enabled=true` 时，后端同步写 `rerank.top_k`，保证最终上下文条数一致
- 请求体为空（所有字段均未提交）返回 `1001`
- 响应 `message` 三种取值：
  - `保存成功，已即时生效` —— 仅分块参数变更（下次上传向量化时生效）
  - `保存成功，检索链路已重建即时生效` —— 检索参数变更，链路已按新配置重建
  - `配置已保存，但链路重建失败，将在下次重启后生效` —— 配置已落盘，旧链路继续服务
- 保存流程：写 `config/retrieval_config.yml` → 同步内存 `retrieval_conf` → 检索参数变更时重建 RAG 单例（构建成功才原子替换）→ 记录 `before→after` 审计日志

---

## 6. 数据库表 ↔ 接口字段映射（后端实现参考）

| 契约字段 | 后端数据来源 |
|---|---|
| user.id / phone / nickname / avatar / createdAt | `user` 表；`nickname` 取用户昵称字段（注册默认手机号） |
| document.name / type / size / uploadedAt | `document` 表 file_name / file_type / file_size / created_at |
| document.vectorizeStatus / vectorizeMessage | `document` 表 vectorize_status / vectorize_message（`processing` → `success` / `failed`） |
| document 去重 | `document.md5` 与本次上传内容摘要比对，命中则跳过 |
| message.role / content / createdAt | `message` 表（role / content / created_at） |
| message.citations.documentId / documentName | 检索命中文档的 `document_id` → 关联 `document` 表 file_name |
| message.citations.sectionPath / pageStart / pageEnd | `document_chunk.metadata`（章节路径、页码区间；缺失为 `null`） |
| message.citations.snippet | `document_chunk.content` 截取前 200 字 |
| conversation 系列 | `chat_conversation` 表；消息落 `message` 表，RAG 对话历史按 `user_{uid}_conv_{cid}` 单独存储 |
| RAG 参数配置 | `backend/app/config/retrieval_config.yml`（保存后同步内存 `retrieval_conf`） |

> citations 与回答来自**同一次检索结果**，不二次检索；同一文档多命中共只保留排序最靠前的一条。

---

## 7. 变更管理

任何字段的新增、删除、改名、类型调整，都必须：

1. 更新本文档对应章节（含示例 JSON、字段取值域与错误码）
2. 同步更新前端 `src/api/`（`src/mock/` 已于 mock 下线后移除）
3. 后端实现严格按本文档响应结构返回，字段命名保持小驼峰

> 契约版本号在文档头部维护；版本不一致时以最新版为准。

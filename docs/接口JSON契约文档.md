# 宸甄 PrivRAG 接口 JSON 契约文档

> 版本：v1.0 ｜ 更新日期：2026-08-13
> 作用：**前端 mock 数据与后端真实接口之间的对接依据**。前端 `src/mock/` 与 `src/api/` 严格按本契约的字段、类型、嵌套结构实现；后端按本契约实现接口。两侧任何一方改动字段，必须同步更新本文档。
> 配套文档：[前后端开发执行文档.md](./前后端开发执行文档.md)

---

## 0. 通用约定

### 0.1 基础信息

- 基础路径：`/api`（前端 Vite 已配置 `/api` 代理到 `http://localhost:8000`）
- 数据格式：请求与响应均为 `application/json`（上传接口除外，使用 `multipart/form-data`）
- 登录态：除登录/注册/验证码/获取当前用户外，请求头需携带 `Authorization: Bearer <token>`；token 失效或未携带 → 返回 `code=401`，前端统一跳转登录页
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
| 3001 | 未登录 / token 失效 | 跳转登录页 |
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

响应 `data`：`null`

### 1.3 发送短信验证码

`POST /api/auth/sms-code`

请求：

```json
{
  "phone": "13800138000",
  "scene": "register"
}
```

`scene` 取值：`register` | `login`。响应 `data`：`null`（开发环境验证码固定 `123456`，mock 阶段前端直接使用）

### 1.4 退出登录

`POST /api/auth/logout`

请求体：空。响应 `data`：`null`

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
      "snippet": "第三章 考勤制度：员工每日上下班需打卡……"
    }
  ],
  "createdAt": "2026-08-12 11:30:00"
}
```

- `role` 取值：`user` | `assistant`
- `citations`：引用知识库来源，**AI 消息必须携带**（可空数组表示未命中）；`user` 消息 `citations` 恒为空数组

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
          "snippet": "第三章 考勤制度：员工每日上下班需打卡……"
        }
      ],
      "createdAt": "2026-08-12 11:30:00"
    }
  ]
}
```

### 2.7 发送消息（非流式，默认）

`POST /api/chat/messages`

请求：

```json
{
  "conversationId": 1,
  "content": "公司考勤制度是什么？"
}
```

响应 `data`：AI 消息对象（同 2.2，`role=assistant`）。

### 2.8 发送消息（流式，增强项）

`POST /api/chat/stream`

请求：同 2.7。

响应：`Content-Type: text/event-stream`（SSE）。事件格式：

```
data: {"type": "token", "content": "根据知识库资"}
data: {"type": "token", "content": "料，公司考勤制度…"}
data: {"type": "done", "message": {完整AI消息对象}}
```

前端收到 `type=done` 时读取完整 `message`（含 `citations`）。

### 2.9 清空会话消息

`DELETE /api/chat/conversations/{id}/messages`

响应 `data`：`null`

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

### 3.3 获取文档列表（分页 + 搜索 + 排序）

`GET /api/documents?page=1&size=10&keyword=员工&sortBy=uploadedAt&sortOrder=desc`

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| page | int | 否 | 页码，默认 1 |
| size | int | 否 | 每页条数，默认 10 |
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

响应 `data`：

```json
{
  "chunkSize": 200,
  "topK": 3,
  "chunkOverlap": 20,
  "separators": ["\n\n", "\n", ".", "!", "?", "。", "！", "？", " ", ""]
}
```

> 当前页面仅使用 `chunkSize`（切分块大小）与 `topK`（检索 Top-K）；`chunkOverlap`、`separators` 为预留字段，便于后续参数扩展，前端可只读展示或忽略。

### 5.2 保存 RAG 参数配置

`PUT /api/settings/rag-config`

请求：

```json
{
  "chunkSize": 200,
  "topK": 3
}
```

响应 `data`：保存后的完整配置（同 5.1 结构）。

---

## 6. 数据库表 ↔ 接口字段映射（后端实现参考）

| 契约字段 | 后端数据来源 |
|---|---|
| user.phone / nickname / avatar / createdAt | `user` 表（phone、nickname 新增字段；full_name 可作 nickname 默认值） |
| document.name / type / size / uploadedAt | `document` 表（file_name / file_type / file_size / created_at 新增字段） |
| document.vectorizeStatus / vectorizeMessage | `document` 表新增字段；或依据 `document_chunk` 是否存在推导 |
| message.citations.documentName / snippet | 检索命中 chunk → 反查 `document` 表 file_name + `document_chunk.content` 截取 |
| conversation 系列 | 新增 `chat_conversation` 表；消息内容复用 `ChatMessageHistory` 文件（session_id = conversation id） |

---

## 7. 变更管理

任何字段的新增、删除、改名、类型调整，都必须：

1. 更新本文档对应章节（含示例 JSON）
2. 同步更新前端 `src/mock/` 与 `src/api/`
3. 后端实现时严格按本文档响应结构返回

> 契约版本号在文档头部维护；版本不一致时以最新版为准。

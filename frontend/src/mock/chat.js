/**
 * mock 会话与问答数据源（字段对齐接口JSON契约文档 第2章）
 */

// mock 会话列表（按 updatedAt 降序）
let conversations = [
  { id: 3, title: '报销流程', createdAt: '2026-08-13 09:00:00', updatedAt: '2026-08-13 09:30:00' },
  { id: 2, title: '考勤制度咨询', createdAt: '2026-08-12 10:00:00', updatedAt: '2026-08-12 11:30:00' },
  { id: 1, title: '薪酬福利咨询', createdAt: '2026-08-11 14:00:00', updatedAt: '2026-08-11 15:20:00' },
]

// 各会话历史消息（key = conversationId）
const messagesMap = {
  3: [
    { id: 31, role: 'user', content: '差旅报销的流程是什么？', citations: [], createdAt: '2026-08-13 09:28:00' },
    {
      id: 32,
      role: 'assistant',
      content: '根据《出差报销流程》文件，差旅报销需要按以下步骤进行：1）出差前通过 OA 系统提交出差申请；2）出差结束后整理票据并填写报销单；3）提交至直属上级审批；4）审批通过后由财务部门在 5 个工作日内完成打款。',
      citations: [
        { documentId: 4, documentName: '出差报销流程.pdf', snippet: '第四章 报销流程：员工需在出差结束后 3 个工作日内提交报销单……' },
        { documentId: 1, documentName: '员工手册.pdf', snippet: '第五章 财务制度：报销款项统一在审批通过后 5 个工作日内发放……' },
      ],
      createdAt: '2026-08-13 09:30:00',
    },
  ],
  2: [
    { id: 21, role: 'user', content: '公司考勤制度是什么？', citations: [], createdAt: '2026-08-12 11:29:00' },
    {
      id: 22,
      role: 'assistant',
      content: '根据《考勤管理制度》与《员工手册》，公司实行标准工时制（每周五天、每天 8 小时），员工每日上下班需通过打卡设备进行考勤记录。迟到或早退累计达到一定次数将影响当月绩效，请假需提前在 OA 系统提交申请。',
      citations: [
        { documentId: 2, documentName: '考勤管理制度.docx', snippet: '第二条 考勤方式：公司实行上下班打卡制度，迟到早退按绩效考核办法处理……' },
        { documentId: 1, documentName: '员工手册.pdf', snippet: '第三章 考勤制度：员工每日上下班需打卡，请假须提前申请……' },
      ],
      createdAt: '2026-08-12 11:30:00',
    },
  ],
  1: [
    { id: 11, role: 'user', content: '公司薪酬福利包括哪些？', citations: [], createdAt: '2026-08-11 15:19:00' },
    {
      id: 12,
      role: 'assistant',
      content: '根据《薪酬福利管理办法》，公司薪酬由基本工资、岗位工资、绩效奖金和各类补贴构成；福利方面包含五险一金、年度体检、带薪年假、节日礼品以及补充商业保险等。具体标准可查阅《薪酬福利管理办法》。',
      citations: [
        { documentId: 3, documentName: '薪酬福利管理办法.docx', snippet: '第二章 薪酬结构：薪酬=基本工资+岗位工资+绩效奖金+补贴……' },
      ],
      createdAt: '2026-08-11 15:20:00',
    },
  ],
}

let conversationIdSeed = 100
let messageIdSeed = 1000

/** 获取会话列表（按 updatedAt 降序） */
export function mockListConversations() {
  return [...conversations].sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))
}

/** 新建会话 */
export function mockCreateConversation(title = '新会话') {
  const d = new Date()
  const pad = (n) => String(n).padStart(2, '0')
  const now = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
  conversationIdSeed += 1
  const conv = { id: conversationIdSeed, title, createdAt: now, updatedAt: now }
  conversations.unshift(conv)
  messagesMap[conv.id] = []
  return conv
}

/** 删除会话 */
export function mockDeleteConversation(id) {
  const idx = conversations.findIndex((c) => c.id === id)
  if (idx !== -1) conversations.splice(idx, 1)
  delete messagesMap[id]
}

/** 获取会话消息列表 */
export function mockListMessages(conversationId) {
  return messagesMap[conversationId] || []
}

/** 清空会话消息 */
export function mockClearMessages(conversationId) {
  if (messagesMap[conversationId]) messagesMap[conversationId] = []
}

/** 记录用户消息并返回消息对象 */
export function mockAppendUserMessage(conversationId, content) {
  messageIdSeed += 1
  const msg = {
    id: messageIdSeed,
    role: 'user',
    content,
    citations: [],
    createdAt: nowTime(),
  }
  const list = messagesMap[conversationId] || []
  list.push(msg)
  touchConversation(conversationId, content)
  return msg
}

/** 追加 AI 回复消息并返回消息对象 */
export function mockAppendAiMessage(conversationId, content, citations) {
  messageIdSeed += 1
  const msg = {
    id: messageIdSeed,
    role: 'assistant',
    content,
    citations,
    createdAt: nowTime(),
  }
  const list = messagesMap[conversationId] || []
  list.push(msg)
  return msg
}

function touchConversation(id, content) {
  const conv = conversations.find((c) => c.id === id)
  if (!conv) return
  conv.updatedAt = nowTime()
  // 新会话未命名时，用首条用户消息作标题
  if (conv.title === '新会话' && content) {
    conv.title = content.length > 12 ? `${content.slice(0, 12)}…` : content
  }
}

function nowTime() {
  const d = new Date()
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

/** 模拟当前时间（支持 mock 历史时间场景） */
export function currentTime() {
  return nowTime()
}

/**
 * 生成 AI 回答（模拟 1.2-2s 延迟由调用方控制）
 * 按关键词匹配知识库词条，返回 { content, citations }
 */
export function mockGenerateAnswer(question) {
  const q = question || ''
  let match = answerBank.find((item) => item.keywords.some((kw) => q.includes(kw)))
  if (!match) {
    match = {
      content:
        '我已根据企业知识库中的资料为您检索到相关信息。由于当前提问较为宽泛，建议您补充更具体的关键词（如：考勤、报销、薪酬、信息安全等），我可以为您提供更精准的答复。',
      citations: [
        { documentId: 1, documentName: '员工手册.pdf', snippet: '第一章 总则：本手册适用于公司全体员工，涵盖考勤、薪酬、福利等制度……' },
      ],
    }
  }
  return { content: match.content, citations: match.citations }
}

// 知识库问答词库（模拟溯源效果）
const answerBank = [
  {
    keywords: ['考勤', '打卡', '迟到', '早退', '请假'],
    content:
      '根据《考勤管理制度》与《员工手册》中的相关条款：公司实行标准工时制，每周工作五天、每天 8 小时，员工每日上下班须通过考勤设备打卡。迟到或早退将按《绩效考核办法》计入当月考勤记录；请假须提前在 OA 系统提交申请，经审批通过后方可生效。',
    citations: [
      { documentId: 2, documentName: '考勤管理制度.docx', snippet: '第二条 考勤方式：公司实行上下班打卡制度，迟到早退按绩效考核办法处理……' },
      { documentId: 1, documentName: '员工手册.pdf', snippet: '第三章 考勤制度：员工每日上下班需打卡，请假须提前申请……' },
    ],
  },
  {
    keywords: ['报销', '差旅', '出差', '报销流程'],
    content:
      '差旅报销流程如下：1）出差前通过 OA 系统提交出差申请并获审批；2）出差结束后 3 个工作日内整理票据、填写报销单；3）提交直属上级审批；4）审批通过后移交财务部门，于 5 个工作日内完成打款。相关细则请参阅《出差报销流程》。',
    citations: [
      { documentId: 4, documentName: '出差报销流程.pdf', snippet: '第四章 报销流程：员工需在出差结束后 3 个工作日内提交报销单……' },
    ],
  },
  {
    keywords: ['薪酬', '工资', '福利', '奖金', '五险一金', '年假'],
    content:
      '公司薪酬由基本工资、岗位工资、绩效奖金与各类补贴构成；福利包含五险一金、年度体检、带薪年假、节日礼品及补充商业保险。月度工资于次月 10 日发放，年终奖金按公司年度经营情况核定，具体标准请查阅《薪酬福利管理办法》。',
    citations: [
      { documentId: 3, documentName: '薪酬福利管理办法.docx', snippet: '第二章 薪酬结构：薪酬=基本工资+岗位工资+绩效奖金+补贴……' },
      { documentId: 1, documentName: '员工手册.pdf', snippet: '第六章 福利保障：公司为员工缴纳五险一金，提供带薪年假等福利……' },
    ],
  },
  {
    keywords: ['安全', '保密', '信息安全', '数据'],
    content:
      '根据《信息安全管理制度》，公司实行信息分级管控：1）内部资料不得外传，离职时须归还全部涉密载体；2）重要数据访问需申请授权并留存审计日志；3）如发现信息泄露，应及时上报信息安全部门处理。',
    citations: [
      { documentId: 5, documentName: '信息安全管理制度.pdf', snippet: '第三条 信息保密：公司内部资料实行分级管理，未经授权不得外传……' },
    ],
  },
  {
    keywords: ['入职', '新员工', '培训', '入职培训'],
    content:
      '新员工入职培训内容包括：企业文化与制度宣导、岗位技能培训、信息安全与保密培训三部分，培训时长共 3 天。培训结束后需通过考核方可转正，详细安排见《新员工入职培训手册》。',
    citations: [
      { documentId: 6, documentName: '新员工入职培训手册.txt', snippet: '培训安排：入职前三天依次进行企业文化、岗位技能、信息安全培训……' },
    ],
  },
  {
    keywords: ['报销', '采购', '合同', '审批'],
    content:
      '采购与合同审批流程：1）需求部门填写采购/合同申请单并附商务说明；2）经部门负责人、分管领导逐级审批；3）金额超过 5 万元的项目需总经理审批；4）合同签署后由行政部统一归档并登记台账。',
    citations: [
      { documentId: 8, documentName: '客户合同模板.docx', snippet: '合同签署流程：申请、审核、会签、盖章、归档……' },
    ],
  },
]

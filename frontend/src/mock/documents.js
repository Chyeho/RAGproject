/**
 * mock 文档数据源（字段对齐接口JSON契约文档 第3章）
 */
export const mockDocuments = [
  { id: 1, name: '员工手册.pdf', type: 'pdf', size: 2101248, uploadedAt: '2026-08-13 10:00:00', vectorizeStatus: 'success', vectorizeMessage: '' },
  { id: 2, name: '考勤管理制度.docx', type: 'docx', size: 102400, uploadedAt: '2026-08-11 15:30:00', vectorizeStatus: 'success', vectorizeMessage: '' },
  { id: 3, name: '薪酬福利管理办法.docx', type: 'docx', size: 153600, uploadedAt: '2026-08-09 09:20:00', vectorizeStatus: 'success', vectorizeMessage: '' },
  { id: 4, name: '出差报销流程.pdf', type: 'pdf', size: 358400, uploadedAt: '2026-08-07 14:10:00', vectorizeStatus: 'success', vectorizeMessage: '' },
  { id: 5, name: '信息安全管理制度.pdf', type: 'pdf', size: 512000, uploadedAt: '2026-08-05 11:00:00', vectorizeStatus: 'failed', vectorizeMessage: '文档解析失败：PDF 内容为扫描件，无可提取文本' },
  { id: 6, name: '新员工入职培训手册.txt', type: 'txt', size: 65536, uploadedAt: '2026-08-03 16:40:00', vectorizeStatus: 'success', vectorizeMessage: '' },
  { id: 7, name: '产品技术白皮书.md', type: 'md', size: 245760, uploadedAt: '2026-08-01 10:30:00', vectorizeStatus: 'success', vectorizeMessage: '' },
  { id: 8, name: '客户合同模板.docx', type: 'docx', size: 88064, uploadedAt: '2026-07-30 13:50:00', vectorizeStatus: 'success', vectorizeMessage: '' },
  { id: 9, name: '财务报表模板.xlsx', type: 'xlsx', size: 51200, uploadedAt: '2026-07-28 09:15:00', vectorizeStatus: 'success', vectorizeMessage: '' },
  { id: 10, name: '项目管理流程手册.docx', type: 'docx', size: 204800, uploadedAt: '2026-07-25 17:05:00', vectorizeStatus: 'success', vectorizeMessage: '' },
  { id: 11, name: '招聘管理制度.pdf', type: 'pdf', size: 307200, uploadedAt: '2026-07-22 10:45:00', vectorizeStatus: 'failed', vectorizeMessage: '向量化超时，请重试' },
  { id: 12, name: '应急预案汇总.txt', type: 'txt', size: 40960, uploadedAt: '2026-07-19 14:25:00', vectorizeStatus: 'success', vectorizeMessage: '' },
  { id: 13, name: '会议纪要模板.docx', type: 'docx', size: 26624, uploadedAt: '2026-07-17 11:35:00', vectorizeStatus: 'success', vectorizeMessage: '' },
  { id: 14, name: '业务数据分析报告.md', type: 'md', size: 187904, uploadedAt: '2026-07-15 16:20:00', vectorizeStatus: 'success', vectorizeMessage: '' },
]

/** 允许上传的文件类型 */
export const ALLOWED_TYPES = ['pdf', 'docx', 'doc', 'txt', 'md', 'xlsx']

/** 单个文件最大 100MB */
export const MAX_FILE_SIZE = 100 * 1024 * 1024

/** 批量总大小不超过 125MB */
export const MAX_BATCH_SIZE = 125 * 1024 * 1024

/** 从文件名解析扩展名 */
export function getFileType(name) {
  const idx = name.lastIndexOf('.')
  if (idx === -1) return ''
  return name.slice(idx + 1).toLowerCase()
}

let mockIdSeed = 1000

/**
 * 模拟上传：将文件信息追加到文档列表
 * @param {Array<{name: string, size: number}>} files
 * @returns 新增文档对象列表
 */
export function mockUpload(files) {
  const now = new Date()
  const pad = (n) => String(n).padStart(2, '0')
  const uploadedAt = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`

  const added = files.map((f) => {
    mockIdSeed += 1
    const doc = {
      id: mockIdSeed,
      name: f.name,
      type: getFileType(f.name),
      size: f.size,
      uploadedAt,
      vectorizeStatus: 'success', // mock：上传即向量化成功
      vectorizeMessage: '',
    }
    mockDocuments.unshift(doc)
    return doc
  })
  return added
}

/** 模拟删除：按 id 移除文档 */
export function mockRemoveDocument(id) {
  const idx = mockDocuments.findIndex((d) => d.id === id)
  if (idx !== -1) mockDocuments.splice(idx, 1)
}

/** 按 id 查询文档 */
export function mockGetDocument(id) {
  return mockDocuments.find((d) => d.id === id) || null
}

/**
 * 模拟分页/搜索/排序查询
 * @param {{page:number, size:number, keyword:string, sortBy:string, sortOrder:string}} params
 */
export function mockQueryDocuments({ page = 1, size = 10, keyword = '', sortBy = 'uploadedAt', sortOrder = 'desc' } = {}) {
  let list = [...mockDocuments]

  // 关键词过滤（文档名称模糊匹配）
  if (keyword) {
    const kw = keyword.trim().toLowerCase()
    list = list.filter((d) => d.name.toLowerCase().includes(kw))
  }

  // 排序
  const order = sortOrder === 'asc' ? 1 : -1
  list.sort((a, b) => {
    if (sortBy === 'size') return (a.size - b.size) * order
    if (sortBy === 'name') return a.name.localeCompare(b.name, 'zh') * order
    if (sortBy === 'type') return a.type.localeCompare(b.type, 'zh') * order
    // 默认按入库时间
    return a.uploadedAt.localeCompare(b.uploadedAt) * order
  })

  const total = list.length
  const start = (page - 1) * size
  const pageList = list.slice(start, start + size)

  return { list: pageList, total, page, size }
}

/** mock 预览内容（按文档类型生成一段模拟文本） */
export function mockPreviewContent(doc) {
  if (!doc) return ''
  const sample = '第一章 总则\n为规范企业经营管理，保障公司与员工的合法权益，特制定本文件。本章内容适用于公司全体成员，解释权归公司人力资源部所有。\n\n第二章 具体条款\n各部门应严格按照制度执行相关工作流程，做到有据可查、有章可循。涉及跨部门协作的事项，由牵头部门负责组织协调，并留存过程记录。\n\n（以上内容为 mock 预览文本，用于模拟文档在线预览效果，实际联调时由后端返回真实文档内容。）'
  return `【${doc.name}】\n\n${sample}`
}

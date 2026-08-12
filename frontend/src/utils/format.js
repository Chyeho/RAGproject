/**
 * 通用格式化工具
 */

/** 文件大小（字节）转可读文本 */
export function formatFileSize(bytes) {
  if (bytes === 0 || bytes == null) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let size = Number(bytes)
  let idx = 0
  while (size >= 1024 && idx < units.length - 1) {
    size /= 1024
    idx++
  }
  const digits = size >= 100 ? 0 : size >= 10 ? 1 : 2
  return `${size.toFixed(digits)} ${units[idx]}`
}

/** 时间字符串格式化（契约格式 YYYY-MM-DD HH:mm:ss，直接透传） */
export function formatDateTime(value) {
  if (!value) return '--'
  return value
}

/** 时间字符串截取日期部分 */
export function formatDate(value) {
  if (!value) return '--'
  return String(value).slice(0, 10)
}

/** 生成当前时间字符串（契约格式 YYYY-MM-DD HH:mm:ss） */
export function nowDateTime() {
  const d = new Date()
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

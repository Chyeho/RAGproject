/** 模拟网络延迟 */
export function delay(ms = 300) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

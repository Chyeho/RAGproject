/**
 * 会话/问答接口层（对接后端真实接口）
 * 函数签名与返回结构与 mock 阶段保持一致，页面无需改动
 */
import request from './request'

/** 获取会话列表 GET /api/chat/conversations */
export async function listConversations() {
  return request.get('/chat/conversations')
}

/** 新建会话 POST /api/chat/conversations */
export async function createConversation(title) {
  return request.post('/chat/conversations', { title: title || '新会话' })
}

/** 删除会话 DELETE /api/chat/conversations/{id} */
export async function deleteConversation(id) {
  return request.delete(`/chat/conversations/${id}`)
}

/** 获取会话消息列表 GET /api/chat/conversations/{id}/messages */
export async function listMessages(conversationId) {
  return request.get(`/chat/conversations/${conversationId}/messages`)
}

/** 清空会话消息 DELETE /api/chat/conversations/{id}/messages */
export async function clearMessages(conversationId) {
  return request.delete(`/chat/conversations/${conversationId}/messages`)
}

/**
 * 发送消息 POST /api/chat/messages（非流式）
 * 用户消息由后端入库，本接口仅返回 AI 消息对象（含引用来源）
 * @returns {{aiMessage: object}}
 */
export async function sendMessage({ conversationId, content }) {
  const aiMessage = await request.post('/chat/messages', { conversationId, content })
  return { aiMessage }
}

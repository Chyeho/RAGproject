/**
 * 会话/问答接口层（mock 阶段返回本地假数据，后端就绪后替换为 request 真实调用）
 */
import { delay } from '../utils/delay'
import * as chatMock from '../mock/chat'

/** 获取会话列表 GET /api/chat/conversations */
export async function listConversations() {
  await delay(300)
  return { list: chatMock.mockListConversations() }
}

/** 新建会话 POST /api/chat/conversations */
export async function createConversation(title) {
  await delay(300)
  return chatMock.mockCreateConversation(title)
}

/** 删除会话 DELETE /api/chat/conversations/{id} */
export async function deleteConversation(id) {
  await delay(300)
  chatMock.mockDeleteConversation(id)
  return null
}

/** 获取会话消息列表 GET /api/chat/conversations/{id}/messages */
export async function listMessages(conversationId) {
  await delay(200)
  return { list: chatMock.mockListMessages(conversationId) }
}

/** 清空会话消息 DELETE /api/chat/conversations/{id}/messages */
export async function clearMessages(conversationId) {
  await delay(300)
  chatMock.mockClearMessages(conversationId)
  return null
}

/**
 * 发送消息 POST /api/chat/messages
 * mock 阶段：先追加用户消息，模拟 1.2-2s 延迟后返回 AI 消息（含引用来源）
 * @returns {{userMessage: object, aiMessage: object}}
 */
export async function sendMessage({ conversationId, content }) {
  const userMessage = chatMock.mockAppendUserMessage(conversationId, content)
  // 模拟网络延迟 1.2-2s
  const latency = 1200 + Math.random() * 800
  await delay(latency)
  const { content: answer, citations } = chatMock.mockGenerateAnswer(content)
  const aiMessage = chatMock.mockAppendAiMessage(conversationId, answer, citations)
  return { userMessage, aiMessage }
}

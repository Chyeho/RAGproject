<template>
  <div class="chat-view">
    <!-- ================= 左侧：会话列表 ================= -->
    <aside class="chat-sidebar">
      <div class="chat-sidebar-header">
        <el-button
          type="primary"
          class="new-conv-btn"
          :icon="Plus"
          @click="handleNewConversation"
        >
          新建会话
        </el-button>
      </div>

      <div class="conversation-list">
        <div
          v-for="conv in conversations"
          :key="conv.id"
          class="conversation-item"
          :class="{ active: conv.id === activeId }"
          @click="selectConversation(conv.id)"
        >
          <el-icon class="conv-icon"><ChatLineRound /></el-icon>
          <span class="conv-title">{{ conv.title }}</span>
          <el-icon
            v-if="conv.id === activeId"
            class="conv-delete"
            title="删除会话"
            @click.stop="removeConversation(conv.id)"
          >
            <Delete />
          </el-icon>
        </div>

        <div v-if="conversations.length === 0" class="conversation-empty">
          <p>暂无会话</p>
          <p class="empty-tip">点击「新建会话」开始提问</p>
        </div>
      </div>
    </aside>

    <!-- ================= 右侧：聊天主区域 ================= -->
    <section class="chat-main">
      <!-- 消息列表 -->
      <div ref="messagesRef" class="chat-messages">
        <template v-if="messages.length > 0">
          <div
            v-for="msg in messages"
            :key="msg.id"
            class="message-row"
            :class="msg.role === 'user' ? 'is-user' : 'is-ai'"
          >
            <div class="bubble" :class="msg.role === 'user' ? 'bubble-user' : 'bubble-ai'">
              <!-- AI 回答：前置角色标识 -->
              <div v-if="msg.role === 'assistant'" class="bubble-role">
                <el-icon :size="13"><MagicStick /></el-icon>
                <span>宸甄 PrivRAG</span>
              </div>
              <div class="bubble-text">{{ msg.content }}</div>

              <!-- 引用知识库来源（AI 消息固定展示，默认折叠） -->
              <div v-if="msg.role === 'assistant'" class="citation-wrap">
                <button
                  class="citation-toggle"
                  :class="{ open: expandedCitations.has(msg.id) }"
                  @click="toggleCitations(msg.id)"
                >
                  <el-icon :size="13"><Document /></el-icon>
                  <span>引用知识库来源</span>
                  <el-icon :size="12" class="toggle-arrow">
                    <ArrowDown />
                  </el-icon>
                </button>
                <el-collapse-transition>
                  <div v-show="expandedCitations.has(msg.id)" class="citation-panel">
                    <div
                      v-for="(cit, idx) in msg.citations"
                      :key="idx"
                      class="citation-item"
                    >
                      <div class="citation-doc">
                        <el-icon :size="13"><DocumentCopy /></el-icon>
                        <span class="citation-name">{{ cit.documentName }}</span>
                      </div>
                      <p class="citation-snippet">{{ cit.snippet }}</p>
                    </div>
                    <div v-if="!msg.citations || msg.citations.length === 0" class="citation-item">
                      <p class="citation-snippet">本次回答未命中知识库资料</p>
                    </div>
                  </div>
                </el-collapse-transition>
              </div>
            </div>
          </div>
        </template>

        <!-- 空状态 -->
        <div v-else class="chat-empty">
          <div class="chat-empty-icon">
            <el-icon :size="40"><ChatLineRound /></el-icon>
          </div>
          <p class="chat-empty-title">欢迎使用宸甄 PrivRAG</p>
          <p class="chat-empty-desc">企业私有知识库问答系统 · 输入问题开始对话，回答将附带知识库引用来源</p>
        </div>
      </div>

      <!-- 底部输入区域 -->
      <div class="chat-input-bar">
        <el-input
          v-model="draft"
          type="textarea"
          :rows="2"
          resize="none"
          maxlength="2000"
          placeholder="请输入您的问题，回车发送（Shift+Enter 换行）"
          @keydown.enter.exact.prevent="handleSend"
        />
        <div class="input-actions">
          <el-button
            type="primary"
            :loading="sending"
            :disabled="!draft.trim()"
            @click="handleSend"
          >
            <el-icon class="btn-icon"><Promotion /></el-icon>发送
          </el-button>
          <el-button :disabled="messages.length === 0" @click="handleClear">
            <el-icon class="btn-icon"><Delete /></el-icon>清空当前会话
          </el-button>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { ref, reactive, nextTick, onMounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Plus,
  Delete,
  ChatLineRound,
  Document,
  DocumentCopy,
  ArrowDown,
  MagicStick,
  Promotion,
} from '@element-plus/icons-vue'
import {
  listConversations,
  createConversation,
  deleteConversation,
  listMessages,
  clearMessages,
  sendMessage,
} from '../../api/chat'
import { nowDateTime } from '../../utils/format'

// ---------------- 数据 ----------------
const conversations = ref([])
const activeId = ref(null)
const messages = ref([])
const draft = ref('')
const sending = ref(false)
const expandedCitations = reactive(new Set())

const messagesRef = ref(null)

// ---------------- 生命周期 ----------------
onMounted(async () => {
  await loadConversations()
  if (conversations.value.length > 0) {
    await selectConversation(conversations.value[0].id)
  }
})

// 新消息时自动滚动到底部
watch(
  () => messages.value.length,
  async () => {
    await nextTick()
    scrollToBottom()
  }
)

// ---------------- 会话管理 ----------------
async function loadConversations() {
  const { list } = await listConversations()
  conversations.value = list
}

async function selectConversation(id) {
  activeId.value = id
  const { list } = await listMessages(id)
  messages.value = list
}

async function handleNewConversation() {
  const conv = await createConversation()
  conversations.value.unshift(conv)
  activeId.value = conv.id
  messages.value = []
  draft.value = ''
}

async function removeConversation(id) {
  try {
    await ElMessageBox.confirm('删除后该会话的对话记录将不可恢复，确定删除吗？', '删除会话', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch (e) {
    return
  }
  await deleteConversation(id)
  conversations.value = conversations.value.filter((c) => c.id !== id)
  ElMessage.success('会话已删除')
  if (activeId.value === id) {
    activeId.value = null
    messages.value = []
    if (conversations.value.length > 0) {
      await selectConversation(conversations.value[0].id)
    }
  }
}

// ---------------- 消息发送 ----------------
async function handleSend() {
  const content = draft.value.trim()
  if (!content || sending.value) return
  if (!activeId.value) {
    ElMessage.warning('请先新建会话')
    return
  }

  // 立即追加用户气泡（乐观更新）
  messages.value.push({
    id: `local-${Date.now()}`,
    role: 'user',
    content,
    citations: [],
    createdAt: nowDateTime(),
  })
  draft.value = ''
  sending.value = true

  try {
    const { aiMessage } = await sendMessage({ conversationId: activeId.value, content })
    messages.value.push(aiMessage)
    // 会话标题可能由首条消息生成，刷新列表
    await loadConversations()
  } catch (e) {
    ElMessage.error(e.message || '发送失败')
  } finally {
    sending.value = false
  }
}

async function handleClear() {
  try {
    await ElMessageBox.confirm('确定清空当前会话的全部消息吗？', '清空会话', {
      confirmButtonText: '清空',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch (e) {
    return
  }
  await clearMessages(activeId.value)
  messages.value = []
  ElMessage.success('当前会话已清空')
}

// ---------------- 引用来源折叠 ----------------
function toggleCitations(msgId) {
  if (expandedCitations.has(msgId)) {
    expandedCitations.delete(msgId)
  } else {
    expandedCitations.add(msgId)
  }
}

// ---------------- 滚动 ----------------
function scrollToBottom() {
  if (messagesRef.value) {
    messagesRef.value.scrollTop = messagesRef.value.scrollHeight
  }
}
</script>

<style scoped>
.chat-view {
  display: flex;
  width: 100%;
  height: 100%;
}

/* ------- 左侧会话栏 ------- */
.chat-sidebar {
  width: 280px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  background-color: var(--bg-card);
  border-right: 1px solid var(--border-light);
}

.chat-sidebar-header {
  padding: 16px;
  border-bottom: 1px solid var(--border-light);
}

.new-conv-btn {
  width: 100%;
}

.conversation-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.conversation-item {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 42px;
  padding: 0 10px;
  margin-bottom: 4px;
  border-radius: 6px;
  cursor: pointer;
  color: var(--text-main);
  transition: background-color 0.15s;
}

.conversation-item:hover {
  background-color: #eef1f5;
}

.conversation-item.active {
  background-color: var(--brand-color-light);
  color: var(--brand-color);
}

.conv-icon {
  flex-shrink: 0;
  font-size: 15px;
  color: var(--text-secondary);
}

.conversation-item.active .conv-icon {
  color: var(--brand-color);
}

.conv-title {
  flex: 1;
  font-size: 14px;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.conv-delete {
  flex-shrink: 0;
  color: var(--text-secondary);
  cursor: pointer;
}

.conv-delete:hover {
  color: var(--danger);
}

.conversation-empty {
  padding: 40px 0;
  text-align: center;
  color: var(--text-secondary);
  font-size: 14px;
}

.conversation-empty .empty-tip {
  margin-top: 8px;
  font-size: 12px;
  color: var(--text-disabled);
}

/* ------- 右侧聊天主区域 ------- */
.chat-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  background-color: #ffffff;
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 24px 32px;
}

/* 空状态 */
.chat-empty {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: var(--text-secondary);
}

.chat-empty-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 80px;
  height: 80px;
  border-radius: 50%;
  background-color: var(--brand-color-light);
  color: var(--brand-color);
  margin-bottom: 20px;
}

.chat-empty-title {
  font-size: 18px;
  color: var(--text-main);
  font-weight: 600;
}

.chat-empty-desc {
  margin-top: 10px;
  font-size: 13px;
  color: var(--text-secondary);
}

/* 消息气泡 */
.message-row {
  display: flex;
  margin-bottom: 20px;
}

.message-row.is-user {
  justify-content: flex-end;
}

.bubble {
  max-width: 70%;
  border-radius: 8px;
  padding: 12px 16px;
  line-height: 1.7;
  word-break: break-word;
}

.bubble-user {
  background: var(--brand-gradient-soft);
  color: var(--text-main);
}

.bubble-ai {
  background-color: #ffffff;
  border: 1px solid var(--border-light);
  box-shadow: var(--shadow-card);
}

.bubble-role {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--brand-color);
  margin-bottom: 6px;
}

.bubble-text {
  white-space: pre-wrap;
  font-size: 14px;
}

/* 引用知识库来源 */
.citation-wrap {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px dashed var(--border-light);
}

.citation-toggle {
  display: flex;
  align-items: center;
  gap: 5px;
  border: none;
  background: transparent;
  cursor: pointer;
  font-size: 12px;
  color: var(--brand-color);
  padding: 2px 0;
}

.citation-toggle .toggle-arrow {
  transition: transform 0.2s;
}

.citation-toggle.open .toggle-arrow {
  transform: rotate(180deg);
}

.citation-panel {
  margin-top: 10px;
  background-color: var(--bg-card);
  border-radius: 6px;
  padding: 4px 12px;
}

.citation-item {
  padding: 8px 0;
}

.citation-item + .citation-item {
  border-top: 1px solid var(--border-light);
}

.citation-doc {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 13px;
  color: var(--text-main);
  font-weight: 600;
}

.citation-snippet {
  margin-top: 4px;
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.6;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* 输入区域 */
.chat-input-bar {
  flex-shrink: 0;
  padding: 12px 32px 16px;
  border-top: 1px solid var(--border-light);
  background-color: #ffffff;
}

.input-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 12px;
}

.btn-icon {
  margin-right: 4px;
}
</style>

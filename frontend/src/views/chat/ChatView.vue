<template>
  <div class="chat-view">
    <!-- ================= 左侧：会话列表（可收起） ================= -->
    <aside class="chat-sidebar" :class="{ 'is-collapsed': sidebarCollapsed }">
      <!-- 收起态：窄条操作栏 -->
      <div v-if="sidebarCollapsed" class="sidebar-rail">
        <el-tooltip content="展开侧栏（Ctrl+B）" placement="right">
          <button class="rail-btn" @click="toggleSidebar">
            <el-icon :size="16"><Expand /></el-icon>
          </button>
        </el-tooltip>
        <el-tooltip content="新建会话" placement="right">
          <button class="rail-btn rail-btn-primary" @click="handleNewConversation">
            <el-icon :size="16"><Plus /></el-icon>
          </button>
        </el-tooltip>
      </div>

      <!-- 展开态：新建按钮 + 会话列表 -->
      <template v-else>
        <div class="chat-sidebar-header">
          <el-button
            type="primary"
            class="new-conv-btn"
            :icon="Plus"
            @click="handleNewConversation"
          >
            新建会话
          </el-button>
          <el-tooltip content="收起侧栏（Ctrl+B）" placement="bottom">
            <button class="sidebar-toggle" @click="toggleSidebar">
              <el-icon :size="16"><Fold /></el-icon>
            </button>
          </el-tooltip>
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
            <p class="empty-tip">直接输入问题发送即可自动新建会话</p>
          </div>
        </div>
      </template>
    </aside>

    <!-- ================= 右侧：聊天主区域 ================= -->
    <section class="chat-main">
      <!-- 消息列表 -->
      <div ref="messagesRef" class="chat-messages">
        <template v-if="messages.length > 0 || sending">
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
                        <span v-if="cit.sectionPath" class="citation-sec">{{ cit.sectionPath }}</span>
                        <span v-if="cit.pageStart" class="citation-page">P{{ pageLabel(cit) }}</span>
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

          <!-- AI 思考中占位：给出明确的"正在处理"反馈，避免用户以为没反应 -->
          <div v-if="sending" class="message-row is-ai">
            <div class="bubble bubble-ai thinking-bubble">
              <div class="bubble-role">
                <el-icon :size="13"><MagicStick /></el-icon>
                <span>宸甄 PrivRAG</span>
              </div>
              <div class="thinking">
                <span class="thinking-dots"><i></i><i></i><i></i></span>
                <span class="thinking-text">正在检索知识库并生成回答…</span>
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
            <el-icon v-if="!sending" class="btn-icon"><Promotion /></el-icon>
            {{ sending ? '生成中…' : '发送' }}
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
import { ref, reactive, nextTick, onMounted, onBeforeUnmount, watch } from 'vue'
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
  Fold,
  Expand,
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
// 输入草稿暂存：切换页面（组件卸载）或刷新后仍能恢复，避免手误点走导致内容丢失
const DRAFT_KEY = 'privrag_chat_draft'
// 侧栏收起状态：记住用户上一次的选择，刷新/切换页面后保持不变
const SIDEBAR_KEY = 'privrag_chat_sidebar_collapsed'

const conversations = ref([])
const activeId = ref(null)
const messages = ref([])
const draft = ref(sessionStorage.getItem(DRAFT_KEY) || '')
const sending = ref(false)
const expandedCitations = reactive(new Set())
const sidebarCollapsed = ref(localStorage.getItem(SIDEBAR_KEY) === '1')

const messagesRef = ref(null)

// 草稿实时写入 sessionStorage（发送/清空/新建会话时自动移除）
watch(draft, (val) => {
  if (val) {
    sessionStorage.setItem(DRAFT_KEY, val)
  } else {
    sessionStorage.removeItem(DRAFT_KEY)
  }
})

// ---------------- 生命周期 ----------------
onMounted(async () => {
  window.addEventListener('keydown', handleShortcut)
  await loadConversations()
  if (conversations.value.length > 0) {
    await selectConversation(conversations.value[0].id)
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleShortcut)
})

// 新消息时自动滚动到底部
watch(
  () => messages.value.length,
  async () => {
    await nextTick()
    scrollToBottom()
  }
)

// 出现/收起「思考中」占位时同样贴底，保证用户一眼看到反馈
watch(sending, async () => {
  await nextTick()
  scrollToBottom()
})

// ---------------- 侧栏收起 / 展开 ----------------
function toggleSidebar() {
  sidebarCollapsed.value = !sidebarCollapsed.value
  localStorage.setItem(SIDEBAR_KEY, sidebarCollapsed.value ? '1' : '0')
  // 侧栏宽度变化会改变消息区宽度，收展后重新贴底，避免出现半截气泡
  nextTick(scrollToBottom)
}

// Ctrl/Cmd + B 快捷切换侧栏
function handleShortcut(e) {
  if ((e.ctrlKey || e.metaKey) && !e.shiftKey && !e.altKey && e.key.toLowerCase() === 'b') {
    e.preventDefault()
    toggleSidebar()
  }
}

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

  sending.value = true
  try {
    // 无任何会话时：先自动新建会话，再直接发送（无需手动点「新建会话」）
    if (!activeId.value) {
      const conv = await createConversation()
      conversations.value.unshift(conv)
      activeId.value = conv.id
      messages.value = []
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

// 页码展示：起止相同显示单页，否则显示区间
function pageLabel(cit) {
  if (!cit.pageEnd || cit.pageStart === cit.pageEnd) return cit.pageStart
  return `${cit.pageStart}-${cit.pageEnd}`
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
  transition: width 0.22s ease;
  overflow: hidden;
}

/* 收起态：只留一条窄操作栏 */
.chat-sidebar.is-collapsed {
  width: 56px;
}

.chat-sidebar-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 16px;
  border-bottom: 1px solid var(--border-light);
}

.new-conv-btn {
  flex: 1;
  min-width: 0;
}

/* 收起 / 展开按钮 */
.sidebar-toggle {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  flex-shrink: 0;
  padding: 0;
  border: 1px solid var(--border-light);
  border-radius: 6px;
  background-color: #ffffff;
  color: var(--text-secondary);
  cursor: pointer;
  transition: color 0.15s, background-color 0.15s, border-color 0.15s;
}

.sidebar-toggle:hover {
  color: var(--brand-color);
  border-color: var(--brand-color-disabled);
  background-color: var(--brand-color-light);
}

/* 收起态窄条 */
.sidebar-rail {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 16px 0;
}

.rail-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  padding: 0;
  border: 1px solid var(--border-light);
  border-radius: 6px;
  background-color: #ffffff;
  color: var(--text-secondary);
  cursor: pointer;
  transition: color 0.15s, background-color 0.15s, border-color 0.15s;
}

.rail-btn:hover {
  color: var(--brand-color);
  border-color: var(--brand-color-disabled);
  background-color: var(--brand-color-light);
}

.rail-btn-primary {
  color: #ffffff;
  border-color: transparent;
  background: var(--brand-gradient);
}

.rail-btn-primary:hover {
  color: #ffffff;
  border-color: transparent;
  background: var(--brand-gradient-hover);
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

/* ------- AI 思考中占位 ------- */
.thinking-bubble {
  /* 浅品牌底色 + 描边，避免白底白框在页面里"消失" */
  background-color: #f8f9ff;
  border-color: var(--brand-color-light-hover);
  animation: thinking-in 0.22s ease-out;
  box-shadow: 0 0 0 3px rgba(43, 79, 224, 0.06), var(--shadow-card);
}

.thinking {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 2px 0;
}

.thinking-dots {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.thinking-dots i {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background-color: var(--brand-color);
  opacity: 0.3;
  animation: thinking-bounce 1.1s infinite ease-in-out;
}

.thinking-dots i:nth-child(2) {
  animation-delay: 0.15s;
}

.thinking-dots i:nth-child(3) {
  animation-delay: 0.3s;
}

.thinking-text {
  font-size: 13px;
  color: #4e5969;
  letter-spacing: 0.2px;
}

@keyframes thinking-bounce {
  0%,
  60%,
  100% {
    transform: translateY(0);
    opacity: 0.3;
  }
  30% {
    transform: translateY(-5px);
    opacity: 1;
  }
}

@keyframes thinking-in {
  from {
    opacity: 0;
    transform: translateY(6px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
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

.citation-sec {
  font-size: 12px;
  font-weight: 400;
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.citation-page {
  flex-shrink: 0;
  font-size: 11px;
  font-weight: 500;
  color: var(--brand-color);
  background-color: var(--brand-color-light);
  border-radius: 4px;
  padding: 1px 6px;
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

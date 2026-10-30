<template>
  <div class="page-container settings-page">
    <!-- ================= 卡片一：账号信息（只读） ================= -->
    <div class="soft-card settings-card">
      <div class="card-title">账号信息</div>

      <el-descriptions :column="2" border class="account-desc">
        <el-descriptions-item label="账号">{{ account.username || '-' }}</el-descriptions-item>
        <el-descriptions-item label="角色">{{ roleText }}</el-descriptions-item>
        <el-descriptions-item label="权限等级">{{ levelText }}</el-descriptions-item>
        <el-descriptions-item label="账号状态">{{ statusText }}</el-descriptions-item>
        <el-descriptions-item label="最后登录">{{ account.lastLoginAt || '暂无记录' }}</el-descriptions-item>
      </el-descriptions>
    </div>

    <!-- ================= 卡片二：修改密码 ================= -->
    <div class="soft-card settings-card">
      <div class="card-title">修改密码</div>

      <el-form
        ref="pwdFormRef"
        :model="pwdForm"
        :rules="pwdRules"
        label-width="110px"
        class="settings-form"
      >
        <el-form-item label="原密码" prop="oldPassword">
          <el-input
            v-model="pwdForm.oldPassword"
            type="password"
            placeholder="请输入原密码"
            show-password
            class="field-input"
          />
        </el-form-item>
        <el-form-item label="新密码" prop="newPassword">
          <el-input
            v-model="pwdForm.newPassword"
            type="password"
            placeholder="8-64位，需包含字母和数字"
            show-password
            class="field-input"
          />
        </el-form-item>
        <el-form-item label="确认新密码" prop="confirmPassword">
          <el-input
            v-model="pwdForm.confirmPassword"
            type="password"
            placeholder="请再次输入新密码"
            show-password
            class="field-input"
          />
        </el-form-item>

        <el-form-item>
          <el-button
            type="primary"
            class="save-btn"
            :loading="pwdSaving"
            @click="handleChangePassword"
          >
            确认修改
          </el-button>
        </el-form-item>
      </el-form>
    </div>

    <!-- ================= 卡片三：知识库RAG参数配置（仅管理员可见） ================= -->
    <div v-if="canRagConfig" class="soft-card settings-card">
      <div class="card-title">知识库 RAG 参数配置</div>

      <el-form
        ref="ragFormRef"
        :model="ragForm"
        :rules="ragRules"
        label-width="110px"
        class="settings-form"
      >
        <el-form-item label="切分块大小" prop="chunkSize">
          <el-input-number
            v-model="ragForm.chunkSize"
            :min="50"
            :max="2000"
            :step="50"
            controls-position="right"
          />
          <span class="field-hint">文档向量化时的文本切分块大小（字符数）</span>
        </el-form-item>

        <el-form-item label="检索 Top-K" prop="topK">
          <el-input-number
            v-model="ragForm.topK"
            :min="1"
            :max="20"
            :step="1"
            controls-position="right"
          />
          <span class="field-hint">每次回答检索的知识库文本块数量</span>
        </el-form-item>

        <!-- ================= 检索增强（P4：混合检索/精排/查询优化，保存后热更新生效） ================= -->
        <div class="group-divider">检索增强</div>

        <el-form-item label="混合检索">
          <el-switch v-model="ragForm.hybridEnabled" />
          <span class="field-hint">向量 + BM25 关键词双路召回，RRF 融合去重</span>
        </el-form-item>
        <template v-if="ragForm.hybridEnabled">
          <el-form-item label="稠密候选数">
            <el-input-number
              v-model="ragForm.hybridDenseTopn"
              :min="1"
              :max="100"
              :step="5"
              controls-position="right"
            />
            <span class="field-hint">向量检索候选条数</span>
          </el-form-item>
          <el-form-item label="BM25 候选数">
            <el-input-number
              v-model="ragForm.hybridBm25Topn"
              :min="1"
              :max="100"
              :step="5"
              controls-position="right"
            />
            <span class="field-hint">关键词检索候选条数</span>
          </el-form-item>
          <el-form-item label="融合候选数">
            <el-input-number
              v-model="ragForm.hybridTopn"
              :min="1"
              :max="100"
              :step="5"
              controls-position="right"
            />
            <span class="field-hint">RRF 融合后送入精排的候选条数</span>
          </el-form-item>
          <el-form-item label="RRF 平滑常数">
            <el-input-number
              v-model="ragForm.hybridRrfK"
              :min="1"
              :max="500"
              :step="10"
              controls-position="right"
            />
            <span class="field-hint">排名融合平滑参数，越大排名差异越平缓</span>
          </el-form-item>
        </template>

        <el-form-item label="结果精排">
          <el-switch v-model="ragForm.rerankEnabled" />
          <span class="field-hint">重排模型精排候选块，开启时精排保留数与 Top-K 联动</span>
        </el-form-item>
        <template v-if="ragForm.rerankEnabled">
          <el-form-item label="精排保留数">
            <el-input-number
              v-model="ragForm.rerankTopK"
              :min="1"
              :max="20"
              :step="1"
              controls-position="right"
            />
            <span class="field-hint">精排后保留并送入生成的条数</span>
          </el-form-item>
          <el-form-item label="远端精排模型">
            <el-input
              v-model="ragForm.rerankRemoteModel"
              placeholder="远端精排模型名（如 gte-rerank）"
              class="field-input"
              clearable
            />
          </el-form-item>
          <el-form-item label="本地精排模型">
            <el-input
              v-model="ragForm.rerankLocalModel"
              placeholder="本地精排模型名（可留空）"
              class="field-input"
              clearable
            />
          </el-form-item>
        </template>

        <el-form-item label="查询优化">
          <el-select v-model="ragForm.queryMode" class="field-input">
            <el-option label="关闭" value="off" />
            <el-option label="多查询扩展（Multi-Query）" value="multi_query" />
            <el-option label="假设文档（HyDE）" value="hyde" />
          </el-select>
          <span class="field-hint">检索前改写问题，提升召回覆盖</span>
        </el-form-item>
        <template v-if="ragForm.queryMode === 'multi_query'">
          <el-form-item label="变体查询数">
            <el-input-number
              v-model="ragForm.multiQueryCount"
              :min="2"
              :max="5"
              :step="1"
              controls-position="right"
            />
            <span class="field-hint">扩展生成的问题数量</span>
          </el-form-item>
          <el-form-item label="融合后精排">
            <el-switch v-model="ragForm.fuseThenRerank" />
            <span class="field-hint">多路召回 RRF 融合后再统一精排</span>
          </el-form-item>
        </template>

        <el-form-item label="兜底检索数">
          <el-input-number
            v-model="ragForm.legacyK"
            :min="1"
            :max="20"
            :step="1"
            controls-position="right"
          />
          <span class="field-hint">检索增强全部关闭时的向量检索条数</span>
        </el-form-item>

        <el-form-item>
          <el-button
            type="primary"
            class="save-btn"
            :loading="ragSaving"
            @click="handleSaveRag"
          >
            保存参数
          </el-button>
        </el-form-item>
      </el-form>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { changePassword } from '../../api/auth'
import { getRagConfig, saveRagConfig } from '../../api/settings'
import { getUser, hasPermission, clearLoginState } from '../../utils/auth'

const router = useRouter()

// ---------------- 账号信息（只读） ----------------
const account = ref(getUser() || {})

const roleText = computed(() => (account.value.role === 'admin' ? '管理员' : '普通用户'))
const levelText = computed(() => {
  if (account.value.role === 'admin') return '—'
  return account.value.level ? `L${account.value.level}` : '—'
})
const statusText = computed(() => (account.value.status === 'disabled' ? '已禁用' : '正常'))

// ---------------- 修改密码 ----------------
const pwdFormRef = ref(null)
const pwdSaving = ref(false)

const pwdForm = reactive({
  oldPassword: '',
  newPassword: '',
  confirmPassword: '',
})

const validateNewPwd = (rule, value, callback) => {
  if (!value) return callback(new Error('请输入新密码'))
  if (value.length < 8 || value.length > 64) return callback(new Error('密码长度为8-64位'))
  if (!/[A-Za-z]/.test(value) || !/\d/.test(value)) {
    return callback(new Error('密码需同时包含字母和数字'))
  }
  callback()
}

const validateConfirmPwd = (rule, value, callback) => {
  if (!value) return callback(new Error('请再次输入新密码'))
  if (value !== pwdForm.newPassword) return callback(new Error('两次输入的新密码不一致'))
  callback()
}

const pwdRules = {
  oldPassword: [{ required: true, message: '请输入原密码', trigger: 'blur' }],
  newPassword: [{ required: true, validator: validateNewPwd, trigger: 'blur' }],
  confirmPassword: [{ required: true, validator: validateConfirmPwd, trigger: 'blur' }],
}

async function handleChangePassword() {
  const valid = await pwdFormRef.value.validate().catch(() => false)
  if (!valid) return

  pwdSaving.value = true
  try {
    await changePassword({ ...pwdForm })
    ElMessage.success('密码修改成功，请使用新密码重新登录')
    clearLoginState()
    router.push('/login')
  } catch (e) {
    ElMessage.error(e.message || '密码修改失败')
  } finally {
    pwdSaving.value = false
  }
}

// ---------------- RAG 参数（仅管理员） ----------------
const canRagConfig = hasPermission('ragConfig')

const ragFormRef = ref(null)
const ragSaving = ref(false)

const ragForm = reactive({
  chunkSize: 200,
  topK: 3,
  // ---- 检索增强（P4）----
  legacyK: 3,
  hybridEnabled: false,
  hybridDenseTopn: 20,
  hybridBm25Topn: 20,
  hybridTopn: 30,
  hybridRrfK: 60,
  rerankEnabled: false,
  rerankTopK: 5,
  rerankRemoteModel: '',
  rerankLocalModel: '',
  queryMode: 'off',
  multiQueryCount: 3,
  fuseThenRerank: false,
})

const ragRules = {
  chunkSize: [{ required: true, message: '请输入切分块大小', trigger: 'change' }],
  topK: [{ required: true, message: '请输入检索 Top-K', trigger: 'change' }],
}

onMounted(async () => {
  if (!canRagConfig) return
  const config = await getRagConfig()
  ragForm.chunkSize = config.chunkSize
  ragForm.topK = config.topK
  // 检索增强分组回填（P4）
  ragForm.legacyK = config.legacyK ?? ragForm.legacyK
  const h = config.hybrid || {}
  ragForm.hybridEnabled = !!h.enabled
  ragForm.hybridDenseTopn = h.denseTopn ?? ragForm.hybridDenseTopn
  ragForm.hybridBm25Topn = h.bm25Topn ?? ragForm.hybridBm25Topn
  ragForm.hybridTopn = h.topn ?? ragForm.hybridTopn
  ragForm.hybridRrfK = h.rrfK ?? ragForm.hybridRrfK
  const r = config.rerank || {}
  ragForm.rerankEnabled = !!r.enabled
  ragForm.rerankTopK = r.topK ?? ragForm.rerankTopK
  ragForm.rerankRemoteModel = r.remoteModel || ''
  ragForm.rerankLocalModel = r.localModel || ''
  const q = config.queryOptimize || {}
  ragForm.queryMode = q.mode || 'off'
  ragForm.multiQueryCount = q.multiQueryCount ?? ragForm.multiQueryCount
  ragForm.fuseThenRerank = !!q.fuseThenRerank
})

async function handleSaveRag() {
  const valid = await ragFormRef.value.validate().catch(() => false)
  if (!valid) return

  ragSaving.value = true
  try {
    await saveRagConfig({
      chunkSize: ragForm.chunkSize,
      topK: ragForm.topK,
      legacyK: ragForm.legacyK,
      hybrid: {
        enabled: ragForm.hybridEnabled,
        denseTopn: ragForm.hybridDenseTopn,
        bm25Topn: ragForm.hybridBm25Topn,
        rrfK: ragForm.hybridRrfK,
        topn: ragForm.hybridTopn,
      },
      rerank: {
        enabled: ragForm.rerankEnabled,
        remoteModel: ragForm.rerankRemoteModel || null, // 空值置 null → 后端跳过不覆盖
        localModel: ragForm.rerankLocalModel || null,
        topK: ragForm.rerankTopK,
      },
      queryOptimize: {
        mode: ragForm.queryMode,
        multiQueryCount: ragForm.multiQueryCount,
        fuseThenRerank: ragForm.fuseThenRerank,
      },
    })
    ElMessage.success('RAG 参数保存成功，已即时生效')
  } catch (e) {
    ElMessage.error(e.message || '保存失败')
  } finally {
    ragSaving.value = false
  }
}
</script>

<style scoped>
.settings-page {
  padding: 20px;
}

.settings-card + .settings-card {
  margin-top: 16px;
}

.card-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-main);
  padding-bottom: 14px;
  margin-bottom: 6px;
  border-bottom: 1px solid var(--border-light);
}

.account-desc {
  margin-top: 18px;
  max-width: 720px;
}

.settings-form {
  margin-top: 18px;
  max-width: 640px;
}

.field-input {
  width: 320px;
}

/* 分组标题 */
.group-divider {
  font-size: 13px;
  color: var(--text-secondary);
  margin: 4px 0 16px;
  padding-left: 10px;
  border-left: 3px solid var(--brand-color);
  line-height: 1.2;
}

/* 字段说明 */
.field-hint {
  margin-left: 12px;
  font-size: 12px;
  color: var(--text-secondary);
}

.save-btn {
  min-width: 120px;
}
</style>

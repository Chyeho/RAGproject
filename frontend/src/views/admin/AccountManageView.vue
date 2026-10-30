<template>
  <div class="page-container account-page">
    <!-- ================= 顶部工具栏 ================= -->
    <div class="account-toolbar">
      <div class="toolbar-left">
        <el-button type="primary" :icon="Plus" @click="handleCreate">
          新建账号
        </el-button>
      </div>

      <div class="toolbar-middle">
        <el-input
          v-model="query.keyword"
          placeholder="按账号搜索"
          clearable
          class="search-input"
          :prefix-icon="Search"
          @input="debouncedSearch"
          @clear="fetchList(1)"
        />
      </div>

      <div class="toolbar-right">
        <el-select
          v-model="query.level"
          placeholder="全部等级"
          clearable
          class="filter-select"
          @change="fetchList(1)"
        >
          <el-option label="L1" :value="1" />
          <el-option label="L2" :value="2" />
          <el-option label="L3" :value="3" />
        </el-select>
        <el-select
          v-model="query.status"
          placeholder="全部状态"
          clearable
          class="filter-select"
          @change="fetchList(1)"
        >
          <el-option label="正常" value="active" />
          <el-option label="已禁用" value="disabled" />
        </el-select>
      </div>
    </div>

    <!-- ================= 账号表格 ================= -->
    <el-table
      v-loading="loading"
      :data="list"
      stripe
      class="account-table"
      empty-text="暂无账号，点击「新建账号」为成员开通"
    >
      <el-table-column prop="username" label="账号" min-width="140" show-overflow-tooltip />
      <el-table-column label="角色" width="100" align="center">
        <template #default="{ row }">
          <el-tag :type="row.role === 'admin' ? 'warning' : 'info'" effect="light" size="small" disable-transitions>
            {{ row.role === 'admin' ? '管理员' : '普通用户' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="权限等级" width="130" align="center">
        <template #default="{ row }">
          <el-select
            v-if="row.role === 'user'"
            :model-value="row.level"
            size="small"
            class="level-select"
            @change="(val) => handleLevelChange(row, val)"
          >
            <el-option label="L1" :value="1" />
            <el-option label="L2" :value="2" />
            <el-option label="L3" :value="3" />
          </el-select>
          <span v-else class="muted">—</span>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="100" align="center">
        <template #default="{ row }">
          <el-switch
            v-if="row.role === 'user'"
            :model-value="row.status === 'active'"
            inline-prompt
            active-text="启用"
            inactive-text="禁用"
            @change="(val) => handleStatusChange(row, val)"
          />
          <span v-else class="muted">正常</span>
        </template>
      </el-table-column>
      <el-table-column label="创建人" width="140" align="center">
        <template #default="{ row }">
          {{ row.createdByName || (row.role === 'admin' ? '系统初始化' : '—') }}
        </template>
      </el-table-column>
      <el-table-column prop="createdAt" label="创建时间" width="170" />
      <el-table-column label="最后登录" width="170">
        <template #default="{ row }">{{ row.lastLoginAt || '暂无记录' }}</template>
      </el-table-column>
      <el-table-column label="操作" width="180" align="center" fixed="right">
        <template #default="{ row }">
          <template v-if="row.role === 'user'">
            <el-button type="primary" link size="small" @click="handleResetPassword(row)">
              重置密码
            </el-button>
            <el-button type="danger" link size="small" @click="handleDelete(row)">删除</el-button>
          </template>
          <span v-else class="muted">不可操作</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- ================= 分页 ================= -->
    <div class="account-pagination">
      <el-pagination
        v-model:current-page="query.page"
        v-model:page-size="query.size"
        :total="total"
        :page-sizes="[10, 20, 50]"
        layout="total, sizes, prev, pager, next, jumper"
        background
        @current-change="fetchList"
        @size-change="fetchList(1)"
      />
    </div>

    <!-- ================= 密码展示弹窗（初始密码/临时密码仅显示一次） ================= -->
    <el-dialog
      v-model="passwordVisible"
      :title="passwordInfo.title"
      width="460px"
      :close-on-click-modal="false"
    >
      <el-alert
        type="warning"
        :closable="false"
        show-icon
        title="密码仅显示本次，关闭后无法再次查看，请立即复制并转交本人"
      />
      <div class="password-block">
        <div class="password-row">
          <span class="password-label">账号</span>
          <span class="password-value">{{ passwordInfo.username }}</span>
        </div>
        <div class="password-row">
          <span class="password-label">密码</span>
          <span class="password-value password-strong">{{ passwordInfo.password }}</span>
        </div>
      </div>
      <template #footer>
        <el-button
          type="primary"
          :icon="CopyDocument"
          @click="handleCopyPassword"
        >
          复制密码
        </el-button>
        <el-button @click="passwordVisible = false">我已保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Search, CopyDocument } from '@element-plus/icons-vue'
import { listUsers, createUser, updateUser, resetUserPassword, deleteUser } from '../../api/admin'

// ---------------- 查询参数 ----------------
const query = reactive({
  page: 1,
  size: 10,
  keyword: '',
  level: null,
  status: null,
})

const list = ref([])
const total = ref(0)
const loading = ref(false)

async function fetchList(page = query.page) {
  query.page = page
  loading.value = true
  try {
    const params = { page: query.page, size: query.size }
    if (query.keyword) params.keyword = query.keyword
    if (query.level) params.level = query.level
    if (query.status) params.status = query.status
    const res = await listUsers(params)
    list.value = res.list
    total.value = res.total
  } catch (e) {
    ElMessage.error(e.message || '账号列表加载失败')
  } finally {
    loading.value = false
  }
}

// 输入防抖搜索（300ms）
let searchTimer = null
function debouncedSearch() {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => fetchList(1), 300)
}

onMounted(() => fetchList(1))
onBeforeUnmount(() => clearTimeout(searchTimer))

// ---------------- 密码展示 ----------------
const passwordVisible = ref(false)
const passwordInfo = reactive({
  title: '',
  username: '',
  password: '',
})

function showPassword(title, username, password) {
  passwordInfo.title = title
  passwordInfo.username = username
  passwordInfo.password = password
  passwordVisible.value = true
}

async function handleCopyPassword() {
  try {
    await navigator.clipboard.writeText(passwordInfo.password)
    ElMessage.success('密码已复制到剪贴板')
  } catch (e) {
    ElMessage.warning('复制失败，请手动记录密码')
  }
}

// ---------------- 新建账号 ----------------
const creating = ref(false)

async function handleCreate() {
  if (creating.value) return
  creating.value = true
  try {
    const res = await createUser()
    showPassword('账号创建成功', res.username, res.initialPassword)
    fetchList(1)
  } catch (e) {
    ElMessage.error(e.message || '账号创建失败')
  } finally {
    creating.value = false
  }
}

// ---------------- 修改等级 ----------------
async function handleLevelChange(row, level) {
  if (level === row.level) return
  try {
    await updateUser(row.id, { level })
    row.level = level
    ElMessage.success(`账号 ${row.username} 等级已调整为 L${level}`)
  } catch (e) {
    ElMessage.error(e.message || '等级修改失败')
    fetchList()
  }
}

// ---------------- 启用/禁用 ----------------
async function handleStatusChange(row, enabled) {
  const status = enabled ? 'active' : 'disabled'
  if (status === row.status) return
  try {
    await updateUser(row.id, { status })
    row.status = status
    ElMessage.success(`账号 ${row.username} 已${enabled ? '启用' : '禁用'}`)
  } catch (e) {
    ElMessage.error(e.message || '状态修改失败')
    fetchList()
  }
}

// ---------------- 重置密码 ----------------
async function handleResetPassword(row) {
  try {
    await ElMessageBox.confirm(
      `将为账号「${row.username}」生成随机临时密码，本人登录后需立即修改，确定重置吗？`,
      '重置密码',
      { confirmButtonText: '重置', cancelButtonText: '取消', type: 'warning' }
    )
  } catch (e) {
    return
  }
  try {
    const res = await resetUserPassword(row.id)
    showPassword('密码重置成功', res.username, res.tempPassword)
    fetchList()
  } catch (e) {
    ElMessage.error(e.message || '密码重置失败')
  }
}

// ---------------- 删除（软删除） ----------------
async function handleDelete(row) {
  try {
    await ElMessageBox.confirm(
      `删除后账号「${row.username}」将立即无法登录，历史记录保留但不可恢复，确定删除吗？`,
      '删除账号',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' }
    )
  } catch (e) {
    return
  }
  try {
    await deleteUser(row.id)
    ElMessage.success(`账号「${row.username}」已删除`)
    if (list.value.length === 1 && query.page > 1) {
      fetchList(query.page - 1)
    } else {
      fetchList()
    }
  } catch (e) {
    ElMessage.error(e.message || '删除失败')
  }
}
</script>

<style scoped>
.account-page {
  padding: 20px;
}

/* ------- 工具栏 ------- */
.account-toolbar {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 16px;
}

.toolbar-middle {
  flex: 1;
  display: flex;
  justify-content: center;
}

.search-input {
  width: 320px;
}

.toolbar-right {
  display: flex;
  gap: 12px;
  justify-content: flex-end;
}

.filter-select {
  width: 130px;
}

/* ------- 表格 ------- */
.account-table {
  width: 100%;
  border: 1px solid var(--border-light);
  border-radius: 6px;
  overflow: hidden;
}

.level-select {
  width: 88px;
}

.muted {
  color: var(--text-secondary);
}

.account-pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

/* ------- 密码弹窗 ------- */
.password-block {
  margin-top: 16px;
  padding: 16px;
  border-radius: 6px;
  background-color: var(--brand-color-light);
}

.password-row {
  display: flex;
  align-items: center;
  line-height: 2;
}

.password-row + .password-row {
  margin-top: 4px;
}

.password-label {
  width: 56px;
  color: var(--text-secondary);
  font-size: 13px;
}

.password-value {
  font-family: Consolas, Monaco, monospace;
  color: var(--text-main);
}

.password-strong {
  font-size: 16px;
  font-weight: 600;
  letter-spacing: 1px;
  color: var(--brand-color);
}
</style>

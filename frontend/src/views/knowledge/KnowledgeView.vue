<template>
  <div class="page-container knowledge-page">
    <!-- ================= 顶部工具栏 ================= -->
    <div class="knowledge-toolbar">
      <div class="toolbar-left">
        <el-button type="primary" :icon="Upload" @click="uploadVisible = true">
          上传文档
        </el-button>
      </div>

      <div class="toolbar-middle">
        <el-input
          v-model="query.keyword"
          placeholder="按文档名称搜索"
          clearable
          class="search-input"
          :prefix-icon="Search"
          @input="debouncedSearch"
          @clear="handleSearch"
        />
      </div>

      <div class="toolbar-right">
        <el-select v-model="query.sortBy" class="sort-select" @change="fetchList(1)">
          <el-option label="入库时间" value="uploadedAt" />
          <el-option label="文档名称" value="name" />
          <el-option label="文档大小" value="size" />
          <el-option label="文档类型" value="type" />
        </el-select>
      </div>
    </div>

    <!-- ================= 文档表格（强制表格，禁止卡片） ================= -->
    <el-table
      v-loading="loading"
      :data="list"
      stripe
      class="doc-table"
      :empty-text="emptyText"
    >
      <el-table-column prop="name" label="文档名称" min-width="220" show-overflow-tooltip />
      <el-table-column prop="type" label="文档类型" width="100" align="center">
        <template #default="{ row }">
          <span class="type-tag">{{ row.type.toUpperCase() }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="size" label="文档大小" width="120" align="right">
        <template #default="{ row }">{{ formatFileSize(row.size) }}</template>
      </el-table-column>
      <el-table-column prop="uploadedAt" label="入库时间" width="170" />
      <el-table-column prop="vectorizeStatus" label="向量化状态" width="120" align="center">
        <template #default="{ row }">
          <el-tag
            :type="row.vectorizeStatus === 'success' ? 'success' : row.vectorizeStatus === 'failed' ? 'danger' : 'info'"
            effect="light"
            size="small"
            disable-transitions
          >
            {{ statusText(row.vectorizeStatus) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="210" align="center" fixed="right">
        <template #default="{ row }">
          <el-button type="primary" link size="small" @click="handlePreview(row)">查看预览</el-button>
          <el-button type="primary" link size="small" @click="handleDownload(row)">下载</el-button>
          <el-button type="danger" link size="small" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- ================= 分页 ================= -->
    <div class="knowledge-pagination">
      <el-pagination
        v-model:current-page="query.page"
        v-model:page-size="query.size"
        :total="total"
        :page-sizes="[5, 10, 20, 50]"
        layout="total, sizes, prev, pager, next, jumper"
        background
        @current-change="fetchList"
        @size-change="fetchList(1)"
      />
    </div>

    <!-- ================= 上传文档弹窗 ================= -->
    <el-dialog
      v-model="uploadVisible"
      title="上传文档"
      width="520px"
      :close-on-click-modal="false"
    >
      <div class="upload-tip">
        <p>支持文件格式：pdf、docx、doc、txt、md、xlsx</p>
        <p>单个文件最大 100MB，批量上传总大小不超过 125MB</p>
      </div>
      <el-upload
        ref="uploadRef"
        v-model:file-list="fileList"
        multiple
        drag
        :auto-upload="false"
        :accept="acceptTypes"
        :on-change="handleFileChange"
        :on-remove="handleFileChange"
      >
        <el-icon class="upload-icon"><UploadFilled /></el-icon>
        <div class="upload-text">将文件拖到此处，或<em>点击选择文件</em></div>
      </el-upload>
      <template #footer>
        <el-button @click="uploadVisible = false">取消</el-button>
        <el-button type="primary" :loading="uploading" :disabled="fileList.length === 0" @click="confirmUpload">
          确认上传
        </el-button>
      </template>
    </el-dialog>

    <!-- ================= 文档预览弹窗 ================= -->
    <el-dialog v-model="previewVisible" title="文档预览" width="640px">
      <div v-if="previewDoc" class="preview-body">
        <div class="preview-meta">
          <span>{{ previewDoc.name }}</span>
          <span class="preview-meta-sub">
            {{ formatFileSize(previewDoc.size) }} · {{ previewDoc.uploadedAt }}
          </span>
        </div>
        <pre class="preview-content">{{ previewDoc.content }}</pre>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Upload, UploadFilled, Search } from '@element-plus/icons-vue'
import {
  queryDocuments,
  uploadDocuments,
  previewDocument,
  downloadDocument,
  deleteDocument,
} from '../../api/documents'
import { formatFileSize, getFileType } from '../../utils/format'

// ---------------- 查询参数 ----------------
const query = reactive({
  page: 1,
  size: 10,
  keyword: '',
  sortBy: 'uploadedAt',
})

const list = ref([])
const total = ref(0)
const loading = ref(false)

// 表格空状态文案
const emptyText = ref('暂无文档，请上传企业文档构建私有知识库')

// ---------------- 列表加载 ----------------
async function fetchList(page = query.page) {
  query.page = page
  loading.value = true
  try {
    const res = await queryDocuments({ ...query })
    list.value = res.list
    total.value = res.total
    // 后端就绪后按需调整空状态
    emptyText.value = '暂无文档，请上传企业文档构建私有知识库'
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  fetchList(1)
}

// 输入防抖搜索（300ms）
let searchTimer = null
function debouncedSearch() {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => handleSearch(), 300)
}

onMounted(() => fetchList(1))
onBeforeUnmount(() => clearTimeout(searchTimer))

// ---------------- 上传 ----------------
const uploadVisible = ref(false)
const uploading = ref(false)
const fileList = ref([])
const acceptTypes = '.pdf,.docx,.doc,.txt,.md,.xlsx'
const uploadRef = ref(null)

function handleFileChange() {
  // 仅用于触发响应式更新
}

function confirmUpload() {
  // 类型与大小校验
  const files = fileList.value.map((f) => f.raw)
  for (const f of files) {
    const type = getFileType(f.name)
    const allowed = ['pdf', 'docx', 'doc', 'txt', 'md', 'xlsx'].includes(type)
    if (!allowed) {
      ElMessage.error(`文件「${f.name}」格式不支持，仅支持 pdf、docx、doc、txt、md、xlsx`)
      return
    }
    if (f.size > 100 * 1024 * 1024) {
      ElMessage.error(`文件「${f.name}」超过单个文件最大 100MB 限制`)
      return
    }
  }
  const totalSize = files.reduce((sum, f) => sum + f.size, 0)
  if (totalSize > 125 * 1024 * 1024) {
    ElMessage.error('批量上传总大小超过 125MB 限制')
    return
  }

  uploading.value = true
  uploadDocuments(files)
    .then(() => {
      ElMessage.success(`上传成功，共 ${files.length} 个文件已加入知识库`)
      uploadVisible.value = false
      fileList.value = []
      uploadRef.value?.clearFiles?.()
      fetchList(1)
    })
    .catch((e) => ElMessage.error(e.message || '上传失败'))
    .finally(() => {
      uploading.value = false
    })
}

// ---------------- 状态文案 ----------------
function statusText(status) {
  return status === 'success' ? '成功' : status === 'failed' ? '失败' : '向量化中'
}

// ---------------- 预览 ----------------
const previewVisible = ref(false)
const previewDoc = ref(null)

async function handlePreview(row) {
  previewDoc.value = await previewDocument(row.id)
  previewVisible.value = true
}

// ---------------- 下载 ----------------
async function handleDownload(row) {
  await downloadDocument(row.id)
  ElMessage.success(`已开始下载「${row.name}」`)
}

// ---------------- 删除 ----------------
async function handleDelete(row) {
  try {
    await ElMessageBox.confirm(
      `删除后文档「${row.name}」将从知识库移除且不可恢复，确定删除吗？`,
      '删除文档',
      {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning',
      }
    )
  } catch (e) {
    return
  }
  await deleteDocument(row.id)
  ElMessage.success(`文档「${row.name}」已删除`)
  // 当前页删空后回退一页
  if (list.value.length === 1 && query.page > 1) {
    fetchList(query.page - 1)
  } else {
    fetchList()
  }
}
</script>

<style scoped>
.knowledge-page {
  padding: 20px;
}

/* ------- 工具栏 ------- */
.knowledge-toolbar {
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
  justify-content: flex-end;
}

.sort-select {
  width: 160px;
}

/* ------- 表格 ------- */
.doc-table {
  width: 100%;
  border: 1px solid var(--border-light);
  border-radius: 6px;
  overflow: hidden;
}

.type-tag {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  background-color: var(--brand-color-light);
  color: var(--brand-color);
  font-size: 12px;
  font-weight: 600;
}

.knowledge-pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

/* ------- 上传弹窗 ------- */
.upload-tip {
  background-color: var(--brand-color-light);
  border-radius: 6px;
  padding: 10px 14px;
  margin-bottom: 16px;
  font-size: 13px;
  color: var(--text-main);
  line-height: 1.8;
}

.upload-icon {
  font-size: 48px;
  color: var(--brand-color);
  margin-bottom: 8px;
}

.upload-text {
  color: var(--text-secondary);
  font-size: 14px;
}

.upload-text em {
  color: var(--brand-color);
  font-style: normal;
}

/* ------- 预览弹窗 ------- */
.preview-body {
  max-height: 480px;
  overflow-y: auto;
}

.preview-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border-light);
  margin-bottom: 12px;
  font-weight: 600;
}

.preview-meta-sub {
  font-weight: 400;
  font-size: 12px;
  color: var(--text-secondary);
}

.preview-content {
  font-family: inherit;
  font-size: 13px;
  line-height: 1.8;
  color: var(--text-main);
  white-space: pre-wrap;
  word-break: break-all;
}
</style>

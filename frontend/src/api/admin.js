/**
 * 账号管理接口层（仅管理员可用）
 */
import request from './request'

/** 账号列表 GET /api/admin/users */
export async function listUsers(params) {
  return request.get('/admin/users', { params })
}

/** 新建普通账号 POST /api/admin/users */
export async function createUser() {
  return request.post('/admin/users')
}

/** 修改等级/状态 PATCH /api/admin/users/{id} */
export async function updateUser(id, payload) {
  return request.patch(`/admin/users/${id}`, payload)
}

/** 重置密码 POST /api/admin/users/{id}/reset-password */
export async function resetUserPassword(id) {
  return request.post(`/admin/users/${id}/reset-password`)
}

/** 软删除账号 DELETE /api/admin/users/{id} */
export async function deleteUser(id) {
  return request.delete(`/admin/users/${id}`)
}

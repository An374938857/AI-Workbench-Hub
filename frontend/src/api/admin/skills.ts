import request from '../request'

export function getAdminSkillList(params?: { page?: number; page_size?: number; keyword?: string }) {
  return request.get('/admin/skills', { params })
}

export function getAdminSkillDetail(id: number) {
  return request.get(`/admin/skills/${id}`)
}

export function createSkill(data: Record<string, unknown>) {
  return request.post('/admin/skills', data)
}

export function updateSkill(id: number, data: Record<string, unknown>) {
  return request.put(`/admin/skills/${id}`, data)
}

export function publishSkill(id: number, changeLog: string) {
  return request.post(`/admin/skills/${id}/publish`, { change_log: changeLog })
}

export function offlineSkill(id: number) {
  return request.post(`/admin/skills/${id}/offline`)
}

export function onlineSkill(id: number) {
  return request.post(`/admin/skills/${id}/online`)
}

export function deleteSkill(id: number) {
  return request.delete(`/admin/skills/${id}`)
}

export function parseSkillPackage(file: File) {
  const formData = new FormData()
  formData.append('package', file)
  return request.post('/admin/skills/parse-package', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 60000,
  })
}

export function getTempFileContent(tempId: string, filePath: string) {
  return request.get(`/admin/skills/temp-package/${tempId}/files/content`, {
    params: { file_path: filePath },
  })
}

export function uploadSkillPackage(id: number, file: File) {
  const formData = new FormData()
  formData.append('package', file)
  return request.post(`/admin/skills/${id}/upload-package`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 60000,
  })
}

export function uploadSkillIcon(id: number, file: File) {
  const formData = new FormData()
  formData.append('icon', file)
  return request.post(`/admin/skills/${id}/upload-icon`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 60000,
  })
}

export function getPackageFiles(id: number, versionType: 'draft' | 'published' = 'draft') {
  return request.get(`/admin/skills/${id}/package-files`, { params: { version_type: versionType } })
}

export function getPackageFileContent(id: number, filePath: string, versionType: 'draft' | 'published' = 'draft') {
  return request.get(`/admin/skills/${id}/package-files/content`, {
    params: { file_path: filePath, version_type: versionType },
  })
}

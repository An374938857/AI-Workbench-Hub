import { h } from 'vue'
import { ElMessageBox } from 'element-plus'

export interface DangerConfirmOptions {
  title: string
  subject: string
  detail: string
  confirmText: string
  confirmType?: 'danger' | 'primary'
  badgeText?: string
}

export function showDangerConfirm(options: DangerConfirmOptions) {
  const confirmType = options.confirmType === 'primary' ? 'primary' : 'danger'
  const badgeText = options.badgeText || (confirmType === 'primary' ? '重要确认' : '高风险操作')

  return ElMessageBox({
    title: options.title,
    message: h('div', { class: 'app-danger-confirm__content' }, [
      h('div', { class: `app-danger-confirm__badge app-danger-confirm__badge--${confirmType}` }, badgeText),
      h('div', { class: 'app-danger-confirm__subject' }, options.subject),
      h('p', { class: 'app-danger-confirm__detail' }, options.detail),
    ]),
    customClass: `app-danger-confirm-dialog app-danger-confirm-dialog--${confirmType}`,
    confirmButtonText: options.confirmText,
    cancelButtonText: '取消',
    confirmButtonClass: `app-danger-confirm__confirm app-danger-confirm__confirm--${confirmType}`,
    cancelButtonClass: 'app-danger-confirm__cancel',
    showClose: true,
    closeOnClickModal: false,
  })
}

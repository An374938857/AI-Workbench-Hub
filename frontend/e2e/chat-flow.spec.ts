import { expect, test, type Page } from '@playwright/test'

async function loginFromPage(page: Page, username: string, password: string) {
  await page.getByPlaceholder('请输入账号').first().fill(username)
  await page.getByPlaceholder('请输入密码').first().fill(password)
  await page.getByRole('button', { name: /登\s*录/ }).click()
  await page.waitForLoadState('networkidle')
}

async function registerAndLoginFallback(page: Page) {
  const ts = Date.now()
  const username = `e2e_user_${ts}`
  const password = `E2E_pass_${ts}`

  await page.getByRole('button', { name: /注册账号/ }).click()
  await page.getByPlaceholder('请输入账号（2-50个字符）').fill(username)
  await page.getByPlaceholder('请输入显示名称（其他用户可见）').fill(`E2E ${ts}`)
  await page.getByPlaceholder('请输入密码（至少6位）').fill(password)
  await page.getByPlaceholder('请再次输入密码').fill(password)
  const registerDialog = page.locator('.el-dialog').filter({ hasText: '注册新账号' }).first()
  await registerDialog.getByRole('button', { name: /注\s*册/ }).click()
  await page.waitForTimeout(500)

  await loginFromPage(page, username, password)
}

test.describe('chat smoke flow', () => {
  test('input-send-stop basic interaction', async ({ page }) => {
    const username = process.env.E2E_USERNAME || 'admin'
    const password = process.env.E2E_PASSWORD || 'admin123'

    await page.goto('/login')
    await loginFromPage(page, username, password)
    if (page.url().includes('/login')) {
      await registerAndLoginFallback(page)
    }

    await page.goto('/chat')
    await expect(page).not.toHaveURL(/\/login/)

    const input = page.locator('#chat-input, .input-box textarea').first()
    await expect(input).toBeVisible({ timeout: 10_000 })
    await input.fill('Playwright smoke test message')

    const sendButton = page.getByRole('button', { name: /发送/ })
    await expect(sendButton).toBeVisible()
    await sendButton.click()

    const stopButton = page.getByRole('button', { name: /停止/ })
    if (await stopButton.isVisible().catch(() => false)) {
      await stopButton.click()
    }
  })

  test('switching back to completed conversation shows latest assistant message immediately', async ({ page }) => {
    test.setTimeout(120_000)
    const username = process.env.E2E_USERNAME || 'admin'
    const password = process.env.E2E_PASSWORD || 'admin123'

    await page.goto('/login')
    await loginFromPage(page, username, password)
    if (page.url().includes('/login')) {
      await registerAndLoginFallback(page)
    }

    await page.goto('/chat')
    await expect(page).not.toHaveURL(/\/login/)

    let sentConversationId: number | null = null
    page.on('request', (request) => {
      if (request.method() !== 'POST') return
      const matched = request.url().match(/\/api\/conversations\/(\d+)\/messages(?:\?.*)?$/)
      if (!matched) return
      const parsed = Number(matched[1])
      if (!Number.isFinite(parsed)) return
      sentConversationId = parsed
    })

    const input = page.locator('#chat-input, .input-box textarea').first()
    await expect(input).toBeVisible({ timeout: 10_000 })
    const uniqueToken = `E2E_SWITCH_BACK_${Date.now()}`
    await input.fill(`请用一句话回复：${uniqueToken}`)
    await page.getByRole('button', { name: /发送/ }).click()
    await expect.poll(() => sentConversationId, { timeout: 15_000 }).not.toBeNull()

    await page.getByRole('button', { name: /新建对话/ }).click()
    const firstConversationItem = page.locator(`.conv-item[data-conv-id="${sentConversationId}"]`).first()
    await expect(firstConversationItem).toBeVisible({ timeout: 10_000 })
    const unreadLamp = firstConversationItem.locator('.conv-status-lamp.is-info')
    await expect(unreadLamp).toBeVisible({ timeout: 90_000 })

    await firstConversationItem.click()

    const latestAssistantMessageContent = page
      .locator('.chat-message:not(.is-user) .msg-content')
      .last()
    await expect(latestAssistantMessageContent).toBeVisible({ timeout: 15_000 })
    await expect.poll(
      async () => (await latestAssistantMessageContent.innerText()).trim().length,
      { timeout: 15_000 },
    ).toBeGreaterThan(0)
    await expect(latestAssistantMessageContent.locator('.cursor-blink')).toHaveCount(0)
  })
})

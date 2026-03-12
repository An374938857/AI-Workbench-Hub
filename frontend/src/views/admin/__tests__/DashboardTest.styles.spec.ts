import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

describe('DashboardTest style contract', () => {
  const filePath = resolve(__dirname, '../DashboardTest.vue')
  const source = readFileSync(filePath, 'utf-8')

  it('does not use striped row tables in dashboard', () => {
    expect(source).not.toMatch(/<el-table[^>]*\bstripe\b/g)
  })

  it('keeps light-mode table rows pure white', () => {
    expect(source).toContain('--table-row-bg-light: #FFFFFF')
  })

  it('defines a dedicated dark-mode table row background token', () => {
    expect(source).toContain('--table-row-bg-dark:')
  })
})

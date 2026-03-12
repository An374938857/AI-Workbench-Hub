import { execSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

function run(command) {
  return execSync(command, { encoding: 'utf8' }).trim()
}

const baselinePath = resolve(process.cwd(), '.any-budget')
const baseline = Number.parseInt(readFileSync(baselinePath, 'utf8').trim(), 10)
if (!Number.isFinite(baseline)) {
  console.error('Invalid .any-budget baseline')
  process.exit(1)
}

const countStr = run("rg -n '\\bany\\b|as any' src --glob '!**/*.d.ts' | wc -l")
const current = Number.parseInt(countStr, 10)

if (!Number.isFinite(current)) {
  console.error('Failed to calculate any usage count')
  process.exit(1)
}

if (current > baseline) {
  console.error(`any budget exceeded: current=${current}, baseline=${baseline}`)
  process.exit(1)
}

console.log(`any budget check passed: current=${current}, baseline=${baseline}`)

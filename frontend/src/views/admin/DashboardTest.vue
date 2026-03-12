<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import {
  getDashboardOverview,
  getDashboardSkills,
  getDashboardTokens,
  getDashboardTrends,
  getDashboardMcpOverview,
  getDashboardMcpStats,
  getDashboardToolRanking,
} from '@/api/admin/dashboard'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart, BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import VChart from 'vue-echarts'

use([CanvasRenderer, LineChart, BarChart, GridComponent, TooltipComponent, LegendComponent])

const loading = ref(false)

const overview = ref({ total_users: 0, active_users_7d: 0, total_conversations: 0, today_conversations: 0, total_tokens: 0 })
const skillStats = ref<any[]>([])
const tokenStats = ref<any[]>([])
const trendData = ref<any[]>([])
const tokenGroupBy = ref('skill')
const trendMetric = ref('conversations')
const mcpOverview = ref({
  total_mcps: 0,
  enabled_mcps: 0,
  total_tool_calls: 0,
  today_tool_calls: 0,
  tool_call_success_rate: 0,
  avg_response_time_ms: 0,
})
const mcpStats = ref<any[]>([])
const toolRanking = ref<any[]>([])

function toLocalDateStr(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

function getDefaultDateRange(): [string, string] {
  const now = new Date()
  const start = new Date(now.getTime() - 30 * 86400000)
  return [toLocalDateStr(start), toLocalDateStr(now)]
}

const dateRange = ref<[string, string]>(getDefaultDateRange())

const dateShortcuts = [
  {
    text: '近 7 天',
    value: () => {
      const end = new Date()
      const start = new Date(end.getTime() - 7 * 86400000)
      return [toLocalDateStr(start), toLocalDateStr(end)]
    },
  },
  {
    text: '近 30 天',
    value: () => {
      const end = new Date()
      const start = new Date(end.getTime() - 30 * 86400000)
      return [toLocalDateStr(start), toLocalDateStr(end)]
    },
  },
  {
    text: '近 90 天',
    value: () => {
      const end = new Date()
      const start = new Date(end.getTime() - 90 * 86400000)
      return [toLocalDateStr(start), toLocalDateStr(end)]
    },
  },
]

const dateParams = computed(() => {
  const [startDate, endDate] = dateRange.value
  return { start_date: startDate, end_date: endDate }
})

async function fetchAll() {
  loading.value = true
  try {
    const [ovRes, skRes, tkRes, trRes, mcpOvRes, mcpStRes, trRes2]: any[] = await Promise.all([
      getDashboardOverview(dateParams.value),
      getDashboardSkills(dateParams.value),
      getDashboardTokens({ ...dateParams.value, group_by: tokenGroupBy.value }),
      getDashboardTrends({ ...dateParams.value, metric: trendMetric.value }),
      getDashboardMcpOverview(dateParams.value),
      getDashboardMcpStats(dateParams.value),
      getDashboardToolRanking(dateParams.value),
    ])
    overview.value = ovRes.data
    skillStats.value = skRes.data
    tokenStats.value = tkRes.data
    trendData.value = trRes.data
    mcpOverview.value = mcpOvRes.data
    mcpStats.value = mcpStRes.data
    toolRanking.value = trRes2.data
  } finally {
    loading.value = false
  }
}

async function refreshTokens() {
  const res: any = await getDashboardTokens({ ...dateParams.value, group_by: tokenGroupBy.value })
  tokenStats.value = res.data
}

async function refreshTrend() {
  const res: any = await getDashboardTrends({ ...dateParams.value, metric: trendMetric.value })
  trendData.value = res.data
}

const _darkFlag = ref(document.documentElement.classList.contains('dark'))
const _observer = new MutationObserver(() => {
  _darkFlag.value = document.documentElement.classList.contains('dark')
})
onMounted(() => _observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] }))
const isDark = computed(() => _darkFlag.value)
const chartTextColor = computed(() => isDark.value ? '#cbd5e1' : '#64748b')
const chartAxisColor = computed(() => isDark.value ? '#f8fafc' : '#1e293b')
const chartSplitColor = computed(() => isDark.value ? '#334155' : '#e2e8f0')
const chartLegendColor = computed(() => isDark.value ? '#cbd5e1' : '#64748b')

const trendOption = computed(() => ({
  tooltip: {
    trigger: 'axis',
    backgroundColor: 'rgba(15,23,42,0.92)',
    borderWidth: 0,
    textStyle: { color: '#f8fafc', fontSize: 13 },
    padding: [10, 14],
    axisPointer: { type: 'line', lineStyle: { color: '#2563eb', width: 1, type: 'dashed' } },
  },
  grid: { left: 46, right: 20, top: 18, bottom: 28 },
  xAxis: {
    type: 'category',
    data: trendData.value.map((d: any) => d.date.slice(5)),
    boundaryGap: false,
    axisLine: { show: false },
    axisLabel: { color: chartTextColor.value, fontSize: 11, margin: 12 },
    axisTick: { show: false },
  },
  yAxis: {
    type: 'value',
    splitLine: { lineStyle: { color: chartSplitColor.value } },
    axisLabel: { color: chartTextColor.value, fontSize: 11 },
    axisLine: { show: false },
    axisTick: { show: false },
  },
  series: [{
    type: 'line',
    data: trendData.value.map((d: any) => d.value),
    smooth: 0.35,
    symbol: 'circle',
    symbolSize: 7,
    showSymbol: false,
    lineStyle: { width: 3, color: '#2563eb' },
    itemStyle: { color: '#2563eb' },
    areaStyle: {
      color: {
        type: 'linear',
        x: 0,
        y: 0,
        x2: 0,
        y2: 1,
        colorStops: [
          { offset: 0, color: 'rgba(37,99,235,0.28)' },
          { offset: 0.6, color: 'rgba(37,99,235,0.08)' },
          { offset: 1, color: 'rgba(37,99,235,0)' },
        ],
      },
    },
  }],
}))

const tokenBarOption = computed(() => {
  const labels = tokenStats.value.map((d: any) => d.label)
  const axisLabelWidth = tokenGroupBy.value === 'model' ? 180 : 96
  return {
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(15,23,42,0.92)',
      borderWidth: 0,
      textStyle: { color: '#f8fafc', fontSize: 13 },
      padding: [10, 14],
    },
    grid: { left: 8, right: 72, top: 18, bottom: 26, containLabel: true },
    xAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: chartSplitColor.value } },
      axisLabel: { color: chartTextColor.value, fontSize: 11 },
      axisLine: { show: false },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'category',
      data: labels,
      inverse: true,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: chartAxisColor.value, fontSize: 12, width: axisLabelWidth, overflow: 'truncate' },
    },
    legend: {
      orient: 'vertical',
      right: 0,
      top: 'middle',
      itemWidth: 10,
      itemHeight: 10,
      itemGap: 14,
      textStyle: { color: chartLegendColor.value, fontSize: 12 },
      data: ['输入', '输出'],
    },
    series: [
      {
        name: '输入',
        type: 'bar',
        stack: 'total',
        barWidth: 16,
        data: tokenStats.value.map((d: any) => d.input_tokens),
        itemStyle: { color: '#1d4ed8', borderRadius: [0, 0, 0, 0] },
      },
      {
        name: '输出',
        type: 'bar',
        stack: 'total',
        barWidth: 16,
        data: tokenStats.value.map((d: any) => d.output_tokens),
        itemStyle: { color: '#06b6d4', borderRadius: [0, 6, 6, 0] },
      },
    ],
  }
})

function formatTokens(n: number): string {
  if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M'
  if (n >= 1000) return (n / 1000).toFixed(1) + 'K'
  return String(n)
}

function formatTime(val: string | null) {
  if (!val) return '-'
  return val.replace('T', ' ').substring(0, 16)
}

const overviewCards = computed(() => [
  {
    label: '注册用户',
    value: overview.value.total_users,
    icon: 'User',
    accent: '#1d4ed8',
    badgeBg: 'linear-gradient(145deg, #dbeafe 0%, #eff6ff 100%)',
  },
  {
    label: '7天活跃',
    value: overview.value.active_users_7d,
    icon: 'TrendCharts',
    accent: '#0f9f69',
    badgeBg: 'linear-gradient(145deg, #dcfce7 0%, #f0fdf4 100%)',
  },
  {
    label: '总对话数',
    value: overview.value.total_conversations,
    icon: 'ChatDotRound',
    accent: '#2563eb',
    badgeBg: 'linear-gradient(145deg, #dbeafe 0%, #f0f9ff 100%)',
  },
  {
    label: '今日对话',
    value: overview.value.today_conversations,
    icon: 'Clock',
    accent: '#d97706',
    badgeBg: 'linear-gradient(145deg, #fde68a 0%, #fffbeb 100%)',
  },
  {
    label: 'Token 消耗',
    value: formatTokens(overview.value.total_tokens),
    icon: 'Coin',
    accent: '#be185d',
    badgeBg: 'linear-gradient(145deg, #fbcfe8 0%, #fdf2f8 100%)',
  },
])

const mcpOverviewCards = computed(() => [
  {
    label: '工具调用总数',
    value: mcpOverview.value.total_tool_calls,
    icon: 'Connection',
    accent: '#5b21b6',
    badgeBg: 'linear-gradient(145deg, #ddd6fe 0%, #f5f3ff 100%)',
  },
  {
    label: '今日调用',
    value: mcpOverview.value.today_tool_calls,
    icon: 'Clock',
    accent: '#0e7490',
    badgeBg: 'linear-gradient(145deg, #cffafe 0%, #ecfeff 100%)',
  },
  {
    label: '调用成功率',
    value: (mcpOverview.value.tool_call_success_rate * 100).toFixed(0) + '%',
    icon: 'CircleCheck',
    accent: '#047857',
    badgeBg: 'linear-gradient(145deg, #d1fae5 0%, #f0fdf4 100%)',
  },
  {
    label: '平均响应',
    value: mcpOverview.value.avg_response_time_ms + 'ms',
    icon: 'Timer',
    accent: '#b45309',
    badgeBg: 'linear-gradient(145deg, #fed7aa 0%, #fff7ed 100%)',
  },
  {
    label: 'MCP 启用/总计',
    value: mcpOverview.value.enabled_mcps + ' / ' + mcpOverview.value.total_mcps,
    icon: 'Setting',
    accent: '#334155',
    badgeBg: 'linear-gradient(145deg, #e2e8f0 0%, #f8fafc 100%)',
  },
])

onMounted(fetchAll)
</script>

<template>
  <div class="dashboard-lab" v-loading="loading">
    <header class="hero-row">
      <div class="hero-copy">
        <h2>数据看板</h2>
        <div class="hero-meta-row">
          <p>查看核心指标、趋势变化、Token 分布与 MCP 统计。</p>
          <div class="date-picker-shell">
            <el-date-picker
              v-model="dateRange"
              type="daterange"
              value-format="YYYY-MM-DD"
              unlink-panels
              range-separator="至"
              start-placeholder="开始日期"
              end-placeholder="结束日期"
              :clearable="false"
              :shortcuts="dateShortcuts"
              class="date-range-picker"
              @change="fetchAll"
            />
          </div>
        </div>
      </div>
    </header>

    <section class="lab-grid">
      <aside class="panel panel-rail">
        <div class="panel-title">
          <span class="title-badge"><el-icon><Histogram /></el-icon></span>
          核心指标
        </div>

        <div class="kpi-rail">
          <article v-for="(c, i) in overviewCards" :key="`ov-${i}`" class="kpi-item">
            <div class="kpi-icon-shell" :style="{ borderColor: c.accent + '44' }">
              <div class="kpi-icon" :style="{ background: c.badgeBg, color: c.accent }">
                <el-icon :size="20"><component :is="c.icon" /></el-icon>
              </div>
            </div>
            <div class="kpi-main">
              <div class="kpi-label">{{ c.label }}</div>
              <div class="kpi-value" :style="{ color: c.accent }">{{ c.value }}</div>
            </div>
          </article>
        </div>
      </aside>

      <section class="panel panel-trend">
        <div class="panel-head-split">
          <div class="panel-title">
            <span class="title-badge"><el-icon><TrendCharts /></el-icon></span>
            使用趋势
          </div>
          <el-radio-group v-model="trendMetric" size="small" @change="refreshTrend">
            <el-radio-button value="conversations">对话数</el-radio-button>
            <el-radio-button value="tokens">Token</el-radio-button>
            <el-radio-button value="tool_calls">工具调用</el-radio-button>
          </el-radio-group>
        </div>
        <v-chart :option="trendOption" class="chart-body trend-body" autoresize />
      </section>

      <section class="panel panel-token">
        <div class="panel-head-split token-head">
          <div class="panel-title">
            <span class="title-badge"><el-icon><PieChart /></el-icon></span>
            Token 分布
          </div>
          <el-radio-group v-model="tokenGroupBy" size="small" @change="refreshTokens">
            <el-radio-button value="skill">Skill</el-radio-button>
            <el-radio-button value="user">用户</el-radio-button>
            <el-radio-button value="provider">提供商</el-radio-button>
            <el-radio-button value="model">模型</el-radio-button>
          </el-radio-group>
        </div>
        <v-chart :option="tokenBarOption" class="chart-body token-body" autoresize />
      </section>

      <section class="panel panel-skills">
        <div class="panel-title panel-title-space">
          <span class="title-badge"><el-icon><Document /></el-icon></span>
          Skill
        </div>
        <div class="skill-table-shell">
          <el-table :data="skillStats" size="default" class="stats-table skill-stats-table">
            <el-table-column prop="skill_name" label="Skill 名称" min-width="150" show-overflow-tooltip>
              <template #default="{ row }">
                <span class="skill-name-cell">{{ row.skill_name }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="call_count" label="调用次数" width="104" sortable>
              <template #default="{ row }">
                <span class="num-cell">{{ row.call_count }}</span>
              </template>
            </el-table-column>
            <el-table-column label="成功率" width="118">
              <template #default="{ row }">
                <div class="rate-cell">
                  <div class="rate-track">
                    <div class="rate-bar" :style="{ width: (row.success_rate * 100) + '%' }" />
                  </div>
                  <span>{{ (row.success_rate * 100).toFixed(0) }}%</span>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="平均评分" width="98">
              <template #default="{ row }">
                <span v-if="row.avg_rating > 0" class="rating-cell">
                  {{ row.avg_rating }} <el-icon color="#d97706" :size="14"><Star /></el-icon>
                </span>
                <span v-else class="muted-cell">-</span>
              </template>
            </el-table-column>
            <el-table-column label="Token 消耗" width="116" sortable sort-by="total_tokens">
              <template #default="{ row }">
                <span class="num-cell">{{ formatTokens(row.total_tokens) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="最近使用" width="138">
              <template #default="{ row }">
                <span class="time-cell">{{ formatTime(row.last_used_at) }}</span>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </section>

      <section class="panel panel-mcp">
        <div class="panel-title panel-title-space">
          <span class="title-badge"><el-icon><Connection /></el-icon></span>
          MCP
        </div>

        <div class="mcp-metrics">
          <article v-for="(c, i) in mcpOverviewCards" :key="`mcp-${i}`" class="mcp-mini">
            <div class="mcp-mini-icon" :style="{ background: c.badgeBg, color: c.accent }">
              <el-icon :size="16"><component :is="c.icon" /></el-icon>
            </div>
            <div class="mcp-mini-main">
              <div class="mcp-mini-label">{{ c.label }}</div>
              <div class="mcp-mini-value">{{ c.value }}</div>
            </div>
          </article>
        </div>

        <div class="mcp-tables">
          <div class="sub-table">
            <div class="sub-title"><el-icon><Histogram /></el-icon> MCP 调用统计</div>
            <el-table :data="mcpStats" size="default" class="stats-table">
              <el-table-column prop="mcp_name" label="MCP" min-width="120" />
              <el-table-column prop="call_count" label="调用" width="86" sortable />
              <el-table-column label="成功率" width="90">
                <template #default="{ row }">
                  <span class="num-cell">{{ (row.success_rate * 100).toFixed(0) }}%</span>
                </template>
              </el-table-column>
              <el-table-column label="平均响应" width="96">
                <template #default="{ row }">
                  <span class="num-cell">{{ row.avg_response_time_ms }}ms</span>
                </template>
              </el-table-column>
            </el-table>
          </div>

          <div class="sub-table">
            <div class="sub-title"><el-icon><DataLine /></el-icon> 工具调用排行</div>
            <el-table :data="toolRanking" size="default" class="stats-table">
              <el-table-column type="index" label="#" width="50" />
              <el-table-column prop="tool_name" label="工具" min-width="130" />
              <el-table-column prop="mcp_name" label="MCP" min-width="100" />
              <el-table-column prop="call_count" label="调用" width="86" sortable />
            </el-table>
          </div>
        </div>
      </section>
    </section>
  </div>
</template>

<style scoped>
.dashboard-lab {
  --panel-bg: var(--bg-card, #ffffff);
  --panel-border: var(--border-primary, #e5e7eb);
  --text-main: var(--text-primary, #0f172a);
  --text-sub: var(--text-secondary, #64748b);
  --text-muted: var(--text-muted, #94a3b8);
  --table-row-bg-light: #FFFFFF;
  --table-row-bg-dark: #1b2534;
  --date-picker-bg: linear-gradient(180deg, #ffffff 0%, #f6faff 100%);
  --date-picker-border: #cfe0f5;
  --date-picker-border-hover: #93c5fd;
  --date-picker-border-active: #3b82f6;
  --date-picker-shadow: 0 6px 14px -12px rgba(29, 78, 216, 0.6);
  --date-picker-range-text: #334155;
  --date-picker-meta-text: #64748b;
  --seg-bg: linear-gradient(180deg, #f8fbff 0%, #f1f6ff 100%);
  --seg-border: #d9e5f7;
  --seg-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.86);
  --seg-text: #64748b;
  --seg-text-hover: #334155;
  --seg-active-text: #ffffff;
  --seg-active-bg: linear-gradient(180deg, #3b82f6 0%, #2563eb 100%);
  --seg-active-shadow: 0 6px 12px -8px rgba(37, 99, 235, 0.65);
  width: 100%;
  min-height: calc(100vh - 48px);
  background: var(--bg-page, #f5f7fa);
  border-radius: 18px;
  padding: 20px;
}

.hero-row {
  display: block;
  margin-bottom: 16px;
}

.hero-copy {
  width: 100%;
}

.hero-copy h2 {
  margin: 6px 0 0;
  font-size: 28px;
  color: var(--text-main);
  letter-spacing: -0.4px;
}

.hero-meta-row {
  margin-top: 8px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.hero-meta-row p {
  flex: 1;
}

.date-picker-shell {
  display: flex;
  justify-content: flex-end;
  flex: 0 0 auto;
}

.hero-copy p {
  margin: 0;
  font-size: 13px;
  line-height: 1.55;
  color: var(--text-sub);
}

.date-range-picker {
  width: 244px !important;
  max-width: 100%;
  flex-shrink: 0;
}

.hero-meta-row :deep(.date-range-picker.el-date-editor) {
  height: 34px;
  border-radius: 10px;
  border: 1px solid var(--date-picker-border);
  background: var(--date-picker-bg);
  box-shadow: var(--date-picker-shadow);
  transition: border-color 0.2s ease, box-shadow 0.2s ease, background-color 0.2s ease;
}

.hero-meta-row :deep(.date-range-picker.el-date-editor:hover) {
  border-color: var(--date-picker-border-hover);
}

.hero-meta-row :deep(.date-range-picker.el-date-editor.is-active) {
  border-color: var(--date-picker-border-active);
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.15);
}

.hero-meta-row :deep(.date-range-picker .el-range-input) {
  color: var(--date-picker-range-text);
  font-size: 12.5px;
  font-weight: 550;
}

.hero-meta-row :deep(.date-range-picker .el-range-separator),
.hero-meta-row :deep(.date-range-picker .el-icon) {
  color: var(--date-picker-meta-text);
}

.lab-grid {
  display: grid;
  gap: 14px;
  grid-template-columns: 236px minmax(0, 1.55fr) minmax(0, 1fr);
  grid-template-areas:
    'rail trend token'
    'rail skills mcp';
  align-items: stretch;
}

.panel {
  background: var(--panel-bg);
  border: 1px solid var(--panel-border);
  border-radius: 16px;
  box-shadow: 0 14px 30px -24px rgba(15, 23, 42, 0.52);
  overflow: hidden;
}

.panel-rail {
  grid-area: rail;
  padding: 14px 12px;
}

.panel-trend {
  grid-area: trend;
  display: flex;
  flex-direction: column;
}

.panel-token {
  grid-area: token;
  display: flex;
  flex-direction: column;
}

.panel-skills {
  grid-area: skills;
  padding: 0 0 8px;
}

.skill-table-shell {
  padding: 0 14px 0;
  overflow-x: auto;
}

.skill-table-shell :deep(.el-table) {
  min-width: 100%;
}

.panel-mcp {
  grid-area: mcp;
  padding: 0 0 8px;
  display: flex;
  flex-direction: column;
}

.panel-head-split {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 14px 14px 0;
}

.token-head {
  flex-wrap: wrap;
}

.panel-title {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--text-main);
  font-size: 15px;
  font-weight: 650;
}

.panel-title-space {
  padding: 14px 14px 10px;
}

.panel-head-split :deep(.el-radio-group) {
  display: inline-flex;
  align-items: center;
  padding: 3px;
  border-radius: 10px;
  border: 1px solid var(--seg-border);
  background: var(--seg-bg);
  box-shadow: var(--seg-shadow);
}

.panel-head-split :deep(.el-radio-button__inner) {
  height: 26px;
  min-width: 62px;
  border: 0 !important;
  border-radius: 7px !important;
  background: transparent;
  box-shadow: none !important;
  color: var(--seg-text);
  font-size: 12px;
  font-weight: 560;
  letter-spacing: 0.1px;
  padding: 0 12px;
  line-height: 26px;
  text-align: center;
  transition: color 0.2s ease, background-color 0.22s ease, box-shadow 0.22s ease;
}

.panel-head-split :deep(.el-radio-button:not(:first-child) .el-radio-button__inner) {
  margin-left: 2px;
}

.panel-head-split :deep(.el-radio-button__original-radio:checked + .el-radio-button__inner) {
  color: var(--seg-active-text);
  background: var(--seg-active-bg);
  box-shadow: var(--seg-active-shadow);
}

.panel-head-split :deep(.el-radio-button__inner:hover) {
  color: var(--seg-text-hover);
}

.title-badge {
  width: 28px;
  height: 28px;
  border-radius: 9px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #1d4ed8;
  background: linear-gradient(145deg, #dbeafe 0%, #eff6ff 100%);
  border: 1px solid #bfdbfe;
}

.kpi-rail {
  display: grid;
  gap: 10px;
  margin-top: 12px;
}

.kpi-item {
  display: flex;
  align-items: center;
  gap: 10px;
  border-radius: 14px;
  padding: 10px;
  border: 1px solid #e2e8f0;
  background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.kpi-item:hover {
  transform: translateX(2px);
  box-shadow: 0 12px 18px -16px rgba(37, 99, 235, 0.8);
}

.kpi-icon-shell {
  width: 44px;
  height: 44px;
  border-radius: 14px;
  border: 1px solid;
  display: grid;
  place-items: center;
  background: #fff;
}

.kpi-icon {
  width: 34px;
  height: 34px;
  border-radius: 11px;
  display: grid;
  place-items: center;
}

.kpi-main {
  min-width: 0;
}

.kpi-label {
  font-size: 12px;
  color: var(--text-sub);
}

.kpi-value {
  margin-top: 2px;
  font-size: 22px;
  line-height: 1.1;
  font-weight: 800;
  letter-spacing: -0.4px;
  font-variant-numeric: tabular-nums;
}

.chart-body {
  flex: 0 0 auto;
  padding: 6px 12px 10px;
}

.trend-body {
  height: 360px !important;
}

.token-body {
  height: 360px !important;
}

.mcp-metrics {
  display: grid;
  grid-template-columns: 1fr;
  gap: 8px;
  padding: 0 12px;
}

.mcp-mini {
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  background: #fff;
  padding: 8px 10px;
  display: flex;
  align-items: center;
  gap: 9px;
}

.mcp-mini-icon {
  width: 28px;
  height: 28px;
  border-radius: 9px;
  border: 1px solid #dbeafe;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.mcp-mini-main {
  min-width: 0;
}

.mcp-mini-label {
  font-size: 11px;
  color: var(--text-sub);
}

.mcp-mini-value {
  margin-top: 1px;
  font-size: 16px;
  font-weight: 700;
  color: var(--text-main);
  font-variant-numeric: tabular-nums;
}

.mcp-tables {
  display: grid;
  grid-template-columns: 1fr;
  gap: 10px;
  padding: 10px 12px 0;
}

.sub-table {
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  overflow: hidden;
  background: #fff;
}

.sub-title {
  height: 36px;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 0 10px;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-main);
  border-bottom: 1px solid #edf2f7;
  background: #f8fbff;
}

.stats-table {
  --el-table-border-color: #edf2f7;
  --el-table-bg-color: var(--table-row-bg-light);
  --el-table-tr-bg-color: var(--table-row-bg-light);
  --el-table-expanded-cell-bg-color: var(--table-row-bg-light);
  --el-table-header-bg-color: #f8fbff;
  --el-table-row-hover-bg-color: #f1f5f9;
  --el-table-text-color: var(--text-main);
  --el-table-header-text-color: #475569;
  background: var(--table-row-bg-light);
}

:deep(.el-table .cell) {
  font-size: 12.5px;
}

.skill-stats-table :deep(.el-table__header .cell) {
  white-space: nowrap;
}

.skill-stats-table :deep(.el-table__header .caret-wrapper) {
  margin-left: 2px;
}

.skill-name-cell {
  font-weight: 600;
  color: var(--text-main);
}

.num-cell {
  font-weight: 700;
  color: var(--text-main);
  font-variant-numeric: tabular-nums;
}

.time-cell {
  color: var(--text-sub);
  font-size: 12px;
}

.rate-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}

.rate-track {
  width: 46px;
  height: 6px;
  background: #e2e8f0;
  border-radius: 4px;
  overflow: hidden;
}

.rate-bar {
  height: 100%;
  min-width: 3px;
  border-radius: 4px;
  background: linear-gradient(90deg, #1d4ed8, #06b6d4);
}

.rating-cell {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-weight: 700;
  color: var(--text-main);
}

.muted-cell {
  color: var(--text-muted);
}

@media (max-width: 1320px) {
  .lab-grid {
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    grid-template-areas:
      'rail rail'
      'trend token'
      'skills mcp';
  }

  .panel-rail {
    padding-bottom: 12px;
  }

  .kpi-rail {
    grid-template-columns: repeat(5, minmax(0, 1fr));
  }
}

@media (max-width: 980px) {
  .hero-meta-row {
    flex-direction: column;
    align-items: stretch;
    gap: 10px;
  }

  .date-picker-shell {
    justify-content: flex-start;
  }

  .date-range-picker {
    width: 100%;
    max-width: 100%;
  }

  .lab-grid {
    grid-template-columns: 1fr;
    grid-template-areas:
      'rail'
      'trend'
      'token'
      'skills'
      'mcp';
  }

  .kpi-rail {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .trend-body,
  .token-body {
    height: 320px;
  }
}

@media (max-width: 640px) {
  .dashboard-lab {
    border-radius: 12px;
    padding: 12px;
  }

  .hero-copy h2 {
    font-size: 23px;
  }

  .kpi-rail {
    grid-template-columns: 1fr;
  }

  .panel-head-split {
    flex-direction: column;
    align-items: flex-start;
  }

  .skill-table-shell {
    padding: 0 10px 0;
  }

  .skill-table-shell :deep(.el-table) {
    min-width: 660px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .kpi-item {
    transition: none;
  }
}

:global(html.dark .dashboard-lab) {
  --panel-bg: var(--bg-card, #242424);
  --panel-border: var(--border-primary, #3a3a3a);
  --text-main: var(--text-primary, #e5e5e5);
  --text-sub: var(--text-secondary, #b3b3b3);
  --text-muted: var(--text-muted, #8a8a8a);
  --table-row-bg-dark: #242424;
  --date-picker-bg: #2a2a2a;
  --date-picker-border: #3a3a3a;
  --date-picker-border-hover: #4b5563;
  --date-picker-border-active: #60a5fa;
  --date-picker-shadow: none;
  --date-picker-range-text: #e5e5e5;
  --date-picker-meta-text: #b3b3b3;
  --seg-bg: linear-gradient(180deg, rgba(55, 65, 81, 0.78) 0%, rgba(43, 54, 69, 0.78) 100%);
  --seg-border: #4b5563;
  --seg-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04);
  --seg-text: #b6c2d1;
  --seg-text-hover: #e2e8f0;
  --seg-active-text: #eff6ff;
  --seg-active-bg: linear-gradient(180deg, #3b82f6 0%, #2563eb 100%);
  --seg-active-shadow: 0 8px 14px -10px rgba(37, 99, 235, 0.72);
  background: var(--bg-page, #111315);
}

:global(html.dark .kpi-item),
:global(html.dark .mcp-mini),
:global(html.dark .sub-table) {
  background: var(--bg-card, #242424);
  border-color: var(--border-primary, #3a3a3a);
}

:global(html.dark .title-badge) {
  border-color: rgba(147, 197, 253, 0.35);
  background: rgba(30, 64, 175, 0.22);
  color: #bfdbfe;
}

:global(html.dark .sub-title) {
  background: #2a2a2a;
  border-bottom-color: var(--border-primary, #3a3a3a);
}

:global(html.dark .stats-table) {
  --el-table-border-color: var(--border-primary, #3a3a3a);
  --el-table-bg-color: var(--table-row-bg-dark);
  --el-table-tr-bg-color: var(--table-row-bg-dark);
  --el-table-expanded-cell-bg-color: var(--table-row-bg-dark);
  --el-table-header-bg-color: #2a2a2a;
  --el-table-row-hover-bg-color: #333333;
  --el-table-text-color: var(--text-primary, #e5e5e5);
  --el-table-header-text-color: var(--text-secondary, #b3b3b3);
  background: var(--table-row-bg-dark);
}
</style>

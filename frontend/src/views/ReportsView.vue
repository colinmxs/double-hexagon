<script setup lang="ts">
import { onMounted, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  useReports,
  AVAILABLE_FIELDS,
  OPERATORS,
  PRE_BUILT_TEMPLATES,
} from '../composables/useReports'
import type { PreBuiltTemplate, SavedReport } from '../composables/useReports'

const { t } = useI18n()

const {
  config,
  result,
  isLoading,
  error,
  savedReports,
  savedReportsLoading,
  isExporting,
  exportError,
  exportSuccess,
  saveReportName,
  isSaving,
  saveError,
  saveSuccess,
  giveawayYears,
  yearsLoading,
  autoRunEnabled,
  fetchGiveawayYears,
  runReport,
  exportCsv,
  fetchSavedReports,
  saveReport,
  loadSavedReport,
  deleteSavedReport,
  loadTemplate,
  addFilter,
  removeFilter,
  toggleColumn,
  setPage,
} = useReports()

function fieldLabel(path: string): string {
  const f = AVAILABLE_FIELDS.find((fd) => fd.path === path)
  return f ? t(f.labelKey) : path
}

function operatorLabel(op: string): string {
  const o = OPERATORS.find((od) => od.value === op)
  return o ? t(o.labelKey) : op
}

// Chart type toggle
import { ref } from 'vue'
const chartType = ref<'bar' | 'pie'>('bar')

const groupEntries = computed(() => {
  if (!result.value?.groups) return []
  return Object.entries(result.value.groups)
    .map(([key, val]) => ({ label: key, count: val.count }))
    .sort((a, b) => b.count - a.count)
})

const maxGroupCount = computed(() => {
  if (groupEntries.value.length === 0) return 1
  return Math.max(...groupEntries.value.map((g) => g.count), 1)
})

const totalGroupCount = computed(() => {
  return groupEntries.value.reduce((sum, g) => sum + g.count, 0) || 1
})

// SVG pie chart segments
const pieSegments = computed(() => {
  const entries = groupEntries.value
  if (entries.length === 0) return []
  const total = totalGroupCount.value
  const colors = ['#4a90d9', '#50c878', '#f5a623', '#d94a4a', '#9b59b6', '#1abc9c', '#e67e22', '#3498db', '#e74c3c', '#2ecc71']
  let cumAngle = 0
  return entries.map((e, i) => {
    const fraction = e.count / total
    const startAngle = cumAngle
    cumAngle += fraction * 360
    const endAngle = cumAngle
    const largeArc = fraction > 0.5 ? 1 : 0
    const startRad = ((startAngle - 90) * Math.PI) / 180
    const endRad = ((endAngle - 90) * Math.PI) / 180
    const x1 = 50 + 40 * Math.cos(startRad)
    const y1 = 50 + 40 * Math.sin(startRad)
    const x2 = 50 + 40 * Math.cos(endRad)
    const y2 = 50 + 40 * Math.sin(endRad)
    const d = fraction >= 1
      ? `M50,10 A40,40 0 1,1 49.99,10 Z`
      : `M50,50 L${x1},${y1} A40,40 0 ${largeArc},1 ${x2},${y2} Z`
    return { d, color: colors[i % colors.length], label: e.label, count: e.count }
  })
})

function handleLoadTemplate(tpl: PreBuiltTemplate) {
  autoRunEnabled.value = false
  loadTemplate(tpl)
  autoRunEnabled.value = true
  runReport()
}

function handleLoadSaved(report: SavedReport) {
  autoRunEnabled.value = false
  loadSavedReport(report)
  autoRunEnabled.value = true
  runReport()
}

function handleDeleteSaved(reportId: string) {
  if (confirm(t('reports.deleteConfirm'))) {
    deleteSavedReport(reportId)
  }
}

onMounted(async () => {
  await fetchGiveawayYears()
  await fetchSavedReports()
})
</script>

<template>
  <div class="reports-view">
    <h1>{{ t('reports.title') }}</h1>

    <div class="reports-view__layout">
      <!-- Sidebar: templates, saved reports -->
      <aside class="reports-view__sidebar">
        <!-- Giveaway Year -->
        <div class="reports-view__section">
          <h3>{{ t('reports.giveawayYear') }}</h3>
          <select v-model="config.giveaway_year" :disabled="yearsLoading" class="reports-view__select">
            <option v-for="y in giveawayYears" :key="y.year" :value="y.year">
              {{ y.year }}{{ y.is_active ? ' ★' : '' }}
            </option>
          </select>
        </div>

        <!-- Pre-built templates -->
        <div class="reports-view__section">
          <h3>{{ t('reports.templates') }}</h3>
          <ul class="reports-view__template-list">
            <li v-for="(tpl, i) in PRE_BUILT_TEMPLATES" :key="i">
              <button class="reports-view__template-btn" @click="handleLoadTemplate(tpl)">
                {{ t(tpl.nameKey) }}
              </button>
            </li>
          </ul>
        </div>

        <!-- Saved reports -->
        <div class="reports-view__section">
          <h3>{{ t('reports.savedReports') }}</h3>
          <div v-if="savedReportsLoading" class="reports-view__hint">{{ t('common.loading') }}</div>
          <ul v-else class="reports-view__saved-list">
            <li v-for="sr in savedReports" :key="sr.report_id" class="reports-view__saved-item">
              <button class="reports-view__template-btn" @click="handleLoadSaved(sr)">{{ sr.name }}</button>
              <button class="reports-view__delete-btn" :aria-label="t('common.delete')" @click="handleDeleteSaved(sr.report_id)">×</button>
            </li>
          </ul>
          <!-- Save current -->
          <div class="reports-view__save-form">
            <input
              v-model="saveReportName"
              type="text"
              :placeholder="t('reports.reportNamePlaceholder')"
              class="reports-view__input"
            />
            <button class="reports-view__btn" :disabled="isSaving || !saveReportName.trim()" @click="saveReport">
              {{ isSaving ? t('common.loading') : t('reports.saveReport') }}
            </button>
          </div>
          <div v-if="saveSuccess" class="reports-view__success" role="status">{{ t(saveSuccess) }}</div>
          <div v-if="saveError" class="reports-view__error" role="alert">{{ t(saveError) }}</div>
        </div>
      </aside>

      <!-- Main content -->
      <div class="reports-view__main">
        <!-- Column picker -->
        <div class="reports-view__section">
          <h3>{{ t('reports.columnPicker') }}</h3>
          <div class="reports-view__columns">
            <label v-for="f in AVAILABLE_FIELDS" :key="f.path" class="reports-view__col-label">
              <input type="checkbox" :checked="config.columns.includes(f.path)" @change="toggleColumn(f.path)" />
              {{ t(f.labelKey) }}
            </label>
          </div>
        </div>

        <!-- Filters -->
        <div class="reports-view__section">
          <h3>{{ t('reports.filters') }}</h3>
          <div v-for="(filter, idx) in config.filters" :key="idx" class="reports-view__filter-row">
            <select v-model="filter.field" class="reports-view__select">
              <option value="">{{ t('reports.field') }}</option>
              <option v-for="f in AVAILABLE_FIELDS" :key="f.path" :value="f.path">{{ t(f.labelKey) }}</option>
            </select>
            <select v-model="filter.operator" class="reports-view__select">
              <option v-for="op in OPERATORS" :key="op.value" :value="op.value">{{ t(op.labelKey) }}</option>
            </select>
            <template v-if="filter.operator === 'between'">
              <input v-model="(filter.value as string[])[0]" type="text" :placeholder="t('reports.valueLow')" class="reports-view__input reports-view__input--sm" />
              <input v-model="(filter.value as string[])[1]" type="text" :placeholder="t('reports.valueHigh')" class="reports-view__input reports-view__input--sm" />
            </template>
            <template v-else>
              <input v-model="filter.value" type="text" :placeholder="filter.operator === 'in_list' ? t('reports.valuesCommaSeparated') : t('reports.value')" class="reports-view__input" />
            </template>
            <button class="reports-view__delete-btn" :aria-label="t('reports.removeFilter')" @click="removeFilter(idx)">×</button>
          </div>
          <button class="reports-view__btn reports-view__btn--secondary" @click="addFilter">{{ t('reports.addFilter') }}</button>
        </div>

        <!-- Group by / Sort -->
        <div class="reports-view__section reports-view__row">
          <div>
            <label>{{ t('reports.groupBy') }}</label>
            <select v-model="config.group_by" class="reports-view__select">
              <option value="">{{ t('reports.noGrouping') }}</option>
              <option v-for="f in AVAILABLE_FIELDS" :key="f.path" :value="f.path">{{ t(f.labelKey) }}</option>
            </select>
          </div>
          <div>
            <label>{{ t('reports.sortBy') }}</label>
            <select v-model="config.sort_by" class="reports-view__select">
              <option value="">—</option>
              <option v-for="f in AVAILABLE_FIELDS" :key="f.path" :value="f.path">{{ t(f.labelKey) }}</option>
            </select>
          </div>
          <div>
            <label>&nbsp;</label>
            <select v-model="config.sort_order" class="reports-view__select">
              <option value="asc">{{ t('reports.ascending') }}</option>
              <option value="desc">{{ t('reports.descending') }}</option>
            </select>
          </div>
          <div>
            <label>{{ t('reports.pageSize') }}</label>
            <select v-model.number="config.page_size" class="reports-view__select">
              <option :value="25">25</option>
              <option :value="50">50</option>
              <option :value="100">100</option>
              <option :value="200">200</option>
            </select>
          </div>
        </div>

        <!-- Export + Run -->
        <div class="reports-view__actions">
          <button class="reports-view__btn" :disabled="isLoading || config.columns.length === 0" @click="runReport">
            {{ isLoading ? t('reports.loading') : t('reports.runReport') }}
          </button>
          <button class="reports-view__btn reports-view__btn--secondary" :disabled="isExporting || config.columns.length === 0" @click="exportCsv">
            {{ isExporting ? t('reports.exporting') : t('reports.exportCsv') }}
          </button>
        </div>
        <div v-if="exportSuccess" class="reports-view__success" role="status">{{ t(exportSuccess) }}</div>
        <div v-if="exportError" class="reports-view__error" role="alert">{{ t(exportError) }}</div>

        <!-- Loading -->
        <div v-if="isLoading" class="reports-view__loading" role="status">{{ t('reports.loading') }}</div>

        <!-- Error -->
        <div v-if="error" class="reports-view__error" role="alert">{{ t(error) }}</div>

        <!-- Results -->
        <template v-if="result && !isLoading">
          <!-- Summary stats -->
          <div class="reports-view__summary">
            <h3>{{ t('reports.summary') }}</h3>
            <div class="reports-view__summary-grid">
              <div class="reports-view__stat">
                <span class="reports-view__stat-value">{{ result.summary.total_applications }}</span>
                <span class="reports-view__stat-label">{{ t('reports.totalApplications') }}</span>
              </div>
              <div class="reports-view__stat">
                <span class="reports-view__stat-value">{{ result.summary.total_children }}</span>
                <span class="reports-view__stat-label">{{ t('reports.totalChildren') }}</span>
              </div>
              <div class="reports-view__stat">
                <span class="reports-view__stat-label">{{ t('reports.byStatus') }}</span>
                <ul class="reports-view__breakdown">
                  <li v-for="(count, status) in result.summary.applications_by_status" :key="status">{{ status }}: {{ count }}</li>
                </ul>
              </div>
              <div class="reports-view__stat">
                <span class="reports-view__stat-label">{{ t('reports.bySource') }}</span>
                <ul class="reports-view__breakdown">
                  <li v-for="(count, source) in result.summary.applications_by_source_type" :key="source">{{ source }}: {{ count }}</li>
                </ul>
              </div>
            </div>
          </div>

          <!-- Groups + Charts -->
          <div v-if="result.groups && groupEntries.length > 0" class="reports-view__groups-section">
            <div class="reports-view__groups-header">
              <h3>{{ t('reports.groups') }}</h3>
              <div class="reports-view__chart-toggle">
                <button :class="['reports-view__chart-btn', { active: chartType === 'bar' }]" @click="chartType = 'bar'">{{ t('reports.barChart') }}</button>
                <button :class="['reports-view__chart-btn', { active: chartType === 'pie' }]" @click="chartType = 'pie'">{{ t('reports.pieChart') }}</button>
              </div>
            </div>

            <!-- Bar chart -->
            <div v-if="chartType === 'bar'" class="reports-view__bar-chart" role="img" :aria-label="t('reports.barChart')">
              <div v-for="g in groupEntries" :key="g.label" class="reports-view__bar-row">
                <span class="reports-view__bar-label">{{ g.label }}</span>
                <div class="reports-view__bar-track">
                  <div class="reports-view__bar-fill" :style="{ width: (g.count / maxGroupCount * 100) + '%' }"></div>
                </div>
                <span class="reports-view__bar-count">{{ g.count }}</span>
              </div>
            </div>

            <!-- Pie chart -->
            <div v-if="chartType === 'pie'" class="reports-view__pie-chart" role="img" :aria-label="t('reports.pieChart')">
              <svg viewBox="0 0 100 100" class="reports-view__pie-svg">
                <path v-for="(seg, i) in pieSegments" :key="i" :d="seg.d" :fill="seg.color" />
              </svg>
              <ul class="reports-view__pie-legend">
                <li v-for="(seg, i) in pieSegments" :key="i">
                  <span class="reports-view__legend-swatch" :style="{ background: seg.color }"></span>
                  {{ seg.label }} ({{ seg.count }})
                </li>
              </ul>
            </div>
          </div>

          <!-- Data table -->
          <div v-if="result.rows.length > 0" class="reports-view__table-wrapper">
            <table class="reports-view__table" aria-label="Report results">
              <thead>
                <tr>
                  <th v-for="col in config.columns" :key="col" scope="col">{{ fieldLabel(col) }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(row, ri) in result.rows" :key="ri">
                  <td v-for="col in config.columns" :key="col">{{ row[col] ?? '' }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div v-else class="reports-view__empty">{{ t('reports.noResults') }}</div>

          <!-- Pagination -->
          <div v-if="result.pagination.total_pages > 1" class="reports-view__pagination">
            <button class="reports-view__btn reports-view__btn--sm" :disabled="config.page <= 1" @click="setPage(config.page - 1)">{{ t('reports.prevPage') }}</button>
            <span>{{ t('reports.pagination', { page: result.pagination.page, total: result.pagination.total_pages }) }}</span>
            <button class="reports-view__btn reports-view__btn--sm" :disabled="config.page >= result.pagination.total_pages" @click="setPage(config.page + 1)">{{ t('reports.nextPage') }}</button>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
.reports-view { padding: 1rem; }
.reports-view h1 { margin: 0 0 1rem; font-size: 1.5rem; }
.reports-view h3 { margin: 0 0 0.5rem; font-size: 1rem; }

.reports-view__layout { display: flex; gap: 1.5rem; }
.reports-view__sidebar { width: 240px; flex-shrink: 0; }
.reports-view__main { flex: 1; min-width: 0; }

.reports-view__section { margin-bottom: 1.25rem; }

.reports-view__select {
  padding: 0.35rem 0.5rem; border: 1px solid #ccc; border-radius: 4px;
  font-size: 0.85rem; width: 100%; box-sizing: border-box;
}

.reports-view__input {
  padding: 0.35rem 0.5rem; border: 1px solid #ccc; border-radius: 4px;
  font-size: 0.85rem; flex: 1; min-width: 80px;
}
.reports-view__input--sm { max-width: 80px; }

.reports-view__columns { display: flex; flex-wrap: wrap; gap: 0.4rem 1rem; }
.reports-view__col-label { display: flex; align-items: center; gap: 0.25rem; font-size: 0.85rem; cursor: pointer; }

.reports-view__filter-row { display: flex; gap: 0.4rem; align-items: center; margin-bottom: 0.4rem; flex-wrap: wrap; }
.reports-view__filter-row .reports-view__select { width: auto; min-width: 120px; }

.reports-view__row { display: flex; gap: 1rem; flex-wrap: wrap; align-items: flex-end; }
.reports-view__row > div { display: flex; flex-direction: column; gap: 0.2rem; }
.reports-view__row label { font-size: 0.8rem; font-weight: 600; }

.reports-view__actions { display: flex; gap: 0.5rem; margin-bottom: 1rem; }

.reports-view__btn {
  padding: 0.4rem 1rem; border: 1px solid #4a90d9; background: #4a90d9;
  color: #fff; border-radius: 4px; font-size: 0.85rem; cursor: pointer;
}
.reports-view__btn:hover:not(:disabled) { background: #357abd; }
.reports-view__btn:disabled { opacity: 0.6; cursor: not-allowed; }
.reports-view__btn--secondary { background: #fff; color: #4a90d9; }
.reports-view__btn--secondary:hover:not(:disabled) { background: #f0f6ff; }
.reports-view__btn--sm { padding: 0.25rem 0.6rem; font-size: 0.8rem; }

.reports-view__template-list, .reports-view__saved-list { list-style: none; padding: 0; margin: 0; }
.reports-view__template-list li, .reports-view__saved-item { margin-bottom: 0.3rem; }
.reports-view__template-btn {
  background: none; border: none; color: #4a90d9; cursor: pointer;
  font-size: 0.85rem; text-align: left; padding: 0.2rem 0;
}
.reports-view__template-btn:hover { text-decoration: underline; }

.reports-view__saved-item { display: flex; align-items: center; gap: 0.3rem; }
.reports-view__delete-btn {
  background: none; border: none; color: #d94a4a; cursor: pointer;
  font-size: 1.1rem; line-height: 1; padding: 0 0.2rem;
}

.reports-view__save-form { display: flex; gap: 0.4rem; margin-top: 0.5rem; }
.reports-view__save-form .reports-view__input { flex: 1; }

.reports-view__hint { font-size: 0.8rem; color: #666; }
.reports-view__loading { padding: 1.5rem; text-align: center; color: #666; }
.reports-view__empty { padding: 1.5rem; text-align: center; color: #666; }
.reports-view__error { padding: 0.5rem 0.75rem; background: #f8d7da; color: #721c24; border-radius: 4px; margin-bottom: 0.75rem; font-size: 0.85rem; }
.reports-view__success { padding: 0.5rem 0.75rem; background: #d4edda; color: #155724; border-radius: 4px; margin-bottom: 0.75rem; font-size: 0.85rem; }

.reports-view__summary { margin-bottom: 1.25rem; padding: 0.75rem; background: #f9f9f9; border-radius: 6px; }
.reports-view__summary-grid { display: flex; flex-wrap: wrap; gap: 1.5rem; }
.reports-view__stat { display: flex; flex-direction: column; }
.reports-view__stat-value { font-size: 1.5rem; font-weight: 700; }
.reports-view__stat-label { font-size: 0.8rem; color: #555; font-weight: 600; }
.reports-view__breakdown { list-style: none; padding: 0; margin: 0.2rem 0 0; font-size: 0.85rem; }

.reports-view__groups-section { margin-bottom: 1.25rem; }
.reports-view__groups-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem; }
.reports-view__chart-toggle { display: flex; gap: 0.3rem; }
.reports-view__chart-btn {
  padding: 0.2rem 0.6rem; border: 1px solid #ccc; background: #fff;
  border-radius: 4px; font-size: 0.8rem; cursor: pointer;
}
.reports-view__chart-btn.active { background: #4a90d9; color: #fff; border-color: #4a90d9; }

.reports-view__bar-chart { max-width: 600px; }
.reports-view__bar-row { display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.3rem; }
.reports-view__bar-label { width: 120px; font-size: 0.8rem; text-align: right; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.reports-view__bar-track { flex: 1; height: 20px; background: #eee; border-radius: 3px; overflow: hidden; }
.reports-view__bar-fill { height: 100%; background: #4a90d9; border-radius: 3px; transition: width 0.3s; }
.reports-view__bar-count { width: 40px; font-size: 0.8rem; font-weight: 600; }

.reports-view__pie-chart { display: flex; align-items: flex-start; gap: 1rem; }
.reports-view__pie-svg { width: 160px; height: 160px; }
.reports-view__pie-legend { list-style: none; padding: 0; margin: 0; font-size: 0.8rem; }
.reports-view__pie-legend li { display: flex; align-items: center; gap: 0.3rem; margin-bottom: 0.2rem; }
.reports-view__legend-swatch { width: 12px; height: 12px; border-radius: 2px; display: inline-block; }

.reports-view__table-wrapper { overflow-x: auto; margin-bottom: 1rem; }
.reports-view__table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
.reports-view__table th, .reports-view__table td { padding: 0.5rem 0.6rem; text-align: left; border-bottom: 1px solid #e0e0e0; }
.reports-view__table th { background: #f5f5f5; font-weight: 600; white-space: nowrap; }

.reports-view__pagination { display: flex; align-items: center; gap: 0.75rem; justify-content: center; padding: 0.75rem 0; font-size: 0.85rem; }

@media (max-width: 768px) {
  .reports-view__layout { flex-direction: column; }
  .reports-view__sidebar { width: 100%; }
  .reports-view__row { flex-direction: column; }
  .reports-view__pie-chart { flex-direction: column; }
}
</style>

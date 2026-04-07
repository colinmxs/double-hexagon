<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useApi } from '../composables/useApi'

const { apiFetch } = useApi()

interface GiveawayYear { year: string; is_active: boolean }
interface Summary {
  total_applications: number
  total_children: number
  applications_by_status: Record<string, number>
  applications_by_source_type: Record<string, number>
}
interface CostData {
  total_cost: number
  cost_per_application: number
  service_breakdown: Record<string, number>
}

const years = ref<GiveawayYear[]>([])
const selectedYear = ref('')
const summary = ref<Summary | null>(null)
const costData = ref<CostData | null>(null)
const isLoading = ref(false)
const error = ref('')
const exportLoading = ref('')
const exportSuccess = ref('')
const exportOpen = ref(false)
const newYear = ref('')
const addingYear = ref(false)
const showAddYear = ref(false)

const serviceColors: Record<string, string> = {
  S3: '#4a90d9', CloudFront: '#50c878', Lambda: '#f5a623',
  'API Gateway': '#d94a4a', DynamoDB: '#9b59b6',
  Textract: '#1abc9c', Bedrock: '#e67e22',
}

const statusColors: Record<string, string> = {
  needs_review: '#f5a623',
  manually_approved: '#4a90d9',
  rejected: '#d94a4a',
  extraction_failed: '#999',
}

// Rotating service cost ticker
const svcTickerIdx = ref(0)
let svcTickerTimer: ReturnType<typeof setInterval> | null = null

const serviceEntries = computed(() => {
  if (!costData.value?.service_breakdown) return []
  return Object.entries(costData.value.service_breakdown).map(([name, amount]) => ({
    name,
    amount: (amount as number),
    color: serviceColors[name] || '#999',
  }))
})

const currentService = computed(() => {
  if (serviceEntries.value.length === 0) return null
  return serviceEntries.value[svcTickerIdx.value % serviceEntries.value.length]
})

function startSvcTicker() {
  stopSvcTicker()
  if (serviceEntries.value.length > 1) {
    svcTickerTimer = setInterval(() => {
      svcTickerIdx.value = (svcTickerIdx.value + 1) % serviceEntries.value.length
    }, 3000)
  }
}

function stopSvcTicker() {
  if (svcTickerTimer) { clearInterval(svcTickerTimer); svcTickerTimer = null }
}

watch(serviceEntries, (entries) => {
  svcTickerIdx.value = 0
  if (entries.length > 1) startSvcTicker()
  else stopSvcTicker()
})

onUnmounted(stopSvcTicker)

function statusLabel(s: string): string {
  return { needs_review: 'Needs Review',
    manually_approved: 'Manually Approved', rejected: 'Rejected',
    extraction_failed: 'Extraction Failed' }[s] || s
}

async function fetchYears() {
  try {
    const res = await apiFetch('/giveaway-years')
    if (!res.ok) return
    years.value = await res.json()
    const active = years.value.find(y => y.is_active)
    selectedYear.value = active?.year || years.value[0]?.year || ''
  } catch { /* */ }
}

async function fetchData() {
  if (!selectedYear.value) return
  isLoading.value = true
  error.value = ''
  summary.value = null
  costData.value = null
  try {
    const [summaryRes, costRes] = await Promise.all([
      apiFetch('/reports/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ giveaway_year: selectedYear.value, columns: ['status'], page_size: 1 }),
      }),
      apiFetch('/cost-dashboard'),
    ])
    if (summaryRes.ok) { const d = await summaryRes.json(); summary.value = d.summary ?? null }
    if (costRes.ok) costData.value = await costRes.json()
  } catch {
    error.value = 'Failed to load data'
  } finally {
    isLoading.value = false
  }
}

function downloadCsv(csv: string, filename: string) {
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = filename; a.style.display = 'none'
  document.body.appendChild(a); a.click(); document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

async function exportCsv(type: 'bike_build_list' | 'family_contact_list' | 'full_report') {
  if (!selectedYear.value) return
  exportLoading.value = type
  exportSuccess.value = ''
  error.value = ''
  try {
    let res
    if (type === 'full_report') {
      res = await apiFetch('/reports/export', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          giveaway_year: selectedYear.value,
          columns: [
            'status', 'source_type', 'referring_agency.agency_name',
            'parent_guardian.first_name', 'parent_guardian.last_name',
            'parent_guardian.phone', 'parent_guardian.city',
            'parent_guardian.primary_language', 'parent_guardian.transportation_access',
            'children[0].first_name', 'children[0].last_name',
            'children[0].age', 'children[0].height_inches', 'children[0].gender',
            'children[0].bike_color_1', 'children[0].bike_color_2',
            'overall_confidence_score',
          ],
          sort_by: 'parent_guardian.last_name', sort_order: 'asc',
        }),
      })
    } else {
      const ep = type === 'bike_build_list' ? 'exports/bike-build-list' : 'exports/family-contact-list'
      res = await apiFetch(`/${ep}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ giveaway_year: selectedYear.value, export_type: type }),
      })
    }
    if (!res.ok) throw new Error()
    if (type === 'full_report') {
      downloadCsv(await res.text(), `full-report-${selectedYear.value}.csv`)
    } else {
      const data = await res.json()
      const label = type === 'bike_build_list' ? 'bike-build' : 'family-contacts'
      downloadCsv(data.csv_content, `${label}-${selectedYear.value}.csv`)
    }
    exportSuccess.value = { bike_build_list: 'Bike Build List', family_contact_list: 'Family Contact List', full_report: 'Full Report' }[type] + ' exported'
  } catch { error.value = 'Export failed' } finally { exportLoading.value = '' }
}

watch(selectedYear, fetchData)
onMounted(async () => { await fetchYears(); fetchData() })

async function addYear() {
  if (!newYear.value.trim()) return
  addingYear.value = true
  try {
    const res = await apiFetch('/giveaway-years/active', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ year: newYear.value.trim() }),
    })
    if (!res.ok) throw new Error()
    newYear.value = ''
    showAddYear.value = false
    await fetchYears()
    fetchData()
  } catch { /* */ }
  finally { addingYear.value = false }
}

function cancelAddYear() {
  showAddYear.value = false
  newYear.value = ''
}

function doExport(type: 'bike_build_list' | 'family_contact_list' | 'full_report') {
  exportOpen.value = false
  exportCsv(type)
}
</script>

<template>
  <div class="rpt" @click="exportOpen = false">
    <!-- Year banner -->
    <div class="rpt__top">
      <div class="rpt__banner">{{ selectedYear }} Giveaway Year</div>
      <div class="rpt__year-picker">
        <select v-model="selectedYear" class="rpt__year-select">
          <option v-for="y in years" :key="y.year" :value="y.year">
            {{ y.year }}{{ y.is_active ? ' ★' : '' }}
          </option>
        </select>
        <button
          v-if="!showAddYear"
          class="rpt__add-year-trigger"
          type="button"
          title="Add Year"
          @click="showAddYear = true"
        >+</button>
        <div v-if="showAddYear" class="rpt__add-year-inline">
          <input
            v-model="newYear"
            type="text"
            placeholder="e.g. 2027"
            class="rpt__add-year-input"
            @keydown.enter="addYear"
            @keydown.escape="cancelAddYear"
          />
          <button
            class="rpt__add-year-btn"
            type="button"
            :disabled="addingYear || !newYear.trim()"
            @click="addYear"
          >Save</button>
          <button
            class="rpt__add-year-cancel"
            type="button"
            @click="cancelAddYear"
          >Cancel</button>
        </div>
      </div>
      <!-- Rotating service ticker in the banner row -->
      <span v-if="currentService" class="rpt__svc-ticker" :style="{ borderColor: currentService.color }">
        <span class="rpt__svc-ticker-dot" :style="{ background: currentService.color }"></span>
        {{ currentService.name }} ${{ currentService.amount.toFixed(2) }}
      </span>
    </div>

    <div v-if="error" class="rpt__msg rpt__msg--error" role="alert">{{ error }}</div>
    <div v-if="exportSuccess" class="rpt__msg rpt__msg--success" role="status">✓ {{ exportSuccess }}</div>
    <div v-if="isLoading" class="rpt__loading">Loading...</div>

    <template v-if="!isLoading && summary">
      <!-- Overview stats -->
      <div class="rpt__stats">
        <div class="rpt__stat rpt__stat--hero">
          <span class="rpt__stat-val">{{ summary.total_applications }}</span>
          <span class="rpt__stat-lbl">Applications</span>
        </div>
        <div v-if="costData" class="rpt__stat">
          <span class="rpt__stat-val">${{ costData.total_cost.toFixed(2) }}</span>
          <span class="rpt__stat-lbl">Total AWS Cost</span>
        </div>
        <div v-if="costData" class="rpt__stat">
          <span class="rpt__stat-val">${{ costData.cost_per_application.toFixed(2) }}</span>
          <span class="rpt__stat-lbl">Cost / Application</span>
        </div>
        <div class="rpt__stat">
          <span class="rpt__stat-val">
            {{ summary.applications_by_source_type['digital'] || 0 }} / {{ summary.applications_by_source_type['upload'] || 0 }}
          </span>
          <span class="rpt__stat-lbl">Digital / Upload</span>
        </div>
      </div>

      <!-- Status + Service breakdown side by side -->
      <div class="rpt__grid">
        <div class="rpt__card">
          <h3>Application Status</h3>
          <div v-for="(count, status) in summary.applications_by_status" :key="status" class="rpt__bar-row">
            <span class="rpt__bar-dot" :style="{ background: statusColors[status as string] || '#999' }"></span>
            <span class="rpt__bar-label">{{ statusLabel(status as string) }}</span>
            <div class="rpt__bar-track">
              <div class="rpt__bar-fill" :style="{
                width: (count as number) / summary.total_applications * 100 + '%',
                background: statusColors[status as string] || '#999',
              }"></div>
            </div>
            <span class="rpt__bar-count">{{ count }}</span>
          </div>
        </div>

        <div v-if="costData" class="rpt__card rpt__card--services">
          <h3>AWS Service Breakdown</h3>
          <div class="rpt__svc-list">
            <div v-for="svc in serviceEntries" :key="svc.name" class="rpt__svc-row">
              <span class="rpt__svc-dot" :style="{ background: svc.color }"></span>
              <span class="rpt__svc-name">{{ svc.name }}</span>
              <div class="rpt__svc-bar-track">
                <div class="rpt__svc-bar-fill" :style="{ width: (svc.amount / costData!.total_cost * 100) + '%', background: svc.color }"></div>
              </div>
              <span class="rpt__svc-amount">${{ svc.amount.toFixed(2) }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Export dropdown -->
      <div class="export-drop" @click.stop>
        <div v-if="exportSuccess" class="export-drop__msg">✓ {{ exportSuccess }}</div>
        <button class="export-drop__trigger" @click="exportOpen = !exportOpen">
          Export {{ selectedYear }} ▾
        </button>
        <div v-if="exportOpen" class="export-drop__menu">
          <button class="export-drop__item" :disabled="!!exportLoading" @click="doExport('bike_build_list')">
            🚲 Bike Build List
            <span v-if="exportLoading === 'bike_build_list'" class="export-drop__spinner">...</span>
          </button>
          <button class="export-drop__item" :disabled="!!exportLoading" @click="doExport('family_contact_list')">
            📋 Family Contacts
            <span v-if="exportLoading === 'family_contact_list'" class="export-drop__spinner">...</span>
          </button>
          <button class="export-drop__item" :disabled="!!exportLoading" @click="doExport('full_report')">
            📊 Full Report
            <span v-if="exportLoading === 'full_report'" class="export-drop__spinner">...</span>
          </button>
        </div>
      </div>

    </template>
  </div>
</template>

<style scoped>
.rpt { padding: 1rem; display: flex; flex-direction: column; gap: 1rem; }
.rpt h3 { margin: 0 0 0.6rem; font-size: 1rem; color: #333; }

.rpt__top { display: flex; align-items: center; gap: 1rem; flex-wrap: wrap; }
.rpt__banner { background: #2c3e50; color: #fff; padding: 0.6rem 1.2rem; border-radius: 6px; font-size: 1.2rem; font-weight: 700; }
.rpt__year-picker { display: flex; align-items: center; gap: 0.4rem; flex-wrap: wrap; }
.rpt__year-select { padding: 0.4rem 0.6rem; border: 1px solid #ccc; border-radius: 4px; font-size: 0.9rem; }

.rpt__add-year-trigger {
  width: 28px; height: 28px; border: 1px solid #ccc; border-radius: 4px;
  background: #faf7f2; color: #4a90d9; font-size: 1.1rem; font-weight: 700;
  cursor: pointer; display: flex; align-items: center; justify-content: center;
  line-height: 1; transition: background 0.15s, color 0.15s;
}
.rpt__add-year-trigger:hover { background: #4a90d9; color: #fff; }
.rpt__add-year-inline { display: flex; align-items: center; gap: 0.3rem; }
.rpt__add-year-input { width: 80px; padding: 0.3rem 0.4rem; border: 1px solid #4a90d9; border-radius: 3px; font-size: 0.85rem; }
.rpt__add-year-btn { padding: 0.3rem 0.6rem; border: none; background: #4a90d9; color: #fff; border-radius: 3px; font-size: 0.8rem; cursor: pointer; }
.rpt__add-year-btn:hover:not(:disabled) { background: #357abd; }
.rpt__add-year-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.rpt__add-year-cancel { padding: 0.3rem 0.6rem; border: 1px solid #ccc; background: #faf7f2; color: #666; border-radius: 3px; font-size: 0.8rem; cursor: pointer; }
.rpt__add-year-cancel:hover { background: #f0ebe3; }

/* Rotating service ticker */
.rpt__svc-ticker {
  display: inline-flex; align-items: center; gap: 0.3rem; margin-left: auto;
  font-size: 0.78rem; font-weight: 600; padding: 0.2rem 0.6rem;
  border-radius: 12px; background: #faf7f2; border: 1.5px solid #ccc; color: #333;
  animation: rpt-svc-fade 0.5s ease; white-space: nowrap;
}
.rpt__svc-ticker-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; animation: rpt-svc-pulse 2s ease-in-out infinite; }
@keyframes rpt-svc-fade { from { opacity: 0; transform: translateY(-4px); } to { opacity: 1; transform: translateY(0); } }
@keyframes rpt-svc-pulse { 0%, 100% { transform: scale(1); } 50% { transform: scale(1.4); } }

.rpt__msg { padding: 0.5rem 0.75rem; border-radius: 4px; font-size: 0.85rem; }
.rpt__msg--error { background: #f8d7da; color: #721c24; }
.rpt__msg--success { background: #d4edda; color: #155724; }
.rpt__loading { padding: 1.5rem; text-align: center; color: #666; }

/* Stats row */
.rpt__stats { display: flex; flex-wrap: wrap; gap: 2rem; padding: 1.25rem; background: #f5f0e8; border-radius: 8px; }
.rpt__stat { display: flex; flex-direction: column; }
.rpt__stat--hero .rpt__stat-val { font-size: 2.2rem; color: #2c3e50; }
.rpt__stat-val { font-size: 1.4rem; font-weight: 700; }
.rpt__stat-lbl { font-size: 0.78rem; color: #666; font-weight: 600; text-transform: uppercase; letter-spacing: 0.03em; }

/* Cards */
.rpt__card { border: 1px solid #e6ddd0; border-radius: 8px; padding: 1rem; background: #faf7f2; }
.rpt__card--services { background: #f5f0e8; }
.rpt__grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }

/* Status bars */
.rpt__bar-row { display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.4rem; font-size: 0.85rem; }
.rpt__bar-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.rpt__bar-label { min-width: 130px; color: #333; }
.rpt__bar-track { flex: 1; height: 20px; background: #f0ebe3; border-radius: 4px; overflow: hidden; }
.rpt__bar-fill { height: 100%; border-radius: 4px; min-width: 3px; transition: width 0.3s; }
.rpt__bar-count { min-width: 35px; text-align: right; font-weight: 700; color: #333; }

/* Service costs with proportional bars */
.rpt__svc-list { display: flex; flex-direction: column; gap: 0.3rem; }
.rpt__svc-row { display: flex; align-items: center; gap: 0.5rem; font-size: 0.85rem; }
.rpt__svc-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
.rpt__svc-name { min-width: 100px; color: #333; }
.rpt__svc-bar-track { flex: 1; height: 12px; background: #ede6db; border-radius: 6px; overflow: hidden; }
.rpt__svc-bar-fill { height: 100%; border-radius: 6px; transition: width 0.4s ease; }
.rpt__svc-amount { min-width: 70px; text-align: right; font-weight: 700; }

/* Export dropdown */
.export-drop { position: relative; display: inline-block; }
.export-drop__msg { padding: 0.35rem 0.7rem; background: #d4edda; color: #155724; border-radius: 6px; font-size: 0.8rem; margin-bottom: 0.5rem; display: inline-block; }
.export-drop__trigger {
  padding: 0.45rem 1rem; background: #faf7f2; border: 1.5px solid #4a90d9; color: #4a90d9;
  border-radius: 7px; font-size: 0.85rem; font-weight: 700; cursor: pointer; transition: all 0.15s;
}
.export-drop__trigger:hover { background: #4a90d9; color: #fff; }
.export-drop__menu {
  position: absolute; top: 100%; left: 0; margin-top: 4px; z-index: 50;
  background: #faf7f2; border: 1px solid #e6ddd0; border-radius: 8px;
  box-shadow: 0 4px 16px rgba(0,0,0,0.1); min-width: 200px; overflow: hidden;
}
.export-drop__item {
  display: flex; align-items: center; justify-content: space-between; gap: 0.5rem;
  width: 100%; padding: 0.6rem 0.85rem; border: none; background: none;
  font-size: 0.85rem; color: #333; cursor: pointer; text-align: left; font-family: inherit;
  transition: background 0.1s;
}
.export-drop__item:hover:not(:disabled) { background: #f0ebe3; }
.export-drop__item:disabled { opacity: 0.5; cursor: not-allowed; }
.export-drop__item + .export-drop__item { border-top: 1px solid #ede6db; }
.export-drop__spinner { color: #999; font-size: 0.8rem; }

@media (max-width: 768px) {
  .rpt__top { flex-direction: column; align-items: flex-start; }
  .rpt__stats { flex-direction: column; gap: 1rem; }
  .rpt__grid { grid-template-columns: 1fr; }
  .rpt__svc-ticker { margin-left: 0; }
}
</style>

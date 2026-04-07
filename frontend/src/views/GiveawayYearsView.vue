<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useApi } from '../composables/useApi'

const { t } = useI18n()
const { apiFetch } = useApi()

interface GiveawayYear {
  year: string
  is_active: boolean
  status: string
}

const years = ref<GiveawayYear[]>([])
const isLoading = ref(false)
const error = ref('')
const actionLoading = ref('')
const newYear = ref('')

// Confirmation modal state
const confirmAction = ref<'archive' | 'delete' | null>(null)
const confirmYear = ref('')
const confirmInput = ref('')

async function fetchYears() {
  isLoading.value = true
  error.value = ''
  try {
    const res = await apiFetch('/giveaway-years')
    if (!res.ok) throw new Error()
    years.value = await res.json()
  } catch {
    error.value = 'years.errorLoading'
  } finally {
    isLoading.value = false
  }
}

async function setActive(year: string) {
  actionLoading.value = 'active-' + year
  error.value = ''
  try {
    const res = await apiFetch('/giveaway-years/active', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ year }),
    })
    if (!res.ok) throw new Error()
    await fetchYears()
  } catch {
    error.value = 'years.actionError'
  } finally {
    actionLoading.value = ''
  }
}

async function createYear() {
  if (!newYear.value.trim()) return
  actionLoading.value = 'create'
  error.value = ''
  try {
    const res = await apiFetch('/giveaway-years/active', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ year: newYear.value.trim() }),
    })
    if (!res.ok) throw new Error()
    newYear.value = ''
    await fetchYears()
  } catch {
    error.value = 'years.actionError'
  } finally {
    actionLoading.value = ''
  }
}

function openConfirm(action: 'archive' | 'delete', year: string) {
  confirmAction.value = action
  confirmYear.value = year
  confirmInput.value = ''
}

function closeConfirm() {
  confirmAction.value = null
  confirmYear.value = ''
  confirmInput.value = ''
}

async function executeConfirmedAction() {
  if (confirmInput.value !== confirmYear.value) return
  const action = confirmAction.value
  const year = confirmYear.value
  closeConfirm()

  if (action === 'archive') {
    await archiveYear(year)
  } else if (action === 'delete') {
    await deleteYear(year)
  }
}

async function archiveYear(year: string) {
  actionLoading.value = 'archive-' + year
  error.value = ''
  try {
    const res = await apiFetch(`/giveaway-years/${year}/archive`, { method: 'POST' })
    if (!res.ok) throw new Error()
    await fetchYears()
  } catch {
    error.value = 'years.actionError'
  } finally {
    actionLoading.value = ''
  }
}

async function unarchiveYear(year: string) {
  actionLoading.value = 'unarchive-' + year
  error.value = ''
  try {
    const res = await apiFetch(`/giveaway-years/${year}/unarchive`, { method: 'POST' })
    if (!res.ok) throw new Error()
    await fetchYears()
  } catch {
    error.value = 'years.actionError'
  } finally {
    actionLoading.value = ''
  }
}

async function deleteYear(year: string) {
  actionLoading.value = 'delete-' + year
  error.value = ''
  try {
    const res = await apiFetch(`/giveaway-years/${year}/delete`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ confirm: true }),
    })
    if (!res.ok) throw new Error()
    await fetchYears()
  } catch {
    error.value = 'years.actionError'
  } finally {
    actionLoading.value = ''
  }
}

// --- Reports & data for selected year ---
interface Summary {
  total_applications: number
  applications_by_status: Record<string, number>
  applications_by_source_type: Record<string, number>
}
interface CostData {
  total_cost: number
  cost_per_application: number
  service_breakdown: Record<string, number>
}

const selectedYear = ref('')
const summary = ref<Summary | null>(null)
const costData = ref<CostData | null>(null)
const rptLoading = ref(false)
const exportLoading = ref('')
const exportSuccess = ref('')

const serviceColors: Record<string, string> = {
  S3: '#4a90d9', CloudFront: '#50c878', Lambda: '#f5a623',
  'API Gateway': '#d94a4a', DynamoDB: '#9b59b6', Textract: '#1abc9c', Bedrock: '#e67e22',
}
const statusColors: Record<string, string> = {
  needs_review: '#f5a623',
  manually_approved: '#4a90d9', rejected: '#d94a4a', extraction_failed: '#999',
}
function statusLabel(s: string): string {
  return { needs_review: 'Needs Review',
    manually_approved: 'Manually Approved', rejected: 'Rejected',
    extraction_failed: 'Extraction Failed' }[s] || s
}

function selectYear(year: string) {
  selectedYear.value = year
}

async function fetchReportData() {
  if (!selectedYear.value) return
  rptLoading.value = true; summary.value = null; costData.value = null
  try {
    const [sRes, cRes] = await Promise.all([
      apiFetch('/reports/run', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ giveaway_year: selectedYear.value, columns: ['status'], page_size: 1 }),
      }),
      apiFetch('/cost-dashboard'),
    ])
    if (sRes.ok) { const d = await sRes.json(); summary.value = d.summary ?? null }
    if (cRes.ok) costData.value = await cRes.json()
  } catch { /* non-fatal */ } finally { rptLoading.value = false }
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
  exportLoading.value = type; exportSuccess.value = ''
  try {
    let res
    if (type === 'full_report') {
      res = await apiFetch('/reports/export', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          giveaway_year: selectedYear.value,
          columns: ['status','source_type','referring_agency.agency_name','parent_guardian.first_name','parent_guardian.last_name','parent_guardian.phone','parent_guardian.city','parent_guardian.primary_language','parent_guardian.transportation_access','children[0].first_name','children[0].last_name','children[0].age','children[0].height_inches','children[0].gender','children[0].bike_color_1','children[0].bike_color_2','overall_confidence_score'],
          sort_by: 'parent_guardian.last_name', sort_order: 'asc',
        }),
      })
    } else {
      const ep = type === 'bike_build_list' ? 'exports/bike-build-list' : 'exports/family-contact-list'
      res = await apiFetch(`/${ep}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ giveaway_year: selectedYear.value, export_type: type }),
      })
    }
    if (!res.ok) throw new Error()
    if (type === 'full_report') downloadCsv(await res.text(), `full-report-${selectedYear.value}.csv`)
    else { const d = await res.json(); downloadCsv(d.csv_content, `${type === 'bike_build_list' ? 'bike-build' : 'family-contacts'}-${selectedYear.value}.csv`) }
    exportSuccess.value = { bike_build_list: 'Bike Build List', family_contact_list: 'Family Contact List', full_report: 'Full Report' }[type] + ' exported'
  } catch { error.value = 'Export failed' } finally { exportLoading.value = '' }
}

watch(selectedYear, fetchReportData)

onMounted(async () => {
  await fetchYears()
  const active = years.value.find(y => y.is_active)
  if (active) { selectedYear.value = active.year }
  else if (years.value.length) { selectedYear.value = years.value[0].year }
})
</script>

<template>
  <div class="years-view">
    <h1>{{ t('nav.years') }}</h1>

    <div v-if="error" class="years-view__error" role="alert">{{ t(error) }}</div>

    <div class="years-view__create">
      <input v-model="newYear" type="text" :placeholder="t('years.newYearPlaceholder')" class="years-view__input" />
      <button class="years-view__btn" :disabled="!!actionLoading || !newYear.trim()" @click="createYear">
        {{ t('years.createYear') }}
      </button>
    </div>

    <div v-if="isLoading" class="years-view__loading" role="status">{{ t('common.loading') }}</div>

    <table v-else-if="years.length" class="years-view__table" aria-label="Giveaway Years">
      <thead>
        <tr>
          <th scope="col">{{ t('years.year') }}</th>
          <th scope="col">{{ t('users.status') }}</th>
          <th scope="col">{{ t('users.actionsCol') }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="y in years" :key="y.year" :class="{ 'years-view__row--selected': y.year === selectedYear }" @click="selectYear(y.year)">
          <td>
            {{ y.year }}
            <span v-if="y.is_active" class="years-view__active-badge">★ {{ t('years.active') }}</span>
          </td>
          <td>
            <span :class="['years-view__status', `years-view__status--${y.status || 'active'}`]">
              {{ y.status || 'active' }}
            </span>
          </td>
          <td class="years-view__actions">
            <button v-if="!y.is_active && y.status !== 'archived'" class="years-view__link" :disabled="!!actionLoading" @click="setActive(y.year)">
              {{ t('years.setActive') }}
            </button>
            <button v-if="y.status === 'archived'" class="years-view__link" :disabled="!!actionLoading" @click="unarchiveYear(y.year)">
              Unarchive
            </button>
            <button v-if="y.status !== 'archived' && !y.is_active" class="years-view__link years-view__link--warn" :disabled="!!actionLoading" @click="openConfirm('archive', y.year)">
              {{ t('years.archive') }}
            </button>
            <button class="years-view__link years-view__link--danger" :disabled="!!actionLoading" @click="openConfirm('delete', y.year)">
              {{ t('common.delete') }}
            </button>
          </td>
        </tr>
      </tbody>
    </table>
    <div v-else class="years-view__empty">{{ t('years.noYears') }}</div>

    <!-- Reports & data for selected year -->
    <div v-if="selectedYear" class="rpt">
      <div v-if="exportSuccess" class="rpt__msg rpt__msg--ok">✓ {{ exportSuccess }}</div>

      <div class="rpt__banner">{{ selectedYear }} Data</div>

      <div v-if="rptLoading" class="rpt__loading">Loading...</div>
      <template v-else-if="summary">
        <div class="rpt__stats">
          <div class="rpt__stat rpt__stat--hero">
            <span class="rpt__stat-val">{{ summary.total_applications }}</span>
            <span class="rpt__stat-lbl">Applications</span>
          </div>
          <div v-if="costData" class="rpt__stat">
            <span class="rpt__stat-val">${{ costData.total_cost.toFixed(2) }}</span>
            <span class="rpt__stat-lbl">AWS Cost</span>
          </div>
          <div v-if="costData" class="rpt__stat">
            <span class="rpt__stat-val">${{ costData.cost_per_application.toFixed(2) }}</span>
            <span class="rpt__stat-lbl">Cost / App</span>
          </div>
          <div class="rpt__stat">
            <span class="rpt__stat-val">{{ summary.applications_by_source_type['digital'] || 0 }} / {{ summary.applications_by_source_type['upload'] || 0 }}</span>
            <span class="rpt__stat-lbl">Digital / Upload</span>
          </div>
        </div>

        <div class="rpt__grid">
          <div class="rpt__card">
            <h3>Status</h3>
            <div v-for="(count, status) in summary.applications_by_status" :key="status" class="rpt__bar-row">
              <span class="rpt__bar-dot" :style="{ background: statusColors[status as string] || '#999' }"></span>
              <span class="rpt__bar-label">{{ statusLabel(status as string) }}</span>
              <div class="rpt__bar-track">
                <div class="rpt__bar-fill" :style="{ width: (count as number) / summary.total_applications * 100 + '%', background: statusColors[status as string] || '#999' }"></div>
              </div>
              <span class="rpt__bar-count">{{ count }}</span>
            </div>
          </div>

          <div v-if="costData" class="rpt__card">
            <h3>AWS Services</h3>
            <div v-for="(amount, svc) in costData.service_breakdown" :key="svc" class="rpt__svc-row">
              <span class="rpt__svc-dot" :style="{ background: serviceColors[svc as string] || '#999' }"></span>
              <span class="rpt__svc-name">{{ svc }}</span>
              <span class="rpt__svc-amount">${{ (amount as number).toFixed(2) }}</span>
            </div>
          </div>

          <div class="rpt__card rpt__card--wide">
            <h3>Export</h3>
            <div class="rpt__exports">
              <div class="rpt__export">
                <div><strong>🚲 Bike Build List</strong><p>One row per child — for the build team.</p></div>
                <button class="rpt__btn" :disabled="!!exportLoading" @click="exportCsv('bike_build_list')">{{ exportLoading === 'bike_build_list' ? '...' : 'CSV' }}</button>
              </div>
              <div class="rpt__export">
                <div><strong>📋 Family Contacts</strong><p>One row per family — for pickup coordination.</p></div>
                <button class="rpt__btn" :disabled="!!exportLoading" @click="exportCsv('family_contact_list')">{{ exportLoading === 'family_contact_list' ? '...' : 'CSV' }}</button>
              </div>
              <div class="rpt__export">
                <div><strong>📊 Full Report</strong><p>Every field, every record.</p></div>
                <button class="rpt__btn" :disabled="!!exportLoading" @click="exportCsv('full_report')">{{ exportLoading === 'full_report' ? '...' : 'CSV' }}</button>
              </div>
            </div>
          </div>
        </div>
      </template>
    </div>

    <!-- Confirmation modal -->
    <div v-if="confirmAction" class="years-view__overlay" @click.self="closeConfirm">
      <div class="years-view__modal" role="dialog" :aria-label="`Confirm ${confirmAction}`">
        <h3 v-if="confirmAction === 'archive'">Archive {{ confirmYear }}?</h3>
        <h3 v-else>Permanently delete {{ confirmYear }}?</h3>

        <p v-if="confirmAction === 'archive'">
          This will mark all applications as read-only. You can unarchive later.
        </p>
        <p v-else>
          This will permanently delete all applications and uploaded documents for this year. This cannot be undone.
        </p>

        <label class="years-view__modal-label" :for="'confirm-input'">
          Type <strong>{{ confirmYear }}</strong> to confirm:
        </label>
        <input
          id="confirm-input"
          v-model="confirmInput"
          type="text"
          class="years-view__modal-input"
          autocomplete="off"
          @keydown.enter="executeConfirmedAction"
        />

        <div class="years-view__modal-actions">
          <button class="years-view__btn years-view__btn--secondary" @click="closeConfirm">Cancel</button>
          <button
            :class="['years-view__btn', confirmAction === 'delete' ? 'years-view__btn--danger' : 'years-view__btn--warn']"
            :disabled="confirmInput !== confirmYear"
            @click="executeConfirmedAction"
          >
            {{ confirmAction === 'delete' ? 'Delete permanently' : 'Archive' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.years-view { padding: 1rem; }
.years-view h1 { margin: 0 0 1rem; font-size: 1.5rem; }

.years-view__create { display: flex; gap: 0.5rem; margin-bottom: 1rem; }
.years-view__input { padding: 0.35rem 0.5rem; border: 1px solid #ccc; border-radius: 4px; font-size: 0.85rem; width: 120px; }
.years-view__btn { padding: 0.4rem 1rem; border: none; background: #4a90d9; color: #fff; border-radius: 4px; font-size: 0.85rem; cursor: pointer; }
.years-view__btn:hover:not(:disabled) { background: #357abd; }
.years-view__btn:disabled { opacity: 0.5; cursor: not-allowed; }
.years-view__btn--secondary { background: #e6ddd0; color: #333; }
.years-view__btn--secondary:hover:not(:disabled) { background: #d0d0d0; }
.years-view__btn--warn { background: #e67e22; }
.years-view__btn--warn:hover:not(:disabled) { background: #d35400; }
.years-view__btn--danger { background: #d94a4a; }
.years-view__btn--danger:hover:not(:disabled) { background: #c0392b; }

.years-view__table { width: 100%; border-collapse: collapse; font-size: 0.85rem; max-width: 600px; }
.years-view__table th, .years-view__table td { padding: 0.5rem 0.6rem; text-align: left; border-bottom: 1px solid #e6ddd0; }
.years-view__table th { background: #f0ebe3; font-weight: 600; }

.years-view__active-badge { background: #d4edda; color: #155724; padding: 0.1rem 0.4rem; border-radius: 10px; font-size: 0.75rem; font-weight: 600; margin-left: 0.4rem; }

.years-view__status { padding: 0.1rem 0.5rem; border-radius: 10px; font-size: 0.75rem; font-weight: 600; }
.years-view__status--active { background: #d4edda; color: #155724; }
.years-view__status--archived { background: #e6ddd0; color: #555; }

.years-view__actions { display: flex; gap: 0.5rem; flex-wrap: wrap; }
.years-view__link { background: none; border: none; color: #4a90d9; cursor: pointer; font-size: 0.8rem; padding: 0.15rem 0; }
.years-view__link:hover { text-decoration: underline; }
.years-view__link--warn { color: #e67e22; }
.years-view__link--danger { color: #d94a4a; }
.years-view__link:disabled { opacity: 0.5; cursor: not-allowed; }

.years-view__loading { padding: 1.5rem; text-align: center; color: #666; }
.years-view__empty { padding: 1.5rem; text-align: center; color: #666; }
.years-view__error { padding: 0.5rem 0.75rem; background: #f8d7da; color: #721c24; border-radius: 4px; margin-bottom: 0.75rem; font-size: 0.85rem; }

/* Confirmation modal */
.years-view__overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; z-index: 100; }
.years-view__modal { background: #faf7f2; border-radius: 8px; padding: 1.5rem; max-width: 420px; width: 90%; box-shadow: 0 4px 20px rgba(0,0,0,0.15); }
.years-view__modal h3 { margin: 0 0 0.5rem; font-size: 1.1rem; }
.years-view__modal p { margin: 0 0 1rem; font-size: 0.85rem; color: #555; line-height: 1.4; }
.years-view__modal-label { display: block; font-size: 0.85rem; margin-bottom: 0.3rem; }
.years-view__modal-input { width: 100%; padding: 0.4rem 0.5rem; border: 1px solid #ccc; border-radius: 4px; font-size: 0.9rem; box-sizing: border-box; margin-bottom: 1rem; }
.years-view__modal-actions { display: flex; gap: 0.5rem; justify-content: flex-end; }

/* Selected row */
.years-view__row--selected { background: #eef4fb; }
.years-view__table tbody tr { cursor: pointer; }
.years-view__table tbody tr:hover { background: #f0ebe3; }
.years-view__row--selected:hover { background: #eef4fb; }

/* Reports section */
.rpt { margin-top: 1.5rem; padding-top: 1.5rem; border-top: 1px solid #e6ddd0; }
.rpt h3 { margin: 0 0 0.5rem; font-size: 1rem; color: #333; }
.rpt__banner { background: #2c3e50; color: #fff; padding: 0.5rem 1rem; border-radius: 6px; font-size: 1.1rem; font-weight: 700; margin-bottom: 1rem; display: inline-block; }
.rpt__loading { padding: 1rem; text-align: center; color: #666; }
.rpt__msg { padding: 0.5rem 0.75rem; border-radius: 4px; margin-bottom: 0.75rem; font-size: 0.85rem; }
.rpt__msg--ok { background: #d4edda; color: #155724; }

.rpt__stats { display: flex; flex-wrap: wrap; gap: 2rem; margin-bottom: 1.25rem; padding: 1rem; background: #f5f0e8; border-radius: 8px; }
.rpt__stat { display: flex; flex-direction: column; }
.rpt__stat--hero .rpt__stat-val { font-size: 2rem; color: #2c3e50; }
.rpt__stat-val { font-size: 1.3rem; font-weight: 700; }
.rpt__stat-lbl { font-size: 0.75rem; color: #666; font-weight: 600; text-transform: uppercase; letter-spacing: 0.03em; }

.rpt__grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
.rpt__card { border: 1px solid #e6ddd0; border-radius: 8px; padding: 1rem; background: #faf7f2; }
.rpt__card--wide { grid-column: 1 / -1; }

.rpt__bar-row { display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.35rem; font-size: 0.85rem; }
.rpt__bar-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.rpt__bar-label { min-width: 120px; color: #333; }
.rpt__bar-track { flex: 1; height: 18px; background: #f0ebe3; border-radius: 4px; overflow: hidden; }
.rpt__bar-fill { height: 100%; border-radius: 4px; min-width: 3px; transition: width 0.3s; }
.rpt__bar-count { min-width: 30px; text-align: right; font-weight: 700; }

.rpt__svc-row { display: flex; align-items: center; gap: 0.5rem; padding: 0.3rem 0; font-size: 0.85rem; border-bottom: 1px solid #ede6db; }
.rpt__svc-row:last-child { border-bottom: none; }
.rpt__svc-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
.rpt__svc-name { flex: 1; }
.rpt__svc-amount { font-weight: 700; }

.rpt__exports { display: flex; flex-direction: column; }
.rpt__export { display: flex; justify-content: space-between; align-items: center; padding: 0.6rem 0; border-bottom: 1px solid #f0ebe3; gap: 1rem; }
.rpt__export:last-child { border-bottom: none; }
.rpt__export p { margin: 0.15rem 0 0; font-size: 0.75rem; color: #777; }
.rpt__export strong { font-size: 0.85rem; }
.rpt__btn { padding: 0.35rem 0.8rem; border: none; background: #4a90d9; color: #fff; border-radius: 4px; font-size: 0.8rem; cursor: pointer; white-space: nowrap; }
.rpt__btn:hover:not(:disabled) { background: #357abd; }
.rpt__btn:disabled { opacity: 0.5; cursor: not-allowed; }

@media (max-width: 768px) { .rpt__grid { grid-template-columns: 1fr; } .rpt__stats { flex-direction: column; gap: 1rem; } }
</style>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import ConfidenceBadge from '../components/ConfidenceBadge.vue'
import { useApi } from '../composables/useApi'

const { t } = useI18n()
const router = useRouter()
const { apiFetch, API_BASE } = useApi()

interface ApplicationChild {
  drawing_image_s3_key?: string
}

interface Application {
  giveaway_year: string
  application_id: string
  reference_number?: string
  family_name?: string
  submission_timestamp: string
  source_type: 'upload' | 'digital'
  status: 'needs_review' | 'manually_approved' | 'extraction_failed'
  overall_confidence_score: number
  parent_guardian: {
    first_name: string
    last_name: string
  }
  referring_agency?: {
    agency_name?: string
  }
  children?: ApplicationChild[]
}

interface GiveawayYear {
  year: string
  is_active: boolean
}

const STATUS_OPTIONS = [
  'needs_review',
  'manually_approved',
  'extraction_failed',
] as const

type SortField = 'familyName' | 'submissionDate' | 'source' | 'status' | 'confidence'
type SortDirection = 'asc' | 'desc'

const applications = ref<Application[]>([])
const giveawayYears = ref<GiveawayYear[]>([])
const selectedYear = ref('')
const selectedStatus = ref('needs_review')
const searchQuery = ref('')
const isLoading = ref(false)
const isLoadingYears = ref(false)
const error = ref('')
const yearsError = ref('')
const nextToken = ref<string | null>(null)
const isLoadingMore = ref(false)
const sortField = ref<SortField>('submissionDate')
const sortDirection = ref<SortDirection>('desc')

// --- Reports/cost state ---
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
const summary = ref<Summary | null>(null)
const costData = ref<CostData | null>(null)
const rptLoading = ref(false)
const rptOpen = ref(true)
const exportLoading = ref('')
const exportSuccess = ref('')
const exportOpen = ref(false)
const serviceColors: Record<string, string> = {
  S3: '#4a90d9', CloudFront: '#50c878', Lambda: '#f5a623',
  'API Gateway': '#d94a4a', DynamoDB: '#9b59b6', Textract: '#1abc9c', Bedrock: '#e67e22',
}
const statusColors: Record<string, string> = {
  needs_review: '#f5a623',
  manually_approved: '#4a90d9', rejected: '#d94a4a', extraction_failed: '#999',
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

function getFamilyName(app: Application): string {
  if (app.family_name) return app.family_name
  const pg = app.parent_guardian
  return pg?.last_name ?? ''
}

function getDrawingThumbnailUrl(app: Application): string | null {
  const raw = (app as unknown as Record<string, string>).drawing_s3_key
  if (raw) return `${API_BASE}/drawings/${raw}`
  const key = app.children?.[0]?.drawing_image_s3_key
  if (key) return `${API_BASE}/drawings/${key}`
  return null
}

function formatDate(timestamp: string): string {
  try {
    return new Date(timestamp).toLocaleDateString()
  } catch {
    return timestamp
  }
}

function statusLabel(status: string): string {
  const map: Record<string, string> = {
    needs_review: t('review.statusNeedsReview'),
    manually_approved: t('review.statusManuallyApproved'),
    extraction_failed: t('review.statusExtractionFailed'),
  }
  return map[status] ?? status
}

function sourceLabel(source: string): string {
  return source === 'digital' ? t('review.sourceDigital') : t('review.sourceUpload')
}

const sortedApplications = computed(() => {
  const list = [...applications.value]
  list.sort((a, b) => {
    let cmp = 0
    switch (sortField.value) {
      case 'familyName':
        cmp = getFamilyName(a).localeCompare(getFamilyName(b))
        break
      case 'submissionDate':
        cmp = a.submission_timestamp.localeCompare(b.submission_timestamp)
        break
      case 'source':
        cmp = a.source_type.localeCompare(b.source_type)
        break
      case 'status':
        cmp = a.status.localeCompare(b.status)
        break
      case 'confidence':
        cmp = a.overall_confidence_score - b.overall_confidence_score
        break
    }
    return sortDirection.value === 'asc' ? cmp : -cmp
  })
  return list
})

function toggleSort(field: SortField) {
  if (sortField.value === field) {
    sortDirection.value = sortDirection.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortField.value = field
    sortDirection.value = field === 'submissionDate' ? 'desc' : 'asc'
  }
}

function sortIndicator(field: SortField): string {
  if (sortField.value !== field) return ''
  return sortDirection.value === 'asc' ? ' ▲' : ' ▼'
}

function navigateToDetail(app: Application) {
  router.push(`/admin/review/${app.application_id}`)
}

async function fetchGiveawayYears() {
  isLoadingYears.value = true
  yearsError.value = ''
  try {
    const res = await apiFetch('/giveaway-years')
    if (!res.ok) throw new Error('Failed to fetch giveaway years')
    const data: GiveawayYear[] = await res.json()
    giveawayYears.value = data
    const active = data.find((y) => y.is_active)
    if (active) {
      selectedYear.value = active.year
    } else if (data.length > 0) {
      selectedYear.value = data[0].year
    }
  } catch {
    yearsError.value = t('review.errorLoadingYears')
  } finally {
    isLoadingYears.value = false
  }
}

async function fetchApplications(append = false) {
  if (!selectedYear.value) return
  if (append) {
    isLoadingMore.value = true
  } else {
    isLoading.value = true
    applications.value = []
    nextToken.value = null
  }
  error.value = ''
  try {
    const params = new URLSearchParams({ giveaway_year: selectedYear.value, page_size: '10' })
    if (selectedStatus.value) params.set('status', selectedStatus.value)
    if (searchQuery.value.trim()) params.set('search', searchQuery.value.trim())
    if (append && nextToken.value) params.set('next_token', nextToken.value)
    const res = await apiFetch(`/applications?${params.toString()}`)
    if (!res.ok) throw new Error('Failed to fetch applications')
    const data = await res.json()
    const newApps = Array.isArray(data) ? data : data.applications ?? []
    if (append) {
      applications.value = [...applications.value, ...newApps]
    } else {
      applications.value = newApps
    }
    nextToken.value = data.next_token ?? null
  } catch {
    error.value = t('review.errorLoading')
    if (!append) applications.value = []
  } finally {
    isLoading.value = false
    isLoadingMore.value = false
  }
}

function loadMore() {
  if (nextToken.value) fetchApplications(true)
}

// --- Reports/cost functions ---
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

function downloadCsvBlob(csv: string, filename: string) {
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
    if (type === 'full_report') downloadCsvBlob(await res.text(), `full-report-${selectedYear.value}.csv`)
    else { const d = await res.json(); downloadCsvBlob(d.csv_content, `${type === 'bike_build_list' ? 'bike-build' : 'family-contacts'}-${selectedYear.value}.csv`) }
    exportSuccess.value = { bike_build_list: 'Bike Build List', family_contact_list: 'Family Contact List', full_report: 'Full Report' }[type] + ' exported'
    setTimeout(() => { exportSuccess.value = '' }, 3000)
  } catch { /* */ } finally { exportLoading.value = '' }
}

const newYear = ref('')
const addingYear = ref(false)
const showAddYear = ref(false)

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
    await fetchGiveawayYears()
    if (selectedYear.value) {
      await fetchApplications()
      fetchReportData()
    }
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

watch([selectedYear, selectedStatus, searchQuery], () => {
  fetchApplications()
  fetchReportData()
})

onMounted(async () => {
  await fetchGiveawayYears()
  if (selectedYear.value) {
    await fetchApplications()
    fetchReportData()
  }
})
</script>

<template>
  <div class="review-list-view" @click="exportOpen = false">
    <h1>{{ t('review.title') }}</h1>

    <!-- Controls bar -->
    <div class="review-list-view__controls">
      <div class="review-list-view__control-group">
        <label for="year-select">{{ t('review.giveawayYear') }}</label>
        <div class="review-list-view__year-picker">
          <select id="year-select" v-model="selectedYear" :disabled="isLoadingYears">
            <option v-for="y in giveawayYears" :key="y.year" :value="y.year">
              {{ y.year }}{{ y.is_active ? ' ★' : '' }}
            </option>
          </select>
          <button
            v-if="!showAddYear"
            class="review-list-view__add-year-trigger"
            type="button"
            :title="t('years.createYear')"
            @click="showAddYear = true"
          >+</button>
          <div v-if="showAddYear" class="review-list-view__add-year-inline">
            <input
              v-model="newYear"
              type="text"
              :placeholder="t('years.newYearPlaceholder')"
              class="review-list-view__add-year-input"
              @keydown.enter="addYear"
              @keydown.escape="cancelAddYear"
            />
            <button
              class="review-list-view__add-year-btn"
              type="button"
              :disabled="addingYear || !newYear.trim()"
              @click="addYear"
            >{{ t('common.save') }}</button>
            <button
              class="review-list-view__add-year-cancel"
              type="button"
              @click="cancelAddYear"
            >{{ t('common.cancel') }}</button>
          </div>
        </div>
      </div>

      <div class="review-list-view__control-group">
        <label for="status-filter">{{ t('review.filterStatus') }}</label>
        <select id="status-filter" v-model="selectedStatus">
          <option value="">{{ t('review.allStatuses') }}</option>
          <option v-for="s in STATUS_OPTIONS" :key="s" :value="s">
            {{ statusLabel(s) }}
          </option>
        </select>
      </div>

      <div class="review-list-view__control-group review-list-view__control-group--search">
        <label for="search-input" class="sr-only">{{ t('common.search') }}</label>
        <input
          id="search-input"
          v-model="searchQuery"
          type="search"
          :placeholder="t('review.searchPlaceholder')"
        />
      </div>

      <div class="export-drop" @click.stop>
        <div v-if="exportSuccess" class="export-drop__msg">✓ {{ exportSuccess }}</div>
        <button class="export-drop__trigger" @click="exportOpen = !exportOpen">
          Export ▾
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
    </div>

    <!-- Error states -->
    <div v-if="yearsError" class="review-list-view__error" role="alert">
      {{ yearsError }}
      <button @click="fetchGiveawayYears">{{ t('review.retry') }}</button>
    </div>

    <div v-if="error" class="review-list-view__error" role="alert">
      {{ error }}
      <button @click="() => fetchApplications()">{{ t('review.retry') }}</button>
    </div>

    <!-- Loading -->
    <div v-if="isLoading" class="review-list-view__loading" role="status">
      {{ t('review.loadingApplications') }}
    </div>

    <!-- Table -->
    <div v-else-if="sortedApplications.length > 0" class="review-list-view__table-wrapper">
      <table class="review-list-view__table" aria-label="Applications">
        <thead>
          <tr>
            <th
              scope="col"
              class="review-list-view__sortable"
              @click="toggleSort('familyName')"
              :aria-sort="sortField === 'familyName' ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'"
            >
              {{ t('review.familyName') }}{{ sortIndicator('familyName') }}
            </th>
            <th scope="col">Ref #</th>
            <th
              scope="col"
              class="review-list-view__sortable"
              @click="toggleSort('submissionDate')"
              :aria-sort="sortField === 'submissionDate' ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'"
            >
              {{ t('review.submissionDate') }}{{ sortIndicator('submissionDate') }}
            </th>
            <th
              scope="col"
              class="review-list-view__sortable"
              @click="toggleSort('source')"
              :aria-sort="sortField === 'source' ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'"
            >
              {{ t('review.source') }}{{ sortIndicator('source') }}
            </th>
            <th
              scope="col"
              class="review-list-view__sortable"
              @click="toggleSort('status')"
              :aria-sort="sortField === 'status' ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'"
            >
              {{ t('review.status') }}{{ sortIndicator('status') }}
            </th>
            <th
              scope="col"
              class="review-list-view__sortable"
              @click="toggleSort('confidence')"
              :aria-sort="sortField === 'confidence' ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'"
            >
              {{ t('review.confidence') }}{{ sortIndicator('confidence') }}
            </th>
            <th scope="col">{{ t('review.drawing') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="app in sortedApplications"
            :key="app.application_id"
            class="review-list-view__row"
            tabindex="0"
            role="link"
            @click="navigateToDetail(app)"
            @keydown.enter="navigateToDetail(app)"
          >
            <td>{{ getFamilyName(app) }}</td>
            <td>{{ app.reference_number || '' }}</td>
            <td>{{ formatDate(app.submission_timestamp) }}</td>
            <td>{{ sourceLabel(app.source_type) }}</td>
            <td>
              <span :class="`review-list-view__status review-list-view__status--${app.status}`">
                {{ statusLabel(app.status) }}
              </span>
            </td>
            <td>
              <ConfidenceBadge :score="app.overall_confidence_score" />
            </td>
            <td>
              <img
                v-if="getDrawingThumbnailUrl(app)"
                :src="getDrawingThumbnailUrl(app)!"
                :alt="t('review.drawing')"
                class="review-list-view__thumbnail"
                loading="lazy"
              />
              <span v-else class="review-list-view__no-drawing">{{ t('review.noDrawing') }}</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Load more -->
    <div v-if="nextToken && !isLoading" class="review-list-view__load-more">
      <button class="review-list-view__load-more-btn" :disabled="isLoadingMore" @click="loadMore">
        {{ isLoadingMore ? 'Loading...' : 'Load More' }}
      </button>
      <span class="review-list-view__count">{{ sortedApplications.length }} loaded</span>
    </div>

    <!-- Empty state -->
    <div v-else-if="!isLoading && !error && sortedApplications.length === 0" class="review-list-view__empty">
      {{ t('review.noApplications') }}
    </div>

    <!-- Stats (collapsible) -->
    <div v-if="summary && !rptLoading" class="rpt">
      <button class="rpt__toggle" @click="rptOpen = !rptOpen">
        <span class="rpt__toggle-arrow">{{ rptOpen ? '▾' : '▸' }}</span>
        <span class="rpt__toggle-title">{{ selectedYear }} Overview</span>
        <span class="rpt__toggle-pills">
          <span class="rpt__pill">{{ summary.total_applications }} apps</span>
          <span class="rpt__pill">{{ summary.applications_by_source_type['digital'] || 0 }}d / {{ summary.applications_by_source_type['upload'] || 0 }}u</span>
          <span v-if="costData" class="rpt__pill rpt__pill--cost">${{ costData.total_cost.toFixed(2) }}</span>
          <span v-if="currentService && !rptOpen" class="rpt__pill rpt__pill--svc" :style="{ borderColor: currentService.color }">
            <span class="rpt__svc-ticker-dot" :style="{ background: currentService.color }"></span>
            {{ currentService.name }} ${{ currentService.amount.toFixed(2) }}
          </span>
        </span>
      </button>
      <div v-if="rptOpen" class="rpt__body">
        <!-- Overview stats row -->
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

        <!-- Status + Service breakdown side by side -->
        <div class="rpt__grid">
          <div class="rpt__card">
            <h4>Status</h4>
            <div v-for="(count, status) in summary.applications_by_status" :key="status" class="rpt__bar-row">
              <span class="rpt__bar-dot" :style="{ background: statusColors[status as string] || '#999' }"></span>
              <span class="rpt__bar-label">{{ statusLabel(status as string) }}</span>
              <div class="rpt__bar-track">
                <div class="rpt__bar-fill" :style="{ width: (count as number) / summary.total_applications * 100 + '%', background: statusColors[status as string] || '#999' }"></div>
              </div>
              <span class="rpt__bar-count">{{ count }}</span>
            </div>
          </div>
          <div v-if="costData" class="rpt__card rpt__card--services">
            <h4>AWS Service Breakdown</h4>
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
      </div>
    </div>
  </div>
</template>

<style scoped>
/* ── Page shell ── */
.review-list-view { padding: 1.25rem 1.5rem; max-width: 1280px; margin: 0 auto; }
.review-list-view h1 { margin: 0 0 1.25rem; font-size: 1.4rem; font-weight: 800; color: #3d2e1f; letter-spacing: -0.01em; }

/* ── Controls bar ── */
.review-list-view__controls { display: flex; flex-wrap: wrap; gap: 0.75rem; margin-bottom: 1.25rem; align-items: flex-end; }
.review-list-view__control-group { display: flex; flex-direction: column; gap: 0.2rem; }
.review-list-view__control-group label { font-size: 0.75rem; font-weight: 700; color: #8b7355; text-transform: uppercase; letter-spacing: 0.04em; }
.review-list-view__control-group select,
.review-list-view__control-group input {
  padding: 0.45rem 0.65rem; border: 1px solid #d4c4a8; border-radius: 6px;
  font-size: 0.85rem; background: #fff; color: #3d2e1f;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.review-list-view__control-group select:focus,
.review-list-view__control-group input:focus { outline: none; border-color: #e8860c; box-shadow: 0 0 0 3px rgba(232,134,12,0.15); }

.review-list-view__year-picker { display: flex; align-items: center; gap: 0.4rem; flex-wrap: wrap; }
.review-list-view__add-year-trigger {
  width: 30px; height: 30px; border: 1px dashed #d4c4a8; border-radius: 6px;
  background: #fff; color: #e8860c; font-size: 1.1rem; font-weight: 700;
  cursor: pointer; display: flex; align-items: center; justify-content: center;
  transition: all 0.15s;
}
.review-list-view__add-year-trigger:hover { border-style: solid; border-color: #e8860c; background: #fef3e2; }
.review-list-view__add-year-inline { display: flex; align-items: center; gap: 0.3rem; }
.review-list-view__add-year-input { width: 80px; padding: 0.35rem 0.45rem; border: 1.5px solid #e8860c; border-radius: 5px; font-size: 0.85rem; }
.review-list-view__add-year-btn { padding: 0.35rem 0.65rem; border: none; background: #e8860c; color: #fff; border-radius: 5px; font-size: 0.78rem; font-weight: 600; cursor: pointer; }
.review-list-view__add-year-btn:hover:not(:disabled) { background: #cf7609; }
.review-list-view__add-year-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.review-list-view__add-year-cancel { padding: 0.35rem 0.65rem; border: 1px solid #d4c4a8; background: #fff; color: #8b7355; border-radius: 5px; font-size: 0.78rem; cursor: pointer; }
.review-list-view__add-year-cancel:hover { background: #f5f0e8; }

.review-list-view__control-group--search { flex: 1; min-width: 200px; }
.review-list-view__control-group--search input { width: 100%; }

.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; border: 0; }

/* ── Error / loading / empty ── */
.review-list-view__error {
  padding: 0.65rem 1rem; background: #fef2f2; color: #991b1b; border: 1px solid #fecaca;
  border-radius: 8px; margin-bottom: 1rem; display: flex; align-items: center; gap: 0.5rem; font-size: 0.85rem;
}
.review-list-view__error button { padding: 0.25rem 0.75rem; border: 1px solid #991b1b; background: transparent; color: #991b1b; border-radius: 5px; cursor: pointer; font-size: 0.8rem; }
.review-list-view__error button:hover { background: #991b1b; color: #fff; }
.review-list-view__loading { padding: 3rem; text-align: center; color: #8b7355; font-size: 0.9rem; }
.review-list-view__empty { padding: 3rem; text-align: center; color: #8b7355; font-size: 0.9rem; }

/* ── Table ── */
.review-list-view__table-wrapper { overflow-x: auto; border: 1px solid #d4c4a8; border-radius: 10px; background: #fff; box-shadow: 0 1px 3px rgba(61,46,31,0.06); }
.review-list-view__table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
.review-list-view__table th,
.review-list-view__table td { padding: 0.65rem 0.85rem; text-align: left; }
.review-list-view__table th {
  background: #3d2e1f; font-weight: 700; font-size: 0.75rem; color: #f5f0e8;
  text-transform: uppercase; letter-spacing: 0.04em; border-bottom: none; white-space: nowrap;
}
.review-list-view__table td { border-bottom: 1px solid #ede6db; color: #3d2e1f; }
.review-list-view__sortable { cursor: pointer; user-select: none; transition: color 0.1s; }
.review-list-view__sortable:hover { color: #f5c87a; background: #4a3828; }
.review-list-view__row { cursor: pointer; transition: background 0.1s; }
.review-list-view__row:nth-child(even) { background: #faf7f2; }
.review-list-view__row:hover { background: #fef3e2; }
.review-list-view__row:hover td { color: #3d2e1f; }
.review-list-view__row:focus { outline: 2px solid #e8860c; outline-offset: -2px; }

/* ── Status pills ── */
.review-list-view__status { display: inline-block; padding: 3px 10px; border-radius: 99px; font-size: 0.74rem; font-weight: 700; letter-spacing: 0.01em; }
.review-list-view__status--needs_review { background: #fef3c7; color: #92400e; }
.review-list-view__status--manually_approved { background: #dbeafe; color: #1e40af; }
.review-list-view__status--extraction_failed { background: #fee2e2; color: #991b1b; }

/* ── Drawing thumbnail ── */
.review-list-view__thumbnail { width: 44px; height: 44px; object-fit: cover; border-radius: 6px; border: 1px solid #d4c4a8; }
.review-list-view__no-drawing { color: #c4b49a; font-size: 0.78rem; }

/* ── Load more ── */
.review-list-view__load-more { display: flex; align-items: center; gap: 1rem; padding: 1rem 0; }
.review-list-view__load-more-btn {
  padding: 0.5rem 1.5rem; border: 1.5px solid #e8860c; background: #fff; color: #e8860c;
  border-radius: 8px; font-size: 0.85rem; font-weight: 600; cursor: pointer; transition: all 0.15s;
}
.review-list-view__load-more-btn:hover:not(:disabled) { background: #e8860c; color: #fff; }
.review-list-view__load-more-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.review-list-view__count { font-size: 0.78rem; color: #8b7355; }

/* ── Export dropdown ── */
.export-drop { position: relative; display: inline-flex; align-items: flex-end; align-self: flex-end; }
.export-drop__msg { position: absolute; bottom: 100%; left: 0; margin-bottom: 4px; padding: 0.3rem 0.6rem; background: #d1fae5; color: #065f46; border-radius: 5px; font-size: 0.75rem; white-space: nowrap; }
.export-drop__trigger {
  padding: 0.45rem 1rem; background: #fff; border: 1.5px solid #e8860c; color: #e8860c;
  border-radius: 7px; font-size: 0.85rem; font-weight: 700; cursor: pointer; transition: all 0.15s;
}
.export-drop__trigger:hover { background: #e8860c; color: #fff; }
.export-drop__menu {
  position: absolute; top: 100%; left: 0; margin-top: 4px; z-index: 50;
  background: #fff; border: 1px solid #d4c4a8; border-radius: 8px;
  box-shadow: 0 4px 16px rgba(61,46,31,0.12); min-width: 200px; overflow: hidden;
}
.export-drop__item {
  display: flex; align-items: center; justify-content: space-between; gap: 0.5rem;
  width: 100%; padding: 0.6rem 0.85rem; border: none; background: none;
  font-size: 0.85rem; color: #3d2e1f; cursor: pointer; text-align: left; font-family: inherit;
  transition: background 0.1s;
}
.export-drop__item:hover:not(:disabled) { background: #fef3e2; }
.export-drop__item:disabled { opacity: 0.5; cursor: not-allowed; }
.export-drop__item + .export-drop__item { border-top: 1px solid #ede6db; }
.export-drop__spinner { color: #8b7355; font-size: 0.8rem; }

/* ── Stats panel ── */
.rpt { margin-top: 1rem; border: 1px solid #d4c4a8; border-radius: 10px; overflow: hidden; background: #fff; box-shadow: 0 1px 3px rgba(61,46,31,0.06); }
.rpt h4 { margin: 0 0 0.5rem; font-size: 0.85rem; font-weight: 700; color: #3d2e1f; }
.rpt__toggle {
  display: flex; align-items: center; gap: 0.5rem; width: 100%;
  padding: 0.7rem 1rem; background: #3d2e1f; border: none;
  font-size: 0.85rem; font-weight: 700; cursor: pointer; color: #f5f0e8; text-align: left;
  transition: background 0.1s;
}
.rpt__toggle:hover { background: #4a3828; }
.rpt__toggle-arrow { flex-shrink: 0; color: #c4b49a; }
.rpt__toggle-title { white-space: nowrap; }
.rpt__toggle-pills { display: flex; align-items: center; gap: 0.35rem; margin-left: auto; flex-wrap: wrap; justify-content: flex-end; }
.rpt__pill { font-size: 0.7rem; font-weight: 700; padding: 0.15rem 0.5rem; border-radius: 99px; background: rgba(255,255,255,0.15); color: #f5f0e8; white-space: nowrap; }
.rpt__pill--cost { background: rgba(16,185,129,0.2); color: #6ee7b7; }
.rpt__pill--svc { background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.25); color: #f5f0e8; display: inline-flex; align-items: center; gap: 0.25rem; animation: rpt-svc-fade 0.5s ease; }
.rpt__svc-ticker-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; animation: rpt-svc-pulse 2s ease-in-out infinite; }
@keyframes rpt-svc-fade { from { opacity: 0; transform: translateY(-4px); } to { opacity: 1; transform: translateY(0); } }
@keyframes rpt-svc-pulse { 0%, 100% { transform: scale(1); } 50% { transform: scale(1.4); } }
.rpt__body { padding: 1rem; display: flex; flex-direction: column; gap: 0.75rem; }
.rpt__msg { padding: 0.4rem 0.75rem; background: #d1fae5; color: #065f46; border-radius: 6px; font-size: 0.82rem; }
.rpt__stats { display: flex; flex-wrap: wrap; gap: 1.5rem; padding: 0.85rem; background: #f5f0e8; border-radius: 8px; }
.rpt__stat { display: flex; flex-direction: column; }
.rpt__stat--hero .rpt__stat-val { font-size: 1.8rem; color: #3d2e1f; }
.rpt__stat-val { font-size: 1.2rem; font-weight: 800; color: #3d2e1f; }
.rpt__stat-lbl { font-size: 0.65rem; color: #8b7355; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; }
.rpt__card { border: 1px solid #ede6db; border-radius: 8px; padding: 0.75rem; background: #fff; }
.rpt__grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem; }
.rpt__bar-row { display: flex; align-items: center; gap: 0.4rem; margin-bottom: 0.3rem; font-size: 0.8rem; }
.rpt__bar-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
.rpt__bar-label { min-width: 110px; color: #3d2e1f; font-weight: 500; }
.rpt__bar-track { flex: 1; height: 14px; background: #f0ebe3; border-radius: 7px; overflow: hidden; }
.rpt__bar-fill { height: 100%; border-radius: 7px; min-width: 2px; transition: width 0.3s ease; }
.rpt__bar-count { min-width: 28px; text-align: right; font-weight: 800; font-size: 0.78rem; color: #3d2e1f; }
.rpt__card--services { background: #faf7f2; }
.rpt__svc-list { display: flex; flex-direction: column; gap: 0.3rem; }
.rpt__svc-row { display: flex; align-items: center; gap: 0.5rem; font-size: 0.8rem; }
.rpt__svc-dot { width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0; }
.rpt__svc-name { min-width: 90px; color: #3d2e1f; font-weight: 500; }
.rpt__svc-bar-track { flex: 1; height: 8px; background: #e6ddd0; border-radius: 4px; overflow: hidden; }
.rpt__svc-bar-fill { height: 100%; border-radius: 4px; transition: width 0.4s ease; }
.rpt__svc-amount { min-width: 60px; text-align: right; font-weight: 800; font-size: 0.78rem; color: #3d2e1f; }

/* ── Responsive ── */
@media (max-width: 768px) {
  .review-list-view { padding: 1rem; }
  .review-list-view__controls { flex-direction: column; }
  .review-list-view__control-group--search { min-width: unset; }
  .rpt__grid { grid-template-columns: 1fr; }
}
</style>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import ConfidenceBadge from '../components/ConfidenceBadge.vue'

const { t } = useI18n()
const router = useRouter()

const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api'

interface ApplicationChild {
  drawing_image_s3_key?: string
}

interface Application {
  giveaway_year: string
  application_id: string
  submission_timestamp: string
  source_type: 'upload' | 'digital'
  status: 'needs_review' | 'auto_approved' | 'manually_approved' | 'extraction_failed'
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
  'auto_approved',
  'manually_approved',
  'extraction_failed',
] as const

type SortField = 'familyName' | 'submissionDate' | 'source' | 'status' | 'confidence'
type SortDirection = 'asc' | 'desc'

const applications = ref<Application[]>([])
const giveawayYears = ref<GiveawayYear[]>([])
const selectedYear = ref('')
const selectedStatus = ref('')
const searchQuery = ref('')
const isLoading = ref(false)
const isLoadingYears = ref(false)
const error = ref('')
const yearsError = ref('')
const sortField = ref<SortField>('submissionDate')
const sortDirection = ref<SortDirection>('desc')

// Export state
const exportStatusFilter = ref<string[]>([])
const isExportingBikeBuild = ref(false)
const isExportingFamilyContact = ref(false)
const exportError = ref('')
const exportSuccess = ref('')

function getFamilyName(app: Application): string {
  const pg = app.parent_guardian
  return pg ? `${pg.last_name}, ${pg.first_name}` : ''
}

function getDrawingThumbnailUrl(app: Application): string | null {
  const key = app.children?.[0]?.drawing_image_s3_key
  if (!key) return null
  return `${API_BASE}/drawings/${encodeURIComponent(key)}`
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
    auto_approved: t('review.statusAutoApproved'),
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
  router.push(`/admin/review/${app.giveaway_year}/${app.application_id}`)
}

async function fetchGiveawayYears() {
  isLoadingYears.value = true
  yearsError.value = ''
  try {
    const res = await fetch(`${API_BASE}/giveaway-years`)
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

async function fetchApplications() {
  if (!selectedYear.value) return
  isLoading.value = true
  error.value = ''
  try {
    const params = new URLSearchParams({ giveaway_year: selectedYear.value })
    if (selectedStatus.value) params.set('status', selectedStatus.value)
    if (searchQuery.value.trim()) params.set('search', searchQuery.value.trim())
    const res = await fetch(`${API_BASE}/applications?${params.toString()}`)
    if (!res.ok) throw new Error('Failed to fetch applications')
    const data = await res.json()
    applications.value = Array.isArray(data) ? data : data.applications ?? []
  } catch {
    error.value = t('review.errorLoading')
    applications.value = []
  } finally {
    isLoading.value = false
  }
}

function toggleExportStatus(status: string) {
  const idx = exportStatusFilter.value.indexOf(status)
  if (idx === -1) {
    exportStatusFilter.value.push(status)
  } else {
    exportStatusFilter.value.splice(idx, 1)
  }
}

function isExportStatusSelected(status: string): boolean {
  return exportStatusFilter.value.includes(status)
}

function downloadCsvBlob(csvContent: string, filename: string) {
  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.style.display = 'none'
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}

async function exportBikeBuildList() {
  if (!selectedYear.value) return
  isExportingBikeBuild.value = true
  exportError.value = ''
  exportSuccess.value = ''
  try {
    const body: Record<string, unknown> = { giveaway_year: selectedYear.value }
    if (exportStatusFilter.value.length > 0) {
      body.status_filter = exportStatusFilter.value
    }
    const res = await fetch(`${API_BASE}/exports/bike-build-list`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!res.ok) throw new Error('Export failed')
    const csv = await res.text()
    downloadCsvBlob(csv, `bike-build-list-${selectedYear.value}.csv`)
    exportSuccess.value = t('review.exportSuccess')
  } catch {
    exportError.value = t('review.exportError')
  } finally {
    isExportingBikeBuild.value = false
  }
}

async function exportFamilyContactList() {
  if (!selectedYear.value) return
  isExportingFamilyContact.value = true
  exportError.value = ''
  exportSuccess.value = ''
  try {
    const body: Record<string, unknown> = { giveaway_year: selectedYear.value }
    if (exportStatusFilter.value.length > 0) {
      body.status_filter = exportStatusFilter.value
    }
    const res = await fetch(`${API_BASE}/exports/family-contact-list`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!res.ok) throw new Error('Export failed')
    const csv = await res.text()
    downloadCsvBlob(csv, `family-contact-list-${selectedYear.value}.csv`)
    exportSuccess.value = t('review.exportSuccess')
  } catch {
    exportError.value = t('review.exportError')
  } finally {
    isExportingFamilyContact.value = false
  }
}

watch([selectedYear, selectedStatus, searchQuery], () => {
  fetchApplications()
})

onMounted(async () => {
  await fetchGiveawayYears()
  if (selectedYear.value) {
    await fetchApplications()
  }
})
</script>

<template>
  <div class="review-list-view">
    <h1>{{ t('review.title') }}</h1>

    <!-- Controls bar -->
    <div class="review-list-view__controls">
      <div class="review-list-view__control-group">
        <label for="year-select">{{ t('review.giveawayYear') }}</label>
        <select id="year-select" v-model="selectedYear" :disabled="isLoadingYears">
          <option v-for="y in giveawayYears" :key="y.year" :value="y.year">
            {{ y.year }}{{ y.is_active ? ' ★' : '' }}
          </option>
        </select>
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
    </div>

    <!-- Error states -->
    <div v-if="yearsError" class="review-list-view__error" role="alert">
      {{ yearsError }}
      <button @click="fetchGiveawayYears">{{ t('review.retry') }}</button>
    </div>

    <div v-if="error" class="review-list-view__error" role="alert">
      {{ error }}
      <button @click="fetchApplications">{{ t('review.retry') }}</button>
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

    <!-- Empty state -->
    <div v-else-if="!isLoading && !error" class="review-list-view__empty">
      {{ t('review.noApplications') }}
    </div>

    <!-- Export section -->
    <div class="review-list-view__export-section">
      <h2>{{ t('review.exportSection') }}</h2>

      <div class="review-list-view__export-status-filter">
        <span class="review-list-view__export-filter-label">{{ t('review.exportStatusFilter') }}:</span>
        <div class="review-list-view__export-checkboxes">
          <label v-for="s in STATUS_OPTIONS" :key="s" class="review-list-view__export-checkbox">
            <input
              type="checkbox"
              :value="s"
              :checked="isExportStatusSelected(s)"
              @change="toggleExportStatus(s)"
            />
            {{ statusLabel(s) }}
          </label>
        </div>
        <span v-if="exportStatusFilter.length === 0" class="review-list-view__export-filter-hint">
          {{ t('review.exportAllStatuses') }}
        </span>
      </div>

      <div class="review-list-view__export-buttons">
        <button
          class="review-list-view__export-btn"
          :disabled="isExportingBikeBuild || !selectedYear"
          @click="exportBikeBuildList"
        >
          {{ isExportingBikeBuild ? t('review.exporting') : t('review.exportBikeBuildList') }}
        </button>
        <button
          class="review-list-view__export-btn"
          :disabled="isExportingFamilyContact || !selectedYear"
          @click="exportFamilyContactList"
        >
          {{ isExportingFamilyContact ? t('review.exporting') : t('review.exportFamilyContactList') }}
        </button>
      </div>

      <div v-if="exportError" class="review-list-view__export-error" role="alert">
        {{ exportError }}
      </div>
      <div v-if="exportSuccess" class="review-list-view__export-success" role="status">
        {{ exportSuccess }}
      </div>
    </div>
  </div>
</template>

<style scoped>
.review-list-view {
  padding: 1rem;
}

.review-list-view h1 {
  margin: 0 0 1rem;
  font-size: 1.5rem;
}

.review-list-view__controls {
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
  margin-bottom: 1rem;
  align-items: flex-end;
}

.review-list-view__control-group {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.review-list-view__control-group label {
  font-size: 0.85rem;
  font-weight: 600;
}

.review-list-view__control-group select,
.review-list-view__control-group input {
  padding: 0.4rem 0.6rem;
  border: 1px solid #ccc;
  border-radius: 4px;
  font-size: 0.9rem;
}

.review-list-view__control-group--search {
  flex: 1;
  min-width: 200px;
}

.review-list-view__control-group--search input {
  width: 100%;
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

.review-list-view__error {
  padding: 0.75rem 1rem;
  background: #f8d7da;
  color: #721c24;
  border-radius: 4px;
  margin-bottom: 1rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.review-list-view__error button {
  padding: 0.25rem 0.75rem;
  border: 1px solid #721c24;
  background: transparent;
  color: #721c24;
  border-radius: 4px;
  cursor: pointer;
}

.review-list-view__loading {
  padding: 2rem;
  text-align: center;
  color: #666;
}

.review-list-view__table-wrapper {
  overflow-x: auto;
}

.review-list-view__table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.9rem;
}

.review-list-view__table th,
.review-list-view__table td {
  padding: 0.6rem 0.75rem;
  text-align: left;
  border-bottom: 1px solid #e0e0e0;
}

.review-list-view__table th {
  background: #f5f5f5;
  font-weight: 600;
  white-space: nowrap;
}

.review-list-view__sortable {
  cursor: pointer;
  user-select: none;
}

.review-list-view__sortable:hover {
  background: #eaeaea;
}

.review-list-view__row {
  cursor: pointer;
}

.review-list-view__row:hover {
  background: #f9f9f9;
}

.review-list-view__row:focus {
  outline: 2px solid #4a90d9;
  outline-offset: -2px;
}

.review-list-view__status {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 0.8rem;
  font-weight: 600;
}

.review-list-view__status--needs_review {
  background: #fff3cd;
  color: #856404;
}

.review-list-view__status--auto_approved {
  background: #d4edda;
  color: #155724;
}

.review-list-view__status--manually_approved {
  background: #cce5ff;
  color: #004085;
}

.review-list-view__status--extraction_failed {
  background: #f8d7da;
  color: #721c24;
}

.review-list-view__thumbnail {
  width: 48px;
  height: 48px;
  object-fit: cover;
  border-radius: 4px;
  border: 1px solid #ddd;
}

.review-list-view__no-drawing {
  color: #999;
  font-size: 0.8rem;
}

.review-list-view__empty {
  padding: 2rem;
  text-align: center;
  color: #666;
}

@media (max-width: 768px) {
  .review-list-view__controls {
    flex-direction: column;
  }

  .review-list-view__control-group--search {
    min-width: unset;
  }

  .review-list-view__export-buttons {
    flex-direction: column;
  }
}

.review-list-view__export-section {
  margin-top: 2rem;
  padding-top: 1.5rem;
  border-top: 1px solid #e0e0e0;
}

.review-list-view__export-section h2 {
  margin: 0 0 1rem;
  font-size: 1.2rem;
}

.review-list-view__export-status-filter {
  margin-bottom: 1rem;
}

.review-list-view__export-filter-label {
  font-size: 0.85rem;
  font-weight: 600;
  margin-right: 0.5rem;
}

.review-list-view__export-checkboxes {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  margin-top: 0.4rem;
}

.review-list-view__export-checkbox {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  font-size: 0.9rem;
  cursor: pointer;
}

.review-list-view__export-filter-hint {
  display: block;
  margin-top: 0.3rem;
  font-size: 0.8rem;
  color: #666;
}

.review-list-view__export-buttons {
  display: flex;
  gap: 0.75rem;
  margin-top: 0.5rem;
}

.review-list-view__export-btn {
  padding: 0.5rem 1.25rem;
  border: 1px solid #4a90d9;
  background: #4a90d9;
  color: #fff;
  border-radius: 4px;
  font-size: 0.9rem;
  cursor: pointer;
}

.review-list-view__export-btn:hover:not(:disabled) {
  background: #357abd;
}

.review-list-view__export-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.review-list-view__export-error {
  margin-top: 0.75rem;
  padding: 0.5rem 0.75rem;
  background: #f8d7da;
  color: #721c24;
  border-radius: 4px;
  font-size: 0.9rem;
}

.review-list-view__export-success {
  margin-top: 0.75rem;
  padding: 0.5rem 0.75rem;
  background: #d4edda;
  color: #155724;
  border-radius: 4px;
  font-size: 0.9rem;
}
</style>

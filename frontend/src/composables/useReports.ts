import { ref, reactive, computed, watch } from 'vue'

const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api'

export interface ReportFilter {
  field: string
  operator: string
  value: unknown
}

export interface ReportConfig {
  giveaway_year: string
  columns: string[]
  filters: ReportFilter[]
  group_by: string
  sort_by: string
  sort_order: 'asc' | 'desc'
  page: number
  page_size: number
}

export interface ReportSummary {
  total_applications: number
  total_children: number
  applications_by_status: Record<string, number>
  applications_by_source_type: Record<string, number>
}

export interface ReportResult {
  summary: ReportSummary
  rows: Record<string, unknown>[]
  pagination: { page: number; page_size: number; total_count: number; total_pages: number }
  giveaway_year: string
  groups?: Record<string, { count: number }>
}

export interface SavedReport {
  user_id: string
  report_id: string
  name: string
  columns: string[]
  filters: ReportFilter[]
  group_by: string | null
  sort_by: string | null
  sort_order: string
  created_at: string
  updated_at: string
}

export interface FieldDef {
  path: string
  labelKey: string
}

export const AVAILABLE_FIELDS: FieldDef[] = [
  { path: 'status', labelKey: 'reports.fieldStatus' },
  { path: 'source_type', labelKey: 'reports.fieldSourceType' },
  { path: 'giveaway_year', labelKey: 'reports.fieldGiveawayYear' },
  { path: 'referring_agency.agency_name', labelKey: 'reports.fieldAgencyName' },
  { path: 'parent_guardian.first_name', labelKey: 'reports.fieldParentFirstName' },
  { path: 'parent_guardian.last_name', labelKey: 'reports.fieldParentLastName' },
  { path: 'parent_guardian.address', labelKey: 'reports.fieldAddress' },
  { path: 'parent_guardian.city', labelKey: 'reports.fieldCity' },
  { path: 'parent_guardian.zip_code', labelKey: 'reports.fieldZipCode' },
  { path: 'parent_guardian.primary_language', labelKey: 'reports.fieldPrimaryLanguage' },
  { path: 'parent_guardian.preferred_contact_method', labelKey: 'reports.fieldPreferredContact' },
  { path: 'parent_guardian.transportation_access', labelKey: 'reports.fieldTransportationAccess' },
  { path: 'submission_timestamp', labelKey: 'reports.fieldSubmissionDate' },
  { path: 'children[0].first_name', labelKey: 'reports.fieldChildFirstName' },
  { path: 'children[0].last_name', labelKey: 'reports.fieldChildLastName' },
  { path: 'children[0].height_inches', labelKey: 'reports.fieldHeightInches' },
  { path: 'children[0].age', labelKey: 'reports.fieldAge' },
  { path: 'children[0].gender', labelKey: 'reports.fieldGender' },
  { path: 'children[0].bike_color_1', labelKey: 'reports.fieldBikeColor1' },
  { path: 'children[0].bike_color_2', labelKey: 'reports.fieldBikeColor2' },
  { path: 'children[0].knows_how_to_ride', labelKey: 'reports.fieldKnowsHowToRide' },
  { path: 'children[0].dream_bike_description', labelKey: 'reports.fieldDreamBikeDescription' },
  { path: 'children[0].drawing_keywords', labelKey: 'reports.fieldDrawingKeywords' },
  { path: 'children[0].bike_number', labelKey: 'reports.fieldBikeNumber' },
  { path: 'overall_confidence_score', labelKey: 'reports.fieldConfidenceScore' },
]

export const OPERATORS = [
  { value: 'equals', labelKey: 'reports.opEquals' },
  { value: 'contains', labelKey: 'reports.opContains' },
  { value: 'greater_than', labelKey: 'reports.opGreaterThan' },
  { value: 'less_than', labelKey: 'reports.opLessThan' },
  { value: 'between', labelKey: 'reports.opBetween' },
  { value: 'in_list', labelKey: 'reports.opInList' },
]

export interface PreBuiltTemplate {
  nameKey: string
  columns: string[]
  group_by: string
  sort_by: string
  sort_order: 'asc' | 'desc'
  filters: ReportFilter[]
}

export const PRE_BUILT_TEMPLATES: PreBuiltTemplate[] = [
  {
    nameKey: 'reports.tplHeightDistribution',
    columns: ['children[0].first_name', 'children[0].last_name', 'children[0].height_inches', 'children[0].age'],
    group_by: 'children[0].height_inches',
    sort_by: 'children[0].height_inches',
    sort_order: 'asc',
    filters: [],
  },
  {
    nameKey: 'reports.tplByAgency',
    columns: ['referring_agency.agency_name', 'parent_guardian.last_name', 'status'],
    group_by: 'referring_agency.agency_name',
    sort_by: 'referring_agency.agency_name',
    sort_order: 'asc',
    filters: [],
  },
  {
    nameKey: 'reports.tplByZipCode',
    columns: ['parent_guardian.zip_code', 'parent_guardian.last_name', 'parent_guardian.city'],
    group_by: 'parent_guardian.zip_code',
    sort_by: 'parent_guardian.zip_code',
    sort_order: 'asc',
    filters: [],
  },
  {
    nameKey: 'reports.tplAgeDistribution',
    columns: ['children[0].first_name', 'children[0].last_name', 'children[0].age', 'children[0].gender'],
    group_by: 'children[0].age',
    sort_by: 'children[0].age',
    sort_order: 'asc',
    filters: [],
  },
  {
    nameKey: 'reports.tplColorPreferences',
    columns: ['children[0].first_name', 'children[0].bike_color_1', 'children[0].bike_color_2'],
    group_by: 'children[0].bike_color_1',
    sort_by: 'children[0].bike_color_1',
    sort_order: 'asc',
    filters: [],
  },
  {
    nameKey: 'reports.tplLanguageDistribution',
    columns: ['parent_guardian.primary_language', 'parent_guardian.last_name'],
    group_by: 'parent_guardian.primary_language',
    sort_by: 'parent_guardian.primary_language',
    sort_order: 'asc',
    filters: [],
  },
  {
    nameKey: 'reports.tplTransportationAccess',
    columns: ['parent_guardian.transportation_access', 'parent_guardian.last_name', 'parent_guardian.city'],
    group_by: 'parent_guardian.transportation_access',
    sort_by: 'parent_guardian.transportation_access',
    sort_order: 'asc',
    filters: [],
  },
  {
    nameKey: 'reports.tplReviewStatus',
    columns: ['status', 'parent_guardian.last_name', 'source_type', 'overall_confidence_score'],
    group_by: 'status',
    sort_by: 'status',
    sort_order: 'asc',
    filters: [],
  },
]

export function useReports() {
  const config = reactive<ReportConfig>({
    giveaway_year: '',
    columns: [],
    filters: [],
    group_by: '',
    sort_by: '',
    sort_order: 'asc',
    page: 1,
    page_size: 50,
  })

  const result = ref<ReportResult | null>(null)
  const isLoading = ref(false)
  const error = ref('')

  const savedReports = ref<SavedReport[]>([])
  const savedReportsLoading = ref(false)
  const savedReportsError = ref('')

  const isExporting = ref(false)
  const exportError = ref('')
  const exportSuccess = ref('')

  const saveReportName = ref('')
  const isSaving = ref(false)
  const saveError = ref('')
  const saveSuccess = ref('')

  const giveawayYears = ref<{ year: string; is_active: boolean }[]>([])
  const yearsLoading = ref(false)

  async function fetchGiveawayYears() {
    yearsLoading.value = true
    try {
      const res = await fetch(`${API_BASE}/giveaway-years`)
      if (!res.ok) throw new Error()
      const data = await res.json()
      giveawayYears.value = data
      const active = data.find((y: { is_active: boolean }) => y.is_active)
      if (active && !config.giveaway_year) {
        config.giveaway_year = active.year
      } else if (data.length > 0 && !config.giveaway_year) {
        config.giveaway_year = data[0].year
      }
    } catch {
      // silent
    } finally {
      yearsLoading.value = false
    }
  }

  async function runReport() {
    if (!config.giveaway_year) return
    isLoading.value = true
    error.value = ''
    try {
      const body: Record<string, unknown> = {
        giveaway_year: config.giveaway_year,
        columns: config.columns,
        filters: config.filters,
        sort_order: config.sort_order,
        page: config.page,
        page_size: config.page_size,
      }
      if (config.group_by) body.group_by = config.group_by
      if (config.sort_by) body.sort_by = config.sort_by
      const res = await fetch(`${API_BASE}/reports/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!res.ok) throw new Error()
      result.value = await res.json()
    } catch {
      error.value = 'reports.errorLoading'
      result.value = null
    } finally {
      isLoading.value = false
    }
  }

  async function exportCsv() {
    if (!config.giveaway_year || config.columns.length === 0) return
    isExporting.value = true
    exportError.value = ''
    exportSuccess.value = ''
    try {
      const body: Record<string, unknown> = {
        giveaway_year: config.giveaway_year,
        columns: config.columns,
        filters: config.filters,
        sort_order: config.sort_order,
      }
      if (config.sort_by) body.sort_by = config.sort_by
      const res = await fetch(`${API_BASE}/reports/export`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!res.ok) throw new Error()
      const csv = await res.text()
      const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `report_${config.giveaway_year}.csv`
      link.style.display = 'none'
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      URL.revokeObjectURL(url)
      exportSuccess.value = 'reports.exportSuccess'
    } catch {
      exportError.value = 'reports.exportError'
    } finally {
      isExporting.value = false
    }
  }

  async function fetchSavedReports() {
    savedReportsLoading.value = true
    savedReportsError.value = ''
    try {
      const res = await fetch(`${API_BASE}/reports/saved`)
      if (!res.ok) throw new Error()
      const data = await res.json()
      savedReports.value = data.reports ?? []
    } catch {
      savedReportsError.value = 'reports.loadError'
    } finally {
      savedReportsLoading.value = false
    }
  }

  async function saveReport() {
    if (!saveReportName.value.trim()) return
    isSaving.value = true
    saveError.value = ''
    saveSuccess.value = ''
    try {
      const body = {
        name: saveReportName.value.trim(),
        columns: config.columns,
        filters: config.filters,
        group_by: config.group_by || null,
        sort_by: config.sort_by || null,
        sort_order: config.sort_order,
      }
      const res = await fetch(`${API_BASE}/reports/saved`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!res.ok) throw new Error()
      saveSuccess.value = 'reports.saveSuccess'
      saveReportName.value = ''
      await fetchSavedReports()
    } catch {
      saveError.value = 'reports.saveError'
    } finally {
      isSaving.value = false
    }
  }

  function loadSavedReport(report: SavedReport) {
    config.columns = [...report.columns]
    config.filters = report.filters ? report.filters.map((f) => ({ ...f })) : []
    config.group_by = report.group_by ?? ''
    config.sort_by = report.sort_by ?? ''
    config.sort_order = (report.sort_order as 'asc' | 'desc') || 'asc'
    config.page = 1
  }

  async function deleteSavedReport(reportId: string) {
    try {
      const res = await fetch(`${API_BASE}/reports/saved/${reportId}`, { method: 'DELETE' })
      if (!res.ok) throw new Error()
      await fetchSavedReports()
    } catch {
      // silent
    }
  }

  function loadTemplate(tpl: PreBuiltTemplate) {
    config.columns = [...tpl.columns]
    config.filters = tpl.filters.map((f) => ({ ...f }))
    config.group_by = tpl.group_by
    config.sort_by = tpl.sort_by
    config.sort_order = tpl.sort_order
    config.page = 1
  }

  function addFilter() {
    config.filters.push({ field: '', operator: 'equals', value: '' })
  }

  function removeFilter(index: number) {
    config.filters.splice(index, 1)
  }

  function toggleColumn(path: string) {
    const idx = config.columns.indexOf(path)
    if (idx === -1) {
      config.columns.push(path)
    } else {
      config.columns.splice(idx, 1)
    }
  }

  function setPage(p: number) {
    config.page = p
  }

  // Auto-run report when config changes (Req 11.13: real-time updates)
  const autoRunEnabled = ref(true)

  watch(
    () => [config.columns.length, config.filters.length, JSON.stringify(config.filters), config.group_by, config.sort_by, config.sort_order, config.giveaway_year, config.page, config.page_size],
    () => {
      if (autoRunEnabled.value && config.giveaway_year && config.columns.length > 0) {
        runReport()
      }
    },
  )

  return {
    config,
    result,
    isLoading,
    error,
    savedReports,
    savedReportsLoading,
    savedReportsError,
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
  }
}

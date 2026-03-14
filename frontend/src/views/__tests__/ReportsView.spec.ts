import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import ReportsView from '../ReportsView.vue'
import en from '../../locales/en.json'
import es from '../../locales/es.json'

function createTestI18n() {
  return createI18n({
    legacy: false,
    locale: 'en',
    messages: { en, es },
  })
}

const mockYears = [
  { year: '2025', is_active: true },
  { year: '2024', is_active: false },
]

const mockReportResult = {
  summary: {
    total_applications: 10,
    total_children: 15,
    applications_by_status: { needs_review: 3, auto_approved: 7 },
    applications_by_source_type: { digital: 6, upload: 4 },
  },
  rows: [
    { status: 'auto_approved', 'parent_guardian.last_name': 'Smith' },
    { status: 'needs_review', 'parent_guardian.last_name': 'Jones' },
  ],
  pagination: { page: 1, page_size: 50, total_count: 2, total_pages: 1 },
  giveaway_year: '2025',
  groups: { auto_approved: { count: 7 }, needs_review: { count: 3 } },
}

const mockSavedReports = {
  reports: [
    {
      user_id: 'u1',
      report_id: 'rpt-abc',
      name: 'My Report',
      columns: ['status'],
      filters: [],
      group_by: null,
      sort_by: null,
      sort_order: 'asc',
      created_at: '2025-01-01T00:00:00Z',
      updated_at: '2025-01-01T00:00:00Z',
    },
  ],
}

function setupFetchMock() {
  return vi.fn((url: string, opts?: RequestInit) => {
    const urlStr = typeof url === 'string' ? url : ''
    if (urlStr.includes('/giveaway-years')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(mockYears) } as Response)
    }
    if (urlStr.includes('/reports/saved') && (!opts || opts.method !== 'POST')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(mockSavedReports) } as Response)
    }
    if (urlStr.includes('/reports/run')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(mockReportResult) } as Response)
    }
    if (urlStr.includes('/reports/export')) {
      return Promise.resolve({ ok: true, text: () => Promise.resolve('col1,col2\nval1,val2') } as Response)
    }
    if (urlStr.includes('/reports/saved') && opts?.method === 'POST') {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ report_id: 'rpt-new' }) } as Response)
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({}) } as Response)
  })
}

function mountView() {
  return mount(ReportsView, {
    global: {
      plugins: [createTestI18n()],
    },
  })
}

describe('ReportsView', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    global.fetch = setupFetchMock() as unknown as typeof fetch
  })

  it('renders the reports title', async () => {
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.text()).toContain('Reports')
  })

  it('loads giveaway years on mount', async () => {
    mountView()
    await flushPromises()
    expect(global.fetch).toHaveBeenCalledWith(expect.stringContaining('/giveaway-years'))
  })

  it('loads saved reports on mount', async () => {
    const wrapper = mountView()
    await flushPromises()
    expect(global.fetch).toHaveBeenCalledWith(expect.stringContaining('/reports/saved'))
    expect(wrapper.text()).toContain('My Report')
  })

  it('renders pre-built template buttons', async () => {
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.text()).toContain('Height Distribution')
    expect(wrapper.text()).toContain('Applications by Referring Agency')
    expect(wrapper.text()).toContain('Applications by Zip Code')
    expect(wrapper.text()).toContain('Age Distribution')
    expect(wrapper.text()).toContain('Color Preferences')
    expect(wrapper.text()).toContain('Language Distribution')
    expect(wrapper.text()).toContain('Transportation Access Summary')
    expect(wrapper.text()).toContain('Review Status Summary')
  })

  it('loads a template and runs report when template clicked', async () => {
    const wrapper = mountView()
    await flushPromises()
    const templateBtns = wrapper.findAll('.reports-view__template-btn')
    // First template is Height Distribution
    await templateBtns[0].trigger('click')
    await flushPromises()
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/reports/run'),
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('displays column checkboxes for all available fields', async () => {
    const wrapper = mountView()
    await flushPromises()
    const checkboxes = wrapper.findAll('.reports-view__col-label')
    expect(checkboxes.length).toBeGreaterThan(10)
    expect(wrapper.text()).toContain('Status')
    expect(wrapper.text()).toContain('Agency Name')
    expect(wrapper.text()).toContain('Height (inches)')
  })

  it('adds and removes filters', async () => {
    const wrapper = mountView()
    await flushPromises()
    const addBtn = wrapper.find('.reports-view__btn--secondary')
    await addBtn.trigger('click')
    expect(wrapper.findAll('.reports-view__filter-row').length).toBe(1)
    const removeBtn = wrapper.find('.reports-view__filter-row .reports-view__delete-btn')
    await removeBtn.trigger('click')
    expect(wrapper.findAll('.reports-view__filter-row').length).toBe(0)
  })

  it('displays summary statistics after running a report', async () => {
    const wrapper = mountView()
    await flushPromises()
    // Click a template to trigger a report run
    const templateBtns = wrapper.findAll('.reports-view__template-btn')
    await templateBtns[0].trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('10')
    expect(wrapper.text()).toContain('15')
    expect(wrapper.text()).toContain('needs_review')
    expect(wrapper.text()).toContain('auto_approved')
  })

  it('renders bar chart for grouped data', async () => {
    const wrapper = mountView()
    await flushPromises()
    const templateBtns = wrapper.findAll('.reports-view__template-btn')
    await templateBtns[0].trigger('click')
    await flushPromises()
    expect(wrapper.find('.reports-view__bar-chart').exists()).toBe(true)
    expect(wrapper.findAll('.reports-view__bar-row').length).toBe(2)
  })

  it('switches to pie chart', async () => {
    const wrapper = mountView()
    await flushPromises()
    const templateBtns = wrapper.findAll('.reports-view__template-btn')
    await templateBtns[0].trigger('click')
    await flushPromises()
    const pieBtn = wrapper.findAll('.reports-view__chart-btn')[1]
    await pieBtn.trigger('click')
    expect(wrapper.find('.reports-view__pie-chart').exists()).toBe(true)
    expect(wrapper.find('.reports-view__pie-svg').exists()).toBe(true)
  })

  it('loads a saved report when clicked', async () => {
    const wrapper = mountView()
    await flushPromises()
    const savedBtns = wrapper.findAll('.reports-view__saved-item .reports-view__template-btn')
    expect(savedBtns.length).toBe(1)
    await savedBtns[0].trigger('click')
    await flushPromises()
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/reports/run'),
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('renders data table with correct columns', async () => {
    const wrapper = mountView()
    await flushPromises()
    const templateBtns = wrapper.findAll('.reports-view__template-btn')
    await templateBtns[0].trigger('click')
    await flushPromises()
    expect(wrapper.find('.reports-view__table').exists()).toBe(true)
    const headers = wrapper.findAll('.reports-view__table th')
    expect(headers.length).toBeGreaterThan(0)
  })
})

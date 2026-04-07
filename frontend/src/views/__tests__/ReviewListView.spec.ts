import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import ReviewListView from '../ReviewListView.vue'
import en from '../../locales/en.json'
import es from '../../locales/es.json'

// Mock vue-router
const mockPush = vi.fn()
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: mockPush }),
}))

function createTestI18n(locale = 'en') {
  return createI18n({
    legacy: false,
    locale,
    fallbackLocale: 'en',
    messages: { en, es },
  })
}

const MOCK_YEARS = [
  { year: '2025', is_active: true },
  { year: '2024', is_active: false },
]

const MOCK_APPLICATIONS = [
  {
    giveaway_year: '2025',
    application_id: 'app-001',
    reference_number: '2025-0001',
    submission_timestamp: '2025-11-15T10:30:00Z',
    source_type: 'upload',
    status: 'needs_review',
    overall_confidence_score: 0.72,
    parent_guardian: { first_name: 'Maria', last_name: 'Garcia' },
    referring_agency: { agency_name: 'Partner Org' },
    children: [{ drawing_image_s3_key: 'drawings/2025/app-001/child-001.png' }],
  },
  {
    giveaway_year: '2025',
    application_id: 'app-002',
    reference_number: '2025-0002',
    submission_timestamp: '2025-11-16T08:00:00Z',
    source_type: 'digital',
    status: 'auto_approved',
    overall_confidence_score: 0.95,
    parent_guardian: { first_name: 'John', last_name: 'Smith' },
    referring_agency: { agency_name: 'Agency B' },
    children: [],
  },
]

function mockFetchSuccess(years = MOCK_YEARS, apps = MOCK_APPLICATIONS) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation((url: string | URL | Request) => {
    const urlStr = typeof url === 'string' ? url : url.toString()
    if (urlStr.includes('giveaway-years')) {
      return Promise.resolve(new Response(JSON.stringify(years), { status: 200 }))
    }
    if (urlStr.includes('applications')) {
      return Promise.resolve(new Response(JSON.stringify(apps), { status: 200 }))
    }
    return Promise.resolve(new Response('{}', { status: 200 }))
  })
}

function mockFetchFailure() {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(() =>
    Promise.resolve(new Response('error', { status: 500 })),
  )
}

async function mountAndWait(locale = 'en', fetchSpy?: ReturnType<typeof vi.spyOn>) {
  if (!fetchSpy) mockFetchSuccess()
  const i18n = createTestI18n(locale)
  const wrapper = mount(ReviewListView, { global: { plugins: [i18n] } })
  await flushPromises()
  return wrapper
}

describe('ReviewListView', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    mockPush.mockReset()
  })

  // --- Req 5.1: Loading state ---

  it('renders loading state while fetching applications', async () => {
    // Resolve giveaway-years immediately, but hang on applications
    let resolveApps: (value: Response) => void
    vi.spyOn(globalThis, 'fetch').mockImplementation((url: string | URL | Request) => {
      const urlStr = typeof url === 'string' ? url : url.toString()
      if (urlStr.includes('giveaway-years')) {
        return Promise.resolve(new Response(JSON.stringify(MOCK_YEARS), { status: 200 }))
      }
      return new Promise((resolve) => { resolveApps = resolve })
    })
    const i18n = createTestI18n()
    const wrapper = mount(ReviewListView, { global: { plugins: [i18n] } })
    await flushPromises() // giveaway-years resolves, applications fetch starts

    expect(wrapper.find('.review-list-view__loading').exists()).toBe(true)

    // Clean up
    resolveApps!(new Response(JSON.stringify([]), { status: 200 }))
    await flushPromises()
  })

  // --- Req 5.1: Displays applications in table ---

  it('displays applications in table after fetch', async () => {
    const wrapper = await mountAndWait()

    const rows = wrapper.findAll('.review-list-view__row')
    expect(rows.length).toBe(2)
    // Default sort: submissionDate descending, so app-002 (Nov 16) comes first
    expect(rows[0].text()).toContain('Smith')
    expect(rows[1].text()).toContain('Garcia')
  })

  // --- Navigation uses simplified URL (no giveawayYear) ---

  it('navigates to detail with simplified URL (no giveawayYear)', async () => {
    const wrapper = await mountAndWait()

    const rows = wrapper.findAll('.review-list-view__row')
    await rows[0].trigger('click')

    // app-002 is first (sorted by date desc)
    expect(mockPush).toHaveBeenCalledWith('/admin/review/app-002')
  })

  // --- Displays reference_number in table ---

  it('displays reference_number in table rows', async () => {
    const wrapper = await mountAndWait()

    const rows = wrapper.findAll('.review-list-view__row')
    // app-002 is first (sorted by date desc)
    expect(rows[0].text()).toContain('2025-0002')
    expect(rows[1].text()).toContain('2025-0001')
  })

  // --- Req 5.2: Status filter dropdown ---

  it('shows status filter dropdown with all options', async () => {
    const wrapper = await mountAndWait()

    const statusSelect = wrapper.find('#status-filter')
    expect(statusSelect.exists()).toBe(true)

    const options = statusSelect.findAll('option')
    // "All Statuses" + 3 status options (no auto_approved)
    expect(options.length).toBe(4)
    expect(options[0].text()).toBe(en.review.allStatuses)
    expect(options[1].text()).toBe(en.review.statusNeedsReview)
    expect(options[2].text()).toBe(en.review.statusManuallyApproved)
    expect(options[3].text()).toBe(en.review.statusExtractionFailed)
  })

  // --- Req 5.3: Search input ---

  it('shows search input', async () => {
    const wrapper = await mountAndWait()

    const searchInput = wrapper.find('#search-input')
    expect(searchInput.exists()).toBe(true)
    expect(searchInput.attributes('placeholder')).toBe(en.review.searchPlaceholder)
  })

  // --- Giveaway year selector ---

  it('shows giveaway year selector with years', async () => {
    const wrapper = await mountAndWait()

    const yearSelect = wrapper.find('#year-select')
    expect(yearSelect.exists()).toBe(true)

    const options = yearSelect.findAll('option')
    expect(options.length).toBe(2)
    expect(options[0].text()).toContain('2025')
    expect(options[0].text()).toContain('★') // active year indicator
    expect(options[1].text()).toContain('2024')
  })

  // --- Req 5.9: ConfidenceBadge for each application ---

  it('displays ConfidenceBadge for each application', async () => {
    const wrapper = await mountAndWait()

    const badges = wrapper.findAll('.confidence-badge')
    expect(badges.length).toBe(2)
    // Default sort: submissionDate descending, so app-002 (95%) comes first
    expect(badges[0].text()).toBe('95%')
    expect(badges[1].text()).toBe('72%')
  })

  // --- Empty state ---

  it('shows empty state when no applications', async () => {
    vi.restoreAllMocks()
    const fetchSpy = mockFetchSuccess(MOCK_YEARS, [])
    const i18n = createTestI18n()
    const w = mount(ReviewListView, { global: { plugins: [i18n] } })
    await flushPromises()

    expect(w.find('.review-list-view__empty').exists()).toBe(true)
    expect(w.text()).toContain(en.review.noApplications)
    fetchSpy.mockRestore()
  })

  // --- Error state ---

  it('shows error state when fetch fails', async () => {
    mockFetchFailure()
    const i18n = createTestI18n()
    const wrapper = mount(ReviewListView, { global: { plugins: [i18n] } })
    await flushPromises()

    const errorEl = wrapper.find('.review-list-view__error')
    expect(errorEl.exists()).toBe(true)
  })

  // --- Export dropdown ---

  it('renders export dropdown trigger button', async () => {
    const wrapper = await mountAndWait()
    const trigger = wrapper.find('.export-drop__trigger')
    expect(trigger.exists()).toBe(true)
    expect(trigger.text()).toContain('Export')
  })

  it('opens export dropdown menu on click', async () => {
    const wrapper = await mountAndWait()
    expect(wrapper.find('.export-drop__menu').exists()).toBe(false)
    await wrapper.find('.export-drop__trigger').trigger('click')
    expect(wrapper.find('.export-drop__menu').exists()).toBe(true)
    const items = wrapper.findAll('.export-drop__item')
    expect(items.length).toBe(3)
  })
})

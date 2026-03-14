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

  // --- Req 5.2: Status filter dropdown ---

  it('shows status filter dropdown with all options', async () => {
    const wrapper = await mountAndWait()

    const statusSelect = wrapper.find('#status-filter')
    expect(statusSelect.exists()).toBe(true)

    const options = statusSelect.findAll('option')
    // "All Statuses" + 4 status options
    expect(options.length).toBe(5)
    expect(options[0].text()).toBe(en.review.allStatuses)
    expect(options[1].text()).toBe(en.review.statusNeedsReview)
    expect(options[2].text()).toBe(en.review.statusAutoApproved)
    expect(options[3].text()).toBe(en.review.statusManuallyApproved)
    expect(options[4].text()).toBe(en.review.statusExtractionFailed)
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
    mockFetchSuccess(MOCK_YEARS, [])
    const wrapper = await mountAndWait('en', vi.spyOn(globalThis, 'fetch'))

    // Re-mount with the empty mock already in place
    vi.restoreAllMocks()
    const fetchSpy = mockFetchSuccess(MOCK_YEARS, [])
    const i18n = createTestI18n()
    const w = mount(ReviewListView, { global: { plugins: [i18n] } })
    await flushPromises()

    expect(w.find('.review-list-view__empty').exists()).toBe(true)
    expect(w.text()).toContain(en.review.noApplications)
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

  // --- Req 6.1, 6.2: Export buttons ---

  it('renders export section with bike build and family contact export buttons', async () => {
    const wrapper = await mountAndWait()

    const exportSection = wrapper.find('.review-list-view__export-section')
    expect(exportSection.exists()).toBe(true)

    const buttons = exportSection.findAll('.review-list-view__export-btn')
    expect(buttons.length).toBe(2)
    expect(buttons[0].text()).toBe(en.review.exportBikeBuildList)
    expect(buttons[1].text()).toBe(en.review.exportFamilyContactList)
  })

  // --- Req 6.3: Export status filter checkboxes ---

  it('renders export status filter checkboxes for all statuses', async () => {
    const wrapper = await mountAndWait()

    const checkboxes = wrapper.findAll('.review-list-view__export-checkbox input[type="checkbox"]')
    expect(checkboxes.length).toBe(4)

    // When none selected, shows "All Statuses" hint
    expect(wrapper.find('.review-list-view__export-filter-hint').exists()).toBe(true)
    expect(wrapper.find('.review-list-view__export-filter-hint').text()).toBe(en.review.exportAllStatuses)
  })

  it('hides all-statuses hint when a status checkbox is checked', async () => {
    const wrapper = await mountAndWait()

    // Trigger change on the first checkbox — the component uses @change to toggle
    const checkboxes = wrapper.findAll('.review-list-view__export-checkbox input[type="checkbox"]')
    // Set the element's checked property then trigger change to simulate user click
    const el = checkboxes[0].element as HTMLInputElement
    el.checked = true
    await checkboxes[0].trigger('change')
    await flushPromises()

    expect(wrapper.find('.review-list-view__export-filter-hint').exists()).toBe(false)
  })

  // --- Req 6.4: Export triggers download via POST ---

  it('calls bike build list export endpoint with year and triggers download', async () => {
    const csvContent = 'first_name,last_name\nCarlos,Garcia'
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation((url: string | URL | Request) => {
      const urlStr = typeof url === 'string' ? url : url.toString()
      if (urlStr.includes('giveaway-years')) {
        return Promise.resolve(new Response(JSON.stringify(MOCK_YEARS), { status: 200 }))
      }
      if (urlStr.includes('applications')) {
        return Promise.resolve(new Response(JSON.stringify(MOCK_APPLICATIONS), { status: 200 }))
      }
      if (urlStr.includes('exports/bike-build-list')) {
        return Promise.resolve(new Response(csvContent, { status: 200, headers: { 'Content-Type': 'text/csv' } }))
      }
      return Promise.resolve(new Response('{}', { status: 200 }))
    })

    // Mock URL.createObjectURL and revokeObjectURL
    const mockUrl = 'blob:http://localhost/fake-blob'
    const createObjectURLSpy = vi.spyOn(URL, 'createObjectURL').mockReturnValue(mockUrl)
    const revokeObjectURLSpy = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})

    const wrapper = await mountAndWait('en', fetchSpy)

    const exportButtons = wrapper.findAll('.review-list-view__export-btn')
    await exportButtons[0].trigger('click')
    await flushPromises()

    // Verify the export endpoint was called with POST
    const exportCall = fetchSpy.mock.calls.find(
      (call) => typeof call[0] === 'string' && call[0].includes('exports/bike-build-list'),
    )
    expect(exportCall).toBeTruthy()
    const requestInit = exportCall![1] as RequestInit
    expect(requestInit.method).toBe('POST')
    const body = JSON.parse(requestInit.body as string)
    expect(body.giveaway_year).toBe('2025')

    // Verify blob download was triggered
    expect(createObjectURLSpy).toHaveBeenCalled()
    expect(revokeObjectURLSpy).toHaveBeenCalled()

    // Verify success message
    expect(wrapper.find('.review-list-view__export-success').exists()).toBe(true)

    createObjectURLSpy.mockRestore()
    revokeObjectURLSpy.mockRestore()
  })

  it('sends status_filter in export request when statuses are selected', async () => {
    const csvContent = 'first_name,last_name\nCarlos,Garcia'
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation((url: string | URL | Request) => {
      const urlStr = typeof url === 'string' ? url : url.toString()
      if (urlStr.includes('giveaway-years')) {
        return Promise.resolve(new Response(JSON.stringify(MOCK_YEARS), { status: 200 }))
      }
      if (urlStr.includes('applications')) {
        return Promise.resolve(new Response(JSON.stringify(MOCK_APPLICATIONS), { status: 200 }))
      }
      if (urlStr.includes('exports/family-contact-list')) {
        return Promise.resolve(new Response(csvContent, { status: 200, headers: { 'Content-Type': 'text/csv' } }))
      }
      return Promise.resolve(new Response('{}', { status: 200 }))
    })

    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:fake')
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})

    const wrapper = await mountAndWait('en', fetchSpy)

    // Check the first status checkbox (needs_review)
    const firstCheckbox = wrapper.find('.review-list-view__export-checkbox input[type="checkbox"]')
    await firstCheckbox.trigger('change')
    await flushPromises()

    // Click family contact list export
    const exportButtons = wrapper.findAll('.review-list-view__export-btn')
    await exportButtons[1].trigger('click')
    await flushPromises()

    const exportCall = fetchSpy.mock.calls.find(
      (call) => typeof call[0] === 'string' && call[0].includes('exports/family-contact-list'),
    )
    expect(exportCall).toBeTruthy()
    const body = JSON.parse((exportCall![1] as RequestInit).body as string)
    expect(body.status_filter).toEqual(['needs_review'])
  })

  it('shows export error when export endpoint fails', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation((url: string | URL | Request) => {
      const urlStr = typeof url === 'string' ? url : url.toString()
      if (urlStr.includes('giveaway-years')) {
        return Promise.resolve(new Response(JSON.stringify(MOCK_YEARS), { status: 200 }))
      }
      if (urlStr.includes('applications')) {
        return Promise.resolve(new Response(JSON.stringify(MOCK_APPLICATIONS), { status: 200 }))
      }
      if (urlStr.includes('exports/')) {
        return Promise.resolve(new Response('error', { status: 500 }))
      }
      return Promise.resolve(new Response('{}', { status: 200 }))
    })

    const wrapper = await mountAndWait('en', fetchSpy)

    const exportButtons = wrapper.findAll('.review-list-view__export-btn')
    await exportButtons[0].trigger('click')
    await flushPromises()

    expect(wrapper.find('.review-list-view__export-error').exists()).toBe(true)
    expect(wrapper.find('.review-list-view__export-error').text()).toBe(en.review.exportError)
  })
})

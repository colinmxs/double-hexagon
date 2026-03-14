import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import ReviewDetailView from '../ReviewDetailView.vue'
import en from '../../locales/en.json'
import es from '../../locales/es.json'

// Mock vue-router
const mockPush = vi.fn()
vi.mock('vue-router', () => ({
  useRoute: () => ({
    params: { giveawayYear: '2025', applicationId: 'app-001' },
  }),
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

const MOCK_APPLICATION = {
  giveaway_year: '2025',
  application_id: 'app-001',
  submission_timestamp: '2025-11-15T10:30:00Z',
  source_type: 'upload' as const,
  status: 'needs_review',
  overall_confidence_score: 0.72,
  referring_agency: {
    agency_name: 'Partner Org',
    contact_name: 'Jane Doe',
    contact_phone: '208-555-0100',
    contact_email: 'jane@partner.org',
  },
  parent_guardian: {
    first_name: 'Maria',
    last_name: 'Garcia',
    address: '123 Main St',
    city: 'Boise',
    zip_code: '83702',
    phone: '208-555-0101',
    email: 'maria@example.com',
    primary_language: 'Spanish',
    english_speaker_in_household: false,
    preferred_contact_method: 'WhatsApp',
    transportation_access: true,
  },
  children: [
    {
      child_id: 'child-001',
      first_name: 'Carlos',
      last_name: 'Garcia',
      height_inches: 48,
      age: 8,
      gender: 'Male',
      bike_color_1: 'Blue',
      bike_color_2: 'Black',
      knows_how_to_ride: true,
      other_siblings_enrolled: 'Sofia Garcia',
      drawing_image_s3_key: 'drawings/2025/app-001/child-001.png',
      drawing_keywords: ['blue', 'mountain bike', 'streamers'],
      dream_bike_description: 'A blue mountain bike with streamers',
      bike_number: '',
    },
  ],
  field_confidence: {
    'referring_agency.agency_name': 0.95,
    'referring_agency.contact_name': 0.88,
    'referring_agency.contact_phone': 0.72,
    'referring_agency.contact_email': 0.91,
    'parent_guardian.first_name': 0.93,
    'parent_guardian.last_name': 0.60,
    'parent_guardian.address': 0.85,
    'parent_guardian.city': 0.90,
    'parent_guardian.zip_code': 0.88,
    'parent_guardian.phone': 0.75,
    'parent_guardian.email': 0.92,
    'parent_guardian.primary_language': 0.80,
    'parent_guardian.preferred_contact_method': 0.65,
    'children[0].first_name': 0.90,
    'children[0].last_name': 0.85,
    'children[0].height_inches': 0.78,
    'children[0].age': 0.92,
    'children[0].gender': 0.82,
    'children[0].drawing_keywords': 0.70,
    'children[0].dream_bike_description': 0.75,
  },
  original_documents: [
    {
      s3_key: 'uploads/2025/app-001/page1.pdf',
      upload_timestamp: '2025-11-15T10:29:00Z',
      page_count: 2,
      presigned_url: 'https://s3.example.com/doc1',
    },
  ],
}

function mockFetchDetail(appData = MOCK_APPLICATION) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation((url: string | URL | Request) => {
    const urlStr = typeof url === 'string' ? url : url.toString()
    if (urlStr.includes('applications/')) {
      return Promise.resolve(new Response(JSON.stringify(appData), { status: 200 }))
    }
    return Promise.resolve(new Response('{}', { status: 200 }))
  })
}

function mockFetchDetailFailure() {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(() =>
    Promise.resolve(new Response('error', { status: 500 })),
  )
}

async function mountAndWait(locale = 'en') {
  const i18n = createTestI18n(locale)
  const wrapper = mount(ReviewDetailView, { global: { plugins: [i18n] } })
  await flushPromises()
  return wrapper
}

describe('ReviewDetailView', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    mockPush.mockReset()
  })

  // --- Loading state ---

  it('shows loading state initially', () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(() => new Promise(() => {}))
    const i18n = createTestI18n()
    const wrapper = mount(ReviewDetailView, { global: { plugins: [i18n] } })

    expect(wrapper.find('.review-detail__loading').exists()).toBe(true)
    expect(wrapper.text()).toContain(en.reviewDetail.loading)
  })

  // --- Req 5.4: Displays application data ---

  it('displays application data after fetch', async () => {
    mockFetchDetail()
    const wrapper = await mountAndWait()

    // Agency fields
    const agencyNameInput = wrapper.find('#field-referring_agency\\.agency_name')
    expect((agencyNameInput.element as HTMLInputElement).value).toBe('Partner Org')

    // Parent fields
    const parentFirstName = wrapper.find('#field-parent_guardian\\.first_name')
    expect((parentFirstName.element as HTMLInputElement).value).toBe('Maria')

    // Child fields
    const childFirstName = wrapper.find('[id="field-children[0].first_name"]')
    expect((childFirstName.element as HTMLInputElement).value).toBe('Carlos')
  })

  // --- Req 5.6: Per-field ConfidenceBadge ---

  it('shows per-field ConfidenceBadge', async () => {
    mockFetchDetail()
    const wrapper = await mountAndWait()

    const badges = wrapper.findAll('.confidence-badge')
    // Should have many badges (one per field)
    expect(badges.length).toBeGreaterThan(5)

    // Check a specific badge value - agency_name has 0.95 confidence
    const agencyField = wrapper.find('#field-referring_agency\\.agency_name')
    const fieldDiv = agencyField.element.closest('.review-detail__field')
    const badge = fieldDiv?.querySelector('.confidence-badge')
    expect(badge?.textContent).toBe('95%')
  })

  // --- Req 5.9: Low-confidence field highlighting ---

  it('highlights low-confidence fields with review-detail__field--low class', async () => {
    mockFetchDetail()
    const wrapper = await mountAndWait()

    const lowFields = wrapper.findAll('.review-detail__field--low')
    expect(lowFields.length).toBeGreaterThan(0)

    // parent_guardian.last_name has 0.60 confidence - should be low
    const lastNameInput = wrapper.find('#field-parent_guardian\\.last_name')
    const lastNameField = lastNameInput.element.closest('.review-detail__field')
    expect(lastNameField?.classList.contains('review-detail__field--low')).toBe(true)

    // referring_agency.agency_name has 0.95 - should NOT be low
    const agencyInput = wrapper.find('#field-referring_agency\\.agency_name')
    const agencyField = agencyInput.element.closest('.review-detail__field')
    expect(agencyField?.classList.contains('review-detail__field--low')).toBe(false)
  })

  // --- Req 5.7: Confidence resets to 1.0 on edit ---

  it('resets confidence to 1.0 when field is edited', async () => {
    mockFetchDetail()
    const wrapper = await mountAndWait()

    // parent_guardian.last_name starts at 0.60 (low)
    const lastNameInput = wrapper.find('#field-parent_guardian\\.last_name')
    const lastNameField = lastNameInput.element.closest('.review-detail__field')
    expect(lastNameField?.classList.contains('review-detail__field--low')).toBe(true)

    // Edit the field
    await lastNameInput.setValue('Garcia-Updated')

    // After edit, confidence should be 1.0 → no longer low
    expect(lastNameField?.classList.contains('review-detail__field--low')).toBe(false)

    // The badge should now show 100%
    const badge = lastNameField?.querySelector('.confidence-badge')
    expect(badge?.textContent).toBe('100%')
  })

  // --- Save and approve buttons ---

  it('shows save and approve buttons', async () => {
    mockFetchDetail()
    const wrapper = await mountAndWait()

    const saveBtn = wrapper.find('.review-detail__btn--save')
    const approveBtn = wrapper.find('.review-detail__btn--approve')
    expect(saveBtn.exists()).toBe(true)
    expect(approveBtn.exists()).toBe(true)
    expect(saveBtn.text()).toBe(en.reviewDetail.saveChanges)
    expect(approveBtn.text()).toBe(en.reviewDetail.approve)
  })

  // --- Save button disabled when no edits ---

  it('save button is disabled when no edits have been made', async () => {
    mockFetchDetail()
    const wrapper = await mountAndWait()

    const saveBtn = wrapper.find('.review-detail__btn--save')
    expect((saveBtn.element as HTMLButtonElement).disabled).toBe(true)
  })

  it('save button is enabled after editing a field', async () => {
    mockFetchDetail()
    const wrapper = await mountAndWait()

    const input = wrapper.find('#field-referring_agency\\.agency_name')
    await input.setValue('New Agency Name')

    const saveBtn = wrapper.find('.review-detail__btn--save')
    expect((saveBtn.element as HTMLButtonElement).disabled).toBe(false)
  })

  // --- Error state ---

  it('shows error when fetch fails', async () => {
    mockFetchDetailFailure()
    const wrapper = await mountAndWait()

    const errorEl = wrapper.find('.review-detail__error')
    expect(errorEl.exists()).toBe(true)
    expect(errorEl.text()).toContain(en.reviewDetail.errorLoading)
  })

  // --- Req 5.10: Drawing keywords for children ---

  it('displays drawing keywords for children', async () => {
    mockFetchDetail()
    const wrapper = await mountAndWait()

    const keywordsInput = wrapper.find('#field-keywords-0')
    expect(keywordsInput.exists()).toBe(true)
    expect((keywordsInput.element as HTMLInputElement).value).toBe('blue, mountain bike, streamers')
  })

  // --- Req 5.11: Bike number field ---

  it('shows bike number field for children', async () => {
    mockFetchDetail()
    const wrapper = await mountAndWait()

    const bikeNumberInput = wrapper.find('#field-bike-0')
    expect(bikeNumberInput.exists()).toBe(true)
  })
})

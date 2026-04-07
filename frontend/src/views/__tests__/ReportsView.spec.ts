import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import ReportsView from '../ReportsView.vue'

const MOCK_YEARS = [
  { year: '2026', is_active: true },
  { year: '2025', is_active: false },
]

const MOCK_SUMMARY = {
  summary: {
    total_applications: 100,
    total_children: 150,
    applications_by_status: { needs_review: 40, manually_approved: 50, rejected: 10 },
    applications_by_source_type: { digital: 60, upload: 40 },
  },
}

const MOCK_COST = {
  total_cost: 50.0,
  cost_per_application: 0.5,
  service_breakdown: { S3: 5.0, Lambda: 10.0, DynamoDB: 15.0, Textract: 20.0 },
}

function mockFetch() {
  return vi.spyOn(globalThis, 'fetch').mockImplementation((url: string | URL | Request) => {
    const urlStr = typeof url === 'string' ? url : url.toString()
    if (urlStr.includes('giveaway-years')) {
      return Promise.resolve(new Response(JSON.stringify(MOCK_YEARS), { status: 200 }))
    }
    if (urlStr.includes('reports/run')) {
      return Promise.resolve(new Response(JSON.stringify(MOCK_SUMMARY), { status: 200 }))
    }
    if (urlStr.includes('cost-dashboard')) {
      return Promise.resolve(new Response(JSON.stringify(MOCK_COST), { status: 200 }))
    }
    return Promise.resolve(new Response('{}', { status: 200 }))
  })
}

describe('ReportsView', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('renders the year banner with active year', async () => {
    mockFetch()
    const wrapper = mount(ReportsView)
    await flushPromises()
    expect(wrapper.find('.rpt__banner').text()).toContain('2026')
  })

  it('loads giveaway years on mount', async () => {
    const spy = mockFetch()
    mount(ReportsView)
    await flushPromises()
    const yearCall = spy.mock.calls.find(
      (c) => typeof c[0] === 'string' && c[0].includes('giveaway-years'),
    )
    expect(yearCall).toBeTruthy()
  })

  it('displays summary stats after data loads', async () => {
    mockFetch()
    const wrapper = mount(ReportsView)
    await flushPromises()
    expect(wrapper.text()).toContain('100')
    expect(wrapper.text()).toContain('$50.00')
  })

  it('renders year selector with options', async () => {
    mockFetch()
    const wrapper = mount(ReportsView)
    await flushPromises()
    const options = wrapper.findAll('.rpt__year-select option')
    expect(options.length).toBe(2)
    expect(options[0].text()).toContain('2026')
  })

  it('renders export dropdown trigger', async () => {
    mockFetch()
    const wrapper = mount(ReportsView)
    await flushPromises()
    const trigger = wrapper.find('.export-drop__trigger')
    expect(trigger.exists()).toBe(true)
  })
})

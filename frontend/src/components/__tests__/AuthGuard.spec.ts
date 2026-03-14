import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import AuthGuard from '../AuthGuard.vue'

const messages = {
  en: {
    auth: {
      loginRequired: 'You must be logged in to access this page.',
      forbidden: 'You do not have permission to access this page.',
      loginRedirect: 'Redirecting to login...',
    },
  },
}

// Mock the useAuth composable
const mockAuthEnabled = { value: true }
const mockIsAuthenticated = { value: false }
const mockUser = { value: null as { role: string } | null }

vi.mock('../../composables/useAuth', () => ({
  useAuth: () => ({
    authEnabled: mockAuthEnabled.value,
    isAuthenticated: mockIsAuthenticated,
    user: mockUser,
  }),
}))

function mountGuard(requiredRole?: string) {
  const i18n = createI18n({ legacy: false, locale: 'en', messages })
  return mount(AuthGuard, {
    props: requiredRole ? { requiredRole } : {},
    global: { plugins: [i18n] },
    slots: { default: '<div class="protected-content">Protected</div>' },
  })
}

describe('AuthGuard', () => {
  beforeEach(() => {
    mockAuthEnabled.value = true
    mockIsAuthenticated.value = false
    mockUser.value = null
  })

  it('renders slot content when AUTH_ENABLED=false', () => {
    mockAuthEnabled.value = false
    const wrapper = mountGuard('admin')
    expect(wrapper.find('.protected-content').exists()).toBe(true)
    expect(wrapper.text()).toContain('Protected')
  })

  it('shows login message when not authenticated', () => {
    mockAuthEnabled.value = true
    mockIsAuthenticated.value = false
    const wrapper = mountGuard()
    expect(wrapper.text()).toContain('You must be logged in to access this page.')
    expect(wrapper.find('.protected-content').exists()).toBe(false)
  })

  it('shows forbidden when authenticated with wrong role', () => {
    mockAuthEnabled.value = true
    mockIsAuthenticated.value = true
    mockUser.value = { role: 'reporter' }
    const wrapper = mountGuard('admin')
    // reporter cannot access admin-only routes (only admin role can)
    // But the component logic: admin always passes, otherwise role must match
    // reporter !== admin, so forbidden
    expect(wrapper.text()).toContain('You do not have permission to access this page.')
    expect(wrapper.find('.protected-content').exists()).toBe(false)
  })

  it('renders slot when authenticated with correct role', () => {
    mockAuthEnabled.value = true
    mockIsAuthenticated.value = true
    mockUser.value = { role: 'admin' }
    const wrapper = mountGuard('admin')
    expect(wrapper.find('.protected-content').exists()).toBe(true)
  })
})

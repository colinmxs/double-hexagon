import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { nextTick } from 'vue'
import SessionTimeout from '../SessionTimeout.vue'

const messages = {
  en: {
    session: {
      warningTitle: 'Session Expiring',
      warningMessage: 'Your session will expire in {minutes} minutes due to inactivity.',
      stayLoggedIn: 'Stay Logged In',
    },
  },
}

function mountTimeout() {
  const i18n = createI18n({ legacy: false, locale: 'en', messages })
  return mount(SessionTimeout, {
    global: { plugins: [i18n] },
    attachTo: document.body,
  })
}

describe('SessionTimeout', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
    // Clean up any teleported content
    document.body.innerHTML = ''
  })

  it('does not show warning initially', () => {
    const wrapper = mountTimeout()
    expect(wrapper.find('.session-timeout-overlay').exists()).toBe(false)
    wrapper.unmount()
  })

  it('shows warning before timeout (at 25 minutes)', async () => {
    const wrapper = mountTimeout()

    // Advance to 25 minutes (warning appears at 30 - 5 = 25 min)
    vi.advanceTimersByTime(25 * 60 * 1000)
    await nextTick()

    // Teleported content is in document.body
    const overlay = document.body.querySelector('.session-timeout-overlay')
    expect(overlay).toBeTruthy()
    expect(overlay!.querySelector('.session-timeout-dialog__title')?.textContent).toBe('Session Expiring')
    wrapper.unmount()
  })

  it('emits timeout event after 30 minutes of inactivity', async () => {
    const wrapper = mountTimeout()

    vi.advanceTimersByTime(30 * 60 * 1000)
    await nextTick()

    expect(wrapper.emitted('timeout')).toBeTruthy()
    expect(wrapper.emitted('timeout')!.length).toBe(1)
    wrapper.unmount()
  })

  it('dismissWarning resets timer (clicking Stay Logged In)', async () => {
    const wrapper = mountTimeout()

    // Advance to warning phase
    vi.advanceTimersByTime(25 * 60 * 1000)
    await nextTick()

    const overlay = document.body.querySelector('.session-timeout-overlay')
    expect(overlay).toBeTruthy()

    // Click "Stay Logged In" button
    const btn = document.body.querySelector('.session-timeout-dialog__btn') as HTMLButtonElement
    btn.click()
    await nextTick()

    // Warning should be dismissed
    expect(document.body.querySelector('.session-timeout-overlay')).toBeFalsy()

    // Should not timeout after another 5 minutes (timer was reset)
    vi.advanceTimersByTime(5 * 60 * 1000)
    await nextTick()
    expect(wrapper.emitted('timeout')).toBeFalsy()

    wrapper.unmount()
  })
})

import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import LanguageToggle from '../LanguageToggle.vue'

function createTestI18n(locale = 'en') {
  return createI18n({
    legacy: false,
    locale,
    fallbackLocale: 'en',
    messages: { en: {}, es: {} },
  })
}

describe('LanguageToggle', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('shows ¿Español? when locale is English', () => {
    const i18n = createTestI18n('en')
    const wrapper = mount(LanguageToggle, { global: { plugins: [i18n] } })
    expect(wrapper.find('button').text()).toBe('¿Español?')
  })

  it('shows English? when locale is Spanish', () => {
    const i18n = createTestI18n('es')
    const wrapper = mount(LanguageToggle, { global: { plugins: [i18n] } })
    expect(wrapper.find('button').text()).toBe('English?')
  })

  it('clicking toggles locale from en to es', async () => {
    const i18n = createTestI18n('en')
    const wrapper = mount(LanguageToggle, { global: { plugins: [i18n] } })

    await wrapper.find('button').trigger('click')

    expect(i18n.global.locale.value).toBe('es')
    expect(wrapper.find('button').text()).toBe('English?')
  })

  it('persists locale to localStorage', async () => {
    const i18n = createTestI18n('en')
    const wrapper = mount(LanguageToggle, { global: { plugins: [i18n] } })

    await wrapper.find('button').trigger('click')

    expect(localStorage.getItem('locale')).toBe('es')
  })
})

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

  it('renders EN and ES buttons', () => {
    const i18n = createTestI18n()
    const wrapper = mount(LanguageToggle, { global: { plugins: [i18n] } })
    const buttons = wrapper.findAll('button')
    expect(buttons).toHaveLength(2)
    expect(buttons[0].text()).toBe('EN')
    expect(buttons[1].text()).toBe('ES')
  })

  it('marks the active locale button with active class', () => {
    const i18n = createTestI18n('en')
    const wrapper = mount(LanguageToggle, { global: { plugins: [i18n] } })
    const buttons = wrapper.findAll('button')
    expect(buttons[0].classes()).toContain('language-toggle__btn--active')
    expect(buttons[1].classes()).not.toContain('language-toggle__btn--active')
  })

  it('clicking ES button changes locale without page reload', async () => {
    const i18n = createTestI18n('en')
    const wrapper = mount(LanguageToggle, { global: { plugins: [i18n] } })

    await wrapper.findAll('button')[1].trigger('click')

    expect(i18n.global.locale.value).toBe('es')
    // Active class should now be on ES button
    expect(wrapper.findAll('button')[1].classes()).toContain('language-toggle__btn--active')
    expect(wrapper.findAll('button')[0].classes()).not.toContain('language-toggle__btn--active')
  })

  it('persists locale to localStorage', async () => {
    const i18n = createTestI18n('en')
    const wrapper = mount(LanguageToggle, { global: { plugins: [i18n] } })

    await wrapper.findAll('button')[1].trigger('click')

    expect(localStorage.getItem('locale')).toBe('es')
  })
})

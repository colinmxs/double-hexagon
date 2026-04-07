import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import ConfidenceBadge from '../ConfidenceBadge.vue'

const messages = {
  en: {
    confidence: {
      high: 'High confidence: {score}',
      medium: 'Medium confidence: {score}',
      low: 'Low confidence: {score}',
    },
  },
}

function mountBadge(score: number, threshold?: number) {
  const i18n = createI18n({ legacy: false, locale: 'en', messages })
  return mount(ConfidenceBadge, {
    props: { score, ...(threshold !== undefined ? { threshold } : {}) },
    global: { plugins: [i18n] },
  })
}

describe('ConfidenceBadge', () => {
  it('displays score as percentage', () => {
    const wrapper = mountBadge(0.85)
    expect(wrapper.text()).toBe('85%')
  })

  it('applies green (high) class when score >= threshold (0.80)', () => {
    const wrapper = mountBadge(0.80)
    expect(wrapper.find('.confidence-badge--high').exists()).toBe(true)
  })

  it('applies yellow (medium) class when score is near threshold (0.65–0.79)', () => {
    const wrapper = mountBadge(0.70)
    expect(wrapper.find('.confidence-badge--medium').exists()).toBe(true)
  })

  it('applies red (low) class when score < threshold - 0.15 (below 0.65)', () => {
    const wrapper = mountBadge(0.50)
    expect(wrapper.find('.confidence-badge--low').exists()).toBe(true)
  })

  it('respects custom threshold prop', () => {
    // With threshold 0.90, score 0.85 should be medium (>= 0.90 - 0.15 = 0.75)
    const wrapper = mountBadge(0.85, 0.90)
    expect(wrapper.find('.confidence-badge--medium').exists()).toBe(true)

    // With threshold 0.90, score 0.92 should be high
    const wrapper2 = mountBadge(0.92, 0.90)
    expect(wrapper2.find('.confidence-badge--high').exists()).toBe(true)

    // With threshold 0.90, score 0.60 should be low (< 0.90 - 0.15 = 0.75)
    const wrapper3 = mountBadge(0.60, 0.90)
    expect(wrapper3.find('.confidence-badge--low').exists()).toBe(true)
  })
})

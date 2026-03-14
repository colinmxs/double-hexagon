import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import DrawingViewer from '../DrawingViewer.vue'

const messages = {
  en: { drawing: { noKeywords: 'No keywords' } },
}

function mountViewer(props: { imageUrl: string; keywords: string[]; altText?: string }) {
  const i18n = createI18n({ legacy: false, locale: 'en', messages })
  return mount(DrawingViewer, { props, global: { plugins: [i18n] } })
}

describe('DrawingViewer', () => {
  it('renders image with correct src', () => {
    const wrapper = mountViewer({
      imageUrl: 'https://example.com/drawing.png',
      keywords: ['blue', 'mountain bike'],
    })
    const img = wrapper.find('img')
    expect(img.exists()).toBe(true)
    expect(img.attributes('src')).toBe('https://example.com/drawing.png')
  })

  it('renders keyword chips', () => {
    const wrapper = mountViewer({
      imageUrl: 'https://example.com/drawing.png',
      keywords: ['blue', 'mountain bike', 'streamers'],
    })
    const chips = wrapper.findAll('.drawing-viewer__chip')
    expect(chips).toHaveLength(3)
    expect(chips[0].text()).toBe('blue')
    expect(chips[1].text()).toBe('mountain bike')
    expect(chips[2].text()).toBe('streamers')
  })

  it('renders no chips when keywords empty', () => {
    const wrapper = mountViewer({
      imageUrl: 'https://example.com/drawing.png',
      keywords: [],
    })
    expect(wrapper.findAll('.drawing-viewer__chip')).toHaveLength(0)
    expect(wrapper.find('.drawing-viewer__keywords').exists()).toBe(false)
  })
})

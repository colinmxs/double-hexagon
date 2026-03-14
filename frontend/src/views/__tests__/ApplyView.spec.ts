import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, VueWrapper } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import ApplyView from '../ApplyView.vue'
import en from '../../locales/en.json'
import es from '../../locales/es.json'

function createTestI18n(locale = 'en') {
  return createI18n({
    legacy: false,
    locale,
    fallbackLocale: 'en',
    messages: { en, es },
  })
}

function mountApplyView(locale = 'en') {
  const i18n = createTestI18n(locale)
  return mount(ApplyView, {
    global: { plugins: [i18n] },
  })
}

/** Fill all required fields so the form passes validation */
async function fillRequiredFields(wrapper: VueWrapper) {
  // Agency
  await wrapper.find('#agency-name').setValue('Test Agency')
  await wrapper.find('#agency-contact-name').setValue('Jane Doe')
  await wrapper.find('#agency-contact-phone').setValue('208-555-0100')
  await wrapper.find('#agency-contact-email').setValue('jane@agency.org')

  // Parent
  await wrapper.find('#parent-first-name').setValue('Maria')
  await wrapper.find('#parent-last-name').setValue('Garcia')
  await wrapper.find('#parent-address').setValue('123 Main St')
  await wrapper.find('#parent-city').setValue('Boise')
  await wrapper.find('#parent-zip').setValue('83702')
  await wrapper.find('#parent-phone').setValue('208-555-0101')
  await wrapper.find('#parent-email').setValue('maria@example.com')
  await wrapper.find('#parent-language').setValue('Spanish')

  // Radio buttons
  const radios = wrapper.findAll('input[type="radio"]')
  // englishSpeaker yes
  await radios.find(r => r.attributes('name') === 'englishSpeaker' && r.attributes('value') === 'yes')!.setValue(true)
  // transportationAccess yes
  await radios.find(r => r.attributes('name') === 'transportationAccess' && r.attributes('value') === 'yes')!.setValue(true)

  // Preferred contact
  await wrapper.find('#parent-preferred-contact').setValue('WhatsApp')

  // Child 0
  await wrapper.find('#child-0-first-name').setValue('Carlos')
  await wrapper.find('#child-0-last-name').setValue('Garcia')
  await wrapper.find('#child-0-height').setValue('48')
  await wrapper.find('#child-0-age').setValue('8')
  await wrapper.find('#child-0-gender').setValue('Male')
  await wrapper.find('#child-0-color1').setValue('Blue')
  await wrapper.find('#child-0-color2').setValue('Black')
  const childRide = radios.find(r => r.attributes('name') === 'knowsHowToRide_0' && r.attributes('value') === 'yes')!
  await childRide.setValue(true)
}

describe('ApplyView', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  // ─── Required field validation (Req 1.3) ───

  describe('required field validation', () => {
    it('shows error messages when submitting an empty form', async () => {
      const wrapper = mountApplyView()
      await wrapper.find('form').trigger('submit')

      const errorSpans = wrapper.findAll('.form-error')
      expect(errorSpans.length).toBeGreaterThan(0)

      // Validation summary should appear
      const alerts = wrapper.findAll('[role="alert"]')
      const summaryAlert = alerts.find(a => a.text().includes(en.apply.validationErrors))
      expect(summaryAlert).toBeTruthy()
    })

    it('shows required error for agency name when empty', async () => {
      const wrapper = mountApplyView()
      await wrapper.find('form').trigger('submit')

      const agencyInput = wrapper.find('#agency-name')
      expect(agencyInput.attributes('aria-invalid')).toBe('true')
    })

    it('shows required error for parent first name when empty', async () => {
      const wrapper = mountApplyView()
      await wrapper.find('form').trigger('submit')

      const input = wrapper.find('#parent-first-name')
      expect(input.attributes('aria-invalid')).toBe('true')
    })

    it('shows required error for child first name when empty', async () => {
      const wrapper = mountApplyView()
      await wrapper.find('form').trigger('submit')

      const input = wrapper.find('#child-0-first-name')
      expect(input.attributes('aria-invalid')).toBe('true')
    })

    it('validates email format for agency contact email', async () => {
      const wrapper = mountApplyView()
      await wrapper.find('#agency-contact-email').setValue('not-an-email')
      await wrapper.find('form').trigger('submit')

      const errorSpans = wrapper.findAll('.form-error')
      const emailError = errorSpans.find(s => s.text() === en.form.invalidEmail)
      expect(emailError).toBeTruthy()
    })

    it('no errors when all required fields are filled', async () => {
      const wrapper = mountApplyView()
      await fillRequiredFields(wrapper)
      // Mock fetch for submission
      vi.spyOn(globalThis, 'fetch').mockResolvedValue(
        new Response(JSON.stringify({ application_id: 'TEST-123' }), { status: 200 })
      )
      await wrapper.find('form').trigger('submit')

      const errorSpans = wrapper.findAll('.form-error')
      expect(errorSpans.length).toBe(0)
    })
  })

  // ─── Multi-child add/remove (Req 1.2) ───

  describe('multi-child add/remove', () => {
    it('starts with one child entry', () => {
      const wrapper = mountApplyView()
      const childEntries = wrapper.findAll('.child-entry')
      expect(childEntries.length).toBe(1)
    })

    it('adds a second child when clicking Add Another Child', async () => {
      const wrapper = mountApplyView()
      const addBtn = wrapper.findAll('button').find(b => b.text().includes(en.apply.addChild))!
      await addBtn.trigger('click')

      const childEntries = wrapper.findAll('.child-entry')
      expect(childEntries.length).toBe(2)
      // Second child fields should exist
      expect(wrapper.find('#child-1-first-name').exists()).toBe(true)
    })

    it('removes a child when clicking Remove Child', async () => {
      const wrapper = mountApplyView()
      // Add a second child first
      const addBtn = wrapper.findAll('button').find(b => b.text().includes(en.apply.addChild))!
      await addBtn.trigger('click')
      expect(wrapper.findAll('.child-entry').length).toBe(2)

      // Remove the second child
      const removeBtn = wrapper.findAll('button').find(b => b.text().includes(en.apply.removeChild))!
      await removeBtn.trigger('click')
      expect(wrapper.findAll('.child-entry').length).toBe(1)
    })

    it('does not show remove button when only one child exists', () => {
      const wrapper = mountApplyView()
      const removeBtn = wrapper.findAll('button').find(b => b.text().includes(en.apply.removeChild))
      expect(removeBtn).toBeUndefined()
    })
  })

  // ─── Responsive rendering (Req 1.5) ───

  describe('responsive rendering', () => {
    it('has responsive CSS classes for layout', () => {
      const wrapper = mountApplyView()
      expect(wrapper.find('.apply-view').exists()).toBe(true)
      expect(wrapper.find('.apply-form').exists()).toBe(true)
      expect(wrapper.findAll('.form-row').length).toBeGreaterThan(0)
    })

    it('renders form sections with proper structure', () => {
      const wrapper = mountApplyView()
      const fieldsets = wrapper.findAll('fieldset')
      expect(fieldsets.length).toBe(3) // Agency, Parent, Children
    })
  })

  // ─── Bilingual labels (Req 1.6, 1.7) ───

  describe('bilingual labels', () => {
    it('renders English labels when locale is en', () => {
      const wrapper = mountApplyView('en')
      expect(wrapper.find('h1').text()).toBe(en.apply.title)
      expect(wrapper.find('legend').text()).toBe(en.apply.sectionAgency)
    })

    it('renders Spanish labels when locale is es', () => {
      const wrapper = mountApplyView('es')
      expect(wrapper.find('h1').text()).toBe(es.apply.title)
      expect(wrapper.find('legend').text()).toBe(es.apply.sectionAgency)
    })

    it('shows Spanish validation messages when locale is es', async () => {
      const wrapper = mountApplyView('es')
      await wrapper.find('form').trigger('submit')

      const errorSpans = wrapper.findAll('.form-error')
      // Should contain Spanish required message
      const spanishRequired = errorSpans.find(s => s.text() === es.form.required)
      expect(spanishRequired).toBeTruthy()
    })

    it('displays training wheels note in English', () => {
      const wrapper = mountApplyView('en')
      const note = wrapper.find('.apply-form__training-wheels-note')
      expect(note.text()).toBe(en.apply.trainingWheelsNote)
    })

    it('displays training wheels note in Spanish', () => {
      const wrapper = mountApplyView('es')
      const note = wrapper.find('.apply-form__training-wheels-note')
      expect(note.text()).toBe(es.apply.trainingWheelsNote)
    })
  })

  // ─── Height validation (Req 1.3) ───

  describe('height validation', () => {
    it('shows error when height is empty', async () => {
      const wrapper = mountApplyView()
      await wrapper.find('form').trigger('submit')

      const errorSpans = wrapper.findAll('.form-error')
      const heightError = errorSpans.find(s => s.text() === en.apply.heightRequired)
      expect(heightError).toBeTruthy()
    })

    it('shows error when height is non-numeric', async () => {
      const wrapper = mountApplyView()
      await wrapper.find('#child-0-height').setValue('abc')
      await wrapper.find('form').trigger('submit')

      const errorSpans = wrapper.findAll('.form-error')
      const heightError = errorSpans.find(s => s.text() === en.apply.heightNumeric)
      expect(heightError).toBeTruthy()
    })

    it('shows error when height is zero', async () => {
      const wrapper = mountApplyView()
      await wrapper.find('#child-0-height').setValue('0')
      await wrapper.find('form').trigger('submit')

      const errorSpans = wrapper.findAll('.form-error')
      const heightError = errorSpans.find(s => s.text() === en.apply.heightNumeric)
      expect(heightError).toBeTruthy()
    })

    it('accepts valid numeric height', async () => {
      const wrapper = mountApplyView()
      await fillRequiredFields(wrapper)
      vi.spyOn(globalThis, 'fetch').mockResolvedValue(
        new Response(JSON.stringify({ application_id: 'TEST-123' }), { status: 200 })
      )
      await wrapper.find('form').trigger('submit')

      const errorSpans = wrapper.findAll('.form-error')
      const heightError = errorSpans.find(s =>
        s.text() === en.apply.heightRequired || s.text() === en.apply.heightNumeric
      )
      expect(heightError).toBeUndefined()
    })
  })

  // ─── Drawing upload validation (Req 1.8) ───

  describe('drawing upload validation', () => {
    it('rejects non-PNG/JPEG file type', async () => {
      const wrapper = mountApplyView()
      const file = new File(['content'], 'doc.pdf', { type: 'application/pdf' })
      const input = wrapper.find('#child-0-drawing')

      // Simulate file input change
      Object.defineProperty(input.element, 'files', { value: [file], writable: false })
      await input.trigger('change')

      const errorSpans = wrapper.findAll('.form-error')
      const typeError = errorSpans.find(s => s.text() === en.apply.drawingInvalidType)
      expect(typeError).toBeTruthy()
    })

    it('rejects file larger than 5MB', async () => {
      const wrapper = mountApplyView()
      const largeContent = new ArrayBuffer(6 * 1024 * 1024) // 6MB
      const file = new File([largeContent], 'big.png', { type: 'image/png' })
      const input = wrapper.find('#child-0-drawing')

      Object.defineProperty(input.element, 'files', { value: [file], writable: false })
      await input.trigger('change')

      const errorSpans = wrapper.findAll('.form-error')
      const sizeError = errorSpans.find(s => s.text() === en.apply.drawingTooLarge)
      expect(sizeError).toBeTruthy()
    })

    it('accepts valid PNG file under 5MB', async () => {
      const wrapper = mountApplyView()
      const file = new File(['img'], 'drawing.png', { type: 'image/png' })
      const input = wrapper.find('#child-0-drawing')

      Object.defineProperty(input.element, 'files', { value: [file], writable: false })
      await input.trigger('change')

      const errorSpans = wrapper.findAll('.form-error')
      const drawingError = errorSpans.find(s =>
        s.text() === en.apply.drawingInvalidType || s.text() === en.apply.drawingTooLarge
      )
      expect(drawingError).toBeUndefined()
      // File name should be displayed
      expect(wrapper.find('.form-file-name').text()).toBe('drawing.png')
    })
  })

  // ─── Confirmation screen (Req 1.4) ───

  describe('confirmation screen', () => {
    it('shows confirmation with reference ID on successful submit', async () => {
      const wrapper = mountApplyView()
      await fillRequiredFields(wrapper)

      vi.spyOn(globalThis, 'fetch').mockResolvedValue(
        new Response(JSON.stringify({ application_id: 'APP-2025-XYZ' }), { status: 200 })
      )

      await wrapper.find('form').trigger('submit')
      // Wait for async submit
      await vi.waitFor(() => {
        expect(wrapper.find('.apply-confirmation').exists()).toBe(true)
      })

      expect(wrapper.find('.apply-confirmation h1').text()).toBe(en.apply.successTitle)
      expect(wrapper.find('.apply-confirmation__ref').text()).toContain('APP-2025-XYZ')
    })

    it('shows error message when API returns failure', async () => {
      const wrapper = mountApplyView()
      await fillRequiredFields(wrapper)

      vi.spyOn(globalThis, 'fetch').mockResolvedValue(
        new Response('error', { status: 500 })
      )

      await wrapper.find('form').trigger('submit')
      await vi.waitFor(() => {
        const alerts = wrapper.findAll('[role="alert"]')
        const submitErr = alerts.find(a => a.text().includes(en.apply.submitError))
        expect(submitErr).toBeTruthy()
      })

      // Form should still be visible (not confirmation)
      expect(wrapper.find('.apply-confirmation').exists()).toBe(false)
    })

    it('shows error message when fetch throws network error', async () => {
      const wrapper = mountApplyView()
      await fillRequiredFields(wrapper)

      vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('Network error'))

      await wrapper.find('form').trigger('submit')
      await vi.waitFor(() => {
        const alerts = wrapper.findAll('[role="alert"]')
        const submitErr = alerts.find(a => a.text().includes(en.apply.submitError))
        expect(submitErr).toBeTruthy()
      })
    })
  })
})

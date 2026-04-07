import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import UploadView from '../UploadView.vue'
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

function mountUploadView(locale = 'en') {
  const i18n = createTestI18n(locale)
  return mount(UploadView, {
    global: { plugins: [i18n] },
  })
}

function createFile(name: string, size: number, type: string): File {
  const content = new ArrayBuffer(size)
  return new File([content], name, { type })
}

/** Simulate adding files via the hidden file input change event */
async function addFilesViaInput(wrapper: ReturnType<typeof mount>, files: File[]) {
  const input = wrapper.find('input[type="file"]')
  const dt = new DataTransfer()
  files.forEach(f => dt.items.add(f))
  Object.defineProperty(input.element, 'files', { value: dt.files, configurable: true })
  await input.trigger('change')
}

describe('UploadView', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  // ─── File type validation (Req 2.1, 2.7) ───

  describe('file type validation', () => {
    it('shows error when adding a .txt file', async () => {
      const wrapper = mountUploadView()
      const txtFile = createFile('notes.txt', 1024, 'text/plain')
      await addFilesViaInput(wrapper, [txtFile])

      const errors = wrapper.find('.upload-view__errors')
      expect(errors.exists()).toBe(true)
      expect(errors.text()).toContain('notes.txt')
      // File should NOT appear in the file list
      expect(wrapper.find('.upload-file-table').exists()).toBe(false)
    })

    it('shows error with accepted formats info for invalid type', async () => {
      const wrapper = mountUploadView()
      const docFile = createFile('report.doc', 2048, 'application/msword')
      await addFilesViaInput(wrapper, [docFile])

      const errors = wrapper.find('.upload-view__errors')
      expect(errors.text()).toContain('report.doc')
      // The error message should mention accepted formats (from i18n key)
      expect(errors.text()).toContain('PDF, PNG, JPEG')
    })
  })

  // ─── File size validation (Req 2.2, 2.7) ───

  describe('file size validation', () => {
    it('shows error when adding a file larger than 10MB', async () => {
      const wrapper = mountUploadView()
      const bigFile = createFile('huge.pdf', 11 * 1024 * 1024, 'application/pdf')
      await addFilesViaInput(wrapper, [bigFile])

      const errors = wrapper.find('.upload-view__errors')
      expect(errors.exists()).toBe(true)
      expect(errors.text()).toContain('huge.pdf')
      expect(errors.text()).toContain('10 MB')
    })

    it('accepts a file exactly at 10MB', async () => {
      const wrapper = mountUploadView()
      const exactFile = createFile('exact.pdf', 10 * 1024 * 1024, 'application/pdf')
      await addFilesViaInput(wrapper, [exactFile])

      expect(wrapper.find('.upload-view__errors').exists()).toBe(false)
      expect(wrapper.find('.upload-file-table').exists()).toBe(true)
    })
  })

  // ─── Valid file acceptance (Req 2.1) ───

  describe('valid file acceptance', () => {
    it('adds a valid PDF and shows it with Pending status', async () => {
      const wrapper = mountUploadView()
      const pdf = createFile('app.pdf', 5000, 'application/pdf')
      await addFilesViaInput(wrapper, [pdf])

      const rows = wrapper.findAll('.upload-file-table tbody tr')
      expect(rows.length).toBe(1)
      expect(rows[0].text()).toContain('app.pdf')
      expect(rows[0].text()).toContain(en.upload.statusPending)
    })

    it('adds a valid PNG file', async () => {
      const wrapper = mountUploadView()
      const png = createFile('scan.png', 3000, 'image/png')
      await addFilesViaInput(wrapper, [png])

      const rows = wrapper.findAll('.upload-file-table tbody tr')
      expect(rows.length).toBe(1)
      expect(rows[0].text()).toContain('scan.png')
    })

    it('adds a valid JPEG file', async () => {
      const wrapper = mountUploadView()
      const jpeg = createFile('photo.jpeg', 4000, 'image/jpeg')
      await addFilesViaInput(wrapper, [jpeg])

      const rows = wrapper.findAll('.upload-file-table tbody tr')
      expect(rows.length).toBe(1)
      expect(rows[0].text()).toContain('photo.jpeg')
    })
  })

  // ─── Multi-file support (Req 2.5) ───

  describe('multi-file support', () => {
    it('adds multiple valid files and all appear in the list', async () => {
      const wrapper = mountUploadView()
      const files = [
        createFile('page1.pdf', 2000, 'application/pdf'),
        createFile('page2.png', 3000, 'image/png'),
        createFile('page3.jpeg', 4000, 'image/jpeg'),
      ]
      await addFilesViaInput(wrapper, files)

      const rows = wrapper.findAll('.upload-file-table tbody tr')
      expect(rows.length).toBe(3)
      expect(rows[0].text()).toContain('page1.pdf')
      expect(rows[1].text()).toContain('page2.png')
      expect(rows[2].text()).toContain('page3.jpeg')
    })

    it('rejects invalid files while keeping valid ones in a mixed batch', async () => {
      const wrapper = mountUploadView()
      const files = [
        createFile('good.pdf', 2000, 'application/pdf'),
        createFile('bad.txt', 1000, 'text/plain'),
      ]
      await addFilesViaInput(wrapper, files)

      // Valid file should be in the list
      const rows = wrapper.findAll('.upload-file-table tbody tr')
      expect(rows.length).toBe(1)
      expect(rows[0].text()).toContain('good.pdf')

      // Error for the invalid file
      const errors = wrapper.find('.upload-view__errors')
      expect(errors.text()).toContain('bad.txt')
    })
  })

  // ─── Remove file ───

  describe('remove file', () => {
    it('removes a file from the list when clicking Remove', async () => {
      const wrapper = mountUploadView()
      const pdf = createFile('removeme.pdf', 2000, 'application/pdf')
      await addFilesViaInput(wrapper, [pdf])

      expect(wrapper.findAll('.upload-file-table tbody tr').length).toBe(1)

      const removeBtn = wrapper.find('.btn--danger')
      await removeBtn.trigger('click')

      // File list table should disappear (no files left)
      expect(wrapper.find('.upload-file-table').exists()).toBe(false)
    })
  })

  // ─── Upload flow (Req 2.3, 2.4) ───

  describe('upload flow', () => {
    it('uploads files via pre-signed URL and shows Uploaded status with reference IDs', async () => {
      const wrapper = mountUploadView()
      const pdf = createFile('doc.pdf', 2000, 'application/pdf')
      await addFilesViaInput(wrapper, [pdf])

      // Mock fetch: first call = presign, second call = S3 PUT
      vi.spyOn(globalThis, 'fetch')
        .mockResolvedValueOnce(
          new Response(JSON.stringify({ upload_url: 'https://s3.example.com/upload', reference_id: 'REF-001' }), { status: 200 })
        )
        .mockResolvedValueOnce(
          new Response(null, { status: 200 })
        )

      const uploadBtn = wrapper.findAll('button').find(b => b.text().includes(en.upload.uploadAll))!
      await uploadBtn.trigger('click')

      // Wait for the confirmation screen to appear (async upload + Vue reactivity)
      await vi.waitFor(() => {
        expect(wrapper.find('.upload-confirmation').exists()).toBe(true)
      })

      expect(wrapper.find('.upload-confirmation h1').text()).toBe(en.upload.successTitle)
      // Reference ID should appear
      expect(wrapper.text()).toContain('REF-001')
    })

    it('sends correct presign request body', async () => {
      const wrapper = mountUploadView()
      const pdf = createFile('test.pdf', 5000, 'application/pdf')
      await addFilesViaInput(wrapper, [pdf])

      const fetchSpy = vi.spyOn(globalThis, 'fetch')
        .mockResolvedValueOnce(
          new Response(JSON.stringify({ upload_url: 'https://s3.example.com/upload', reference_id: 'REF-002' }), { status: 200 })
        )
        .mockResolvedValueOnce(new Response(null, { status: 200 }))

      const uploadBtn = wrapper.findAll('button').find(b => b.text().includes(en.upload.uploadAll))!
      await uploadBtn.trigger('click')

      await vi.waitFor(() => {
        expect(fetchSpy).toHaveBeenCalledTimes(2)
      })

      // Check presign call
      const presignCall = fetchSpy.mock.calls[0]
      expect(presignCall[0]).toContain('/uploads/presign')
      const body = JSON.parse((presignCall[1] as RequestInit).body as string)
      expect(body.file_name).toBe('test.pdf')
      expect(body.file_type).toBe('application/pdf')
      expect(body.file_size).toBe(5000)
    })
  })

  // ─── Upload error handling ───

  describe('upload error handling', () => {
    it('shows error status when presign request fails', async () => {
      const wrapper = mountUploadView()
      const pdf = createFile('fail.pdf', 2000, 'application/pdf')
      await addFilesViaInput(wrapper, [pdf])

      vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
        new Response('error', { status: 500 })
      )

      const uploadBtn = wrapper.findAll('button').find(b => b.text().includes(en.upload.uploadAll))!
      await uploadBtn.trigger('click')

      await vi.waitFor(() => {
        const errorSpans = wrapper.findAll('.upload-status--error')
        expect(errorSpans.length).toBe(1)
      })

      // Error message should appear
      expect(wrapper.find('.upload-error-inline').exists()).toBe(true)
    })

    it('shows error status when S3 upload fails', async () => {
      const wrapper = mountUploadView()
      const pdf = createFile('s3fail.pdf', 2000, 'application/pdf')
      await addFilesViaInput(wrapper, [pdf])

      vi.spyOn(globalThis, 'fetch')
        .mockResolvedValueOnce(
          new Response(JSON.stringify({ upload_url: 'https://s3.example.com/upload', reference_id: 'REF-X' }), { status: 200 })
        )
        .mockResolvedValueOnce(
          new Response('error', { status: 403 })
        )

      const uploadBtn = wrapper.findAll('button').find(b => b.text().includes(en.upload.uploadAll))!
      await uploadBtn.trigger('click')

      await vi.waitFor(() => {
        const errorSpans = wrapper.findAll('.upload-status--error')
        expect(errorSpans.length).toBe(1)
      })
    })

    it('shows error status when fetch throws a network error', async () => {
      const wrapper = mountUploadView()
      const pdf = createFile('net.pdf', 2000, 'application/pdf')
      await addFilesViaInput(wrapper, [pdf])

      vi.spyOn(globalThis, 'fetch').mockRejectedValueOnce(new Error('Network error'))

      const uploadBtn = wrapper.findAll('button').find(b => b.text().includes(en.upload.uploadAll))!
      await uploadBtn.trigger('click')

      await vi.waitFor(() => {
        const errorSpans = wrapper.findAll('.upload-status--error')
        expect(errorSpans.length).toBe(1)
      })
    })
  })

  // ─── Bilingual (Req 2.6) ───

  describe('bilingual support', () => {
    it('renders English labels when locale is en', () => {
      const wrapper = mountUploadView('en')
      expect(wrapper.find('h1').text()).toBe(en.upload.title)
      expect(wrapper.text()).toContain(en.upload.browseButton)
    })

    it('renders Spanish labels when locale is es', () => {
      const wrapper = mountUploadView('es')
      expect(wrapper.find('h1').text()).toBe(es.upload.title)
      expect(wrapper.text()).toContain(es.upload.browseButton)
    })

    it('shows Spanish error messages for invalid file type', async () => {
      const wrapper = mountUploadView('es')
      const txtFile = createFile('notas.txt', 1024, 'text/plain')
      await addFilesViaInput(wrapper, [txtFile])

      const errors = wrapper.find('.upload-view__errors')
      expect(errors.text()).toContain('PDF, PNG, JPEG')
      expect(errors.text()).toContain('notas.txt')
    })
  })

  // ─── Confirmation screen (Req 2.4) ───

  describe('confirmation screen', () => {
    it('shows confirmation with all reference IDs after all files uploaded', async () => {
      const wrapper = mountUploadView()
      const files = [
        createFile('a.pdf', 1000, 'application/pdf'),
        createFile('b.png', 2000, 'image/png'),
      ]
      await addFilesViaInput(wrapper, files)

      vi.spyOn(globalThis, 'fetch')
        // File 1: presign + S3
        .mockResolvedValueOnce(new Response(JSON.stringify({ upload_url: 'https://s3.example.com/1', reference_id: 'REF-AAA' }), { status: 200 }))
        .mockResolvedValueOnce(new Response(null, { status: 200 }))
        // File 2: presign + S3
        .mockResolvedValueOnce(new Response(JSON.stringify({ upload_url: 'https://s3.example.com/2', reference_id: 'REF-BBB' }), { status: 200 }))
        .mockResolvedValueOnce(new Response(null, { status: 200 }))

      const uploadBtn = wrapper.findAll('button').find(b => b.text().includes(en.upload.uploadAll))!
      await uploadBtn.trigger('click')

      await vi.waitFor(() => {
        expect(wrapper.find('.upload-confirmation').exists()).toBe(true)
      })

      expect(wrapper.text()).toContain('REF-AAA')
      expect(wrapper.text()).toContain('REF-BBB')
      expect(wrapper.find('.upload-confirmation h1').text()).toBe(en.upload.successTitle)
      expect(wrapper.text()).toContain(en.upload.successMessage)
    })

    it('allows uploading more files after confirmation via reset button', async () => {
      const wrapper = mountUploadView()
      const pdf = createFile('doc.pdf', 1000, 'application/pdf')
      await addFilesViaInput(wrapper, [pdf])

      vi.spyOn(globalThis, 'fetch')
        .mockResolvedValueOnce(new Response(JSON.stringify({ upload_url: 'https://s3.example.com/1', reference_id: 'REF-123' }), { status: 200 }))
        .mockResolvedValueOnce(new Response(null, { status: 200 }))

      const uploadBtn = wrapper.findAll('button').find(b => b.text().includes(en.upload.uploadAll))!
      await uploadBtn.trigger('click')

      await vi.waitFor(() => {
        expect(wrapper.find('.upload-confirmation').exists()).toBe(true)
      })

      // Click "Upload More Files"
      const moreBtn = wrapper.findAll('button').find(b => b.text().includes(en.upload.uploadMore))!
      await moreBtn.trigger('click')

      // Should be back to the upload interface
      expect(wrapper.find('.upload-confirmation').exists()).toBe(false)
      expect(wrapper.find('.upload-dropzone').exists()).toBe(true)
    })
  })
})

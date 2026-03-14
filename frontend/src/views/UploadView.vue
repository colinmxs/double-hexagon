<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api'

const ACCEPTED_TYPES = ['application/pdf', 'image/png', 'image/jpeg']
const MAX_FILE_SIZE = 10 * 1024 * 1024 // 10MB

type FileStatus = 'pending' | 'uploading' | 'uploaded' | 'error'

interface UploadFile {
  id: string
  file: File
  status: FileStatus
  referenceId: string
  errorMessage: string
}

const files = ref<UploadFile[]>([])
const isDragOver = ref(false)
const uploading = ref(false)
const allDone = ref(false)
const validationErrors = ref<string[]>([])

const uploadedRefs = computed(() =>
  files.value.filter(f => f.status === 'uploaded' && f.referenceId).map(f => f.referenceId)
)

const canUpload = computed(() =>
  files.value.length > 0 && files.value.some(f => f.status === 'pending') && !uploading.value
)

function generateId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function validateFile(file: File): string | null {
  if (!ACCEPTED_TYPES.includes(file.type)) {
    return t('upload.errorInvalidType', { name: file.name })
  }
  if (file.size > MAX_FILE_SIZE) {
    return t('upload.errorFileTooLarge', { name: file.name })
  }
  return null
}

function addFiles(newFiles: FileList | File[]) {
  validationErrors.value = []
  for (const file of Array.from(newFiles)) {
    const error = validateFile(file)
    if (error) {
      validationErrors.value.push(error)
      continue
    }
    files.value.push({
      id: generateId(),
      file,
      status: 'pending',
      referenceId: '',
      errorMessage: '',
    })
  }
}

function removeFile(id: string) {
  files.value = files.value.filter(f => f.id !== id)
}

function onDragOver(e: DragEvent) {
  e.preventDefault()
  isDragOver.value = true
}

function onDragLeave() {
  isDragOver.value = false
}

function onDrop(e: DragEvent) {
  e.preventDefault()
  isDragOver.value = false
  if (e.dataTransfer?.files) {
    addFiles(e.dataTransfer.files)
  }
}

function onFileInput(e: Event) {
  const input = e.target as HTMLInputElement
  if (input.files) {
    addFiles(input.files)
  }
  input.value = ''
}

async function uploadSingleFile(entry: UploadFile): Promise<void> {
  entry.status = 'uploading'
  entry.errorMessage = ''

  try {
    const presignRes = await fetch(`${API_BASE}/uploads/presign`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        fileName: entry.file.name,
        fileType: entry.file.type,
        fileSize: entry.file.size,
      }),
    })

    if (!presignRes.ok) {
      entry.status = 'error'
      entry.errorMessage = t('upload.errorUploadFailed', { name: entry.file.name })
      return
    }

    const { uploadUrl, referenceId } = await presignRes.json()

    const uploadRes = await fetch(uploadUrl, {
      method: 'PUT',
      headers: { 'Content-Type': entry.file.type },
      body: entry.file,
    })

    if (!uploadRes.ok) {
      entry.status = 'error'
      entry.errorMessage = t('upload.errorUploadFailed', { name: entry.file.name })
      return
    }

    entry.status = 'uploaded'
    entry.referenceId = referenceId
  } catch {
    entry.status = 'error'
    entry.errorMessage = t('upload.errorUploadFailed', { name: entry.file.name })
  }
}

async function uploadAll() {
  uploading.value = true
  validationErrors.value = []

  const pending = files.value.filter(f => f.status === 'pending' || f.status === 'error')
  for (const entry of pending) {
    await uploadSingleFile(entry)
  }

  uploading.value = false

  if (files.value.every(f => f.status === 'uploaded')) {
    allDone.value = true
  }
}

function reset() {
  files.value = []
  validationErrors.value = []
  allDone.value = false
  uploading.value = false
}

function statusLabel(status: FileStatus): string {
  const map: Record<FileStatus, string> = {
    pending: t('upload.statusPending'),
    uploading: t('upload.statusUploading'),
    uploaded: t('upload.statusUploaded'),
    error: t('upload.statusError'),
  }
  return map[status]
}

function statusClass(status: FileStatus): string {
  return `upload-status--${status}`
}
</script>

<template>
  <div class="upload-view">
    <!-- Success Screen -->
    <div v-if="allDone" class="upload-confirmation">
      <h1>{{ t('upload.successTitle') }}</h1>
      <p>{{ t('upload.successMessage') }}</p>
      <div class="upload-confirmation__refs">
        <div v-for="refId in uploadedRefs" :key="refId" class="upload-confirmation__ref">
          <strong>{{ t('upload.referenceId') }}:</strong> {{ refId }}
        </div>
      </div>
      <button type="button" class="btn btn--primary" @click="reset">
        {{ t('upload.uploadMore') }}
      </button>
    </div>

    <!-- Upload Interface -->
    <div v-else>
      <h1>{{ t('upload.title') }}</h1>
      <p class="upload-view__intro">{{ t('upload.intro') }}</p>

      <!-- Validation Errors -->
      <div v-if="validationErrors.length" class="upload-view__errors" role="alert">
        <p v-for="(err, i) in validationErrors" :key="i">{{ err }}</p>
      </div>

      <!-- Drop Zone -->
      <div
        class="upload-dropzone"
        :class="{ 'upload-dropzone--active': isDragOver }"
        role="button"
        tabindex="0"
        :aria-label="t('upload.dropzoneLabel')"
        @dragover="onDragOver"
        @dragleave="onDragLeave"
        @drop="onDrop"
        @click="($refs.fileInput as HTMLInputElement).click()"
        @keydown.enter="($refs.fileInput as HTMLInputElement).click()"
        @keydown.space.prevent="($refs.fileInput as HTMLInputElement).click()"
      >
        <div class="upload-dropzone__content">
          <svg class="upload-dropzone__icon" xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
            <polyline points="17 8 12 3 7 8" />
            <line x1="12" y1="3" x2="12" y2="15" />
          </svg>
          <p v-if="isDragOver" class="upload-dropzone__text">{{ t('upload.dragOver') }}</p>
          <p v-else class="upload-dropzone__text">{{ t('upload.dropzoneLabel') }}</p>
          <button type="button" class="btn btn--secondary upload-dropzone__btn" @click.stop="($refs.fileInput as HTMLInputElement).click()">
            {{ t('upload.browseButton') }}
          </button>
          <p class="upload-dropzone__hint">{{ t('upload.acceptedFormats') }} · {{ t('upload.maxFileSize') }}</p>
        </div>
      </div>
      <input
        ref="fileInput"
        type="file"
        multiple
        accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg"
        class="upload-view__hidden-input"
        @change="onFileInput"
        aria-hidden="true"
        tabindex="-1"
      />

      <!-- File List -->
      <div v-if="files.length" class="upload-file-list">
        <h2>{{ t('upload.fileList') }}</h2>
        <table class="upload-file-table" role="table">
          <thead>
            <tr>
              <th scope="col">{{ t('upload.fileName') }}</th>
              <th scope="col">{{ t('upload.fileSize') }}</th>
              <th scope="col">{{ t('upload.fileStatus') }}</th>
              <th scope="col"><span class="sr-only">{{ t('common.delete') }}</span></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="entry in files" :key="entry.id">
              <td>{{ entry.file.name }}</td>
              <td>{{ formatSize(entry.file.size) }}</td>
              <td>
                <span :class="['upload-status', statusClass(entry.status)]">{{ statusLabel(entry.status) }}</span>
                <span v-if="entry.referenceId" class="upload-ref-inline"> — {{ entry.referenceId }}</span>
                <span v-if="entry.errorMessage" class="upload-error-inline" role="alert">{{ entry.errorMessage }}</span>
              </td>
              <td>
                <button
                  v-if="entry.status === 'pending' || entry.status === 'error'"
                  type="button"
                  class="btn btn--danger btn--sm"
                  :aria-label="t('upload.removeFileLabel', { name: entry.file.name })"
                  @click="removeFile(entry.id)"
                >
                  {{ t('upload.removeFile') }}
                </button>
              </td>
            </tr>
          </tbody>
        </table>

        <div class="upload-file-list__actions">
          <button type="button" class="btn btn--primary" :disabled="!canUpload" @click="uploadAll">
            {{ uploading ? t('upload.uploading') : t('upload.uploadAll') }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.upload-view {
  max-width: 720px;
  margin: 0 auto;
  padding: 1rem;
}

.upload-view__intro {
  color: #555;
  margin-bottom: 1.5rem;
}

.upload-view__hidden-input {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

.upload-view__errors {
  background: #ffebee;
  border: 1px solid #ef9a9a;
  border-radius: 4px;
  padding: 0.75rem 1rem;
  color: #c62828;
  margin-bottom: 1rem;
}

.upload-view__errors p {
  margin: 0.25rem 0;
}

/* Drop Zone */
.upload-dropzone {
  border: 2px dashed #bdbdbd;
  border-radius: 8px;
  padding: 2rem 1rem;
  text-align: center;
  cursor: pointer;
  transition: border-color 0.2s, background-color 0.2s;
  background: #fafafa;
}

.upload-dropzone:hover,
.upload-dropzone:focus-visible {
  border-color: #1976d2;
  background: #e3f2fd;
  outline: none;
}

.upload-dropzone--active {
  border-color: #1976d2;
  background: #bbdefb;
}

.upload-dropzone__content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5rem;
}

.upload-dropzone__icon {
  color: #9e9e9e;
}

.upload-dropzone--active .upload-dropzone__icon {
  color: #1976d2;
}

.upload-dropzone__text {
  font-size: 1rem;
  color: #555;
  margin: 0;
}

.upload-dropzone__btn {
  margin-top: 0.5rem;
}

.upload-dropzone__hint {
  font-size: 0.8rem;
  color: #999;
  margin: 0.25rem 0 0;
}

/* File List */
.upload-file-list {
  margin-top: 1.5rem;
}

.upload-file-list h2 {
  font-size: 1.1rem;
  margin-bottom: 0.75rem;
}

.upload-file-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.9rem;
}

.upload-file-table th,
.upload-file-table td {
  text-align: left;
  padding: 0.5rem 0.75rem;
  border-bottom: 1px solid #e0e0e0;
}

.upload-file-table th {
  font-weight: 600;
  color: #555;
  background: #f5f5f5;
}

.upload-status {
  font-weight: 500;
  font-size: 0.85rem;
}

.upload-status--pending { color: #757575; }
.upload-status--uploading { color: #1976d2; }
.upload-status--uploaded { color: #388e3c; }
.upload-status--error { color: #d32f2f; }

.upload-ref-inline {
  font-size: 0.8rem;
  color: #388e3c;
}

.upload-error-inline {
  display: block;
  font-size: 0.8rem;
  color: #d32f2f;
  margin-top: 0.25rem;
}

.upload-file-list__actions {
  margin-top: 1rem;
  text-align: center;
}

/* Confirmation */
.upload-confirmation {
  text-align: center;
  padding: 2rem 1rem;
}

.upload-confirmation h1 {
  color: #388e3c;
}

.upload-confirmation__refs {
  margin: 1.5rem 0;
}

.upload-confirmation__ref {
  background: #e8f5e9;
  border-radius: 6px;
  padding: 0.75rem 1rem;
  margin-bottom: 0.5rem;
  font-size: 1.05rem;
  word-break: break-all;
}

/* Shared button styles (matching ApplyView) */
.btn {
  padding: 0.6rem 1.25rem;
  border: none;
  border-radius: 4px;
  font-size: 0.95rem;
  cursor: pointer;
  font-weight: 500;
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn--primary {
  background: #1976d2;
  color: #fff;
}

.btn--primary:hover:not(:disabled) {
  background: #1565c0;
}

.btn--secondary {
  background: #e0e0e0;
  color: #333;
}

.btn--secondary:hover {
  background: #d0d0d0;
}

.btn--danger {
  background: #d32f2f;
  color: #fff;
}

.btn--danger:hover {
  background: #c62828;
}

.btn--sm {
  padding: 0.3rem 0.75rem;
  font-size: 0.85rem;
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

/* Responsive: 320px minimum */
@media (max-width: 600px) {
  .upload-view {
    padding: 0.5rem;
  }

  .upload-dropzone {
    padding: 1.5rem 0.75rem;
  }

  .upload-file-table th:nth-child(2),
  .upload-file-table td:nth-child(2) {
    display: none;
  }

  .upload-file-table th,
  .upload-file-table td {
    padding: 0.4rem 0.5rem;
    font-size: 0.8rem;
  }
}
</style>

<script setup lang="ts">
import { ref, computed, onMounted, reactive } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import ConfidenceBadge from '../components/ConfidenceBadge.vue'
import DrawingViewer from '../components/DrawingViewer.vue'
import { useApi } from '../composables/useApi'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const { apiFetch, API_BASE } = useApi()
const CONFIDENCE_THRESHOLD = 0.8

// --- Types ---

interface ReferringAgency {
  agency_name: string
  contact_name: string
  contact_phone: string
  contact_email: string
}

interface ParentGuardian {
  first_name: string
  last_name: string
  address: string
  city: string
  zip_code: string
  phone: string
  email: string
  primary_language: string
  english_speaker_in_household: boolean
  preferred_contact_method: string
  transportation_access: boolean
}

interface Child {
  child_id: string
  first_name: string
  last_name: string
  height_inches: number
  age: number
  gender: string
  bike_color_1: string
  bike_color_2: string
  knows_how_to_ride: boolean
  other_siblings_enrolled: string
  drawing_image_s3_key: string
  drawing_keywords: string[]
  dream_bike_description: string
  bike_number: string
}

interface OriginalDocument {
  s3_key: string
  upload_timestamp: string
  page_count: number
  presigned_url?: string
}

interface ApplicationDetail {
  giveaway_year: string
  application_id: string
  reference_number?: string
  submission_timestamp: string
  source_type: 'upload' | 'digital'
  status: string
  overall_confidence_score: number
  referring_agency: ReferringAgency
  parent_guardian: ParentGuardian
  children: Child[]
  field_confidence: Record<string, number>
  original_documents: OriginalDocument[]
}

// --- State ---

const isLoading = ref(true)
const error = ref('')
const isSaving = ref(false)
const isApproving = ref(false)
const saveMessage = ref('')
const saveError = ref('')

const application = ref<ApplicationDetail | null>(null)
const editedFields = reactive<Record<string, unknown>>({})
const localConfidence = reactive<Record<string, number>>({})

// --- Audit timeline ---
interface AuditChange {
  field_name: string
  previous_value: string | null
  new_value: string | null
}

interface AuditEntry {
  timestamp: string
  user_id: string
  user_name: string
  action_type: string
  details?: { changes?: AuditChange[]; [key: string]: unknown }
}

const auditEntries = ref<AuditEntry[]>([])
const auditLoading = ref(false)
const auditExpanded = ref<number | null>(null)

// --- Computed ---

const applicationId = computed(() => route.params.applicationId as string)

const currentDocumentUrl = computed(() => {
  if (!application.value?.original_documents?.length) return ''
  const doc = application.value.original_documents[0]
  if (doc.s3_key) return `${API_BASE}/documents/${doc.s3_key}`
  return doc.presigned_url || ''
})

const isApproved = computed(() => application.value?.status === 'manually_approved')

// --- Helpers ---

function getConfidence(fieldKey: string): number {
  if (fieldKey in localConfidence) return localConfidence[fieldKey]
  return application.value?.field_confidence?.[fieldKey] ?? 1.0
}

function isLowConfidence(fieldKey: string): boolean {
  return getConfidence(fieldKey) < CONFIDENCE_THRESHOLD
}

function getFieldValue(fieldKey: string, fallback: unknown = ''): unknown {
  if (fieldKey in editedFields) return editedFields[fieldKey]
  const parts = fieldKey.split('.')
  let obj: unknown = application.value
  for (const part of parts) {
    const arrayMatch = part.match(/^(\w+)\[(\d+)]$/)
    if (arrayMatch) {
      obj = (obj as Record<string, unknown[]>)?.[arrayMatch[1]]?.[Number(arrayMatch[2])]
    } else {
      obj = (obj as Record<string, unknown>)?.[part]
    }
    if (obj === undefined) return fallback
  }
  return obj ?? fallback
}

function onFieldEdit(fieldKey: string, value: unknown) {
  editedFields[fieldKey] = value
  localConfidence[fieldKey] = 1.0
}

function statusLabel(status: string): string {
  const map: Record<string, string> = {
    needs_review: t('reviewDetail.statusNeedsReview'),
    manually_approved: t('reviewDetail.statusManuallyApproved'),
    extraction_failed: t('reviewDetail.statusExtractionFailed'),
  }
  return map[status] ?? status
}

function formatDate(ts: string): string {
  try { return new Date(ts).toLocaleDateString() } catch { return ts }
}

function getDrawingUrl(child: Child): string {
  if (!child.drawing_image_s3_key) return ''
  return `${API_BASE}/drawings/${child.drawing_image_s3_key}`
}

function getChildKeywordsString(index: number): string {
  const key = `children[${index}].drawing_keywords`
  if (key in editedFields) return editedFields[key] as string
  const child = application.value?.children?.[index]
  return child?.drawing_keywords?.join(', ') ?? ''
}

function onKeywordsEdit(index: number, value: string) {
  editedFields[`children[${index}].drawing_keywords`] = value
  localConfidence[`children[${index}].drawing_keywords`] = 1.0
}

// --- API calls ---

async function fetchAuditLog() {
  if (!applicationId.value) return
  auditLoading.value = true
  try {
    // Try fetching by reference_number first, fall back to application_id
    const refNum = application.value?.reference_number
    const resourceId = refNum || applicationId.value
    const res = await apiFetch(`/audit-log?resource_id=${encodeURIComponent(resourceId)}`)
    if (!res.ok) return
    const data = await res.json()
    auditEntries.value = data.entries ?? []
  } catch {
    // Non-fatal — audit log is supplementary
  } finally {
    auditLoading.value = false
  }
}

async function fetchApplication() {
  isLoading.value = true
  error.value = ''
  try {
    const res = await apiFetch(`/applications/${applicationId.value}`)
    if (!res.ok) throw new Error('Failed to fetch')
    const data = await res.json()
    application.value = data.application ?? data
    // Initialize localConfidence from server data
    if (application.value?.field_confidence) {
      Object.entries(application.value.field_confidence).forEach(([k, v]) => {
        localConfidence[k] = v
      })
    }
  } catch {
    error.value = t('reviewDetail.errorLoading')
  } finally {
    isLoading.value = false
  }
  fetchAuditLog()
}

async function saveChanges() {
  if (!application.value) return
  isSaving.value = true
  saveMessage.value = ''
  saveError.value = ''

  try {
    // Build the update payload from editedFields
    const updates: Record<string, unknown> = {}

    for (const [key, value] of Object.entries(editedFields)) {
      // Handle drawing_keywords: convert comma string back to array
      if (key.includes('drawing_keywords')) {
        updates[key] = (value as string).split(',').map((s: string) => s.trim()).filter(Boolean)
      } else {
        updates[key] = value
      }
    }

    const res = await apiFetch(`/applications/${applicationId.value}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        field_updates: updates,
      }),
    })

    if (!res.ok) throw new Error('Save failed')

    saveMessage.value = t('reviewDetail.saveSuccess')
    // Clear edited fields after successful save
    Object.keys(editedFields).forEach((k) => delete editedFields[k])
    // Refresh data
    await fetchApplication()
  } catch {
    saveError.value = t('reviewDetail.saveError')
  } finally {
    isSaving.value = false
  }
}

async function approveApplication() {
  if (!application.value) return
  isApproving.value = true
  saveMessage.value = ''
  saveError.value = ''

  try {
    const res = await apiFetch(`/applications/${applicationId.value}/status`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        status: 'manually_approved',
      }),
    })

    if (!res.ok) throw new Error('Approve failed')

    saveMessage.value = t('reviewDetail.approveSuccess')
    await fetchApplication()
  } catch {
    saveError.value = t('reviewDetail.approveError')
  } finally {
    isApproving.value = false
  }
}

function openOriginalDocument() {
  const url = currentDocumentUrl.value
  if (url) {
    window.open(url, '_blank')
  }
}

function goBack() {
  router.push('/admin/review')
}

onMounted(fetchApplication)
</script>

<template>
  <div class="review-detail">
    <!-- Header -->
    <div class="review-detail__header">
      <button class="review-detail__back-btn" @click="goBack">
        ← {{ t('reviewDetail.backToList') }}
      </button>
      <div v-if="application" class="review-detail__meta">
        <span v-if="application.reference_number" class="review-detail__meta-item">
          Ref: {{ application.reference_number }}
        </span>
        <span class="review-detail__meta-item">
          {{ t('reviewDetail.status') }}:
          <span :class="`review-detail__status review-detail__status--${application.status}`">
            {{ statusLabel(application.status) }}
          </span>
        </span>
        <span class="review-detail__meta-item">
          {{ t('reviewDetail.overallConfidence') }}:
          <ConfidenceBadge :score="application.overall_confidence_score" />
        </span>
        <span class="review-detail__meta-item">
          {{ t('reviewDetail.source') }}:
          {{ application.source_type === 'digital' ? t('reviewDetail.sourceDigital') : t('reviewDetail.sourceUpload') }}
        </span>
        <span class="review-detail__meta-item">
          {{ t('reviewDetail.submissionDate') }}: {{ formatDate(application.submission_timestamp) }}
        </span>
        <button
          v-if="application.source_type === 'upload' && application.original_documents?.length"
          class="review-detail__view-original-btn"
          @click="openOriginalDocument"
        >
          View Uploaded Documents
        </button>
      </div>
    </div>

    <!-- Loading -->
    <div v-if="isLoading" class="review-detail__loading" role="status">
      {{ t('reviewDetail.loading') }}
    </div>

    <!-- Error -->
    <div v-else-if="error" class="review-detail__error" role="alert">
      {{ error }}
      <button @click="fetchApplication">{{ t('reviewDetail.retry') }}</button>
    </div>

    <!-- Main content -->
    <div v-else-if="application" class="review-detail__content">
      <!-- AI transcription warning banner for upload-type apps -->
      <div
        v-if="application.source_type === 'upload'"
        class="review-detail__ai-banner"
      >
        <div class="review-detail__ai-banner-icon">🤖</div>
        <div class="review-detail__ai-banner-text">
          <span class="review-detail__ai-banner-title">AI-Transcribed Application</span>
          <span class="review-detail__ai-banner-desc">This application was scanned from a paper form and transcribed using AI. Always verify the data against the original document.</span>
        </div>
        <button
          v-if="application.original_documents?.length"
          class="review-detail__ai-banner-btn"
          @click="openOriginalDocument"
        >
          View Original ↗
        </button>
      </div>
      <div class="review-detail__form-panel">
        <!-- Audit Timeline -->
        <div class="review-detail__audit">
          <h2>Activity Log</h2>
          <div v-if="auditLoading" class="review-detail__audit-loading">Loading history...</div>
          <div v-else-if="auditEntries.length === 0" class="review-detail__audit-empty">No activity recorded yet.</div>
          <div v-else class="review-detail__audit-list">
            <div
              v-for="(ae, ai) in auditEntries"
              :key="ai"
              class="review-detail__audit-entry"
              :class="{ 'review-detail__audit-entry--clickable': ae.details?.changes?.length }"
              @click="ae.details?.changes?.length ? (auditExpanded = auditExpanded === ai ? null : ai) : null"
            >
              <div class="review-detail__audit-header">
                <span
                  class="review-detail__audit-action"
                  :style="{
                    color: ae.action_type === 'create' ? '#155724' : ae.action_type === 'view' ? '#004085' : ae.action_type === 'update' ? '#856404' : ae.action_type === 'delete' ? '#721c24' : '#6f42c1',
                    background: ae.action_type === 'create' ? '#d4edda' : ae.action_type === 'view' ? '#cce5ff' : ae.action_type === 'update' ? '#fff3cd' : ae.action_type === 'delete' ? '#f8d7da' : '#e8daef',
                  }"
                >{{ ae.action_type }}</span>
                <span class="review-detail__audit-user">{{ ae.user_name || ae.user_id }}</span>
                <span class="review-detail__audit-time">{{ new Date(ae.timestamp).toLocaleString() }}</span>
                <span v-if="ae.details?.changes?.length" class="review-detail__audit-expand">
                  {{ auditExpanded === ai ? '▾' : '▸' }} {{ ae.details.changes.length }} change{{ ae.details.changes.length > 1 ? 's' : '' }}
                </span>
              </div>
              <div v-if="auditExpanded === ai && ae.details?.changes" class="review-detail__audit-diff">
                <div v-for="(c, ci) in ae.details.changes" :key="ci" class="review-detail__audit-diff-line">
                  <span class="review-detail__audit-diff-field">{{ c.field_name }}</span>
                  <span class="review-detail__audit-diff-old">{{ c.previous_value ?? '∅' }}</span>
                  <span class="review-detail__audit-diff-arrow">→</span>
                  <span class="review-detail__audit-diff-new">{{ c.new_value ?? '∅' }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <h2>{{ t('reviewDetail.transcription') }}</h2>

        <!-- Messages -->
        <div v-if="saveMessage" class="review-detail__success" role="status">{{ saveMessage }}</div>
        <div v-if="saveError" class="review-detail__error" role="alert">{{ saveError }}</div>

        <!-- Referring Agency -->
        <fieldset class="review-detail__section">
          <legend>{{ t('reviewDetail.sectionAgency') }}</legend>
          <div
            v-for="field in ([
              { key: 'referring_agency.agency_name', label: t('reviewDetail.agencyName') },
              { key: 'referring_agency.contact_name', label: t('reviewDetail.contactName') },
              { key: 'referring_agency.contact_phone', label: t('reviewDetail.contactPhone') },
              { key: 'referring_agency.contact_email', label: t('reviewDetail.contactEmail') },
            ] as const)"
            :key="field.key"
            class="review-detail__field"
            :class="{ 'review-detail__field--low': isLowConfidence(field.key) }"
          >
            <label :for="`field-${field.key}`">
              {{ field.label }}
              <ConfidenceBadge :score="getConfidence(field.key)" />
            </label>
            <input
              :id="`field-${field.key}`"
              type="text"
              :value="getFieldValue(field.key)"
              @input="onFieldEdit(field.key, ($event.target as HTMLInputElement).value)"
            />
          </div>
        </fieldset>

        <!-- Parent/Guardian -->
        <fieldset class="review-detail__section">
          <legend>{{ t('reviewDetail.sectionParent') }}</legend>
          <div
            v-for="field in ([
              { key: 'parent_guardian.first_name', label: t('reviewDetail.firstName') },
              { key: 'parent_guardian.last_name', label: t('reviewDetail.lastName') },
              { key: 'parent_guardian.address', label: t('reviewDetail.address') },
              { key: 'parent_guardian.city', label: t('reviewDetail.city') },
              { key: 'parent_guardian.zip_code', label: t('reviewDetail.zipCode') },
              { key: 'parent_guardian.phone', label: t('reviewDetail.phone') },
              { key: 'parent_guardian.email', label: t('reviewDetail.email') },
              { key: 'parent_guardian.primary_language', label: t('reviewDetail.primaryLanguage') },
              { key: 'parent_guardian.preferred_contact_method', label: t('reviewDetail.preferredContact') },
            ] as const)"
            :key="field.key"
            class="review-detail__field"
            :class="{ 'review-detail__field--low': isLowConfidence(field.key) }"
          >
            <label :for="`field-${field.key}`">
              {{ field.label }}
              <ConfidenceBadge :score="getConfidence(field.key)" />
            </label>
            <input
              :id="`field-${field.key}`"
              type="text"
              :value="getFieldValue(field.key)"
              @input="onFieldEdit(field.key, ($event.target as HTMLInputElement).value)"
            />
          </div>

          <!-- Boolean fields -->
          <div
            class="review-detail__field"
            :class="{ 'review-detail__field--low': isLowConfidence('parent_guardian.english_speaker_in_household') }"
          >
            <label :for="'field-english-speaker'">
              {{ t('reviewDetail.englishSpeaker') }}
              <ConfidenceBadge :score="getConfidence('parent_guardian.english_speaker_in_household')" />
            </label>
            <select
              id="field-english-speaker"
              :value="String(getFieldValue('parent_guardian.english_speaker_in_household', false))"
              @change="onFieldEdit('parent_guardian.english_speaker_in_household', ($event.target as HTMLSelectElement).value === 'true')"
            >
              <option value="true">{{ t('common.yes') }}</option>
              <option value="false">{{ t('common.no') }}</option>
            </select>
          </div>

          <div
            class="review-detail__field"
            :class="{ 'review-detail__field--low': isLowConfidence('parent_guardian.transportation_access') }"
          >
            <label :for="'field-transportation'">
              {{ t('reviewDetail.transportationAccess') }}
              <ConfidenceBadge :score="getConfidence('parent_guardian.transportation_access')" />
            </label>
            <select
              id="field-transportation"
              :value="String(getFieldValue('parent_guardian.transportation_access', false))"
              @change="onFieldEdit('parent_guardian.transportation_access', ($event.target as HTMLSelectElement).value === 'true')"
            >
              <option value="true">{{ t('common.yes') }}</option>
              <option value="false">{{ t('common.no') }}</option>
            </select>
          </div>
        </fieldset>

        <!-- Children -->
        <fieldset
          v-for="(child, idx) in application.children"
          :key="child.child_id"
          class="review-detail__section"
        >
          <legend>{{ t('reviewDetail.child', { index: idx + 1 }) }}</legend>

          <div
            v-for="field in ([
              { key: `children[${idx}].first_name`, label: t('reviewDetail.childFirstName') },
              { key: `children[${idx}].last_name`, label: t('reviewDetail.childLastName') },
              { key: `children[${idx}].height_inches`, label: t('reviewDetail.heightInches') },
              { key: `children[${idx}].age`, label: t('reviewDetail.age') },
              { key: `children[${idx}].gender`, label: t('reviewDetail.gender') },
              { key: `children[${idx}].bike_color_1`, label: t('reviewDetail.bikeColor1') },
              { key: `children[${idx}].bike_color_2`, label: t('reviewDetail.bikeColor2') },
              { key: `children[${idx}].other_siblings_enrolled`, label: t('reviewDetail.otherSiblings') },
            ])"
            :key="field.key"
            class="review-detail__field"
            :class="{ 'review-detail__field--low': isLowConfidence(field.key) }"
          >
            <label :for="`field-${field.key}`">
              {{ field.label }}
              <ConfidenceBadge :score="getConfidence(field.key)" />
            </label>
            <input
              :id="`field-${field.key}`"
              type="text"
              :value="getFieldValue(field.key)"
              @input="onFieldEdit(field.key, ($event.target as HTMLInputElement).value)"
            />
          </div>

          <!-- Knows how to ride (boolean) -->
          <div
            class="review-detail__field"
            :class="{ 'review-detail__field--low': isLowConfidence(`children[${idx}].knows_how_to_ride`) }"
          >
            <label :for="`field-ride-${idx}`">
              {{ t('reviewDetail.knowsHowToRide') }}
              <ConfidenceBadge :score="getConfidence(`children[${idx}].knows_how_to_ride`)" />
            </label>
            <select
              :id="`field-ride-${idx}`"
              :value="String(getFieldValue(`children[${idx}].knows_how_to_ride`, false))"
              @change="onFieldEdit(`children[${idx}].knows_how_to_ride`, ($event.target as HTMLSelectElement).value === 'true')"
            >
              <option value="true">{{ t('common.yes') }}</option>
              <option value="false">{{ t('common.no') }}</option>
            </select>
          </div>

          <!-- Bike Number -->
          <div class="review-detail__field">
            <label :for="`field-bike-${idx}`">{{ t('reviewDetail.bikeNumber') }}</label>
            <div class="review-detail__inline-action">
              <input
                :id="`field-bike-${idx}`"
                type="text"
                :value="getFieldValue(`children[${idx}].bike_number`, '')"
                @input="onFieldEdit(`children[${idx}].bike_number`, ($event.target as HTMLInputElement).value)"
              />
            </div>
          </div>

          <!-- Dream Bike Description -->
          <div
            class="review-detail__field"
            :class="{ 'review-detail__field--low': isLowConfidence(`children[${idx}].dream_bike_description`) }"
          >
            <label :for="`field-dream-${idx}`">
              {{ t('reviewDetail.dreamBikeDescription') }}
              <ConfidenceBadge :score="getConfidence(`children[${idx}].dream_bike_description`)" />
            </label>
            <textarea
              :id="`field-dream-${idx}`"
              rows="3"
              :value="getFieldValue(`children[${idx}].dream_bike_description`, '') as string"
              @input="onFieldEdit(`children[${idx}].dream_bike_description`, ($event.target as HTMLTextAreaElement).value)"
            />
          </div>

          <!-- Drawing -->
          <div class="review-detail__drawing-section">
            <h4>{{ t('reviewDetail.dreamBikeDrawing') }}</h4>
            <DrawingViewer
              v-if="child.drawing_image_s3_key"
              :image-url="getDrawingUrl(child)"
              :keywords="child.drawing_keywords ?? []"
            />

            <!-- Editable keywords -->
            <div
              class="review-detail__field"
              :class="{ 'review-detail__field--low': isLowConfidence(`children[${idx}].drawing_keywords`) }"
            >
              <label :for="`field-keywords-${idx}`">
                {{ t('reviewDetail.drawingKeywords') }}
                <ConfidenceBadge :score="getConfidence(`children[${idx}].drawing_keywords`)" />
              </label>
              <input
                :id="`field-keywords-${idx}`"
                type="text"
                :placeholder="t('reviewDetail.drawingKeywordsHelp')"
                :value="getChildKeywordsString(idx)"
                @input="onKeywordsEdit(idx, ($event.target as HTMLInputElement).value)"
              />
            </div>
          </div>
        </fieldset>

        <!-- Action buttons -->
        <div class="review-detail__actions">
          <button
            class="review-detail__btn review-detail__btn--save"
            :disabled="isSaving || Object.keys(editedFields).length === 0"
            @click="saveChanges"
          >
            {{ isSaving ? t('reviewDetail.saving') : t('reviewDetail.saveChanges') }}
          </button>
          <button
            class="review-detail__btn review-detail__btn--approve"
            :disabled="isApproving || isApproved"
            @click="approveApplication"
          >
            {{ isApproving ? t('reviewDetail.approving') : t('reviewDetail.approve') }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.review-detail {
  padding: 1rem;
}

.review-detail__header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 1rem;
  margin-bottom: 1rem;
}

.review-detail__back-btn {
  padding: 0.4rem 0.8rem;
  border: 1px solid #ccc;
  background: #faf7f2;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.9rem;
  white-space: nowrap;
}

.review-detail__back-btn:hover {
  background: #f0ebe3;
}

.review-detail__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
  align-items: center;
  font-size: 0.9rem;
}

.review-detail__meta-item {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
}

.review-detail__view-original-btn {
  display: none;
}

/* AI transcription banner */
.review-detail__ai-banner {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.75rem 1rem;
  background: #fffbeb;
  border: 1.5px solid #f59e0b;
  border-radius: 8px;
  margin-bottom: 1rem;
}

.review-detail__ai-banner-icon {
  font-size: 1.6rem;
  flex-shrink: 0;
}

.review-detail__ai-banner-text {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
}

.review-detail__ai-banner-title {
  font-size: 0.85rem;
  font-weight: 700;
  color: #92400e;
}

.review-detail__ai-banner-desc {
  font-size: 0.78rem;
  color: #a16207;
  line-height: 1.3;
}

.review-detail__ai-banner-btn {
  padding: 0.5rem 1rem;
  border: none;
  background: #f59e0b;
  color: #fff;
  border-radius: 6px;
  font-size: 0.85rem;
  font-weight: 700;
  cursor: pointer;
  white-space: nowrap;
  transition: background 0.15s;
}

.review-detail__ai-banner-btn:hover {
  background: #d97706;
}

.review-detail__status {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 0.8rem;
  font-weight: 600;
}

.review-detail__status--needs_review {
  background: #fff3cd;
  color: #856404;
}

.review-detail__status--manually_approved {
  background: #cce5ff;
  color: #004085;
}

.review-detail__status--extraction_failed {
  background: #f8d7da;
  color: #721c24;
}

.review-detail__loading {
  padding: 2rem;
  text-align: center;
  color: #666;
}

.review-detail__error {
  padding: 0.75rem 1rem;
  background: #f8d7da;
  color: #721c24;
  border-radius: 4px;
  margin-bottom: 1rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.review-detail__error button {
  padding: 0.25rem 0.75rem;
  border: 1px solid #721c24;
  background: transparent;
  color: #721c24;
  border-radius: 4px;
  cursor: pointer;
}

.review-detail__success {
  padding: 0.75rem 1rem;
  background: #d4edda;
  color: #155724;
  border-radius: 4px;
  margin-bottom: 1rem;
}

.review-detail__content {
  max-width: 800px;
}

/* Form panel */
.review-detail__form-panel h2 {
  margin: 0 0 0.75rem;
  font-size: 1.2rem;
}

.review-detail__section {
  border: 1px solid #e6ddd0;
  border-radius: 6px;
  padding: 1rem;
  margin-bottom: 1rem;
}

.review-detail__section legend {
  font-weight: 600;
  font-size: 1rem;
  padding: 0 0.5rem;
}

.review-detail__field {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  margin-bottom: 0.75rem;
  padding: 0.4rem;
  border-radius: 4px;
  transition: background-color 0.2s;
}

.review-detail__field--low {
  background-color: #fff3cd;
  border-left: 3px solid #ffc107;
}

.review-detail__field label {
  font-size: 0.85rem;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 0.4rem;
}

.review-detail__field input,
.review-detail__field select,
.review-detail__field textarea {
  padding: 0.4rem 0.6rem;
  border: 1px solid #ccc;
  border-radius: 4px;
  font-size: 0.9rem;
  font-family: inherit;
}

.review-detail__field textarea {
  resize: vertical;
}

.review-detail__inline-action {
  display: flex;
  gap: 0.5rem;
  align-items: center;
}

.review-detail__inline-action input {
  flex: 1;
  padding: 0.4rem 0.6rem;
  border: 1px solid #ccc;
  border-radius: 4px;
  font-size: 0.9rem;
}

.review-detail__drawing-section {
  margin-top: 0.75rem;
  padding-top: 0.75rem;
  border-top: 1px solid #ede6db;
}

.review-detail__drawing-section h4 {
  margin: 0 0 0.5rem;
  font-size: 0.95rem;
}

.review-detail__actions {
  display: flex;
  gap: 1rem;
  margin-top: 1rem;
  padding-top: 1rem;
  border-top: 1px solid #e6ddd0;
}

.review-detail__btn {
  padding: 0.6rem 1.5rem;
  border: none;
  border-radius: 4px;
  font-size: 0.95rem;
  font-weight: 600;
  cursor: pointer;
}

.review-detail__btn:disabled {
  opacity: 0.5;
  cursor: default;
}

.review-detail__btn--save {
  background: #0d6efd;
  color: #fff;
}

.review-detail__btn--save:hover:not(:disabled) {
  background: #0b5ed7;
}

.review-detail__btn--approve {
  background: #198754;
  color: #fff;
}

.review-detail__btn--approve:hover:not(:disabled) {
  background: #157347;
}

/* Audit timeline */
.review-detail__audit { margin-bottom: 1.5rem; border: 1px solid #e6ddd0; border-radius: 6px; padding: 1rem; background: #f5f0e8; }
.review-detail__audit h2 { margin: 0 0 0.75rem; font-size: 1rem; }
.review-detail__audit-loading, .review-detail__audit-empty { font-size: 0.8rem; color: #999; }
.review-detail__audit-list { display: flex; flex-direction: column; gap: 0.4rem; max-height: 300px; overflow-y: auto; }
.review-detail__audit-entry { padding: 0.4rem 0.5rem; border-radius: 4px; background: #faf7f2; border: 1px solid #ede6db; }
.review-detail__audit-entry--clickable { cursor: pointer; }
.review-detail__audit-entry--clickable:hover { border-color: #ccc; }
.review-detail__audit-header { display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap; font-size: 0.8rem; }
.review-detail__audit-action { display: inline-block; padding: 0.1rem 0.4rem; border-radius: 8px; font-size: 0.7rem; font-weight: 600; }
.review-detail__audit-user { font-weight: 600; color: #333; }
.review-detail__audit-time { color: #999; font-size: 0.75rem; margin-left: auto; }
.review-detail__audit-expand { font-size: 0.75rem; color: #888; }
.review-detail__audit-diff { margin-top: 0.4rem; padding: 0.4rem; background: #f5f0e8; border-radius: 3px; font-family: monospace; font-size: 0.75rem; }
.review-detail__audit-diff-line { display: flex; gap: 0.4rem; align-items: baseline; padding: 0.1rem 0; }
.review-detail__audit-diff-field { color: #555; min-width: 140px; font-weight: 600; }
.review-detail__audit-diff-old { color: #c0392b; text-decoration: line-through; }
.review-detail__audit-diff-arrow { color: #999; }
.review-detail__audit-diff-new { color: #27ae60; font-weight: 600; }

/* Responsive: stack vertically on narrow screens */
@media (max-width: 900px) {
  .review-detail__actions {
    flex-direction: column;
  }
}
</style>

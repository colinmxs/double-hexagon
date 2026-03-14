<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api'

interface AuditEntry {
  timestamp: string
  user_id: string
  user_name: string
  action_type: string
  resource_type: string
  resource_id: string
  details?: Record<string, unknown>
}

const entries = ref<AuditEntry[]>([])
const isLoading = ref(false)
const error = ref('')
const isExporting = ref(false)

const filters = ref({
  user: '',
  action_type: '',
  resource_type: '',
  date_from: '',
  date_to: '',
})

async function fetchEntries() {
  isLoading.value = true
  error.value = ''
  try {
    const params = new URLSearchParams()
    if (filters.value.user) params.set('user', filters.value.user)
    if (filters.value.action_type) params.set('action_type', filters.value.action_type)
    if (filters.value.resource_type) params.set('resource_type', filters.value.resource_type)
    if (filters.value.date_from) params.set('date_from', filters.value.date_from)
    if (filters.value.date_to) params.set('date_to', filters.value.date_to)
    const qs = params.toString()
    const res = await fetch(`${API_BASE}/audit-log${qs ? '?' + qs : ''}`)
    if (!res.ok) throw new Error()
    const data = await res.json()
    entries.value = data.entries ?? []
  } catch {
    error.value = 'audit.errorLoading'
  } finally {
    isLoading.value = false
  }
}

async function exportCsv() {
  isExporting.value = true
  try {
    const body: Record<string, string> = {}
    if (filters.value.user) body.user = filters.value.user
    if (filters.value.action_type) body.action_type = filters.value.action_type
    if (filters.value.resource_type) body.resource_type = filters.value.resource_type
    if (filters.value.date_from) body.date_from = filters.value.date_from
    if (filters.value.date_to) body.date_to = filters.value.date_to
    const res = await fetch(`${API_BASE}/audit-log/export`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!res.ok) throw new Error()
    const csv = await res.text()
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = 'audit_log.csv'
    link.style.display = 'none'
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
  } catch {
    error.value = 'audit.exportError'
  } finally {
    isExporting.value = false
  }
}

const ACTION_TYPES = ['view', 'create', 'update', 'delete', 'export', 'login', 'logout']

onMounted(fetchEntries)
</script>

<template>
  <div class="audit-view">
    <h1>{{ t('nav.audit') }}</h1>

    <!-- Filters -->
    <div class="audit-view__filters">
      <input v-model="filters.user" type="text" :placeholder="t('audit.filterUser')" class="audit-view__input" />
      <select v-model="filters.action_type" class="audit-view__select">
        <option value="">{{ t('audit.allActions') }}</option>
        <option v-for="a in ACTION_TYPES" :key="a" :value="a">{{ a }}</option>
      </select>
      <input v-model="filters.resource_type" type="text" :placeholder="t('audit.filterResource')" class="audit-view__input" />
      <input v-model="filters.date_from" type="date" class="audit-view__input" />
      <input v-model="filters.date_to" type="date" class="audit-view__input" />
      <button class="audit-view__btn" :disabled="isLoading" @click="fetchEntries">{{ t('common.filter') }}</button>
      <button class="audit-view__btn audit-view__btn--secondary" :disabled="isExporting" @click="exportCsv">
        {{ isExporting ? t('common.loading') : t('audit.exportCsv') }}
      </button>
    </div>

    <div v-if="error" class="audit-view__error" role="alert">{{ t(error) }}</div>
    <div v-if="isLoading" class="audit-view__loading" role="status">{{ t('common.loading') }}</div>

    <table v-else-if="entries.length" class="audit-view__table" aria-label="Audit Log">
      <thead>
        <tr>
          <th scope="col">{{ t('audit.timestamp') }}</th>
          <th scope="col">{{ t('audit.userName') }}</th>
          <th scope="col">{{ t('audit.actionType') }}</th>
          <th scope="col">{{ t('audit.resourceType') }}</th>
          <th scope="col">{{ t('audit.resourceId') }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(e, i) in entries" :key="i">
          <td>{{ e.timestamp }}</td>
          <td>{{ e.user_name }}</td>
          <td>{{ e.action_type }}</td>
          <td>{{ e.resource_type }}</td>
          <td>{{ e.resource_id }}</td>
        </tr>
      </tbody>
    </table>
    <div v-else class="audit-view__empty">{{ t('audit.noEntries') }}</div>
  </div>
</template>

<style scoped>
.audit-view { padding: 1rem; }
.audit-view h1 { margin: 0 0 1rem; font-size: 1.5rem; }

.audit-view__filters { display: flex; gap: 0.5rem; flex-wrap: wrap; margin-bottom: 1rem; align-items: center; }
.audit-view__input { padding: 0.35rem 0.5rem; border: 1px solid #ccc; border-radius: 4px; font-size: 0.85rem; }
.audit-view__select { padding: 0.35rem 0.5rem; border: 1px solid #ccc; border-radius: 4px; font-size: 0.85rem; }
.audit-view__btn { padding: 0.4rem 1rem; border: 1px solid #4a90d9; background: #4a90d9; color: #fff; border-radius: 4px; font-size: 0.85rem; cursor: pointer; }
.audit-view__btn:hover:not(:disabled) { background: #357abd; }
.audit-view__btn:disabled { opacity: 0.6; cursor: not-allowed; }
.audit-view__btn--secondary { background: #fff; color: #4a90d9; }

.audit-view__table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
.audit-view__table th, .audit-view__table td { padding: 0.5rem 0.6rem; text-align: left; border-bottom: 1px solid #e0e0e0; }
.audit-view__table th { background: #f5f5f5; font-weight: 600; white-space: nowrap; }

.audit-view__loading { padding: 1.5rem; text-align: center; color: #666; }
.audit-view__empty { padding: 1.5rem; text-align: center; color: #666; }
.audit-view__error { padding: 0.5rem 0.75rem; background: #f8d7da; color: #721c24; border-radius: 4px; margin-bottom: 0.75rem; font-size: 0.85rem; }
</style>

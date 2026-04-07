<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useApi } from '../composables/useApi'

const route = useRoute()
const { apiFetch } = useApi()

interface Change {
  field_name: string
  previous_value: string | null
  new_value: string | null
}

interface AuditEntry {
  timestamp: string
  user_id: string
  user_name: string
  action_type: string
  resource_type: string
  resource_id: string
  details?: { changes?: Change[]; [key: string]: unknown }
}

type SearchMode = 'resource'

const entries = ref<AuditEntry[]>([])
const expandedRow = ref<number | null>(null)
const isLoading = ref(false)
const error = ref('')
const searchMode = ref<SearchMode>('resource')
const searchQuery = ref('')
const hasSearched = ref(false)

function formatTimestamp(ts: string): string {
  try {
    const d = new Date(ts)
    return d.toLocaleString()
  } catch {
    return ts
  }
}

function actionColor(action: string): string {
  const map: Record<string, string> = {
    create: '#155724',
    view: '#004085',
    update: '#856404',
    delete: '#721c24',
    export: '#6f42c1',
  }
  return map[action] || '#333'
}

function actionBg(action: string): string {
  const map: Record<string, string> = {
    create: '#d4edda',
    view: '#cce5ff',
    update: '#fff3cd',
    delete: '#f8d7da',
    export: '#e8daef',
  }
  return map[action] || '#f0f0f0'
}

function getChanges(entry: AuditEntry): Change[] {
  return entry.details?.changes ?? []
}

function changeSummary(entry: AuditEntry): string {
  const changes = getChanges(entry)
  if (changes.length === 0) {
    if (entry.action_type === 'create') return 'Application created'
    if (entry.action_type === 'view') return 'Viewed'
    if (entry.action_type === 'export') return entry.details?.export_type as string || 'Exported'
    return ''
  }
  if (changes.length === 1) {
    const c = changes[0]
    const field = c.field_name.split('.').pop() || c.field_name
    return `${field}: ${c.previous_value ?? '∅'} → ${c.new_value ?? '∅'}`
  }
  return `${changes.length} fields changed`
}

function toggleRow(i: number) {
  expandedRow.value = expandedRow.value === i ? null : i
}

const userSearchName = ref('')

async function searchByUser(userId: string, userName: string) {
  isLoading.value = true
  error.value = ''
  hasSearched.value = true
  searchQuery.value = ''
  userSearchName.value = userName || userId
  try {
    const res = await apiFetch(`/audit-log?user=${encodeURIComponent(userId)}`)
    if (!res.ok) throw new Error()
    const data = await res.json()
    entries.value = data.entries ?? []
  } catch {
    error.value = 'Failed to query audit log'
  } finally {
    isLoading.value = false
  }
}

async function search() {
  if (!searchQuery.value.trim()) return
  isLoading.value = true
  error.value = ''
  hasSearched.value = true
  userSearchName.value = ''
  try {
    const res = await apiFetch(`/audit-log?resource_id=${encodeURIComponent(searchQuery.value.trim())}`)
    if (!res.ok) throw new Error()
    const data = await res.json()
    entries.value = data.entries ?? []
  } catch {
    error.value = 'Failed to query audit log'
  } finally {
    isLoading.value = false
  }
}

async function loadRecent() {
  isLoading.value = true
  error.value = ''
  hasSearched.value = false
  searchQuery.value = ''
  userSearchName.value = ''
  try {
    const res = await apiFetch('/audit-log')
    if (!res.ok) throw new Error()
    const data = await res.json()
    entries.value = data.entries ?? []
  } catch {
    error.value = 'Failed to load audit log'
  } finally {
    isLoading.value = false
  }
}

onMounted(() => {
  const userParam = route.query.user as string | undefined
  if (userParam) {
    searchByUser(userParam, userParam)
  } else {
    loadRecent()
  }
})
</script>

<template>
  <div class="audit-view">
    <h1>Audit Log</h1>

    <div class="audit-view__search">
      <input
        v-model="searchQuery"
        type="text"
        :placeholder="'Search by ref # (e.g. 2026-0042)'"
        class="audit-view__input"
        @keydown.enter="search"
      />
      <button class="audit-view__btn" :disabled="isLoading || !searchQuery.trim()" @click="search">
        Search
      </button>
      <button class="audit-view__btn audit-view__btn--secondary" :disabled="isLoading" @click="loadRecent">
        Show Recent
      </button>
    </div>

    <div v-if="error" class="audit-view__error" role="alert">{{ error }}</div>
    <div v-if="isLoading" class="audit-view__loading" role="status">Loading...</div>

    <div v-if="hasSearched && !isLoading" class="audit-view__result-header">
      {{ entries.length }} {{ entries.length === 1 ? 'entry' : 'entries' }}
      <span v-if="userSearchName"> for user <strong>{{ userSearchName }}</strong></span>
      <span v-else-if="searchQuery"> for <strong>{{ searchQuery }}</strong></span>
    </div>

    <table v-if="entries.length && !isLoading" class="audit-view__table" aria-label="Audit Log">
      <thead>
        <tr>
          <th scope="col">When</th>
          <th scope="col">Who</th>
          <th scope="col">Action</th>
          <th scope="col">Ref #</th>
          <th scope="col">Details</th>
        </tr>
      </thead>
      <tbody>
        <template v-for="(e, i) in entries" :key="i">
          <tr :class="{ 'audit-view__row--clickable': getChanges(e).length > 1 }" @click="getChanges(e).length > 1 ? toggleRow(i) : null">
            <td class="audit-view__ts">{{ formatTimestamp(e.timestamp) }}</td>
            <td>
              <button class="audit-view__user-link" @click.stop="searchByUser(e.user_id, e.user_name)">
                {{ e.user_name || e.user_id }}
              </button>
            </td>
            <td>
              <span class="audit-view__action" :style="{ color: actionColor(e.action_type), background: actionBg(e.action_type) }">
                {{ e.action_type }}
              </span>
            </td>
            <td >
              <button class="audit-view__resource-link" @click.stop="searchQuery = e.resource_id; searchMode = 'resource'; search()">
                {{ e.resource_id }}
              </button>
            </td>
            <td class="audit-view__details">
              <span class="audit-view__summary">{{ changeSummary(e) }}</span>
              <span v-if="getChanges(e).length > 1" class="audit-view__expand">
                {{ expandedRow === i ? '▾' : '▸' }}
              </span>
            </td>
          </tr>
          <tr v-if="expandedRow === i && getChanges(e).length > 1" class="audit-view__diff-row">
            <td :colspan="5">
              <div class="audit-view__diff">
                <div v-for="(c, ci) in getChanges(e)" :key="ci" class="audit-view__diff-line">
                  <span class="audit-view__diff-field">{{ c.field_name }}</span>
                  <span class="audit-view__diff-old">{{ c.previous_value ?? '∅' }}</span>
                  <span class="audit-view__diff-arrow">→</span>
                  <span class="audit-view__diff-new">{{ c.new_value ?? '∅' }}</span>
                </div>
              </div>
            </td>
          </tr>
        </template>
      </tbody>
    </table>

    <div v-else-if="!isLoading && !error && hasSearched" class="audit-view__empty">
      No audit entries found.
    </div>
  </div>
</template>

<style scoped>
.audit-view { padding: 1.25rem 1.5rem; max-width: 1280px; margin: 0 auto; }
.audit-view h1 { margin: 0 0 1rem; font-size: 1.4rem; font-weight: 800; color: #3d2e1f; }

.audit-view__search { display: flex; gap: 0.5rem; margin-bottom: 1rem; align-items: center; }
.audit-view__input { padding: 0.45rem 0.65rem; border: 1px solid #d4c4a8; border-radius: 6px; font-size: 0.85rem; flex: 1; max-width: 400px; background: #fff; color: #3d2e1f; }
.audit-view__btn { padding: 0.4rem 1rem; border: none; background: #e8860c; color: #fff; border-radius: 6px; font-size: 0.85rem; font-weight: 600; cursor: pointer; }
.audit-view__btn:hover:not(:disabled) { background: #cf7609; }
.audit-view__btn:disabled { opacity: 0.5; cursor: not-allowed; }
.audit-view__btn--secondary { background: #fff; color: #3d2e1f; border: 1px solid #d4c4a8; }
.audit-view__btn--secondary:hover:not(:disabled) { background: #f5f0e8; }

.audit-view__result-header { font-size: 0.85rem; color: #8b7355; margin-bottom: 0.75rem; }

.audit-view__table { width: 100%; border-collapse: collapse; font-size: 0.85rem; border: 1px solid #d4c4a8; border-radius: 10px; overflow: hidden; background: #fff; box-shadow: 0 1px 3px rgba(61,46,31,0.06); }
.audit-view__table th, .audit-view__table td { padding: 0.6rem 0.75rem; text-align: left; }
.audit-view__table th { background: #3d2e1f; font-weight: 700; font-size: 0.75rem; color: #f5f0e8; text-transform: uppercase; letter-spacing: 0.04em; white-space: nowrap; border-bottom: none; }
.audit-view__table td { border-bottom: 1px solid #ede6db; color: #3d2e1f; }
.audit-view__table tbody tr:nth-child(even) { background: #faf7f2; }
.audit-view__table tbody tr:hover { background: #fef3e2; }
.audit-view__ts { white-space: nowrap; color: #8b7355; font-size: 0.8rem; }

.audit-view__action { display: inline-block; padding: 0.1rem 0.5rem; border-radius: 10px; font-size: 0.75rem; font-weight: 600; }

.audit-view__resource-link { background: none; border: none; color: #e8860c; cursor: pointer; font-size: 0.85rem; padding: 0; }
.audit-view__resource-link:hover { text-decoration: underline; }

.audit-view__user-link { background: none; border: none; color: #3d2e1f; cursor: pointer; font-size: 0.85rem; padding: 0; font-weight: 600; }
.audit-view__user-link:hover { text-decoration: underline; color: #e8860c; }

.audit-view__details { font-size: 0.8rem; }
.audit-view__summary { color: #8b7355; }
.audit-view__expand { margin-left: 0.3rem; color: #c4b49a; font-size: 0.7rem; }
.audit-view__row--clickable { cursor: pointer; }
.audit-view__row--clickable:hover { background: #fef3e2; }

.audit-view__diff-row td { padding: 0 0.6rem 0.5rem; background: #f5f0e8; }
.audit-view__diff { display: flex; flex-direction: column; gap: 0.2rem; padding: 0.4rem 0.6rem; background: #fff; border: 1px solid #ede6db; border-radius: 6px; font-size: 0.8rem; font-family: monospace; }
.audit-view__diff-line { display: flex; gap: 0.5rem; align-items: baseline; }
.audit-view__diff-field { color: #8b7355; min-width: 180px; font-weight: 600; }
.audit-view__diff-old { color: #c0392b; text-decoration: line-through; }
.audit-view__diff-arrow { color: #c4b49a; }
.audit-view__diff-new { color: #27ae60; font-weight: 600; }

.audit-view__loading { padding: 1.5rem; text-align: center; color: #8b7355; }
.audit-view__empty { padding: 1.5rem; text-align: center; color: #8b7355; }
.audit-view__error { padding: 0.5rem 0.75rem; background: #f8d7da; color: #721c24; border-radius: 4px; margin-bottom: 0.75rem; font-size: 0.85rem; }
</style>

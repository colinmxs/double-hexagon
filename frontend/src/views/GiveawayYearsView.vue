<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api'

interface GiveawayYear {
  year: string
  is_active: boolean
  status: string
}

const years = ref<GiveawayYear[]>([])
const isLoading = ref(false)
const error = ref('')
const actionLoading = ref('')
const newYear = ref('')

async function fetchYears() {
  isLoading.value = true
  error.value = ''
  try {
    const res = await fetch(`${API_BASE}/giveaway-years`)
    if (!res.ok) throw new Error()
    years.value = await res.json()
  } catch {
    error.value = 'years.errorLoading'
  } finally {
    isLoading.value = false
  }
}

async function setActive(year: string) {
  actionLoading.value = 'active-' + year
  error.value = ''
  try {
    const res = await fetch(`${API_BASE}/giveaway-years/active`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ year }),
    })
    if (!res.ok) throw new Error()
    await fetchYears()
  } catch {
    error.value = 'years.actionError'
  } finally {
    actionLoading.value = ''
  }
}

async function createYear() {
  if (!newYear.value.trim()) return
  actionLoading.value = 'create'
  error.value = ''
  try {
    const res = await fetch(`${API_BASE}/giveaway-years/active`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ year: newYear.value.trim() }),
    })
    if (!res.ok) throw new Error()
    newYear.value = ''
    await fetchYears()
  } catch {
    error.value = 'years.actionError'
  } finally {
    actionLoading.value = ''
  }
}

async function archiveYear(year: string) {
  if (!confirm(t('years.archiveConfirm', { year }))) return
  actionLoading.value = 'archive-' + year
  error.value = ''
  try {
    const res = await fetch(`${API_BASE}/giveaway-years/${year}/archive`, { method: 'POST' })
    if (!res.ok) throw new Error()
    await fetchYears()
  } catch {
    error.value = 'years.actionError'
  } finally {
    actionLoading.value = ''
  }
}

async function deleteYear(year: string) {
  if (!confirm(t('years.deleteConfirm', { year }))) return
  actionLoading.value = 'delete-' + year
  error.value = ''
  try {
    const res = await fetch(`${API_BASE}/giveaway-years/${year}/delete`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ confirm: true }),
    })
    if (!res.ok) throw new Error()
    await fetchYears()
  } catch {
    error.value = 'years.actionError'
  } finally {
    actionLoading.value = ''
  }
}

onMounted(fetchYears)
</script>

<template>
  <div class="years-view">
    <h1>{{ t('nav.years') }}</h1>

    <div v-if="error" class="years-view__error" role="alert">{{ t(error) }}</div>

    <!-- Create new year -->
    <div class="years-view__create">
      <input v-model="newYear" type="text" :placeholder="t('years.newYearPlaceholder')" class="years-view__input" />
      <button class="years-view__btn" :disabled="!!actionLoading || !newYear.trim()" @click="createYear">
        {{ t('years.createYear') }}
      </button>
    </div>

    <div v-if="isLoading" class="years-view__loading" role="status">{{ t('common.loading') }}</div>

    <table v-else-if="years.length" class="years-view__table" aria-label="Giveaway Years">
      <thead>
        <tr>
          <th scope="col">{{ t('years.year') }}</th>
          <th scope="col">{{ t('users.status') }}</th>
          <th scope="col">{{ t('users.actionsCol') }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="y in years" :key="y.year">
          <td>
            {{ y.year }}
            <span v-if="y.is_active" class="years-view__active-badge">★ {{ t('years.active') }}</span>
          </td>
          <td>{{ y.status || 'active' }}</td>
          <td class="years-view__actions">
            <button v-if="!y.is_active" class="years-view__link" :disabled="!!actionLoading" @click="setActive(y.year)">
              {{ t('years.setActive') }}
            </button>
            <button v-if="y.status !== 'archived'" class="years-view__link years-view__link--warn" :disabled="!!actionLoading" @click="archiveYear(y.year)">
              {{ t('years.archive') }}
            </button>
            <button class="years-view__link years-view__link--danger" :disabled="!!actionLoading" @click="deleteYear(y.year)">
              {{ t('common.delete') }}
            </button>
          </td>
        </tr>
      </tbody>
    </table>
    <div v-else class="years-view__empty">{{ t('years.noYears') }}</div>
  </div>
</template>

<style scoped>
.years-view { padding: 1rem; }
.years-view h1 { margin: 0 0 1rem; font-size: 1.5rem; }

.years-view__create { display: flex; gap: 0.5rem; margin-bottom: 1rem; }
.years-view__input { padding: 0.35rem 0.5rem; border: 1px solid #ccc; border-radius: 4px; font-size: 0.85rem; width: 120px; }
.years-view__btn { padding: 0.4rem 1rem; border: 1px solid #4a90d9; background: #4a90d9; color: #fff; border-radius: 4px; font-size: 0.85rem; cursor: pointer; }
.years-view__btn:hover:not(:disabled) { background: #357abd; }
.years-view__btn:disabled { opacity: 0.6; cursor: not-allowed; }

.years-view__table { width: 100%; border-collapse: collapse; font-size: 0.85rem; max-width: 600px; }
.years-view__table th, .years-view__table td { padding: 0.5rem 0.6rem; text-align: left; border-bottom: 1px solid #e0e0e0; }
.years-view__table th { background: #f5f5f5; font-weight: 600; }

.years-view__active-badge { background: #d4edda; color: #155724; padding: 0.1rem 0.4rem; border-radius: 10px; font-size: 0.75rem; font-weight: 600; margin-left: 0.4rem; }

.years-view__actions { display: flex; gap: 0.5rem; flex-wrap: wrap; }
.years-view__link { background: none; border: none; color: #4a90d9; cursor: pointer; font-size: 0.8rem; padding: 0.15rem 0; }
.years-view__link:hover { text-decoration: underline; }
.years-view__link--warn { color: #e67e22; }
.years-view__link--danger { color: #d94a4a; }
.years-view__link:disabled { opacity: 0.5; cursor: not-allowed; }

.years-view__loading { padding: 1.5rem; text-align: center; color: #666; }
.years-view__empty { padding: 1.5rem; text-align: center; color: #666; }
.years-view__error { padding: 0.5rem 0.75rem; background: #f8d7da; color: #721c24; border-radius: 4px; margin-bottom: 0.75rem; font-size: 0.85rem; }
</style>

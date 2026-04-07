<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useApi } from '../composables/useApi'

const { t } = useI18n()
const { apiFetch } = useApi()

interface User {
  user_id: string
  name: string
  email: string
  role: string
  authorized_giveaway_years: string[]
  status: string
  last_login: string
}

const users = ref<User[]>([])
const isLoading = ref(false)
const error = ref('')

// Create form
const showCreate = ref(false)
const createForm = ref({ name: '', email: '', role: 'reporter', authorized_giveaway_years: '' })
const createLoading = ref(false)
const createError = ref('')

// Edit form
const editingUser = ref<User | null>(null)
const editForm = ref({ role: '', authorized_giveaway_years: '', name: '' })
const editLoading = ref(false)
const editError = ref('')

const actionLoading = ref('')
const actionError = ref('')

async function fetchUsers() {
  isLoading.value = true
  error.value = ''
  try {
    const res = await apiFetch('/users')
    if (!res.ok) throw new Error()
    const data = await res.json()
    users.value = data.users ?? []
  } catch {
    error.value = 'users.errorLoading'
  } finally {
    isLoading.value = false
  }
}

async function createUser() {
  createLoading.value = true
  createError.value = ''
  try {
    const years = createForm.value.authorized_giveaway_years
      .split(',').map(s => s.trim()).filter(Boolean)
    const res = await apiFetch('/users', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: createForm.value.name,
        email: createForm.value.email,
        role: createForm.value.role,
        authorized_giveaway_years: years,
      }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      createError.value = err.error || 'users.createError'
      return
    }
    showCreate.value = false
    createForm.value = { name: '', email: '', role: 'reporter', authorized_giveaway_years: '' }
    await fetchUsers()
  } catch {
    createError.value = 'users.createError'
  } finally {
    createLoading.value = false
  }
}

function startEdit(user: User) {
  editingUser.value = user
  editForm.value = {
    role: user.role,
    authorized_giveaway_years: (user.authorized_giveaway_years || []).join(', '),
    name: user.name,
  }
  editError.value = ''
}

async function saveEdit() {
  if (!editingUser.value) return
  editLoading.value = true
  editError.value = ''
  try {
    const years = editForm.value.authorized_giveaway_years
      .split(',').map(s => s.trim()).filter(Boolean)
    const res = await apiFetch(`/users/${editingUser.value.user_id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        role: editForm.value.role,
        authorized_giveaway_years: years,
        name: editForm.value.name,
      }),
    })
    if (!res.ok) throw new Error()
    editingUser.value = null
    await fetchUsers()
  } catch {
    editError.value = 'users.editError'
  } finally {
    editLoading.value = false
  }
}

async function userAction(userId: string, action: 'disable' | 'enable' | 'delete' | 'reset_password') {
  if (action === 'delete' && !confirm(t('users.deleteConfirm'))) return
  actionLoading.value = userId + action
  actionError.value = ''
  try {
    let url: string
    let method: string
    let body: string | undefined
    if (action === 'disable') {
      url = `/users/${userId}/disable`; method = 'POST'
    } else if (action === 'enable') {
      url = `/users/${userId}/enable`; method = 'POST'
    } else if (action === 'delete') {
      url = `/users/${userId}`; method = 'DELETE'
    } else {
      url = `/users/${userId}`; method = 'PUT'
      body = JSON.stringify({ reset_password: true })
    }
    const opts: RequestInit = { method, headers: { 'Content-Type': 'application/json' } }
    if (body) opts.body = body
    const res = await apiFetch(url, opts)
    if (!res.ok) throw new Error()
    await fetchUsers()
  } catch {
    actionError.value = 'users.actionError'
  } finally {
    actionLoading.value = ''
  }
}

onMounted(fetchUsers)
</script>

<template>
  <div class="users-view">
    <div class="users-view__header">
      <h1>{{ t('nav.users') }}</h1>
      <button class="users-view__btn" @click="showCreate = !showCreate">
        {{ showCreate ? t('common.cancel') : t('users.createUser') }}
      </button>
    </div>

    <div v-if="error" class="users-view__error" role="alert">{{ t(error) }}</div>
    <div v-if="actionError" class="users-view__error" role="alert">{{ t(actionError) }}</div>

    <!-- Create form -->
    <div v-if="showCreate" class="users-view__form">
      <h2>{{ t('users.createUser') }}</h2>
      <div class="users-view__field">
        <label>{{ t('users.name') }}</label>
        <input v-model="createForm.name" type="text" class="users-view__input" />
      </div>
      <div class="users-view__field">
        <label>{{ t('form.email') }}</label>
        <input v-model="createForm.email" type="email" class="users-view__input" />
      </div>
      <div class="users-view__field">
        <label>{{ t('users.role') }}</label>
        <select v-model="createForm.role" class="users-view__select">
          <option value="admin">Admin</option>
          <option value="reporter">Reporter</option>
          <option value="submitter">Submitter</option>
        </select>
      </div>
      <div class="users-view__field">
        <label>{{ t('users.authorizedYears') }}</label>
        <input v-model="createForm.authorized_giveaway_years" type="text" :placeholder="t('users.yearsPlaceholder')" class="users-view__input" />
      </div>
      <div v-if="createError" class="users-view__error" role="alert">{{ createError.startsWith('users.') ? t(createError) : createError }}</div>
      <button class="users-view__btn" :disabled="createLoading" @click="createUser">
        {{ createLoading ? t('common.loading') : t('users.createUser') }}
      </button>
    </div>

    <!-- Edit modal -->
    <div v-if="editingUser" class="users-view__form">
      <h2>{{ t('users.editUser') }}: {{ editingUser.name }}</h2>
      <div class="users-view__field">
        <label>{{ t('users.name') }}</label>
        <input v-model="editForm.name" type="text" class="users-view__input" />
      </div>
      <div class="users-view__field">
        <label>{{ t('users.role') }}</label>
        <select v-model="editForm.role" class="users-view__select">
          <option value="admin">Admin</option>
          <option value="reporter">Reporter</option>
          <option value="submitter">Submitter</option>
        </select>
      </div>
      <div class="users-view__field">
        <label>{{ t('users.authorizedYears') }}</label>
        <input v-model="editForm.authorized_giveaway_years" type="text" class="users-view__input" />
      </div>
      <div v-if="editError" class="users-view__error" role="alert">{{ t(editError) }}</div>
      <div class="users-view__actions">
        <button class="users-view__btn" :disabled="editLoading" @click="saveEdit">
          {{ editLoading ? t('common.loading') : t('common.save') }}
        </button>
        <button class="users-view__btn users-view__btn--secondary" @click="editingUser = null">{{ t('common.cancel') }}</button>
      </div>
    </div>

    <!-- User table -->
    <div v-if="isLoading" class="users-view__loading" role="status">{{ t('common.loading') }}</div>
    <table v-else-if="users.length" class="users-view__table" aria-label="Users">
      <thead>
        <tr>
          <th scope="col">{{ t('users.name') }}</th>
          <th scope="col">{{ t('form.email') }}</th>
          <th scope="col">{{ t('users.role') }}</th>
          <th scope="col">{{ t('users.authorizedYears') }}</th>
          <th scope="col">{{ t('users.status') }}</th>
          <th scope="col">{{ t('users.lastLogin') }}</th>
          <th scope="col">{{ t('users.actionsCol') }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="u in users" :key="u.user_id">
          <td>
            <router-link :to="`/admin/audit?user=${u.user_id}`" class="users-view__name-link">
              {{ u.name }}
            </router-link>
          </td>
          <td>{{ u.email }}</td>
          <td>{{ u.role }}</td>
          <td>{{ (u.authorized_giveaway_years || []).join(', ') || '—' }}</td>
          <td>
            <span :class="['users-view__status', u.status === 'active' ? 'users-view__status--active' : 'users-view__status--inactive']">
              {{ u.status }}
            </span>
          </td>
          <td>{{ u.last_login || '—' }}</td>
          <td class="users-view__actions-cell">
            <button class="users-view__link" @click="startEdit(u)">{{ t('common.edit') }}</button>
            <button v-if="u.status === 'active'" class="users-view__link users-view__link--warn" :disabled="!!actionLoading" @click="userAction(u.user_id, 'disable')">{{ t('users.deactivate') }}</button>
            <button v-else class="users-view__link" :disabled="!!actionLoading" @click="userAction(u.user_id, 'enable')">{{ t('users.enable') }}</button>
            <button class="users-view__link" :disabled="!!actionLoading" @click="userAction(u.user_id, 'reset_password')">{{ t('users.resetPassword') }}</button>
            <button class="users-view__link users-view__link--danger" :disabled="!!actionLoading" @click="userAction(u.user_id, 'delete')">{{ t('common.delete') }}</button>
          </td>
        </tr>
      </tbody>
    </table>
    <div v-else class="users-view__empty">{{ t('users.noUsers') }}</div>
  </div>
</template>

<style scoped>
.users-view { padding: 1.25rem 1.5rem; max-width: 1280px; margin: 0 auto; }
.users-view__header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; }
.users-view h1 { margin: 0; font-size: 1.4rem; font-weight: 800; color: #3d2e1f; }
.users-view h2 { margin: 0 0 0.75rem; font-size: 1.1rem; color: #3d2e1f; }

.users-view__btn { padding: 0.4rem 1rem; border: none; background: #e8860c; color: #fff; border-radius: 6px; font-size: 0.85rem; font-weight: 600; cursor: pointer; }
.users-view__btn:hover:not(:disabled) { background: #cf7609; }
.users-view__btn:disabled { opacity: 0.6; cursor: not-allowed; }
.users-view__btn--secondary { background: #fff; color: #e8860c; border: 1.5px solid #e8860c; }

.users-view__form { padding: 1rem; background: #f5f0e8; border-radius: 6px; margin-bottom: 1rem; max-width: 500px; }
.users-view__field { margin-bottom: 0.6rem; }
.users-view__field label { display: block; font-size: 0.8rem; font-weight: 600; margin-bottom: 0.2rem; }
.users-view__input { padding: 0.35rem 0.5rem; border: 1px solid #d4c4a8; border-radius: 6px; font-size: 0.85rem; width: 100%; box-sizing: border-box; background: #fff; }
.users-view__select { padding: 0.35rem 0.5rem; border: 1px solid #d4c4a8; border-radius: 6px; font-size: 0.85rem; width: 100%; background: #fff; }
.users-view__actions { display: flex; gap: 0.5rem; margin-top: 0.5rem; }

.users-view__table { width: 100%; border-collapse: collapse; font-size: 0.85rem; border: 1px solid #d4c4a8; border-radius: 10px; overflow: hidden; background: #fff; box-shadow: 0 1px 3px rgba(61,46,31,0.06); }
.users-view__table th, .users-view__table td { padding: 0.6rem 0.75rem; text-align: left; }
.users-view__table th { background: #3d2e1f; font-weight: 700; font-size: 0.75rem; color: #f5f0e8; text-transform: uppercase; letter-spacing: 0.04em; white-space: nowrap; border-bottom: none; }
.users-view__table td { border-bottom: 1px solid #ede6db; color: #3d2e1f; }
.users-view__table tbody tr:nth-child(even) { background: #faf7f2; }
.users-view__table tbody tr:hover { background: #fef3e2; }

.users-view__status { padding: 0.15rem 0.5rem; border-radius: 10px; font-size: 0.75rem; font-weight: 600; }
.users-view__status--active { background: #d4edda; color: #155724; }
.users-view__status--inactive { background: #f8d7da; color: #721c24; }

.users-view__actions-cell { display: flex; gap: 0.25rem; flex-wrap: nowrap; white-space: nowrap; }
.users-view__link { background: none; border: none; color: #4a90d9; cursor: pointer; font-size: 0.75rem; padding: 0.15rem 0; white-space: nowrap; }
.users-view__link + .users-view__link::before { content: '·'; color: #ccc; margin-right: 0.25rem; }
.users-view__link:hover { text-decoration: underline; }
.users-view__link--warn { color: #e67e22; }
.users-view__link--danger { color: #d94a4a; }
.users-view__link:disabled { opacity: 0.5; cursor: not-allowed; }

.users-view__name-link { color: #3d2e1f; font-weight: 600; text-decoration: none; }
.users-view__name-link:hover { color: #e8860c; text-decoration: underline; }

.users-view__loading { padding: 1.5rem; text-align: center; color: #8b7355; }
.users-view__empty { padding: 1.5rem; text-align: center; color: #8b7355; }
.users-view__error { padding: 0.5rem 0.75rem; background: #f8d7da; color: #721c24; border-radius: 4px; margin-bottom: 0.75rem; font-size: 0.85rem; }
</style>

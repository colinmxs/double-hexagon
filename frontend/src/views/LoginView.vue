<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuth } from '../composables/useAuth'

const router = useRouter()
const { login, completeNewPassword, pendingChallenge, isAuthenticated } = useAuth()

const username = ref('')
const password = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const error = ref('')
const loading = ref(false)

async function handleLogin() {
  error.value = ''
  loading.value = true
  try {
    await login(username.value, password.value)
    if (isAuthenticated.value) {
      router.push('/admin/review')
    }
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : 'Login failed'
    if (msg !== 'NEW_PASSWORD_REQUIRED') {
      error.value = msg
    }
  } finally {
    loading.value = false
  }
}

async function handleNewPassword() {
  error.value = ''
  if (newPassword.value !== confirmPassword.value) {
    error.value = 'Passwords do not match'
    return
  }
  if (newPassword.value.length < 8) {
    error.value = 'Password must be at least 8 characters'
    return
  }
  loading.value = true
  try {
    await completeNewPassword(newPassword.value)
    if (isAuthenticated.value) {
      router.push('/admin/review')
    }
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : 'Password change failed'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login">
    <div class="login__card">
      <!-- New password form (first-time login) -->
      <template v-if="pendingChallenge">
        <h1 class="login__title">Set New Password</h1>
        <p class="login__subtitle">Your account requires a password change before you can continue.</p>
        <form class="login__form" @submit.prevent="handleNewPassword">
          <div v-if="error" class="login__error" role="alert">{{ error }}</div>
          <label class="login__label" for="new-pass">New Password</label>
          <input
            id="new-pass"
            v-model="newPassword"
            type="password"
            class="login__input"
            autocomplete="new-password"
            required
          />
          <label class="login__label" for="confirm-pass">Confirm Password</label>
          <input
            id="confirm-pass"
            v-model="confirmPassword"
            type="password"
            class="login__input"
            autocomplete="new-password"
            required
          />
          <button class="login__btn" type="submit" :disabled="loading || !newPassword || !confirmPassword">
            {{ loading ? 'Updating...' : 'Set Password' }}
          </button>
        </form>
      </template>

      <!-- Normal login form -->
      <template v-else>
        <h1 class="login__title">Staff Login</h1>
        <p class="login__subtitle">Sign in to access the admin dashboard</p>
        <form class="login__form" @submit.prevent="handleLogin">
          <div v-if="error" class="login__error" role="alert">{{ error }}</div>
          <label class="login__label" for="login-user">Username or Email</label>
          <input
            id="login-user"
            v-model="username"
            type="text"
            class="login__input"
            autocomplete="username"
            required
          />
          <label class="login__label" for="login-pass">Password</label>
          <input
            id="login-pass"
            v-model="password"
            type="password"
            class="login__input"
            autocomplete="current-password"
            required
          />
          <button class="login__btn" type="submit" :disabled="loading || !username || !password">
            {{ loading ? 'Signing in...' : 'Sign In' }}
          </button>
        </form>
      </template>
    </div>
  </div>
</template>

<style scoped>
.login { display: flex; align-items: center; justify-content: center; min-height: 70vh; padding: 2rem; }
.login__card { background: #fff; border: 1px solid #d4c4a8; border-radius: 12px; padding: 2rem; width: 100%; max-width: 380px; box-shadow: 0 2px 8px rgba(61,46,31,0.08); }
.login__title { margin: 0 0 0.25rem; font-size: 1.4rem; font-weight: 800; color: #3d2e1f; }
.login__subtitle { margin: 0 0 1.25rem; font-size: 0.85rem; color: #8b7355; }
.login__form { display: flex; flex-direction: column; gap: 0.5rem; }
.login__label { font-size: 0.75rem; font-weight: 700; color: #8b7355; text-transform: uppercase; letter-spacing: 0.04em; }
.login__input { padding: 0.5rem 0.65rem; border: 1px solid #d4c4a8; border-radius: 6px; font-size: 0.9rem; background: #fff; color: #3d2e1f; }
.login__input:focus { outline: none; border-color: #e8860c; box-shadow: 0 0 0 3px rgba(232,134,12,0.15); }
.login__btn { margin-top: 0.5rem; padding: 0.6rem; border: none; background: #e8860c; color: #fff; border-radius: 8px; font-size: 0.9rem; font-weight: 700; cursor: pointer; transition: background 0.15s; }
.login__btn:hover:not(:disabled) { background: #cf7609; }
.login__btn:disabled { opacity: 0.5; cursor: not-allowed; }
.login__error { padding: 0.5rem 0.75rem; background: #fef2f2; color: #991b1b; border: 1px solid #fecaca; border-radius: 6px; font-size: 0.85rem; }
</style>

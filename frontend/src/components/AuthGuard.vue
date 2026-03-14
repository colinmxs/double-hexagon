<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAuth } from '../composables/useAuth'

const props = defineProps<{
  requiredRole?: string
}>()

const { t } = useI18n()
const { authEnabled, isAuthenticated, user } = useAuth()

const allowed = computed(() => {
  if (!authEnabled) return true
  if (!isAuthenticated.value) return false
  if (!props.requiredRole) return true
  const current = user.value
  if (!current) return false
  if (current.role === 'admin') return true
  return current.role === props.requiredRole
})

const showForbidden = computed(() => {
  if (!authEnabled) return false
  return isAuthenticated.value && !allowed.value
})

const showLogin = computed(() => {
  if (!authEnabled) return false
  return !isAuthenticated.value
})
</script>

<template>
  <slot v-if="allowed" />
  <div v-else-if="showLogin" class="auth-guard" role="alert">
    <p>{{ t('auth.loginRequired') }}</p>
    <p class="auth-guard__redirect">{{ t('auth.loginRedirect') }}</p>
  </div>
  <div v-else-if="showForbidden" class="auth-guard" role="alert">
    <p>{{ t('auth.forbidden') }}</p>
  </div>
</template>

<style scoped>
.auth-guard {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px 24px;
  text-align: center;
  color: #555;
}

.auth-guard__redirect {
  font-size: 0.85rem;
  color: #888;
}
</style>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useSessionTimeout } from '../composables/useSessionTimeout'

const emit = defineEmits<{
  timeout: []
}>()

const { t } = useI18n()

const { showWarning, remainingMinutes, dismissWarning } = useSessionTimeout(
  () => emit('timeout'),
)
</script>

<template>
  <Teleport to="body">
    <div
      v-if="showWarning"
      class="session-timeout-overlay"
      role="alertdialog"
      aria-modal="true"
      :aria-label="t('session.warningTitle')"
    >
      <div class="session-timeout-dialog">
        <h2 class="session-timeout-dialog__title">{{ t('session.warningTitle') }}</h2>
        <p class="session-timeout-dialog__message">
          {{ t('session.warningMessage', { minutes: remainingMinutes }) }}
        </p>
        <button
          type="button"
          class="session-timeout-dialog__btn"
          @click="dismissWarning"
        >
          {{ t('session.stayLoggedIn') }}
        </button>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.session-timeout-overlay {
  position: fixed;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background-color: rgba(0, 0, 0, 0.5);
  z-index: 9999;
}

.session-timeout-dialog {
  background: #faf7f2;
  border-radius: 8px;
  padding: 24px 32px;
  max-width: 400px;
  width: 90%;
  text-align: center;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.2);
}

.session-timeout-dialog__title {
  margin: 0 0 12px;
  font-size: 1.2rem;
  color: #333;
}

.session-timeout-dialog__message {
  margin: 0 0 20px;
  color: #555;
  font-size: 0.95rem;
}

.session-timeout-dialog__btn {
  padding: 8px 24px;
  border: none;
  border-radius: 4px;
  background-color: #1a73e8;
  color: #fff;
  font-size: 0.9rem;
  font-weight: 600;
  cursor: pointer;
}

.session-timeout-dialog__btn:hover {
  background-color: #1557b0;
}
</style>

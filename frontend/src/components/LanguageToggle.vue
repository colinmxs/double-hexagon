<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { isSupportedLocale } from '../i18n'
import type { SupportedLocale } from '../i18n'

const { locale } = useI18n()

const toggle = computed(() => {
  const current = locale.value as SupportedLocale
  if (current === 'en') {
    return { target: 'es' as SupportedLocale, label: '¿Español?' }
  }
  return { target: 'en' as SupportedLocale, label: 'English?' }
})

function switchLocale() {
  const target = toggle.value.target
  if (!isSupportedLocale(target)) return
  locale.value = target
  localStorage.setItem('locale', target)
}
</script>

<template>
  <button
    type="button"
    class="language-toggle"
    :aria-label="`Switch language to ${toggle.target === 'es' ? 'Spanish' : 'English'}`"
    @click="switchLocale"
  >
    {{ toggle.label }}
  </button>
</template>

<style scoped>
.language-toggle {
  padding: 4px 12px;
  border: none;
  border-radius: 4px;
  background: transparent;
  cursor: pointer;
  font-size: 0.85rem;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.85);
  text-decoration: underline;
  text-underline-offset: 2px;
  transition: opacity 0.15s;
}

.language-toggle:hover {
  opacity: 0.75;
}
</style>

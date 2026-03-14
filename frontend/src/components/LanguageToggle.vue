<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { SUPPORTED_LOCALES, isSupportedLocale } from '../i18n'
import type { SupportedLocale } from '../i18n'

const { locale } = useI18n()

const labels: Record<SupportedLocale, string> = {
  en: 'EN',
  es: 'ES',
}

function switchLocale(target: SupportedLocale) {
  if (!isSupportedLocale(target)) return
  locale.value = target
  localStorage.setItem('locale', target)
}
</script>

<template>
  <nav class="language-toggle" aria-label="Language selection">
    <button
      v-for="loc in SUPPORTED_LOCALES"
      :key="loc"
      type="button"
      class="language-toggle__btn"
      :class="{ 'language-toggle__btn--active': locale === loc }"
      :aria-current="locale === loc ? 'true' : undefined"
      :aria-label="`Switch to ${labels[loc]}`"
      @click="switchLocale(loc)"
    >
      {{ labels[loc] }}
    </button>
  </nav>
</template>

<style scoped>
.language-toggle {
  display: inline-flex;
  gap: 4px;
}

.language-toggle__btn {
  padding: 4px 10px;
  border: 1px solid #ccc;
  border-radius: 4px;
  background: transparent;
  cursor: pointer;
  font-size: 0.85rem;
  font-weight: 600;
  color: #555;
  transition: background-color 0.15s, color 0.15s;
}

.language-toggle__btn--active {
  background-color: #1a73e8;
  color: #fff;
  border-color: #1a73e8;
}

.language-toggle__btn:hover:not(.language-toggle__btn--active) {
  background-color: #f0f0f0;
}
</style>

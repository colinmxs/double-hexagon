<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import LanguageToggle from './components/LanguageToggle.vue'

const { t } = useI18n()
</script>

<template>
  <div id="app-root">
    <header class="app-header">
      <h1 class="app-header__title">{{ t('app.tagline') }}</h1>
      <LanguageToggle />
    </header>
    <main>
      <router-view />
    </main>
  </div>
</template>

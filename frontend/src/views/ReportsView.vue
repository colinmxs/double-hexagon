<script setup lang="ts">
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
</script>

<template>
  <div class="reports-view">
    <h1>{{ t('nav.reports') }}</h1>
  </div>
</template>

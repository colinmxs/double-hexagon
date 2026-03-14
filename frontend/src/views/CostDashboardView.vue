<script setup lang="ts">
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
</script>

<template>
  <div class="cost-dashboard-view">
    <h1>{{ t('nav.cost') }}</h1>
  </div>
</template>

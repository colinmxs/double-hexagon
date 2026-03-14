<script setup lang="ts">
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
</script>

<template>
  <div class="audit-log-view">
    <h1>{{ t('nav.audit') }}</h1>
  </div>
</template>

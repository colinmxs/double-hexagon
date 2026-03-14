<script setup lang="ts">
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
</script>

<template>
  <div class="admin-layout">
    <nav class="admin-layout__nav" aria-label="Admin navigation">
      <router-link to="/admin/review">{{ t('nav.review') }}</router-link>
      <router-link to="/admin/reports">{{ t('nav.reports') }}</router-link>
      <router-link to="/admin/cost">{{ t('nav.cost') }}</router-link>
      <router-link to="/admin/users">{{ t('nav.users') }}</router-link>
      <router-link to="/admin/audit">{{ t('nav.audit') }}</router-link>
      <router-link to="/admin/years">{{ t('nav.years') }}</router-link>
    </nav>
    <div class="admin-layout__content">
      <router-view />
    </div>
  </div>
</template>

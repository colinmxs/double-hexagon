<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useApi } from '../composables/useApi'

const { t } = useI18n()
const { apiFetch } = useApi()

interface CostData {
  giveaway_year: string
  service_breakdown: Record<string, number>
  total_cost: number
  applications_total: number
  cost_per_application: number
}

const costData = ref<CostData | null>(null)
const isLoading = ref(false)
const error = ref('')

const serviceColors: Record<string, string> = {
  S3: '#4a90d9',
  CloudFront: '#50c878',
  Lambda: '#f5a623',
  'API Gateway': '#d94a4a',
  DynamoDB: '#9b59b6',
  Textract: '#1abc9c',
  Bedrock: '#e67e22',
}

async function fetchCostData() {
  isLoading.value = true
  error.value = ''
  try {
    const res = await apiFetch('/cost-dashboard')
    if (!res.ok) throw new Error()
    costData.value = await res.json()
  } catch {
    error.value = 'Failed to load cost data'
  } finally {
    isLoading.value = false
  }
}

onMounted(fetchCostData)
</script>

<template>
  <div class="cost-view">
    <h1>{{ t('cost.title') }}</h1>

    <div v-if="isLoading" class="cost-view__loading" role="status">{{ t('common.loading') }}</div>
    <div v-if="error" class="cost-view__error" role="alert">{{ error }}</div>

    <template v-if="costData && !isLoading">
      <div class="cost-view__year-banner">
        {{ costData.giveaway_year }} Giveaway Year
      </div>

      <div class="cost-view__summary">
        <div class="cost-view__stat cost-view__stat--primary">
          <span class="cost-view__stat-value">${{ costData.total_cost.toFixed(2) }}</span>
          <span class="cost-view__stat-label">Total AWS Cost</span>
        </div>
        <div class="cost-view__stat">
          <span class="cost-view__stat-value">{{ costData.applications_total }}</span>
          <span class="cost-view__stat-label">Applications</span>
        </div>
        <div class="cost-view__stat">
          <span class="cost-view__stat-value">${{ costData.cost_per_application.toFixed(2) }}</span>
          <span class="cost-view__stat-label">Cost per Application</span>
        </div>
      </div>

      <div class="cost-view__section">
        <h2>{{ t('cost.serviceBreakdown') }}</h2>
        <div class="cost-view__breakdown">
          <div v-for="(amount, svc) in costData.service_breakdown" :key="svc" class="cost-view__svc-row">
            <span class="cost-view__svc-name">
              <span class="cost-view__svc-dot" :style="{ background: serviceColors[svc as string] || '#999' }"></span>
              {{ svc }}
            </span>
            <span class="cost-view__svc-amount">${{ (amount as number).toFixed(2) }}</span>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.cost-view { padding: 1rem; }
.cost-view h1 { margin: 0 0 1rem; font-size: 1.5rem; }
.cost-view h2 { margin: 0 0 0.5rem; font-size: 1.1rem; }
.cost-view__loading { padding: 1.5rem; text-align: center; color: #666; }
.cost-view__error { padding: 0.5rem 0.75rem; background: #f8d7da; color: #721c24; border-radius: 4px; margin-bottom: 0.75rem; font-size: 0.85rem; }
.cost-view__year-banner { background: #2c3e50; color: #fff; padding: 0.6rem 1rem; border-radius: 6px; font-size: 1.1rem; font-weight: 700; margin-bottom: 1rem; display: inline-block; }
.cost-view__summary { display: flex; flex-wrap: wrap; gap: 2rem; margin-bottom: 1.5rem; padding: 1rem; background: #f5f0e8; border-radius: 6px; }
.cost-view__stat { display: flex; flex-direction: column; }
.cost-view__stat--primary .cost-view__stat-value { font-size: 2rem; color: #2c3e50; }
.cost-view__stat-value { font-size: 1.5rem; font-weight: 700; }
.cost-view__stat-label { font-size: 0.8rem; color: #555; font-weight: 600; }
.cost-view__section { margin-bottom: 1.5rem; }
.cost-view__breakdown { max-width: 400px; }
.cost-view__svc-row { display: flex; justify-content: space-between; align-items: center; padding: 0.4rem 0; font-size: 0.9rem; border-bottom: 1px solid #ede6db; }
.cost-view__svc-row:last-child { border-bottom: none; }
.cost-view__svc-name { display: flex; align-items: center; gap: 0.4rem; }
.cost-view__svc-dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
.cost-view__svc-amount { font-weight: 600; }
@media (max-width: 768px) { .cost-view__summary { flex-direction: column; gap: 0.75rem; } }
</style>

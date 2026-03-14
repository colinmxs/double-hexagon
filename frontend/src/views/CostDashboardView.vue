<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api'

interface CostData {
  service_breakdown: Record<string, number>
  trend: { month: string; total: number; services: Record<string, number> }[]
  applications_this_month: number
  applications_total: number
  current_month_cost: number
  cost_per_application: number
  budget: number | null
  exceeds_budget: boolean
}

const costData = ref<CostData | null>(null)
const isLoading = ref(false)
const error = ref('')
const budgetInput = ref('')
const budgetSaving = ref(false)
const budgetError = ref('')
const budgetSuccess = ref('')

async function fetchCostData() {
  isLoading.value = true
  error.value = ''
  try {
    const res = await fetch(`${API_BASE}/cost-dashboard`)
    if (!res.ok) throw new Error()
    costData.value = await res.json()
    if (costData.value?.budget != null) {
      budgetInput.value = String(costData.value.budget)
    }
  } catch {
    error.value = 'cost.errorLoading'
  } finally {
    isLoading.value = false
  }
}

async function saveBudget() {
  budgetSaving.value = true
  budgetError.value = ''
  budgetSuccess.value = ''
  try {
    const val = parseFloat(budgetInput.value)
    if (isNaN(val) || val < 0) {
      budgetError.value = 'cost.budgetInvalid'
      return
    }
    const res = await fetch(`${API_BASE}/cost-dashboard/budget`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ budget: val }),
    })
    if (!res.ok) throw new Error()
    budgetSuccess.value = 'cost.budgetSaved'
    if (costData.value) {
      costData.value.budget = val
      costData.value.exceeds_budget = costData.value.current_month_cost > val
    }
  } catch {
    budgetError.value = 'cost.budgetSaveError'
  } finally {
    budgetSaving.value = false
  }
}

const trendMax = computed(() => {
  if (!costData.value?.trend.length) return 1
  return Math.max(...costData.value.trend.map((t) => t.total), 1)
})

const serviceColors: Record<string, string> = {
  S3: '#4a90d9',
  CloudFront: '#50c878',
  Lambda: '#f5a623',
  'API Gateway': '#d94a4a',
  DynamoDB: '#9b59b6',
  Textract: '#1abc9c',
  Bedrock: '#e67e22',
}

onMounted(fetchCostData)
</script>

<template>
  <div class="cost-view">
    <h1>{{ t('cost.title') }}</h1>

    <div v-if="isLoading" class="cost-view__loading" role="status">{{ t('common.loading') }}</div>
    <div v-if="error" class="cost-view__error" role="alert">{{ t(error) }}</div>

    <template v-if="costData && !isLoading">
      <!-- Budget warning -->
      <div v-if="costData.exceeds_budget" class="cost-view__warning" role="alert">
        ⚠️ {{ t('cost.exceedsBudget', { cost: costData.current_month_cost.toFixed(2), budget: costData.budget?.toFixed(2) }) }}
      </div>

      <!-- Summary stats -->
      <div class="cost-view__summary">
        <div class="cost-view__stat">
          <span class="cost-view__stat-value">${{ costData.current_month_cost.toFixed(2) }}</span>
          <span class="cost-view__stat-label">{{ t('cost.currentMonthCost') }}</span>
        </div>
        <div class="cost-view__stat">
          <span class="cost-view__stat-value">{{ costData.applications_this_month }}</span>
          <span class="cost-view__stat-label">{{ t('cost.appsThisMonth') }}</span>
        </div>
        <div class="cost-view__stat">
          <span class="cost-view__stat-value">${{ costData.cost_per_application.toFixed(2) }}</span>
          <span class="cost-view__stat-label">{{ t('cost.costPerApp') }}</span>
        </div>
        <div class="cost-view__stat">
          <span class="cost-view__stat-value">{{ costData.applications_total }}</span>
          <span class="cost-view__stat-label">{{ t('cost.appsTotal') }}</span>
        </div>
      </div>

      <!-- Service breakdown -->
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

      <!-- 6-month trend -->
      <div class="cost-view__section">
        <h2>{{ t('cost.trend') }}</h2>
        <div class="cost-view__trend" role="img" :aria-label="t('cost.trend')">
          <div v-for="t in costData.trend" :key="t.month" class="cost-view__trend-bar">
            <div class="cost-view__trend-fill" :style="{ height: (t.total / trendMax * 100) + '%' }"></div>
            <span class="cost-view__trend-label">{{ t.month }}</span>
            <span class="cost-view__trend-amount">${{ t.total.toFixed(2) }}</span>
          </div>
        </div>
      </div>

      <!-- Budget setting -->
      <div class="cost-view__section">
        <h2>{{ t('cost.budgetThreshold') }}</h2>
        <div class="cost-view__budget-form">
          <label for="budget-input">{{ t('cost.monthlyBudget') }}</label>
          <div class="cost-view__budget-row">
            <span class="cost-view__budget-prefix">$</span>
            <input
              id="budget-input"
              v-model="budgetInput"
              type="number"
              min="0"
              step="0.01"
              class="cost-view__input"
            />
            <button class="cost-view__btn" :disabled="budgetSaving" @click="saveBudget">
              {{ budgetSaving ? t('common.loading') : t('common.save') }}
            </button>
          </div>
        </div>
        <div v-if="budgetSuccess" class="cost-view__success" role="status">{{ t(budgetSuccess) }}</div>
        <div v-if="budgetError" class="cost-view__error" role="alert">{{ t(budgetError) }}</div>
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
.cost-view__success { padding: 0.5rem 0.75rem; background: #d4edda; color: #155724; border-radius: 4px; margin-top: 0.5rem; font-size: 0.85rem; }
.cost-view__warning { padding: 0.75rem 1rem; background: #fff3cd; color: #856404; border: 1px solid #ffc107; border-radius: 6px; margin-bottom: 1rem; font-weight: 600; font-size: 0.95rem; }

.cost-view__summary { display: flex; flex-wrap: wrap; gap: 1.5rem; margin-bottom: 1.5rem; padding: 1rem; background: #f9f9f9; border-radius: 6px; }
.cost-view__stat { display: flex; flex-direction: column; }
.cost-view__stat-value { font-size: 1.5rem; font-weight: 700; }
.cost-view__stat-label { font-size: 0.8rem; color: #555; font-weight: 600; }

.cost-view__section { margin-bottom: 1.5rem; }

.cost-view__breakdown { max-width: 400px; }
.cost-view__svc-row { display: flex; justify-content: space-between; align-items: center; padding: 0.3rem 0; font-size: 0.9rem; }
.cost-view__svc-name { display: flex; align-items: center; gap: 0.4rem; }
.cost-view__svc-dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
.cost-view__svc-amount { font-weight: 600; }

.cost-view__trend { display: flex; align-items: flex-end; gap: 0.75rem; height: 180px; padding-top: 1rem; }
.cost-view__trend-bar { display: flex; flex-direction: column; align-items: center; flex: 1; height: 100%; justify-content: flex-end; }
.cost-view__trend-fill { width: 100%; max-width: 60px; background: #4a90d9; border-radius: 3px 3px 0 0; transition: height 0.3s; min-height: 2px; }
.cost-view__trend-label { font-size: 0.7rem; color: #666; margin-top: 0.3rem; }
.cost-view__trend-amount { font-size: 0.7rem; font-weight: 600; }

.cost-view__budget-form { max-width: 300px; }
.cost-view__budget-form label { font-size: 0.85rem; font-weight: 600; display: block; margin-bottom: 0.3rem; }
.cost-view__budget-row { display: flex; align-items: center; gap: 0.4rem; }
.cost-view__budget-prefix { font-size: 1rem; font-weight: 600; }
.cost-view__input { padding: 0.35rem 0.5rem; border: 1px solid #ccc; border-radius: 4px; font-size: 0.85rem; width: 120px; }
.cost-view__btn { padding: 0.4rem 1rem; border: 1px solid #4a90d9; background: #4a90d9; color: #fff; border-radius: 4px; font-size: 0.85rem; cursor: pointer; }
.cost-view__btn:hover:not(:disabled) { background: #357abd; }
.cost-view__btn:disabled { opacity: 0.6; cursor: not-allowed; }

@media (max-width: 768px) {
  .cost-view__summary { flex-direction: column; gap: 0.75rem; }
  .cost-view__trend { height: 140px; }
}
</style>

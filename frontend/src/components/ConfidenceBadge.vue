<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

const props = withDefaults(
  defineProps<{
    score: number
    threshold?: number
  }>(),
  { threshold: 0.8 },
)

const { t } = useI18n()

type ConfidenceLevel = 'high' | 'medium' | 'low'

const level = computed<ConfidenceLevel>(() => {
  if (props.score >= props.threshold) return 'high'
  if (props.score >= props.threshold - 0.15) return 'medium'
  return 'low'
})

const displayScore = computed(() => `${Math.round(props.score * 100)}%`)

const ariaLabel = computed(() =>
  t(`confidence.${level.value}`, { score: displayScore.value }),
)
</script>

<template>
  <span
    class="confidence-badge"
    :class="`confidence-badge--${level}`"
    role="status"
    :aria-label="ariaLabel"
  >
    {{ displayScore }}
  </span>
</template>

<style scoped>
.confidence-badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 0.8rem;
  font-weight: 600;
  line-height: 1.4;
}

.confidence-badge--high {
  background-color: #d4edda;
  color: #155724;
}

.confidence-badge--medium {
  background-color: #fff3cd;
  color: #856404;
}

.confidence-badge--low {
  background-color: #f8d7da;
  color: #721c24;
}
</style>

import { ref, onMounted, onUnmounted } from 'vue'
import type { MaybeRefOrGetter } from 'vue'
import { toValue } from 'vue'

const ACTIVITY_EVENTS = ['mousemove', 'mousedown', 'keydown', 'scroll', 'touchstart'] as const

export interface UseSessionTimeoutOptions {
  /** Total inactivity timeout in milliseconds */
  timeoutMs: MaybeRefOrGetter<number>
  /** Warning threshold in milliseconds before timeout */
  warningMs: MaybeRefOrGetter<number>
}

const DEFAULT_TIMEOUT_MS = 30 * 60 * 1000 // 30 minutes
const DEFAULT_WARNING_MS = 5 * 60 * 1000 // 5 minutes

export function useSessionTimeout(
  onTimeout: () => void,
  options?: Partial<UseSessionTimeoutOptions>,
) {
  const timeoutMs = options?.timeoutMs ?? DEFAULT_TIMEOUT_MS
  const warningMs = options?.warningMs ?? DEFAULT_WARNING_MS

  const showWarning = ref(false)
  const remainingMinutes = ref(0)

  let timeoutTimer: ReturnType<typeof setTimeout> | null = null
  let warningTimer: ReturnType<typeof setTimeout> | null = null
  let countdownInterval: ReturnType<typeof setInterval> | null = null

  function clearTimers() {
    if (timeoutTimer) {
      clearTimeout(timeoutTimer)
      timeoutTimer = null
    }
    if (warningTimer) {
      clearTimeout(warningTimer)
      warningTimer = null
    }
    if (countdownInterval) {
      clearInterval(countdownInterval)
      countdownInterval = null
    }
  }

  function resetTimers() {
    clearTimers()
    showWarning.value = false

    const totalMs = toValue(timeoutMs)
    const warnMs = toValue(warningMs)
    const warningAt = totalMs - warnMs

    warningTimer = setTimeout(() => {
      showWarning.value = true
      remainingMinutes.value = Math.ceil(warnMs / 60_000)
      countdownInterval = setInterval(() => {
        remainingMinutes.value = Math.max(0, remainingMinutes.value - 1)
      }, 60_000)
    }, warningAt)

    timeoutTimer = setTimeout(() => {
      clearTimers()
      showWarning.value = false
      onTimeout()
    }, totalMs)
  }

  function dismissWarning() {
    resetTimers()
  }

  onMounted(() => {
    resetTimers()
    for (const event of ACTIVITY_EVENTS) {
      window.addEventListener(event, resetTimers, { passive: true })
    }
  })

  onUnmounted(() => {
    clearTimers()
    for (const event of ACTIVITY_EVENTS) {
      window.removeEventListener(event, resetTimers)
    }
  })

  return {
    showWarning,
    remainingMinutes,
    dismissWarning,
  }
}

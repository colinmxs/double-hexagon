import { ref, computed } from 'vue'

export type UserRole = 'admin' | 'reporter' | 'submitter'

export interface AuthUser {
  userId: string
  email: string
  name: string
  role: UserRole
  authorizedGiveawayYears?: string[]
}

const LOCAL_DEV_USER: AuthUser = {
  userId: 'local-admin-001',
  email: 'admin@localhost',
  name: 'Local Admin',
  role: 'admin',
}

const currentUser = ref<AuthUser | null>(null)
const isLoading = ref(false)

const authEnabled = import.meta.env.VITE_AUTH_ENABLED !== 'false'

export function useAuth() {
  const isAuthenticated = computed(() => !authEnabled || currentUser.value !== null)

  const user = computed<AuthUser | null>(() => {
    if (!authEnabled) {
      return LOCAL_DEV_USER
    }
    return currentUser.value
  })

  const userRole = computed<UserRole | null>(() => user.value?.role ?? null)

  function hasRole(role: string): boolean {
    const current = user.value
    if (!current) return false
    if (current.role === 'admin') return true
    return current.role === role
  }

  function setUser(u: AuthUser | null) {
    currentUser.value = u
  }

  function logout() {
    currentUser.value = null
  }

  return {
    authEnabled,
    isAuthenticated,
    isLoading,
    user,
    userRole,
    hasRole,
    setUser,
    logout,
  }
}

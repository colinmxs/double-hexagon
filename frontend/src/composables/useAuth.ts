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
const accessToken = ref<string | null>(null)
const isLoading = ref(false)
const pendingChallenge = ref<{ session: string; username: string; challenge: string } | null>(null)

let authEnabled = false
const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api'

// Runtime config — loaded from /config.json (deployed by CDK) or falls back to env vars
let cognitoRegion = import.meta.env.VITE_COGNITO_REGION || 'us-west-2'
let cognitoClientId = import.meta.env.VITE_COGNITO_CLIENT_ID || ''
let runtimeConfigLoaded = false

async function loadRuntimeConfig(): Promise<void> {
  if (runtimeConfigLoaded) return
  try {
    const res = await fetch('/config.json')
    if (res.ok) {
      const config = await res.json()
      if (config.cognitoRegion) cognitoRegion = config.cognitoRegion
      if (config.cognitoClientId) cognitoClientId = config.cognitoClientId
      if (config.authEnabled !== undefined) authEnabled = !!config.authEnabled
    }
  } catch { /* use env var fallbacks */ }
  // Auth is enabled if we have a Cognito client ID from any source
  authEnabled = !!cognitoClientId
  runtimeConfigLoaded = true
}

async function cognitoLogin(username: string, password: string): Promise<void> {
  await loadRuntimeConfig()
  const url = `https://cognito-idp.${cognitoRegion}.amazonaws.com/`
  const res = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-amz-json-1.1',
      'X-Amz-Target': 'AWSCognitoIdentityProviderService.InitiateAuth',
    },
    body: JSON.stringify({
      AuthFlow: 'USER_PASSWORD_AUTH',
      ClientId: cognitoClientId,
      AuthParameters: { USERNAME: username, PASSWORD: password },
    }),
  })
  const data = await res.json()
  if (!res.ok) {
    throw new Error(data.message || data.__type || 'Login failed')
  }

  // Handle NEW_PASSWORD_REQUIRED challenge (admin-created users)
  if (data.ChallengeName === 'NEW_PASSWORD_REQUIRED') {
    pendingChallenge.value = {
      session: data.Session,
      username,
      challenge: data.ChallengeName,
    }
    throw new Error('NEW_PASSWORD_REQUIRED')
  }

  const idToken = data.AuthenticationResult?.IdToken
  const at = data.AuthenticationResult?.AccessToken
  if (!idToken) throw new Error('No token received')
  accessToken.value = idToken
  localStorage.setItem('bbp_token', idToken)
  if (at) localStorage.setItem('bbp_access_token', at)
  await fetchMe()
}

async function completeNewPassword(newPassword: string): Promise<void> {
  if (!pendingChallenge.value) throw new Error('No pending challenge')
  await loadRuntimeConfig()
  const url = `https://cognito-idp.${cognitoRegion}.amazonaws.com/`
  const res = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-amz-json-1.1',
      'X-Amz-Target': 'AWSCognitoIdentityProviderService.RespondToAuthChallenge',
    },
    body: JSON.stringify({
      ChallengeName: 'NEW_PASSWORD_REQUIRED',
      ClientId: cognitoClientId,
      Session: pendingChallenge.value.session,
      ChallengeResponses: {
        USERNAME: pendingChallenge.value.username,
        NEW_PASSWORD: newPassword,
      },
    }),
  })
  const data = await res.json()
  pendingChallenge.value = null
  if (!res.ok) {
    throw new Error(data.message || data.__type || 'Password change failed')
  }
  const idToken = data.AuthenticationResult?.IdToken
  const at = data.AuthenticationResult?.AccessToken
  if (!idToken) throw new Error('No token received')
  accessToken.value = idToken
  localStorage.setItem('bbp_token', idToken)
  if (at) localStorage.setItem('bbp_access_token', at)
  await fetchMe()
}

function clearSession() {
  currentUser.value = null
  accessToken.value = null
  localStorage.removeItem('bbp_token')
  localStorage.removeItem('bbp_access_token')
}

async function fetchMe(): Promise<void> {
  const token = accessToken.value || localStorage.getItem('bbp_token')
  if (!token) return
  try {
    const res = await fetch(`${API_BASE}/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (!res.ok) {
      clearSession()
      return
    }
    const data = await res.json()
    currentUser.value = {
      userId: data.user_id,
      email: data.email,
      name: data.name,
      role: data.role,
      authorizedGiveawayYears: data.authorized_giveaway_years,
    }
    accessToken.value = token
  } catch {
    clearSession()
  }
}

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
    clearSession()
  }

  function getToken(): string | null {
    return accessToken.value || localStorage.getItem('bbp_token')
  }

  async function tryRestoreSession(): Promise<void> {
    await loadRuntimeConfig()
    if (!authEnabled) return
    const token = localStorage.getItem('bbp_token')
    if (token) {
      accessToken.value = token
      await fetchMe()
    }
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
    getToken,
    login: cognitoLogin,
    completeNewPassword,
    pendingChallenge,
    tryRestoreSession,
  }
}

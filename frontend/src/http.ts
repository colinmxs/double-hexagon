/**
 * Global HTTP client.
 *
 * Overrides window.fetch to automatically inject the Authorization header
 * from localStorage on every request to the API. Import this once in main.ts
 * and every fetch call in the app gets auth for free.
 */

const originalFetch = window.fetch.bind(window)

window.fetch = function (input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url
  const isApiCall = url.startsWith('/api') || url.includes('/api/')

  if (isApiCall) {
    const token = localStorage.getItem('bbp_token')
    if (token) {
      const headers = new Headers(init?.headers)
      if (!headers.has('Authorization')) {
        headers.set('Authorization', `Bearer ${token}`)
      }
      init = { ...init, headers }
    }
  }

  return originalFetch(input, init)
}

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

describe('Global fetch interceptor (src/http.ts)', () => {
  let originalFetch: typeof globalThis.fetch

  beforeEach(() => {
    // Save the real fetch before the interceptor overrides it
    originalFetch = globalThis.fetch

    // Reset localStorage
    localStorage.clear()

    // Track calls made to the underlying fetch
    globalThis.fetch = vi.fn(() => {
      return Promise.resolve(new Response('{}', { status: 200 }))
    }) as typeof globalThis.fetch

    // Now load the interceptor — it wraps whatever globalThis.fetch currently is
    // We need to re-import it fresh each time
    vi.resetModules()
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
    localStorage.clear()
    vi.restoreAllMocks()
  })

  async function loadInterceptorAndCall(url: string, init?: RequestInit) {
    // The interceptor captures window.fetch at import time, so we need
    // to set up our mock first, then import
    const mockFetch = vi.fn(() => Promise.resolve(new Response('{}', { status: 200 })))
    globalThis.fetch = mockFetch as unknown as typeof globalThis.fetch

    // Dynamically import to trigger the interceptor setup
    await import('../http')

    // Now globalThis.fetch is the interceptor wrapping mockFetch
    await globalThis.fetch(url, init)

    return mockFetch
  }

  it('adds Authorization header when token exists and URL starts with /api', async () => {
    localStorage.setItem('bbp_token', 'test-jwt-token-123')
    const mockFetch = await loadInterceptorAndCall('/api/giveaway-years')

    expect(mockFetch).toHaveBeenCalledOnce()
    const calledUrl = mockFetch.mock.calls[0][0]
    const calledInit = mockFetch.mock.calls[0][1] as RequestInit | undefined
    expect(calledUrl).toBe('/api/giveaway-years')

    const headers = new Headers(calledInit?.headers)
    expect(headers.get('Authorization')).toBe('Bearer test-jwt-token-123')
  })

  it('adds Authorization header when URL contains /api/', async () => {
    localStorage.setItem('bbp_token', 'my-token')
    const mockFetch = await loadInterceptorAndCall('https://example.com/api/users')

    const calledInit = mockFetch.mock.calls[0][1] as RequestInit | undefined
    const headers = new Headers(calledInit?.headers)
    expect(headers.get('Authorization')).toBe('Bearer my-token')
  })

  it('does NOT add Authorization header when no token in localStorage', async () => {
    // No token set
    const mockFetch = await loadInterceptorAndCall('/api/giveaway-years')

    const calledInit = mockFetch.mock.calls[0][1] as RequestInit | undefined
    const headers = new Headers(calledInit?.headers)
    expect(headers.get('Authorization')).toBeNull()
  })

  it('does NOT add Authorization header for non-API URLs', async () => {
    localStorage.setItem('bbp_token', 'my-token')
    const mockFetch = await loadInterceptorAndCall('/config.json')

    const calledInit = mockFetch.mock.calls[0][1] as RequestInit | undefined
    const headers = new Headers(calledInit?.headers)
    expect(headers.get('Authorization')).toBeNull()
  })

  it('preserves existing headers when adding Authorization', async () => {
    localStorage.setItem('bbp_token', 'my-token')
    const mockFetch = await loadInterceptorAndCall('/api/applications', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{}',
    })

    const calledInit = mockFetch.mock.calls[0][1] as RequestInit | undefined
    const headers = new Headers(calledInit?.headers)
    expect(headers.get('Authorization')).toBe('Bearer my-token')
    expect(headers.get('Content-Type')).toBe('application/json')
    expect(calledInit?.method).toBe('POST')
    expect(calledInit?.body).toBe('{}')
  })

  it('does NOT overwrite an existing Authorization header', async () => {
    localStorage.setItem('bbp_token', 'my-token')
    const mockFetch = await loadInterceptorAndCall('/api/auth/me', {
      headers: { 'Authorization': 'Bearer explicit-token' },
    })

    const calledInit = mockFetch.mock.calls[0][1] as RequestInit | undefined
    const headers = new Headers(calledInit?.headers)
    expect(headers.get('Authorization')).toBe('Bearer explicit-token')
  })
})

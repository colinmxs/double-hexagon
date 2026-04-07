/**
 * API helper. Provides the base URL and a convenience fetch wrapper.
 * Auth headers are handled globally by src/http.ts.
 */

const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api'

export function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  return fetch(`${API_BASE}${path}`, init)
}

export function useApi() {
  return { apiFetch, API_BASE }
}

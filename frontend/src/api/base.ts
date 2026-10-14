// Where the backend is. Empty in development, where the dev server proxies /api to it
// (vite.config.ts); set VITE_API_BASE_URL at build time when the backend is deployed on
// its own domain, e.g. https://api.example.com.
const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/+$/, '')

// A backend path ("/api/...") as a URL the browser can fetch from this page.
export function apiUrl(path: string): string {
  return `${API_BASE_URL}${path}`
}

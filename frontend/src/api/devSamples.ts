import type { NarrationResponse } from '../narration/types'
import type { FinancialReport } from '../types/report'

export interface DevSample {
  report: FinancialReport
  narration: NarrationResponse
}

// Local development only: a saved run served by the backend's /api/dev/samples
// endpoint (enabled by DEV_SAMPLES_DIR), for previewing the UI with real model output
// without making any API calls.
export async function loadDevSample(name: string, version: string | null): Promise<DevSample> {
  const query = version ? `?version=${encodeURIComponent(version)}` : ''
  const response = await fetch(`/api/dev/samples/${encodeURIComponent(name)}${query}`)

  if (!response.ok) {
    const body = await response.json().catch(() => null)
    const detail = typeof body?.detail === 'string' ? body.detail : null
    if (response.status === 404 && !detail) {
      throw new Error('Sample endpoint not found - set DEV_SAMPLES_DIR in backend/.env and restart the backend.')
    }
    throw new Error(detail ?? `Request failed with status ${response.status}`)
  }

  return response.json()
}

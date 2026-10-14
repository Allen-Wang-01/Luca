import type { NarrationAudio, NarrationResponse } from '../narration/types'
import type { FinancialReport } from '../types/report'

export interface DevSample {
  report: FinancialReport
  narration: NarrationResponse
  // Saved speech clips, one entry per narration line (null where none was generated).
  audio: NarrationAudio
}

export interface DevSampleSummary {
  name: string
  company_name: string
  report_type: string
  fiscal_period: string
}

// The saved runs the backend has to offer, shown as demos on the start page. A backend
// without any (DEV_SAMPLES_DIR unset, so no such endpoint) simply has none to show.
export async function listDevSamples(): Promise<DevSampleSummary[]> {
  const response = await fetch('/api/dev/samples')
  if (!response.ok) return []
  return response.json()
}

// A saved run served by the backend's /api/dev/samples endpoint (enabled by
// DEV_SAMPLES_DIR): real model output, shown without making any API calls.
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

import type { NarrationResponse } from '../narration/types'
import type { FinancialReport } from '../types/report'

export async function generateNarration(report: FinancialReport): Promise<NarrationResponse> {
  const response = await fetch('/api/reports/narration', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ report }),
  })

  if (!response.ok) {
    const body = await response.json().catch(() => null)
    const detail = typeof body?.detail === 'string' ? body.detail : null
    throw new Error(detail ?? `Request failed with status ${response.status}`)
  }

  return response.json()
}

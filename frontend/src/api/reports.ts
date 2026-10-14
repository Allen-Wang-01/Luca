import type { FinancialReport } from '../types/report'
import { apiUrl } from './base'

export async function parseReport(file: File): Promise<FinancialReport> {
  const formData = new FormData()
  formData.append('file', file)

  const response = await fetch(apiUrl('/api/reports/parse'), {
    method: 'POST',
    body: formData,
  })

  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(body?.detail ?? `Request failed with status ${response.status}`)
  }

  return response.json()
}

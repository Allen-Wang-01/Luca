import type { FinancialReport } from '../types/report'

export async function parseReport(file: File): Promise<FinancialReport> {
  const formData = new FormData()
  formData.append('file', file)

  const response = await fetch('/api/reports/parse', {
    method: 'POST',
    body: formData,
  })

  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(body?.detail ?? `Request failed with status ${response.status}`)
  }

  return response.json()
}

import type { NarrationEvent, NarrationResponse } from '../narration/types'
import type { FinancialReport } from '../types/report'
import { apiUrl } from './base'

// The stream ends with one of these two, after the run's own events.
type StreamMessage =
  | NarrationEvent
  | { type: 'result'; narration: NarrationResponse }
  | { type: 'error'; detail: string }

// Asks for a report's narration and follows the run while it happens: `onEvent` gets
// each thing the agent reports, and the promise settles with the finished script. The
// response is a server-sent event stream, read by hand since EventSource can't POST.
export async function generateNarration(
  report: FinancialReport,
  onEvent?: (event: NarrationEvent) => void,
): Promise<NarrationResponse> {
  const response = await fetch(apiUrl('/api/reports/narration/stream'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ report }),
  })

  if (!response.ok || !response.body) {
    const body = await response.json().catch(() => null)
    const detail = typeof body?.detail === 'string' ? body.detail : null
    throw new Error(detail ?? `Request failed with status ${response.status}`)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    // Events are separated by a blank line; whatever follows the last one is incomplete.
    let end = buffer.indexOf('\n\n')
    while (end !== -1) {
      const frame = buffer.slice(0, end)
      buffer = buffer.slice(end + 2)
      end = buffer.indexOf('\n\n')

      const data = frame
        .split('\n')
        .filter((line) => line.startsWith('data: '))
        .map((line) => line.slice('data: '.length))
        .join('\n')
      // A frame without data is the server's keep-alive comment.
      if (!data) continue

      const message = JSON.parse(data) as StreamMessage
      if (message.type === 'result') return message.narration
      if (message.type === 'error') throw new Error(message.detail)
      onEvent?.(message)
    }
  }

  throw new Error('The connection closed before the walkthrough was ready.')
}

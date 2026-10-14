import { useCallback, useEffect, useMemo, useState, useSyncExternalStore } from 'react'
import { generateNarration } from '../api/narration'
import type { FinancialReport } from '../types/report'
import { buildStubScript } from './buildStubScript'
import type { NarrationAudio, NarrationEvent, NarrationResponse, NarrationScript, NarrationTrace } from './types'

export type NarrationStatus = 'loading' | 'ready' | 'failed'

export interface GeneratedNarration {
  status: NarrationStatus
  // Empty while loading; the stub script once generation has failed.
  script: NarrationScript
  trace: NarrationTrace | null
  // Speech for `script`, when there is any; null means every line is timed, not spoken.
  audio: NarrationAudio | null
  // What the run has reported so far, in order: the advisor's work, as it happens.
  // Empty for a narration that was supplied rather than generated here.
  progress: NarrationEvent[]
  error: string | null
  retry: () => void
}

// Each generation is a multi-turn agent run that costs real money, so the request is
// cached per report object at module level rather than in component state: React
// StrictMode's dev-only effect double-run then reuses the in-flight request instead of
// starting (and paying for) a second one.
const requestCache = new WeakMap<FinancialReport, Promise<NarrationResponse>>()

// Speech clips that came with a seeded narration, per line.
const audioCache = new WeakMap<FinancialReport, NarrationAudio>()

// Supplies an already-generated narration for a report (e.g. a saved dev sample), so
// rendering it never triggers a generation request. Call before the report renders.
export function seedNarration(report: FinancialReport, narration: NarrationResponse, audio?: NarrationAudio): void {
  requestCache.set(report, Promise.resolve(narration))
  // A sample with no clips at all is simply an unvoiced script, not one with gaps.
  if (audio?.some((clip) => clip !== null)) audioCache.set(report, audio)
}

// What the run for a report has reported so far. Kept beside the request, outside
// component state, for the same reason: the request outlives any one mount. The array
// is replaced, never changed, so it can be handed to React as a snapshot.
const NO_EVENTS: NarrationEvent[] = []
const progressCache = new WeakMap<FinancialReport, NarrationEvent[]>()
const progressListeners = new WeakMap<FinancialReport, Set<() => void>>()

function setProgress(report: FinancialReport, events: NarrationEvent[]): void {
  progressCache.set(report, events)
  progressListeners.get(report)?.forEach((listener) => listener())
}

function requestNarration(report: FinancialReport): Promise<NarrationResponse> {
  let request = requestCache.get(report)
  if (!request) {
    // A retry starts its own run; what the failed one reported no longer applies.
    setProgress(report, NO_EVENTS)
    request = generateNarration(report, (event) =>
      setProgress(report, [...(progressCache.get(report) ?? NO_EVENTS), event]),
    )
    // A failed request mustn't stay cached, or retrying would just replay the failure.
    request.catch(() => requestCache.delete(report))
    requestCache.set(report, request)
  }
  return request
}

type RequestState =
  | { attempt: number; status: 'loading' }
  | { attempt: number; status: 'ready'; response: NarrationResponse }
  | { attempt: number; status: 'failed'; error: string }

export function useGeneratedNarration(report: FinancialReport): GeneratedNarration {
  const [attempt, setAttempt] = useState(0)
  const [state, setState] = useState<RequestState>({ attempt, status: 'loading' })

  useEffect(() => {
    let cancelled = false
    requestNarration(report).then(
      (response) => {
        if (!cancelled) setState({ attempt, status: 'ready', response })
      },
      (err: unknown) => {
        if (!cancelled) {
          setState({ attempt, status: 'failed', error: err instanceof Error ? err.message : 'Narration request failed.' })
        }
      },
    )
    return () => {
      cancelled = true
    }
  }, [report, attempt])

  const subscribe = useCallback(
    (listener: () => void) => {
      let listeners = progressListeners.get(report)
      if (!listeners) {
        listeners = new Set()
        progressListeners.set(report, listeners)
      }
      listeners.add(listener)
      return () => {
        listeners.delete(listener)
      }
    },
    [report],
  )
  const progress = useSyncExternalStore(subscribe, () => progressCache.get(report) ?? NO_EVENTS)

  const stubScript = useMemo(() => buildStubScript(report), [report])
  const retry = useCallback(() => setAttempt((n) => n + 1), [])

  // Right after a retry, `state` still describes the failed attempt until the new
  // request settles - treat that gap as loading rather than showing the stale failure.
  const current: RequestState = state.attempt === attempt ? state : { attempt, status: 'loading' }

  switch (current.status) {
    case 'loading':
      return { status: 'loading', script: EMPTY_SCRIPT, trace: null, audio: null, progress, error: null, retry }
    case 'ready':
      return {
        status: 'ready',
        script: current.response.lines,
        trace: current.response.trace,
        audio: audioCache.get(report) ?? null,
        progress,
        error: null,
        retry,
      }
    case 'failed':
      return { status: 'failed', script: stubScript, trace: null, audio: null, progress, error: current.error, retry }
  }
}

const EMPTY_SCRIPT: NarrationScript = []

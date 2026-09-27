import { useCallback, useEffect, useState } from 'react'
import type { NarrationLine, NarrationScript } from './types'

const WORDS_PER_SECOND = 3.3
const MIN_LINE_MS = 2500
const MAX_LINE_MS = 9000

// Estimated reading time for a line, standing in for the real duration a TTS audio
// clip will eventually have - this is what drives auto-advance timing until real
// narration audio exists.
export function lineDurationMs(text: string): number {
  const wordCount = text.trim().split(/\s+/).filter(Boolean).length
  const estimated = (wordCount / WORDS_PER_SECOND) * 1000
  return Math.min(MAX_LINE_MS, Math.max(MIN_LINE_MS, estimated))
}

export interface NarrationPlayer {
  currentIndex: number
  currentLine: NarrationLine | null
  isPlaying: boolean
  total: number
  durationMs: number
  play: () => void
  pause: () => void
  next: () => void
  prev: () => void
}

export function useNarrationPlayer(script: NarrationScript): NarrationPlayer {
  const [currentIndex, setCurrentIndex] = useState(0)
  const [isPlaying, setIsPlaying] = useState(false)

  const total = script.length
  const currentLine = script[currentIndex] ?? null
  const durationMs = currentLine ? lineDurationMs(currentLine.text) : 0

  const play = useCallback(() => setIsPlaying(true), [])
  const pause = useCallback(() => setIsPlaying(false), [])
  const next = useCallback(() => setCurrentIndex((i) => Math.min(i + 1, total - 1)), [total])
  const prev = useCallback(() => setCurrentIndex((i) => Math.max(i - 1, 0)), [])

  useEffect(() => {
    if (!isPlaying || !currentLine) return

    const isLastLine = currentIndex >= total - 1
    const timer = setTimeout(() => {
      if (isLastLine) {
        setIsPlaying(false)
      } else {
        setCurrentIndex((i) => i + 1)
      }
    }, durationMs)

    return () => clearTimeout(timer)
    // Only the line boundary and play state should restart the timer - durationMs is
    // derived from currentLine/currentIndex, so including it would be redundant.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentIndex, isPlaying, total])

  return { currentIndex, currentLine, isPlaying, total, durationMs, play, pause, next, prev }
}

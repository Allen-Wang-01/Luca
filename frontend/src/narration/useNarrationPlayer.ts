import { useCallback, useEffect, useRef, useState } from 'react'
import type { NarrationAudio, NarrationLine, NarrationScript } from './types'

const WORDS_PER_SECOND = 3.3
const MIN_LINE_MS = 2500
const MAX_LINE_MS = 9000

// Estimated reading time for a line. Drives auto-advance for any line without an audio
// clip; a line that has one lasts as long as the clip instead.
export function lineDurationMs(text: string): number {
  const wordCount = text.trim().split(/\s+/).filter(Boolean).length
  const estimated = (wordCount / WORDS_PER_SECOND) * 1000
  return Math.min(MAX_LINE_MS, Math.max(MIN_LINE_MS, estimated))
}

export interface NarrationPlayer {
  currentIndex: number
  currentLine: NarrationLine | null
  isPlaying: boolean
  // Whether the current line has audio; false means it's timed and shown as a caption only.
  isSpoken: boolean
  total: number
  durationMs: number
  play: () => void
  pause: () => void
  next: () => void
  prev: () => void
}

export function useNarrationPlayer(script: NarrationScript, audio: NarrationAudio | null = null): NarrationPlayer {
  const [currentIndex, setCurrentIndex] = useState(0)
  const [isPlaying, setIsPlaying] = useState(false)

  // A different script (another language, or the fallback after a failed generation)
  // starts over from the top rather than landing mid-way at the old index. Adjusting
  // state during render, not in an effect, so there's no frame showing the old index.
  const [prevScript, setPrevScript] = useState(script)
  if (script !== prevScript) {
    setPrevScript(script)
    setCurrentIndex(0)
    setIsPlaying(false)
  }

  const total = script.length
  const currentLine = script[currentIndex] ?? null
  const clip = audio?.[currentIndex] ?? null
  const durationMs = currentLine ? (clip?.duration_ms ?? lineDurationMs(currentLine.text)) : 0

  const play = useCallback(() => setIsPlaying(true), [])
  const pause = useCallback(() => setIsPlaying(false), [])
  const next = useCallback(() => setCurrentIndex((i) => Math.min(i + 1, total - 1)), [total])
  const prev = useCallback(() => setCurrentIndex((i) => Math.max(i - 1, 0)), [])

  // One audio element for the whole script. `loadedUrlRef` is the clip it currently
  // holds: pausing and resuming the same line keeps the element (and its position),
  // while leaving a line clears this so coming back to it starts from the top.
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const loadedUrlRef = useRef<string | null>(null)
  useEffect(() => {
    return () => {
      loadedUrlRef.current = null
    }
  }, [currentIndex, script])

  useEffect(() => {
    if (!isPlaying || !currentLine) return

    const isLastLine = currentIndex >= total - 1
    const advance = () => {
      if (isLastLine) {
        setIsPlaying(false)
      } else {
        setCurrentIndex((i) => i + 1)
      }
    }

    if (!clip) {
      const timer = setTimeout(advance, durationMs)
      return () => clearTimeout(timer)
    }

    // The line lasts exactly as long as its audio: the next one starts when it ends.
    const element = (audioRef.current ??= new Audio())
    if (loadedUrlRef.current !== clip.url) {
      element.src = clip.url
      loadedUrlRef.current = clip.url
    }

    // A clip that can't be played (file gone, playback blocked by the browser) falls
    // back to timing the line, so narration never stalls on a silent line.
    let cancelled = false
    let fallbackTimer: ReturnType<typeof setTimeout> | undefined
    const fallBackToTimer = () => {
      if (!cancelled && fallbackTimer === undefined) fallbackTimer = setTimeout(advance, durationMs)
    }

    element.addEventListener('ended', advance)
    element.addEventListener('error', fallBackToTimer)
    element.play().catch(fallBackToTimer)

    return () => {
      cancelled = true
      clearTimeout(fallbackTimer)
      element.removeEventListener('ended', advance)
      element.removeEventListener('error', fallBackToTimer)
      element.pause()
    }
    // Only the line boundary and play state should restart playback - durationMs is
    // derived from currentLine/clip, so including it would be redundant.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentIndex, isPlaying, total, clip])

  return { currentIndex, currentLine, isPlaying, isSpoken: clip !== null, total, durationMs, play, pause, next, prev }
}

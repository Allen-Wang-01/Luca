import { useEffect, useState } from 'react'
import './PreparationSteps.css'

const STEPS = [
  { key: 'parsing', title: 'Reading the report', detail: 'Every table and figure is read off the PDF and its totals are checked.' },
  {
    key: 'narrating',
    title: 'Preparing the walkthrough',
    detail: 'Your advisor runs the numbers, looks up outside context and writes what to say.',
  },
] as const

interface PreparationStepsProps {
  // The step in progress; the ones before it are done.
  stage: (typeof STEPS)[number]['key']
}

function useElapsedSeconds(): number {
  const [seconds, setSeconds] = useState(0)
  useEffect(() => {
    const timer = setInterval(() => setSeconds((s) => s + 1), 1000)
    return () => clearInterval(timer)
  }, [])
  return seconds
}

function formatElapsed(seconds: number): string {
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`
}

// The two things that happen between choosing a PDF and being able to press play. They
// are two separate requests, so the step shown as running is the one that really is.
// Mount it with a `key` per stage so the clock restarts with each step.
export function PreparationSteps({ stage }: PreparationStepsProps) {
  const elapsed = useElapsedSeconds()
  const activeIndex = STEPS.findIndex((step) => step.key === stage)

  return (
    <ol className="preparation-steps">
      {STEPS.map((step, index) => {
        const state = index < activeIndex ? 'done' : index === activeIndex ? 'active' : 'pending'
        return (
          <li key={step.key} className="preparation-steps__step" data-state={state}>
            <span className="preparation-steps__marker" aria-hidden="true">
              {state === 'done' ? '✓' : state === 'active' ? <span className="spinner" /> : index + 1}
            </span>
            <div>
              <div className="preparation-steps__title">
                {step.title}
                {state === 'active' && <span className="preparation-steps__elapsed">{formatElapsed(elapsed)}</span>}
              </div>
              <div className="preparation-steps__detail">{step.detail}</div>
            </div>
          </li>
        )
      })}
    </ol>
  )
}

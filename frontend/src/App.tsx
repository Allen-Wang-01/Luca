import { useEffect, useState } from 'react'
import './App.css'
import { listDevSamples, loadDevSample, type DevSampleSummary } from './api/devSamples'
import { parseReport } from './api/reports'
import { HomeScreen } from './components/HomeScreen'
import { PreparationSteps } from './components/report/PreparationSteps'
import { ReportView } from './components/report/ReportView'
import { seedNarration } from './narration/useGeneratedNarration'
import type { FinancialReport } from './types/report'

// 'idle': the start page. 'parsing': a report is on its way. Once there is a report it
// takes over the whole page (ReportView), whatever the status was.
type Status = 'idle' | 'parsing' | 'error'

// A saved run shown instead of an uploaded PDF: a demo picked on the start page, or
// `?sample=<name>[&version=<v>]` in the address. `live` (`&live=1`) takes only the
// saved report and has the advisor prepare the walkthrough again, for real.
interface SampleChoice {
  name: string
  version: string | null
  live: boolean
}

function readSampleParams(): SampleChoice | null {
  const params = new URLSearchParams(window.location.search)
  const name = params.get('sample')
  return name ? { name, version: params.get('version'), live: params.get('live') === '1' } : null
}

function App() {
  const [devSample, setDevSample] = useState(readSampleParams)
  const [demos, setDemos] = useState<DevSampleSummary[]>([])
  const [status, setStatus] = useState<Status>(devSample ? 'parsing' : 'idle')
  const [report, setReport] = useState<FinancialReport | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [isSample, setIsSample] = useState(false)

  useEffect(() => {
    let cancelled = false
    listDevSamples().then(
      (samples) => {
        if (!cancelled) setDemos(samples)
      },
      // No demos to offer is not an error worth showing: uploading still works.
      () => {},
    )
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (!devSample) return
    let cancelled = false
    loadDevSample(devSample.name, devSample.version).then(
      (sample) => {
        if (cancelled) return
        // Seeded before the report renders, so the saved narration is used as-is and
        // no generation request (and no API cost) ever happens. A live run is left
        // unseeded: rendering the report then requests its narration like an upload's.
        if (!devSample.live) seedNarration(sample.report, sample.narration, sample.audio)
        setReport(sample.report)
        setIsSample(true)
        setStatus('idle')
      },
      (err: unknown) => {
        if (cancelled) return
        setErrorMessage(err instanceof Error ? err.message : 'Failed to load sample.')
        setStatus('error')
      },
    )
    return () => {
      cancelled = true
    }
  }, [devSample])

  const handleDemoSelected = (name: string, live: boolean) => {
    setStatus('parsing')
    setErrorMessage(null)
    setDevSample({ name, version: null, live })
  }

  const handleFileSelected = async (file: File) => {
    setStatus('parsing')
    setErrorMessage(null)
    setIsSample(false)
    setDevSample(null)
    try {
      const result = await parseReport(file)
      setReport(result)
      setStatus('idle')
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'Failed to parse report.')
      setStatus('error')
    }
  }

  const handleExit = () => {
    setStatus('idle')
    setReport(null)
    setErrorMessage(null)
    setIsSample(false)
    setDevSample(null)
  }

  if (report) {
    const sampleLabel = !isSample || !devSample
      ? null
      : devSample.live
        ? `Live run on a saved report: ${devSample.name}`
        : `Saved run: ${devSample.name}${devSample.version ? ` (${devSample.version})` : ''}`
    return <ReportView report={report} sampleLabel={sampleLabel} onExit={handleExit} />
  }

  return (
    <div className="app-shell">
      <header className="app-header">
        <span className="app-header__logo" aria-hidden="true">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.2" strokeLinecap="round">
            <path d="M6 15V9" />
            <path d="M12 18V6" />
            <path d="M18 15V9" />
          </svg>
        </span>
        <h1 className="app-header__title">Luca</h1>
        <span className="app-header__tagline">AI-narrated financial report walkthroughs</span>
      </header>

      <main className="app-main">
        {status === 'parsing' ? (
          <div className="app-waiting">
            {devSample ? (
              <div className="status-banner status-banner--loading">
                <span className="spinner" aria-hidden="true" />
                {devSample.live ? 'Opening the saved report…' : 'Opening the saved walkthrough…'}
              </div>
            ) : (
              <>
                <h2 className="app-waiting__title">Getting your walkthrough ready</h2>
                <PreparationSteps stage="parsing" />
                <p className="app-waiting__hint">
                  This can take a minute or two. The report opens as soon as it has been read.
                </p>
              </>
            )}
          </div>
        ) : (
          <HomeScreen
            demos={demos}
            onDemoSelected={handleDemoSelected}
            onFileSelected={handleFileSelected}
            error={status === 'error' ? errorMessage : null}
          />
        )}
      </main>
    </div>
  )
}

export default App

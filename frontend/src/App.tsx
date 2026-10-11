import { useEffect, useState } from 'react'
import './App.css'
import { loadDevSample } from './api/devSamples'
import { parseReport } from './api/reports'
import { HomeScreen } from './components/HomeScreen'
import { PreparationSteps } from './components/report/PreparationSteps'
import { ReportView } from './components/report/ReportView'
import { seedNarration } from './narration/useGeneratedNarration'
import type { FinancialReport } from './types/report'

// 'idle': the start page. 'parsing': a report is on its way. Once there is a report it
// takes over the whole page (ReportView), whatever the status was.
type Status = 'idle' | 'parsing' | 'error'

// Dev-only `?sample=<name>[&version=<v>]`: preview a saved run instead of uploading a
// PDF. Read once at startup; production builds compile this down to null.
function readDevSampleParams(): { name: string; version: string | null } | null {
  if (!import.meta.env.DEV) return null
  const params = new URLSearchParams(window.location.search)
  const name = params.get('sample')
  return name ? { name, version: params.get('version') } : null
}

function App() {
  const [devSample] = useState(readDevSampleParams)
  const [status, setStatus] = useState<Status>(devSample ? 'parsing' : 'idle')
  const [report, setReport] = useState<FinancialReport | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [isSample, setIsSample] = useState(false)

  useEffect(() => {
    if (!devSample) return
    let cancelled = false
    loadDevSample(devSample.name, devSample.version).then(
      (sample) => {
        if (cancelled) return
        // Seeded before the report renders, so the saved narration is used as-is and
        // no generation request (and no API cost) ever happens.
        seedNarration(sample.report, sample.narration, sample.audio)
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

  const handleFileSelected = async (file: File) => {
    setStatus('parsing')
    setErrorMessage(null)
    setIsSample(false)
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
  }

  if (report) {
    const sampleLabel =
      isSample && devSample ? `Saved sample: ${devSample.name}${devSample.version ? ` (${devSample.version})` : ''}` : null
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
        <h1 className="app-header__title">Financial Agent</h1>
        <span className="app-header__tagline">AI-narrated financial report walkthroughs</span>
      </header>

      <main className="app-main">
        {status === 'parsing' ? (
          <div className="app-waiting">
            {devSample ? (
              <div className="status-banner status-banner--loading">
                <span className="spinner" aria-hidden="true" />
                Loading saved sample…
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
          <HomeScreen onFileSelected={handleFileSelected} error={status === 'error' ? errorMessage : null} />
        )}
      </main>
    </div>
  )
}

export default App

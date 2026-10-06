import { useEffect, useState } from 'react'
import './App.css'
import { loadDevSample } from './api/devSamples'
import { parseReport } from './api/reports'
import { PdfUploader } from './components/PdfUploader'
import { ReportView } from './components/report/ReportView'
import { seedNarration } from './narration/useGeneratedNarration'
import type { FinancialReport } from './types/report'

type ParseStatus = 'idle' | 'parsing' | 'success' | 'error'

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
  const [status, setStatus] = useState<ParseStatus>(devSample ? 'parsing' : 'idle')
  const [report, setReport] = useState<FinancialReport | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [isSample, setIsSample] = useState(false)
  // Bumped on reset to remount PdfUploader with fresh internal state (selected file, etc).
  const [uploaderKey, setUploaderKey] = useState(0)

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
        setStatus('success')
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
      setStatus('success')
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'Failed to parse report.')
      setStatus('error')
    }
  }

  const handleReset = () => {
    setStatus('idle')
    setReport(null)
    setErrorMessage(null)
    setIsSample(false)
    setUploaderKey((key) => key + 1)
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
        <PdfUploader key={uploaderKey} onFileSelected={handleFileSelected} disabled={status === 'parsing'} />

        {status === 'parsing' && (
          <div className="status-banner status-banner--loading">
            <span className="spinner" aria-hidden="true" />
            {devSample && !report ? 'Loading saved sample…' : 'Parsing report…'}
          </div>
        )}

        {status === 'error' && errorMessage && (
          <div className="status-banner status-banner--error">{errorMessage}</div>
        )}

        {status === 'success' && report && (
          <section className="report-panel">
            <div className="report-panel__header">
              <div>
                <h2 className="report-panel__title">{report.meta.company_name}</h2>
                <span className="report-panel__meta">
                  {report.meta.report_type} · {report.meta.fiscal_period}
                </span>
                {isSample && devSample && (
                  <span className="report-panel__sample-badge" title="Loaded from a saved run - no API calls">
                    Saved sample: {devSample.name}
                    {devSample.version ? ` (${devSample.version})` : ''}
                  </span>
                )}
              </div>
              <button type="button" className="report-panel__reset" onClick={handleReset}>
                Upload another report
              </button>
            </div>
            <ReportView report={report} />
          </section>
        )}
      </main>
    </div>
  )
}

export default App

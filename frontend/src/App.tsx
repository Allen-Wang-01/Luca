import { useState } from 'react'
import './App.css'
import { parseReport } from './api/reports'
import { PdfUploader } from './components/PdfUploader'
import { ReportView } from './components/report/ReportView'
import type { FinancialReport } from './types/report'

type ParseStatus = 'idle' | 'parsing' | 'success' | 'error'

function App() {
  const [status, setStatus] = useState<ParseStatus>('idle')
  const [report, setReport] = useState<FinancialReport | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  // Bumped on reset to remount PdfUploader with fresh internal state (selected file, etc).
  const [uploaderKey, setUploaderKey] = useState(0)

  const handleFileSelected = async (file: File) => {
    setStatus('parsing')
    setErrorMessage(null)
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
            Parsing report…
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

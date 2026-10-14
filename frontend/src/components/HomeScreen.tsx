import type { DevSampleSummary } from '../api/devSamples'
import { PdfUploader } from './PdfUploader'
import './HomeScreen.css'

interface HomeScreenProps {
  // Reports read earlier that open without uploading anything; may be empty.
  demos: DevSampleSummary[]
  // `live`: have the advisor prepare the walkthrough again instead of playing the saved one.
  onDemoSelected: (name: string, live: boolean) => void
  onFileSelected: (file: File) => void
  // Why the last upload didn't go through, if it didn't.
  error: string | null
}

const STEPS = [
  {
    title: 'Upload the report',
    detail: 'An earnings release or a set of financial statements, as the PDF the company published.',
  },
  {
    title: 'Your advisor reads it',
    detail: 'Every figure is read off the page, the totals are checked, and the numbers that matter are worked out.',
  },
  {
    title: 'Watch the walkthrough',
    detail: 'A spoken explanation, with each figure lit up on the report as it is mentioned.',
  },
]

// A still of what a walkthrough looks like, drawn with made-up figures: a statement
// with one figure lit, the card that repeats it, and the line being spoken.
function WalkthroughPreview() {
  return (
    <div className="home-preview" aria-hidden="true">
      <div className="home-preview__table">
        <div className="home-preview__row home-preview__row--head">
          <span />
          <span>This year</span>
          <span>Last year</span>
        </div>
        <div className="home-preview__row home-preview__row--dim">
          <span>Revenue</span>
          <span>12,400</span>
          <span>8,100</span>
        </div>
        <div className="home-preview__row home-preview__row--dim">
          <span>Cost of sales</span>
          <span>7,150</span>
          <span>4,960</span>
        </div>
        <div className="home-preview__row home-preview__row--active">
          <span>Operating income</span>
          <span className="home-preview__cell--active">2,900</span>
          <span>1,640</span>
        </div>
        <div className="home-preview__row home-preview__row--dim">
          <span>Net income</span>
          <span>2,210</span>
          <span>1,270</span>
        </div>
      </div>
      <div className="home-preview__card">
        <span className="home-preview__card-label">Operating income · This year</span>
        <span className="home-preview__card-value">2,900</span>
      </div>
      <div className="home-preview__caption">
        <span className="home-preview__play" />
        Operating income nearly doubled - profit is growing faster than sales.
      </div>
    </div>
  )
}

// The start page: what this is, the upload, and what to expect.
export function HomeScreen({ demos, onDemoSelected, onFileSelected, error }: HomeScreenProps) {
  return (
    <div className="home">
      <section className="home__hero">
        <div className="home__intro">
          <h2 className="home__headline">A financial report, explained out loud.</h2>
          <p className="home__lede">
            Upload a company's report and an AI advisor walks you through it - what the numbers are, how they
            changed, and what that means - pointing at each figure on the page as it goes.
          </p>
          <PdfUploader onFileSelected={onFileSelected} />
          {error && <div className="status-banner status-banner--error">{error}</div>}
          {demos.length > 0 && (
            <div className="home__demos">
              <p className="home__demos-title">Or try a report that has already been read - no upload</p>
              <div className="home__demo-list">
                {demos.map((demo) => (
                  <div key={demo.name} className="home__demo">
                    <span className="home__demo-company">{demo.company_name}</span>
                    <span className="home__demo-period">
                      {demo.report_type} · {demo.fiscal_period}
                    </span>
                    <div className="home__demo-actions">
                      <button
                        type="button"
                        className="home__demo-button home__demo-button--primary"
                        onClick={() => onDemoSelected(demo.name, false)}
                      >
                        Play the walkthrough
                      </button>
                      <button
                        type="button"
                        className="home__demo-button"
                        onClick={() => onDemoSelected(demo.name, true)}
                      >
                        Run the agent live
                      </button>
                    </div>
                  </div>
                ))}
              </div>
              <p className="home__demos-note">
                Running the agent live prepares a new walkthrough for real, which takes about two minutes, and
                plays it with captions. The saved walkthrough opens at once, with the voice where one was recorded.
              </p>
            </div>
          )}
        </div>
        <WalkthroughPreview />
      </section>

      <ol className="home__steps">
        {STEPS.map((step, index) => (
          <li key={step.title} className="home__step">
            <span className="home__step-number">{index + 1}</span>
            <h3 className="home__step-title">{step.title}</h3>
            <p className="home__step-detail">{step.detail}</p>
          </li>
        ))}
      </ol>

      <p className="home__scope">
        Works with English-language earnings releases and financial statements of listed companies, as PDFs up to
        25MB. Banks, insurers and funds aren't supported yet. The walkthrough is an automated reading of the
        report, not investment advice.
      </p>
    </div>
  )
}

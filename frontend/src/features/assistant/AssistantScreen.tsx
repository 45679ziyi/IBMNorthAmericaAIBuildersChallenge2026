import { useState } from 'react'
import './AssistantScreen.css'
import { askAssistant, AssistantResponse } from '../../api/client'

const EXAMPLE_PROMPTS = [
  'What is FERPA and how does it protect student records?',
  'How can I access my education records at SBU?',
  'Where is Melville Library and what services does it offer?',
  'What is the SBU events calendar feed?',
]

function fmtDate(iso: string) {
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

export default function AssistantScreen() {
  const [question, setQuestion] = useState('')
  const [response, setResponse] = useState<AssistantResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [history, setHistory] = useState<{ q: string; r: AssistantResponse }[]>([])

  async function handleAsk(q = question) {
    if (!q.trim()) return
    setLoading(true); setError(null); setResponse(null)
    try {
      const r = await askAssistant(q)
      setResponse(r)
      setHistory(h => [{ q, r }, ...h].slice(0, 10))
    } catch (e) { setError(String(e)) }
    setLoading(false)
  }

  return (
    <div>
      <div className="screen-title">
        <h1>Campus Assistant</h1>
        <p>Ask questions grounded in the curated SBU public knowledge base.</p>
      </div>

      <div className="card mb-2" role="note" style={{ background: '#f0f9ff', borderColor: '#bae6fd' }}>
        <p className="text-sm" style={{ margin: 0 }}>
          <strong>Knowledge source:</strong> A small curated set of public SBU policy pages. Answers are for informational purposes only.
          Verify important decisions with the official university source linked below each answer.
        </p>
      </div>

      {/* Example prompts */}
      <div className="mb-2">
        <p className="text-muted text-sm">Try an example:</p>
        <div className="example-prompts">
          {EXAMPLE_PROMPTS.map(p => (
            <button key={p} className="btn btn-ghost btn-sm" onClick={() => { setQuestion(p); handleAsk(p) }}>
              {p}
            </button>
          ))}
        </div>
      </div>

      {/* Input */}
      <form className="ask-form" onSubmit={e => { e.preventDefault(); handleAsk() }} aria-label="Ask assistant">
        <input
          type="text"
          placeholder="Ask about SBU policies, calendar, library, events…"
          value={question}
          onChange={e => setQuestion(e.target.value)}
          aria-label="Your question"
          disabled={loading}
        />
        <button type="submit" className="btn btn-primary" disabled={loading || !question.trim()}>
          {loading ? 'Searching…' : 'Ask'}
        </button>
      </form>

      {error && <div className="state-error mt-1" role="alert">{error}</div>}

      {/* Current response */}
      {response && (
        <div className="answer-card card mt-2" role="region" aria-label="Answer">
          <div className="flex items-center gap-1 mb-1">
            <strong>Answer</strong>
            <span className={`coverage-${response.coverage}`}>
              ({response.coverage === 'supported' ? '✓ Supported' : response.coverage === 'partial' ? '⚠ Partial' : '✕ Not found'})
            </span>
          </div>
          <p style={{ whiteSpace: 'pre-wrap' }}>{response.answer}</p>

          {response.sources.length > 0 && (
            <div className="sources-section">
              <strong className="text-sm">Sources:</strong>
              <ul className="sources-list">
                {response.sources.map((s, i) => (
                  <li key={i} className="source-item">
                    <a href={s.url} target="_blank" rel="noopener noreferrer">{s.title}</a>
                    <span className="text-muted text-sm"> — {s.publisher} · Last verified: {fmtDate(s.last_verified_at_utc)}</span>
                    <p className="text-muted text-sm excerpt">{s.excerpt}</p>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <p className="text-muted text-sm mt-1" style={{ fontStyle: 'italic' }}>{response.disclaimer}</p>
        </div>
      )}

      {/* History */}
      {history.length > 1 && (
        <div className="mt-2">
          <h3>Previous questions</h3>
          <ul className="history-list">
            {history.slice(1).map((h, i) => (
              <li key={i} className="card" style={{ padding: '.6rem 1rem' }}>
                <button className="btn btn-ghost btn-sm" style={{ justifyContent: 'flex-start', width: '100%', textAlign: 'left' }}
                  onClick={() => { setQuestion(h.q); setResponse(h.r) }}>
                  {h.q}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

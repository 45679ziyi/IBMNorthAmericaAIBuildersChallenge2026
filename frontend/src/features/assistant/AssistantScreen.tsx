import { useState, useRef, useEffect } from 'react'
import './AssistantScreen.css'
import { askAssistant, AssistantResponse } from '../../api/client'
import { Send, ExternalLink, CheckCircle, AlertCircle, XCircle } from 'lucide-react'

const SUGGESTED_CHIPS = [
  'What is FERPA?',
  'How do I access my education records?',
  'Where is the library?',
]

// Scenario-specific personal chips (shown alongside general chips)
const PERSONAL_CHIPS = [
  'What changed today?',
  'Where do I need to be next?',
  'Can I finish the assignment tonight?',
]

function fmtDate(iso: string) {
  return new Date(iso).toLocaleDateString('en-US', {
    month: 'short', day: 'numeric', year: 'numeric',
  })
}

interface ChatEntry {
  id: number
  role: 'user' | 'assistant'
  text: string
  response?: AssistantResponse
  isLoading?: boolean
}

// ── Detect personal answer (campus data, not official sources) ────────────────
function isPersonalAnswer(response: AssistantResponse): boolean {
  return (
    response.disclaimer.startsWith('Answer built from your campus data') ||
    (response.sources.length > 0 && response.sources.every(s => s.url === '#'))
  )
}

// ── Coverage line (text + icon, not color-only) ───────────────────────────────
function CoverageLine({ response }: { response: AssistantResponse }) {
  const { coverage } = response
  const personal = isPersonalAnswer(response)

  if (personal) {
    const Icon = coverage === 'supported' ? CheckCircle : coverage === 'partial' ? AlertCircle : XCircle
    const cls = `coverage-line coverage-line-${coverage === 'supported' ? 'supported' : coverage === 'partial' ? 'partial' : 'not-found'}`
    return (
      <div className={cls}>
        <Icon size={14} aria-hidden="true" />
        <span>Personal context</span>
        {coverage === 'partial' && <span className="coverage-provider">Partial — no scenario loaded</span>}
      </div>
    )
  }

  if (coverage === 'supported') {
    return (
      <div className="coverage-line coverage-line-supported">
        <CheckCircle size={14} aria-hidden="true" />
        <span>Verified from {response.sources.length} official source{response.sources.length !== 1 ? 's' : ''}</span>
      </div>
    )
  }
  if (coverage === 'partial') {
    return (
      <div className="coverage-line coverage-line-partial">
        <AlertCircle size={14} aria-hidden="true" />
        <span>Partly covered. Check the sources below.</span>
      </div>
    )
  }
  return (
    <div className="coverage-line coverage-line-not-found">
      <XCircle size={14} aria-hidden="true" />
      <span>Couldn't verify this. Try the official site.</span>
    </div>
  )
}

// ── Main screen ───────────────────────────────────────────────────────────────
export default function AssistantScreen() {
  const [thread, setThread] = useState<ChatEntry[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [idCounter, setIdCounter] = useState(0)
  const bottomRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [thread])

  function nextId() {
    const id = idCounter + 1
    setIdCounter(id)
    return id
  }

  async function handleAsk(q = input.trim()) {
    if (!q || loading) return
    setInput('')

    const userId = nextId()
    const loadingId = userId + 1
    setIdCounter(loadingId)

    setThread(prev => [
      ...prev,
      { id: userId, role: 'user', text: q },
      { id: loadingId, role: 'assistant', text: '', isLoading: true },
    ])
    setLoading(true)

    try {
      const r = await askAssistant(q)
      setThread(prev => prev.map(e =>
        e.id === loadingId
          ? { id: loadingId, role: 'assistant', text: r.answer, response: r }
          : e
      ))
    } catch (err) {
      setThread(prev => prev.map(e =>
        e.id === loadingId
          ? { id: loadingId, role: 'assistant', text: `Couldn't get an answer. Check that the backend is running on port 8000, then try again.` }
          : e
      ))
    }
    setLoading(false)
    inputRef.current?.focus()
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    // Enter sends; Shift+Enter adds newline
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleAsk()
    }
  }

  return (
    <div className="assistant-layout">
      <div className="screen-title">
        <h1>Ask</h1>
        <p>Questions grounded in public SBU knowledge sources.</p>
      </div>

      <div className="assistant-notice card" role="note">
        <p className="text-sm">
          <strong>Knowledge source:</strong> A curated set of public SBU policy pages.
          Verify important decisions with the official source.
        </p>
      </div>

      {/* Chat thread */}
      <div className="chat-thread" role="region" aria-label="Conversation" tabIndex={0}>
        {thread.length === 0 && (
          <div className="chat-empty">
            <p className="chat-empty-prompt">Ask anything about SBU policies, calendar, library, or campus events.</p>
            <div className="suggested-chips" aria-label="Suggested questions">
              {SUGGESTED_CHIPS.map(p => (
                <button key={p} className="chip-btn" onClick={() => handleAsk(p)}>
                  {p}
                </button>
              ))}
            </div>
            <p className="chat-chips-label text-muted text-sm">Today's context:</p>
            <div className="suggested-chips suggested-chips-personal" aria-label="Personal context questions">
              {PERSONAL_CHIPS.map(p => (
                <button key={p} className="chip-btn chip-btn-personal" onClick={() => handleAsk(p)}>
                  {p}
                </button>
              ))}
            </div>
          </div>
        )}

        <div role="log" aria-live="polite" aria-label="Conversation messages">
          {thread.map(entry => (
            <div
              key={entry.id}
              className={`chat-bubble-row chat-bubble-row-${entry.role}`}
            >
              <div className={`chat-bubble chat-bubble-${entry.role}`}>
                {entry.isLoading
                  ? <span className="chat-searching" aria-label="Searching sources…">Searching sources…</span>
                  : (
                    <>
                      <p className="chat-text">{entry.text}</p>

                      {entry.response && (
                        <div className="chat-meta">
                          <CoverageLine response={entry.response} />

                          {entry.response.sources.length > 0 && (
                            <details className="sources-details">
                              <summary className="sources-summary">
                                {entry.response.sources.length} source{entry.response.sources.length > 1 ? 's' : ''}
                              </summary>
                              <ul className="sources-list">
                                {entry.response.sources.map((s, i) => (
                                  <li key={i} className="source-item">
                                    <a
                                      href={s.url}
                                      target="_blank"
                                      rel="noopener noreferrer"
                                      className="source-link-row"
                                    >
                                      {s.title}
                                      <ExternalLink size={11} aria-hidden="true" />
                                    </a>
                                    <span className="text-muted text-sm">
                                      {s.publisher} · last verified {fmtDate(s.last_verified_at_utc)}
                                    </span>
                                    <details className="source-excerpt-details">
                                      <summary className="text-sm source-excerpt-toggle">Show excerpt</summary>
                                      <p className="text-muted text-sm source-excerpt">{s.excerpt}</p>
                                    </details>
                                  </li>
                                ))}
                              </ul>
                            </details>
                          )}

                          <p className="chat-disclaimer text-muted">{entry.response.disclaimer}</p>
                        </div>
                      )}
                    </>
                  )
                }
              </div>
            </div>
          ))}
        </div>

        <div ref={bottomRef} aria-hidden="true" />
      </div>

      {/* Composer — sticky at bottom, above tab bar */}
      <div className="chat-composer-wrap">
        <form
          className="chat-input-bar"
          onSubmit={e => { e.preventDefault(); handleAsk() }}
          aria-label="Ask assistant"
        >
          <textarea
            ref={inputRef}
            placeholder="Ask about SBU policies, calendar, library, events… (Enter to send)"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            aria-label="Your question"
            disabled={loading}
            autoComplete="off"
            rows={1}
            className="chat-textarea"
          />
          <button
            type="submit"
            className="btn btn-primary btn-icon"
            disabled={loading || !input.trim()}
            aria-label="Send"
          >
            <Send size={16} aria-hidden="true" />
          </button>
        </form>
      </div>
    </div>
  )
}

import { useState, useRef, useEffect } from 'react'
import './AssistantScreen.css'
import { askAssistant, AssistantResponse } from '../../api/client'
import { Send, Bot, User, ExternalLink } from 'lucide-react'

const EXAMPLE_PROMPTS = [
  'What is FERPA and how does it protect student records?',
  'How can I access my education records at SBU?',
  'Where is Melville Library and what services does it offer?',
  'What is the SBU events calendar feed?',
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

// ── Coverage badge ──────────────────────────────────────────────────────────
function CoverageBadge({ coverage }: { coverage: 'supported' | 'partial' | 'not_found' }) {
  const map: Record<string, { cls: string; label: string }> = {
    supported: { cls: 'badge-ok', label: '✓ Supported' },
    partial:   { cls: 'badge-warn', label: '⚠ Partial' },
    not_found: { cls: 'badge-err', label: '✕ Not found' },
  }
  const { cls, label } = map[coverage] ?? map.not_found
  return <span className={`badge ${cls}`}>{label}</span>
}

// ── Main screen ─────────────────────────────────────────────────────────────
export default function AssistantScreen() {
  const [thread, setThread] = useState<ChatEntry[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [idCounter, setIdCounter] = useState(0)
  const bottomRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [thread])

  function nextId() {
    const id = idCounter + 1
    setIdCounter(id)
    return id
  }

  async function handleAsk(q = input) {
    if (!q.trim() || loading) return
    setInput('')

    const userId = nextId()
    const loadingId = userId + 1
    setIdCounter(loadingId)

    // Add user bubble + loading bubble atomically
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
          ? { id: loadingId, role: 'assistant', text: `Error: ${String(err)}` }
          : e
      ))
    }
    setLoading(false)
    inputRef.current?.focus()
  }

  function handleExampleClick(p: string) {
    setInput(p)
    handleAsk(p)
  }

  return (
    <div className="assistant-layout">
      <div className="screen-title">
        <h1>Campus Assistant</h1>
        <p>Ask questions grounded in the curated SBU public knowledge base.</p>
      </div>

      <div className="assistant-notice card" role="note">
        <p className="text-sm" style={{ margin: 0 }}>
          <strong>Knowledge source:</strong> A small curated set of public SBU policy pages.
          Answers are for informational purposes only. Verify important decisions with the official source.
        </p>
      </div>

      {/* Chat thread */}
      <div className="chat-thread" aria-label="Conversation" aria-live="polite">
        {thread.length === 0 && (
          <div className="chat-empty">
            <Bot size={32} strokeWidth={1.5} aria-hidden="true" />
            <p>Ask anything about SBU policies, calendar, library, or campus events.</p>
            <div className="example-prompts">
              {EXAMPLE_PROMPTS.map(p => (
                <button key={p} className="btn btn-ghost btn-sm" onClick={() => handleExampleClick(p)}>
                  {p}
                </button>
              ))}
            </div>
          </div>
        )}

        {thread.map(entry => (
          <div
            key={entry.id}
            className={`chat-bubble-row chat-bubble-row-${entry.role}`}
          >
            <div className={`chat-avatar chat-avatar-${entry.role}`} aria-hidden="true">
              {entry.role === 'user' ? <User size={14} /> : <Bot size={14} />}
            </div>

            <div className={`chat-bubble chat-bubble-${entry.role}`}>
              {entry.isLoading
                ? (
                  <span className="chat-typing" aria-label="Thinking…">
                    <span /><span /><span />
                  </span>
                )
                : (
                  <>
                    <p style={{ whiteSpace: 'pre-wrap', margin: 0 }}>{entry.text}</p>

                    {entry.response && (
                      <div className="chat-meta">
                        <CoverageBadge coverage={entry.response.coverage} />
                        {entry.response.sources.length > 0 && (
                          <details className="sources-details">
                            <summary className="text-sm" style={{ cursor: 'pointer', color: 'var(--accent)' }}>
                              {entry.response.sources.length} source{entry.response.sources.length > 1 ? 's' : ''}
                            </summary>
                            <ul className="sources-list">
                              {entry.response.sources.map((s, i) => (
                                <li key={i} className="source-item">
                                  <a href={s.url} target="_blank" rel="noopener noreferrer" className="flex items-center gap-1">
                                    {s.title} <ExternalLink size={11} aria-hidden="true" />
                                  </a>
                                  <span className="text-muted text-sm">
                                    {s.publisher} · Verified: {fmtDate(s.last_verified_at_utc)}
                                  </span>
                                  <p className="text-muted text-sm excerpt">{s.excerpt}</p>
                                </li>
                              ))}
                            </ul>
                          </details>
                        )}
                        <p className="text-muted text-sm disclaimer">{entry.response.disclaimer}</p>
                      </div>
                    )}
                  </>
                )
              }
            </div>
          </div>
        ))}

        <div ref={bottomRef} aria-hidden="true" />
      </div>

      {/* Input bar */}
      <form
        className="chat-input-bar"
        onSubmit={e => { e.preventDefault(); handleAsk() }}
        aria-label="Ask assistant"
      >
        <input
          ref={inputRef}
          type="text"
          placeholder="Ask about SBU policies, calendar, library, events…"
          value={input}
          onChange={e => setInput(e.target.value)}
          aria-label="Your question"
          disabled={loading}
          autoComplete="off"
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
  )
}

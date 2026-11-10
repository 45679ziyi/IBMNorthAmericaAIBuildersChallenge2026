import { useState, useEffect } from 'react'
import {
  getEvents, createCourseUpdateDraft, previewCourseUpdate, approveCourseUpdate,
  type CalendarEvent, type CourseUpdateDraft,
} from '../../api/client'
import { useIdentity } from '../../hooks/useIdentity'
import { LoadingState } from '../../components/states/LoadingState'
import { ErrorState } from '../../components/states/ErrorState'
import { EmptyState } from '../../components/states/EmptyState'
import { PermissionDenied } from '../../components/states/PermissionDenied'
import '../../components/states/states.css'
import './FacultyScreen.css'

const AI_BADGE_VALIDATED = '✓ Plain language by AI, facts verified'
const AI_BADGE_FALLBACK  = 'Rule-based extraction'

function AIBadge({ fallbackUsed, validated }: { fallbackUsed?: boolean; validated?: boolean }) {
  if (fallbackUsed) return <span className="ai-badge ai-badge-fallback">{AI_BADGE_FALLBACK}</span>
  if (validated)    return <span className="ai-badge ai-badge-validated">{AI_BADGE_VALIDATED}</span>
  return null
}

// ── Course Update Composer ────────────────────────────────────────────────────

function CourseUpdateComposer({ sectionId, onClose }: { sectionId: string; onClose: () => void }) {
  const [text, setText] = useState('')
  const [draft, setDraft] = useState<CourseUpdateDraft | null>(null)
  const [preview, setPreview] = useState<{ preview: string; recipients: number } | null>(null)
  const [step, setStep] = useState<'compose' | 'extracted' | 'preview' | 'done'>('compose')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  async function handleCompose() {
    if (!text.trim()) return
    setBusy(true); setErr(null)
    try {
      const d = await createCourseUpdateDraft(sectionId, text.trim())
      setDraft(d)
      setStep('extracted')
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : 'Failed')
    } finally {
      setBusy(false)
    }
  }

  async function handlePreview() {
    if (!draft) return
    setBusy(true); setErr(null)
    try {
      const p = await previewCourseUpdate(draft.id)
      setPreview(p)
      setStep('preview')
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : 'Failed')
    } finally {
      setBusy(false)
    }
  }

  async function handleApprove() {
    if (!draft) return
    setBusy(true); setErr(null)
    try {
      await approveCourseUpdate(draft.id)
      setStep('done')
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : 'Failed')
    } finally {
      setBusy(false)
    }
  }

  const ex = draft?.extracted

  return (
    <div className="cu-composer">
      <div className="cu-header">
        <h3>Course Update — {sectionId}</h3>
        <button className="btn btn-ghost btn-sm" onClick={onClose}>✕</button>
      </div>

      {step === 'compose' && (
        <>
          <textarea
            className="form-control cu-textarea"
            rows={4}
            maxLength={4000}
            placeholder="Write an update for your students (e.g. new deadline, room change, office hours)…"
            value={text}
            onChange={e => setText(e.target.value)}
          />
          {err && <p className="form-error">{err}</p>}
          <div className="cu-actions">
            <button className="btn btn-primary" disabled={!text.trim() || busy} onClick={handleCompose}>
              {busy ? 'Extracting…' : 'Extract deadline →'}
            </button>
          </div>
        </>
      )}

      {step === 'extracted' && draft && (
        <>
          <div className="cu-extracted">
            <p className="cu-text-preview">{draft.text}</p>
            {ex && ex.confidence > 0 ? (
              <dl className="cu-dl">
                {ex.due_date && <><dt>Due date</dt><dd>{ex.due_date}{ex.due_time ? ` at ${ex.due_time}` : ''}</dd></>}
                {ex.est_minutes && <><dt>Est. time</dt><dd>{Math.round(ex.est_minutes / 60)} hr</dd></>}
                <dt>Confidence</dt><dd>{Math.round(ex.confidence * 100)}%</dd>
                {ex.quote && <><dt>Quote</dt><dd className="cu-quote">{ex.quote}</dd></>}
              </dl>
            ) : (
              <p className="cu-no-deadline">No deadline detected.</p>
            )}
            <AIBadge fallbackUsed={true} />
          </div>
          {err && <p className="form-error">{err}</p>}
          <div className="cu-actions">
            <button className="btn btn-secondary" onClick={() => setStep('compose')}>← Edit</button>
            <button className="btn btn-primary" disabled={busy} onClick={handlePreview}>
              {busy ? 'Previewing…' : 'Preview →'}
            </button>
          </div>
        </>
      )}

      {step === 'preview' && preview && (
        <>
          <div className="cu-preview-box">
            <p className="cu-preview-label">Students will see:</p>
            <blockquote className="cu-preview-text">{preview.preview}</blockquote>
            <p className="cu-recipients">Recipients: {preview.recipients >= 5 ? preview.recipients : 'fewer than 5'}</p>
          </div>
          {err && <p className="form-error">{err}</p>}
          <div className="cu-actions">
            <button className="btn btn-secondary" onClick={() => setStep('extracted')}>← Back</button>
            <button className="btn btn-primary" disabled={busy} onClick={handleApprove}>
              {busy ? 'Publishing…' : 'Approve & Publish'}
            </button>
          </div>
        </>
      )}

      {step === 'done' && (
        <div className="cu-done">
          <p>✓ Update published. Students have been notified.</p>
          <button className="btn btn-secondary" onClick={onClose}>Close</button>
        </div>
      )}
    </div>
  )
}

// ── Main Screen ───────────────────────────────────────────────────────────────

export default function FacultyScreen() {
  const { me } = useIdentity()
  const [classes, setClasses] = useState<CalendarEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [composingFor, setComposingFor] = useState<string | null>(null)

  useEffect(() => {
    getEvents()
      .then(evs => setClasses(evs.filter(e => e.event_type === 'class')))
      .catch(e => setError(String(e)))
      .finally(() => setLoading(false))
  }, [])

  if (me && me.role !== 'faculty' && me.role !== 'academic_ops') {
    return <PermissionDenied requiredRole="faculty" currentRole={me.role} />
  }

  if (loading) return <LoadingState message="Loading courses…" />
  if (error) return <ErrorState message={error} onRetry={() => { setLoading(true); setError(null) }} />

  return (
    <div className="faculty-screen">
      <div className="screen-title">
        <h1>Faculty Workspace</h1>
        <p>Manage your courses and publish updates for students.</p>
      </div>

      {composingFor && (
        <CourseUpdateComposer
          sectionId={composingFor}
          onClose={() => setComposingFor(null)}
        />
      )}

      <section>
        <h2>Today's Classes</h2>
        {classes.length === 0 ? (
          <EmptyState title="No classes today" message="Your class schedule will appear here." />
        ) : (
          <ul className="faculty-class-list">
            {classes.map(cls => (
              <li key={cls.id} className="faculty-class-card card">
                <div className="faculty-class-row">
                  <div>
                    <strong className="faculty-class-title">{cls.title}</strong>
                    {cls.location_text && (
                      <span className="faculty-class-room">📍 {cls.location_text}</span>
                    )}
                    <span className="faculty-class-time text-muted text-sm">
                      {new Date(cls.start_at_utc).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      {' – '}
                      {new Date(cls.end_at_utc).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </span>
                  </div>
                  <button
                    className="btn btn-secondary btn-sm"
                    onClick={() => setComposingFor(cls.source_reference ?? cls.id)}
                  >
                    Post update
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}

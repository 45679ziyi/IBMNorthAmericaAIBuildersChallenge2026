import { useEffect, useState } from 'react'
import './TasksScreen.css'
import { getTasks, createTask, updateTask, deleteTask, Task } from '../../api/client'

const PRIORITY_LABELS: Record<string, string> = { low: 'Low', normal: 'Normal', high: 'High', urgent: 'Urgent' }

function fmtDue(iso: string | undefined) {
  if (!iso) return null
  return new Date(iso).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', timeZone: 'America/New_York' })
}

const EMPTY_FORM = {
  title: '', description: '', course_label: '', due_at_utc: '',
  estimated_minutes: 30, priority: 'normal' as Task['priority'], status: 'todo' as Task['status'],
}

export default function TasksScreen() {
  const [tasks, setTasks] = useState<Task[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [form, setForm] = useState(EMPTY_FORM)
  const [editing, setEditing] = useState<string | null>(null)
  const [showForm, setShowForm] = useState(false)

  const load = () => getTasks().then(setTasks).catch(e => setError(String(e))).finally(() => setLoading(false))
  useEffect(() => { load() }, [])

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const payload = {
      ...form,
      due_at_utc: form.due_at_utc ? new Date(form.due_at_utc).toISOString() : undefined,
    }
    try {
      if (editing) {
        await updateTask(editing, payload)
      } else {
        await createTask({ ...payload, source_type: 'manual' })
      }
      setForm(EMPTY_FORM); setEditing(null); setShowForm(false)
      load()
    } catch (err) { setError(String(err)) }
  }

  async function handleComplete(t: Task) {
    await updateTask(t.id, { status: t.status === 'done' ? 'todo' : 'done' })
    load()
  }

  async function handleDelete(id: string) {
    if (!confirm('Delete this task?')) return
    await deleteTask(id)
    load()
  }

  function startEdit(t: Task) {
    setForm({
      title: t.title,
      description: t.description ?? '',
      course_label: t.course_label ?? '',
      due_at_utc: t.due_at_utc ? new Date(t.due_at_utc).toISOString().slice(0, 16) : '',
      estimated_minutes: t.estimated_minutes,
      priority: t.priority,
      status: t.status,
    })
    setEditing(t.id)
    setShowForm(true)
  }

  if (loading) return <div className="state-loading">Loading tasks…</div>

  const open = tasks.filter(t => t.status !== 'done')
  const done = tasks.filter(t => t.status === 'done')

  return (
    <div>
      <div className="screen-title flex justify-between items-center" style={{ flexWrap: 'wrap', gap: '.5rem' }}>
        <div>
          <h1>Tasks</h1>
          <p>Manage your tasks and assignments. Demo tasks are labeled.</p>
        </div>
        <button className="btn btn-primary btn-sm" onClick={() => { setForm(EMPTY_FORM); setEditing(null); setShowForm(s => !s) }}>
          {showForm && !editing ? '✕ Cancel' : '+ New Task'}
        </button>
      </div>

      {error && <div className="state-error mb-2">{error}</div>}

      {showForm && (
        <form className="card mb-2" onSubmit={handleSubmit} aria-label="Task form">
          <h3>{editing ? 'Edit Task' : 'New Task'}</h3>
          <div className="grid-2">
            <div>
              <label htmlFor="t-title">Title *</label>
              <input id="t-title" required value={form.title} onChange={e => setForm(f => ({ ...f, title: e.target.value }))} />
            </div>
            <div>
              <label htmlFor="t-course">Course label</label>
              <input id="t-course" placeholder="CSE 213" value={form.course_label} onChange={e => setForm(f => ({ ...f, course_label: e.target.value }))} />
            </div>
            <div>
              <label htmlFor="t-due">Due date/time</label>
              <input id="t-due" type="datetime-local" value={form.due_at_utc} onChange={e => setForm(f => ({ ...f, due_at_utc: e.target.value }))} />
            </div>
            <div>
              <label htmlFor="t-est">Estimated duration (min)</label>
              <input id="t-est" type="number" min={1} max={1440} value={form.estimated_minutes}
                onChange={e => setForm(f => ({ ...f, estimated_minutes: parseInt(e.target.value) || 30 }))} />
            </div>
            <div>
              <label htmlFor="t-pri">Priority</label>
              <select id="t-pri" value={form.priority} onChange={e => setForm(f => ({ ...f, priority: e.target.value as Task['priority'] }))}>
                {Object.entries(PRIORITY_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </div>
            <div>
              <label htmlFor="t-status">Status</label>
              <select id="t-status" value={form.status} onChange={e => setForm(f => ({ ...f, status: e.target.value as Task['status'] }))}>
                <option value="todo">To Do</option>
                <option value="in_progress">In Progress</option>
                <option value="done">Done</option>
              </select>
            </div>
          </div>
          <div className="mt-1">
            <label htmlFor="t-desc">Notes</label>
            <textarea id="t-desc" rows={2} value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} />
          </div>
          <div className="flex gap-1 mt-1">
            <button type="submit" className="btn btn-primary btn-sm">{editing ? 'Save Changes' : 'Add Task'}</button>
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => { setShowForm(false); setEditing(null); setForm(EMPTY_FORM) }}>Cancel</button>
          </div>
        </form>
      )}

      <section aria-labelledby="open-tasks">
        <h2 id="open-tasks">Open ({open.length})</h2>
        {open.length === 0
          ? <div className="state-empty">No open tasks. Add one above!</div>
          : <ul className="tasks-list">
              {open.map(t => <TaskRow key={t.id} task={t} onComplete={handleComplete} onEdit={startEdit} onDelete={handleDelete} />)}
            </ul>
        }
      </section>

      {done.length > 0 && (
        <section aria-labelledby="done-tasks" className="mt-2">
          <h2 id="done-tasks">Completed ({done.length})</h2>
          <ul className="tasks-list">
            {done.map(t => <TaskRow key={t.id} task={t} onComplete={handleComplete} onEdit={startEdit} onDelete={handleDelete} />)}
          </ul>
        </section>
      )}
    </div>
  )
}

function TaskRow({ task: t, onComplete, onEdit, onDelete }: {
  task: Task
  onComplete: (t: Task) => void
  onEdit: (t: Task) => void
  onDelete: (id: string) => void
}) {
  return (
    <li className={`card task-row ${t.status === 'done' ? 'task-done' : ''}`}>
      <div className="flex items-center gap-1">
        <input type="checkbox" id={`chk-${t.id}`} checked={t.status === 'done'}
          onChange={() => onComplete(t)} aria-label={`Mark "${t.title}" as done`} style={{ width: 'auto', cursor: 'pointer' }} />
        <label htmlFor={`chk-${t.id}`} style={{ fontWeight: 600, flex: 1, cursor: 'pointer', margin: 0 }}>{t.title}</label>
        <span className={`badge badge-${t.priority === 'urgent' ? 'err' : t.priority === 'high' ? 'warn' : 'ok'}`}>{t.priority}</span>
        {t.source_type === 'demo' && <span className="badge badge-demo">DEMO</span>}
      </div>
      {t.course_label && <div className="text-muted text-sm">{t.course_label}</div>}
      {t.due_at_utc && <div className="text-muted text-sm">Due: {fmtDue(t.due_at_utc)} · {t.estimated_minutes} min</div>}
      {t.description && <p className="text-sm mt-1">{t.description}</p>}
      <div className="flex gap-1 mt-1">
        <button className="btn btn-ghost btn-sm" onClick={() => onEdit(t)}>Edit</button>
        <button className="btn btn-danger btn-sm" onClick={() => onDelete(t.id)}>Delete</button>
      </div>
    </li>
  )
}

import { useEffect, useState, useRef } from 'react'
import './TasksScreen.css'
import { getTasks, createTask, updateTask, deleteTask, Task } from '../../api/client'
import { useToast } from '../../components/Toast'
import { useConfirm } from '../../components/ConfirmModal'
import { Sheet } from '../../components/Sheet'
import { EmptyState } from '../../components/EmptyState'
import { SkeletonList } from '../../components/Skeleton'
import { useBadges } from '../../state/badges'
import { relativeDue, isSameDayAsNow, CAMPUS_TZ } from '../../lib/time'
import { MoreVertical } from 'lucide-react'

const PRIORITY_LABELS: Record<Task['priority'], string> = {
  low: 'Low', normal: 'Normal', high: 'High', urgent: 'Urgent',
}

const EMPTY_FORM = {
  title: '', description: '', course_label: '', due_at_utc: '',
  estimated_minutes: 30, priority: 'normal' as Task['priority'],
}

interface TaskFormData {
  title: string
  description: string
  course_label: string
  due_at_utc: string
  estimated_minutes: number
  priority: Task['priority']
}

// ── Task form (used in Sheet) ─────────────────────────────────────────────────
function TaskForm({
  form, setForm, onSubmit, onCancel, editing,
}: {
  form: TaskFormData
  setForm: React.Dispatch<React.SetStateAction<TaskFormData>>
  onSubmit: (e: React.FormEvent) => void
  onCancel: () => void
  editing: boolean
}) {
  return (
    <form onSubmit={onSubmit} aria-label={editing ? 'Edit task' : 'New task'}>
      <div className="grid-2">
        <div>
          <label htmlFor="t-title">Title *</label>
          <input
            id="t-title" required value={form.title}
            onChange={e => setForm(f => ({ ...f, title: e.target.value }))}
            autoFocus
          />
        </div>
        <div>
          <label htmlFor="t-course">Course label</label>
          <input
            id="t-course" placeholder="CSE 213" value={form.course_label}
            onChange={e => setForm(f => ({ ...f, course_label: e.target.value }))}
          />
        </div>
        <div>
          <label htmlFor="t-due">Due date/time</label>
          <input
            id="t-due" type="datetime-local" value={form.due_at_utc}
            onChange={e => setForm(f => ({ ...f, due_at_utc: e.target.value }))}
          />
        </div>
        <div>
          <label htmlFor="t-est">Estimated duration (min)</label>
          <input
            id="t-est" type="number" min={1} max={1440} value={form.estimated_minutes}
            onChange={e => setForm(f => ({ ...f, estimated_minutes: parseInt(e.target.value) || 30 }))}
          />
        </div>
        <div>
          <label htmlFor="t-pri">Priority</label>
          <select
            id="t-pri" value={form.priority}
            onChange={e => setForm(f => ({ ...f, priority: e.target.value as Task['priority'] }))}
          >
            {Object.entries(PRIORITY_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </div>
      </div>
      <div className="mt-1">
        <label htmlFor="t-desc">Notes</label>
        <textarea
          id="t-desc" rows={2} value={form.description}
          onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
        />
      </div>
      <div className="flex gap-1 mt-2">
        <button type="submit" className="btn btn-primary btn-sm">
          {editing ? 'Save changes' : 'Add task'}
        </button>
        <button type="button" className="btn btn-ghost btn-sm" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  )
}

// ── Task row ──────────────────────────────────────────────────────────────────
function TaskRow({
  task: t,
  onComplete,
  onEdit,
  onDelete,
}: {
  task: Task
  onComplete: (t: Task) => void
  onEdit: (t: Task) => void
  onDelete: (t: Task) => void
}) {
  const [menuOpen, setMenuOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)
  const due = relativeDue(t.due_at_utc)

  // Close menu on outside click
  useEffect(() => {
    if (!menuOpen) return
    function close(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false)
      }
    }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [menuOpen])

  return (
    <li className={`task-row card${t.status === 'done' ? ' task-row-done' : ''}`}>
      <div className="task-row-main">
        {/* 44px touch target checkbox */}
        <button
          className="task-check"
          role="checkbox"
          aria-checked={t.status === 'done'}
          onClick={() => onComplete(t)}
          aria-label={`Mark "${t.title}" as done`}
        >
          <span className={`task-check-box${t.status === 'done' ? ' task-check-box-done' : ''}`} aria-hidden="true" />
        </button>

        <div className="task-row-body">
          <span className={`task-title${t.status === 'done' ? ' task-title-done' : ''}`}>{t.title}</span>
          <div className="task-meta">
            {t.course_label && <span className="task-course">{t.course_label}</span>}
            {due && (
              <span className={`task-due${due.isOverdue ? ' task-due-overdue' : ''}`}>
                {due.text}
              </span>
            )}
            {t.estimated_minutes > 0 && (
              <span className="task-est">{t.estimated_minutes} min</span>
            )}
          </div>
        </div>

        <div className="task-row-right">
          {(t.priority === 'urgent' || t.priority === 'high') && (
            <span className={`badge badge-${t.priority === 'urgent' ? 'err' : 'warn'}`}>
              {PRIORITY_LABELS[t.priority]}
            </span>
          )}
          {t.source_type === 'demo' && <span className="badge badge-demo">Demo</span>}

          {/* Overflow menu */}
          <div className="task-overflow-wrap" ref={menuRef}>
            <button
              className="btn btn-ghost btn-icon btn-sm task-overflow-btn"
              onClick={() => setMenuOpen(o => !o)}
              aria-label="Task options"
              aria-expanded={menuOpen}
              aria-haspopup="menu"
            >
              <MoreVertical size={14} aria-hidden="true" />
            </button>
            {menuOpen && (
              <div className="task-overflow-menu" role="menu">
                <button
                  role="menuitem"
                  className="task-overflow-item"
                  onClick={() => { setMenuOpen(false); onEdit(t) }}
                >
                  Edit
                </button>
                <button
                  role="menuitem"
                  className="task-overflow-item task-overflow-item-danger"
                  onClick={() => { setMenuOpen(false); onDelete(t) }}
                >
                  Delete
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
      {t.description && <p className="task-desc">{t.description}</p>}
    </li>
  )
}

// ── Main screen ───────────────────────────────────────────────────────────────
export default function TasksScreen() {
  const [tasks, setTasks] = useState<Task[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [quickAdd, setQuickAdd] = useState('')
  const [sheetOpen, setSheetOpen] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [form, setForm] = useState<TaskFormData>(EMPTY_FORM)
  const [completedOpen, setCompletedOpen] = useState(false)

  const { showToast } = useToast()
  const { confirm } = useConfirm()
  const { refresh: refreshBadges } = useBadges()

  const load = () => {
    getTasks()
      .then(setTasks)
      .catch(e => setError(String(e)))
      .finally(() => setLoading(false))
  }
  useEffect(() => { load() }, [])

  async function handleQuickAdd(e: React.FormEvent) {
    e.preventDefault()
    if (!quickAdd.trim()) return
    try {
      await createTask({ title: quickAdd.trim(), status: 'todo', priority: 'normal', estimated_minutes: 30, source_type: 'manual' })
      setQuickAdd('')
      load()
      refreshBadges()
      showToast('Task added', 'success')
    } catch (err) { showToast(String(err), 'error') }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const payload = {
      ...form,
      due_at_utc: form.due_at_utc ? new Date(form.due_at_utc).toISOString() : undefined,
    }
    try {
      if (editingId) {
        await updateTask(editingId, payload)
        showToast('Task updated', 'success')
      } else {
        await createTask({ ...payload, source_type: 'manual' })
        showToast('Task added', 'success')
      }
      setSheetOpen(false); setEditingId(null); setForm(EMPTY_FORM)
      load(); refreshBadges()
    } catch (err) { showToast(String(err), 'error') }
  }

  async function handleComplete(t: Task) {
    const newStatus = t.status === 'done' ? 'todo' : 'done'
    // Optimistic
    setTasks(prev => prev.map(x => x.id === t.id ? { ...x, status: newStatus } : x))
    try {
      await updateTask(t.id, { status: newStatus })
      refreshBadges()
      if (newStatus === 'done') showToast(`"${t.title}" marked done`, 'success')
    } catch (err) {
      setTasks(prev => prev.map(x => x.id === t.id ? { ...x, status: t.status } : x))
      showToast(String(err), 'error')
    }
  }

  async function handleDelete(t: Task) {
    const ok = await confirm(`Delete "${t.title}"?`, 'Delete')
    if (!ok) return
    await deleteTask(t.id)
    load(); refreshBadges()
  }

  function startEdit(t: Task) {
    setForm({
      title: t.title,
      description: t.description ?? '',
      course_label: t.course_label ?? '',
      due_at_utc: t.due_at_utc ? new Date(t.due_at_utc).toISOString().slice(0, 16) : '',
      estimated_minutes: t.estimated_minutes,
      priority: t.priority,
    })
    setEditingId(t.id)
    setSheetOpen(true)
  }

  if (loading) return <SkeletonList count={4} lines={2} />

  // Group tasks
  const now = Date.now()
  const open = tasks.filter(t => t.status !== 'done')
  const done = tasks.filter(t => t.status === 'done')

  const overdue = open.filter(t => t.due_at_utc && new Date(t.due_at_utc).getTime() < now)
  const today = open.filter(t => t.due_at_utc && isSameDayAsNow(t.due_at_utc) && !overdue.includes(t))
  const thisWeek = open.filter(t => {
    if (!t.due_at_utc) return false
    const dueMs = new Date(t.due_at_utc).getTime()
    if (dueMs <= now) return false
    if (isSameDayAsNow(t.due_at_utc)) return false
    return dueMs <= now + 7 * 24 * 3600_000
  })
  const later = open.filter(t => {
    if (!t.due_at_utc) return false
    return new Date(t.due_at_utc).getTime() > now + 7 * 24 * 3600_000
  })
  const noDate = open.filter(t => !t.due_at_utc)

  const GROUPS = [
    { id: 'overdue',   label: 'Overdue',    tasks: overdue,  emptyMsg: 'No overdue tasks.' },
    { id: 'today',     label: 'Today',      tasks: today,    emptyMsg: 'Nothing due today.' },
    { id: 'this-week', label: 'This week',  tasks: thisWeek, emptyMsg: 'Nothing due this week.' },
    { id: 'later',     label: 'Later',      tasks: later,    emptyMsg: 'Nothing due later.' },
    { id: 'no-date',   label: 'No date',    tasks: noDate,   emptyMsg: 'No undated tasks.' },
  ]

  return (
    <div>
      <div className="screen-title">
        <h1>Tasks</h1>
        <p>Manage your tasks and assignments.</p>
      </div>

      {error && <div className="state-error mb-2" role="alert">{error}</div>}

      {/* Quick add */}
      <form className="quick-add-form" onSubmit={handleQuickAdd} aria-label="Quick add task">
        <input
          type="text"
          placeholder="Add a task…"
          value={quickAdd}
          onChange={e => setQuickAdd(e.target.value)}
          aria-label="Add a task"
          className="quick-add-input"
        />
        <button
          type="button"
          className="btn btn-ghost btn-sm"
          onClick={() => { setForm(EMPTY_FORM); setEditingId(null); setSheetOpen(true) }}
          aria-label="More options"
        >
          More options
        </button>
      </form>

      {/* Groups */}
      {GROUPS.map(group => (
        group.tasks.length > 0 ? (
          <section key={group.id} aria-labelledby={`group-${group.id}`} className="task-group">
            <h2 id={`group-${group.id}`} className={`task-group-title${group.id === 'overdue' ? ' task-group-title-overdue' : ''}`}>
              {group.label} <span className="task-group-count">({group.tasks.length})</span>
            </h2>
            <ul className="tasks-list">
              {group.tasks.map(t => (
                <TaskRow key={t.id} task={t} onComplete={handleComplete} onEdit={startEdit} onDelete={handleDelete} />
              ))}
            </ul>
          </section>
        ) : null
      ))}

      {open.length === 0 && (
        <EmptyState message="No open tasks. Type in the field above to add one." />
      )}

      {/* Completed (toggle) */}
      {done.length > 0 && (
        <section aria-labelledby="group-done" className="task-group">
          <button
            className="task-group-toggle"
            onClick={() => setCompletedOpen(o => !o)}
            aria-expanded={completedOpen}
            id="group-done"
          >
            <span>Completed ({done.length})</span>
            <span className="task-toggle-arrow">{completedOpen ? '▲' : '▼'}</span>
          </button>
          {completedOpen && (
            <ul className="tasks-list">
              {done.map(t => (
                <TaskRow key={t.id} task={t} onComplete={handleComplete} onEdit={startEdit} onDelete={handleDelete} />
              ))}
            </ul>
          )}
        </section>
      )}

      {/* Sheet for full form */}
      <Sheet
        open={sheetOpen}
        onClose={() => { setSheetOpen(false); setEditingId(null); setForm(EMPTY_FORM) }}
        title={editingId ? 'Edit task' : 'New task'}
      >
        <TaskForm
          form={form}
          setForm={setForm}
          onSubmit={handleSubmit}
          onCancel={() => { setSheetOpen(false); setEditingId(null); setForm(EMPTY_FORM) }}
          editing={!!editingId}
        />
      </Sheet>
    </div>
  )
}

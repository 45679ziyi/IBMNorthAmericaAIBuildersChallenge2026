import { useState } from 'react'
import { createServiceRequest } from '../../api/client'
import './ServiceRequestForm.css'

// Known service IDs for demo selection
const SERVICE_OPTIONS = [
  { id: 'wifi',        label: 'Wi-Fi / Network' },
  { id: 'hvac',        label: 'Heating / Cooling (HVAC)' },
  { id: 'elevator',    label: 'Elevator' },
  { id: 'facilities',  label: 'Facilities / Maintenance' },
  { id: 'it_support',  label: 'IT Support' },
  { id: 'registrar',   label: 'Registrar' },
  { id: 'other',       label: 'Other' },
]

interface Props {
  onSubmitted?: (id: string) => void
}

export default function ServiceRequestForm({ onSubmitted }: Props) {
  const [serviceId, setServiceId] = useState(SERVICE_OPTIONS[0].id)
  const [title, setTitle] = useState('')
  const [body, setBody] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!title.trim()) return
    setSubmitting(true)
    setError(null)
    setSuccess(null)
    try {
      const sr = await createServiceRequest({ service_id: serviceId, title: title.trim(), body })
      setSuccess(`Request submitted (ID: ${sr.id.slice(0, 8)}…). Status: ${sr.status}.`)
      setTitle('')
      setBody('')
      onSubmitted?.(sr.id)
    } catch (e) {
      setError(String(e))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form className="sr-form" onSubmit={handleSubmit} aria-label="Submit a service request">
      <h3 className="sr-form-title">New Service Request</h3>

      <label className="sr-label" htmlFor="sr-service">Service</label>
      <select
        id="sr-service"
        className="sr-select"
        value={serviceId}
        onChange={e => setServiceId(e.target.value)}
        disabled={submitting}
      >
        {SERVICE_OPTIONS.map(o => (
          <option key={o.id} value={o.id}>{o.label}</option>
        ))}
      </select>

      <label className="sr-label" htmlFor="sr-title">Title <span aria-hidden="true">*</span></label>
      <input
        id="sr-title"
        className="sr-input"
        type="text"
        value={title}
        onChange={e => setTitle(e.target.value)}
        placeholder="Brief description of the issue"
        maxLength={256}
        required
        disabled={submitting}
      />

      <label className="sr-label" htmlFor="sr-body">Details</label>
      <textarea
        id="sr-body"
        className="sr-textarea"
        value={body}
        onChange={e => setBody(e.target.value)}
        placeholder="Additional context (optional)"
        rows={4}
        maxLength={4000}
        disabled={submitting}
      />

      {error && <p className="sr-error" role="alert">{error}</p>}
      {success && <p className="sr-success" role="status">{success}</p>}

      <button
        type="submit"
        className="btn btn-primary"
        disabled={submitting || !title.trim()}
      >
        {submitting ? 'Submitting…' : 'Submit Request'}
      </button>
    </form>
  )
}

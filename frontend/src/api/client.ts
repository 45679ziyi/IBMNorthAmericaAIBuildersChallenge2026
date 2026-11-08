/**
 * AURORA API client — typed fetch wrapper.
 * All calls target /api/v1 (proxied to FastAPI in dev, direct in prod).
 */

import { CAMPUS_TZ } from '../lib/time'

const BASE = '/api/v1'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...init?.headers },
    ...init,
  })
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(detail.detail ?? `HTTP ${res.status}`)
  }
  return res.json() as Promise<T>
}

// ── Types ──────────────────────────────────────────────────────────────────

export interface CalendarEvent {
  id: string
  user_id: string
  title: string
  description?: string
  start_at_utc: string
  end_at_utc: string
  location_text?: string
  event_type: string
  source_type: string
  source_reference?: string
  last_synced_at: string
}

export interface Task {
  id: string
  user_id: string
  title: string
  description?: string
  course_label?: string
  due_at_utc?: string
  estimated_minutes: number
  priority: 'low' | 'normal' | 'high' | 'urgent'
  status: 'todo' | 'in_progress' | 'done'
  source_type: string
  source_url?: string
  provenance?: string
  created_at: string
  updated_at: string
}

export interface Announcement {
  id: string
  user_id: string
  course_label: string
  title: string
  body_summary: string
  published_at_utc?: string
  source_url?: string
  source_type: string
  retrieved_at_utc: string
  is_demo: boolean
  is_read: boolean
  read_at_utc?: string
}

export interface CampusEvent {
  id: string
  title: string
  description?: string
  start_at_utc?: string
  end_at_utc?: string
  location_text?: string
  source_title: string
  source_url: string
  retrieved_at_utc: string
  is_demo_data: boolean
}

export interface PlanBlock {
  id: string
  task_id?: string
  calendar_event_id?: string
  title: string
  start_at_utc: string
  end_at_utc: string
  block_type: 'fixed_event' | 'task' | 'break' | 'suggestion'
  reason: string
  is_user_edited: boolean
}

export interface DailyPlan {
  id: string
  user_id: string
  plan_date: string
  timezone: string
  generated_at_utc: string
  algorithm_version: string
  status: 'draft' | 'accepted' | 'rejected'
  blocks: PlanBlock[]
  unscheduled: { task_id: string; title: string; reason: string }[]
  warnings: string[]
}

export interface AssistantSource {
  title: string
  url: string
  publisher: string
  last_verified_at_utc: string
  excerpt: string
}

export interface AssistantResponse {
  answer: string
  sources: AssistantSource[]
  coverage: 'supported' | 'partial' | 'not_found'
  updated_at: string
  disclaimer: string
  coverage_score: number
  matched_terms: string[]
}

export interface PulseSeries {
  sensor_label: string
  metric_type: string
  points: PulsePoint[]
}

export interface PulsePoint {
  bucket_ts: string
  value: number
  unit: string
  data_origin: string
}

export interface PulseInsight {
  id: string
  severity: 'info' | 'warn' | 'critical'
  sensor_label: string
  metric_type: string
  message: string
  evidence: Record<string, unknown>
  recommended_human_action: string
  automated_action: null
  data_origin: string
}

export interface SecurityFinding {
  id: string
  kind: string
  severity: string
  title: string
  evidence: string[]
  affected_asset_ids: string[]
  advisory_id?: string
  status: string
  recommended_human_action: string
  detected_at_utc: string
  data_origin: string
}

export interface SecurityReport {
  last_run_at_utc: string
  schedule_note: string
  summary: { critical: number; warn: number; info: number }
  findings: SecurityFinding[]
}

export interface ConnectorStatus {
  name: string
  status: 'connected' | 'demo' | 'unavailable'
  description: string
  last_checked: string
  data_categories: string[]
  purpose: string
  sends_to_external_model: boolean
}

export interface SensorReading {
  id: string
  sensor_label: string
  metric_type: string
  value: number
  unit: string
  recorded_at_utc: string
  data_origin: string
}

export interface HealthResponse {
  status: string
  version: string
  database: string
  ai_provider: string
  disclaimer: string
}

export interface SimState {
  mode: 'real' | 'scenario'
  scenario_id: string | null
  anchor_date: string | null
  virtual_now: string | null  // ISO UTC when in scenario mode
  applied_signal_ids: string[]
}

export interface Move {
  id: string; key: string; kind: string; audience: string; status: string
  policy: string; urgency: string; impact: string
  title: string; summary: string
  why: Array<{ feed: string; signal_id?: string; text: string }>
  actions: Array<{ id: string; type: string; params: Record<string, unknown>; external: boolean; simulated: boolean }>
  fingerprint: string; created_at: string; updated_at: string
}

export interface AutonomyPolicy {
  policy: Record<string, string>
  locked: string[]
  note: string
}

export interface Signal {
  id: string; feed: string; kind: string; at_utc: string; summary: string
  payload: Record<string, unknown>; relevance: string; relevance_reason: string | null
  data_origin: string
}

export interface FeedStatus {
  feed: string; last_signal_at: string | null; signals_seen: number; signals_filtered: number
}

// ── Ops / Incidents (M5) ──────────────────────────────────────────────────

export interface OpsIncident {
  id: string
  room_id: string
  room_name: string
  type: string
  temperature_c: number | null
  trend: string | null
  reported_at_utc: string
  status: 'active' | 'resolved'
}

export interface AffectedClass {
  commitment_id: string
  title: string
  course: string
  start: string
  end: string
  room_name: string
  enrolled: number
  status: 'in_session' | 'not_started'
  feasible_rooms: Array<{ room_id: string; room_name: string; capacity: number }>
}

export interface FeasibleMitigation {
  commitment_id: string
  course: string
  room_id: string
  room_name: string
  action: string
  simulated: boolean
}

export interface ImpactGraph {
  incident: OpsIncident
  affected_classes: AffectedClass[]
  total_students: number
  feasible_mitigations: FeasibleMitigation[]
  student_effect: string
}

// ── API functions ──────────────────────────────────────────────────────────

// Health
export const getHealth = () => request<HealthResponse>('/health')

// Events
export const getEvents = () => request<CalendarEvent[]>('/events')
export const createEvent = (data: Partial<CalendarEvent>) =>
  request<CalendarEvent>('/events', { method: 'POST', body: JSON.stringify(data) })
export const updateEvent = (id: string, data: Partial<CalendarEvent>) =>
  request<CalendarEvent>(`/events/${id}`, { method: 'PUT', body: JSON.stringify(data) })
export const deleteEvent = (id: string) =>
  fetch(`${BASE}/events/${id}`, { method: 'DELETE' })
export async function importICS(file: File): Promise<{
  imported: number; skipped: number; warnings: string[]; events: CalendarEvent[]
}> {
  const fd = new FormData()
  fd.append('file', file)
  const res = await fetch(`${BASE}/events/import/ics`, { method: 'POST', body: fd })
  if (!res.ok) {
    const d = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(d.detail ?? `HTTP ${res.status}`)
  }
  return res.json()
}

// Tasks
export const getTasks = () => request<Task[]>('/tasks')
export const createTask = (data: Partial<Task>) =>
  request<Task>('/tasks', { method: 'POST', body: JSON.stringify(data) })
export const updateTask = (id: string, data: Partial<Task>) =>
  request<Task>(`/tasks/${id}`, { method: 'PUT', body: JSON.stringify(data) })
export const deleteTask = (id: string) =>
  fetch(`${BASE}/tasks/${id}`, { method: 'DELETE' })

// Announcements
export const getAnnouncements = () => request<Announcement[]>('/announcements')
export const getUnreadCount = () => request<{ unread: number }>('/announcements/unread-count')
export const markAnnouncementRead = (id: string, is_read: boolean) =>
  request<Announcement>(`/announcements/${id}`, { method: 'PATCH', body: JSON.stringify({ is_read }) })
export const markAllAnnouncementsRead = () =>
  request<{ marked: number }>('/announcements/mark-all-read', { method: 'POST' })

// Plans
export const generatePlan = (plan_date: string, timezone = CAMPUS_TZ) =>
  request<DailyPlan>('/plans/generate', {
    method: 'POST',
    body: JSON.stringify({ plan_date, timezone }),
  })
export const acceptPlan = (id: string) =>
  request<DailyPlan>(`/plans/${id}/accept`, { method: 'POST' })
export const rejectPlan = (id: string) =>
  request<DailyPlan>(`/plans/${id}/reject`, { method: 'POST' })

// Assistant
export const askAssistant = (question: string) =>
  request<AssistantResponse>('/assistant/ask', {
    method: 'POST',
    body: JSON.stringify({ question }),
  })
export const searchKnowledge = (q: string) =>
  request<AssistantSource[]>(`/knowledge/search?q=${encodeURIComponent(q)}`)

// Connectors
export const getConnectors = () => request<ConnectorStatus[]>('/connectors/status')

// Campus Pulse
export const getCampusPulse = () => request<SensorReading[]>('/campus-pulse/demo')
export const getPulseSeries = (params?: { points?: number; scenario?: string }) =>
  request<PulseSeries[]>(`/campus-pulse/series${params ? '?' + new URLSearchParams(params as Record<string, string>) : ''}`)
export const getPulseInsights = (scenario?: string) =>
  request<PulseInsight[]>(`/campus-pulse/insights${scenario ? '?scenario=' + scenario : ''}`)

// Security
export const getSecurityReport = () => request<SecurityReport>('/security/watchdog')
export const runSecurityCheck = () => request<SecurityReport>('/security/watchdog/run', { method: 'POST' })
export const escalateFinding = (id: string) =>
  request<{ status: string; message: string }>(`/security/findings/${id}/escalate`, { method: 'POST' })

// Reset
export const resetDemoData = () =>
  request<{ status: string; message: string }>('/demo/reset', { method: 'DELETE' })
export const deleteUserData = () =>
  request<{ status: string; message: string }>('/user/data', { method: 'DELETE' })

// Sim
export const getSimState = () => request<SimState>('/sim/state')
export const startScenario = (scenario_id: string) =>
  request<SimState>('/sim/start', { method: 'POST', body: JSON.stringify({ scenario_id }) })
export const advanceSim = (params: { minutes?: number; to?: string; to_next_signal?: boolean }) =>
  request<SimState>('/sim/advance', { method: 'POST', body: JSON.stringify(params) })
export const resetSim = () => request<SimState>('/sim/reset', { method: 'POST' })
export const stopSim = () => request<{ mode: string }>('/sim/stop', { method: 'POST' })

// Moves
export const getMoves = (audience?: 'student' | 'staff') =>
  request<Move[]>(`/moves${audience ? '?audience=' + audience : ''}`)
export const getHandledMoves = () => request<Move[]>('/moves/handled')
export const approveMoveReq = (id: string) =>
  request<Move>(`/moves/${id}/approve`, { method: 'POST' })
export const dismissMove = (id: string) =>
  request<Move>(`/moves/${id}/dismiss`, { method: 'POST' })
export const undoMoveAll = (id: string) =>
  request<{ status: string; message: string }>(`/moves/${id}/undo-all`, { method: 'POST' })
export const undoAction = (id: string) =>
  request<{ status: string; message: string }>(`/actions/${id}/undo`, { method: 'POST' })

// Autonomy
export const getAutonomy = () => request<AutonomyPolicy>('/autonomy')
export const updateAutonomy = (category: string, value: string) =>
  request<AutonomyPolicy>('/autonomy', { method: 'PUT', body: JSON.stringify({ category, value }) })

// Signals & Feeds
export const getSignals = (params?: { feed?: string; relevance?: string }) =>
  request<Signal[]>(`/signals${params ? '?' + new URLSearchParams(params as Record<string, string>) : ''}`)
export const getFeedsStatus = () => request<FeedStatus[]>('/feeds/status')

// Ops / Incidents (M5)
export const getOpsIncidents = () => request<OpsIncident[]>('/ops/incidents')
export const getIncidentImpact = (incidentId: string) =>
  request<ImpactGraph>(`/ops/incidents/${incidentId}/impact`)
export const approveMitigation = (incidentId: string) =>
  request<{ status: string; message: string; changes: string[] }>(
    `/ops/incidents/${incidentId}/approve-mitigation`,
    { method: 'POST' }
  )

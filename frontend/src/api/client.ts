/**
 * AURORA API client — typed fetch wrapper.
 * All calls target /api/v1 (proxied to FastAPI in dev, direct in prod).
 *
 * U1: Every request carries X-Demo-Tenant and X-Demo-Actor headers.
 * These are stored in module-level mutable state and updated by the
 * tenant/persona switchers.
 */

import { getTz } from '../lib/time'

const BASE = '/api/v1'

// ── U1: Demo context headers ────────────────────────────────────────────────

let _currentTenant = 'sbu_demo'
let _currentActor  = 'student_alex'

export function setDemoTenant(id: string) { _currentTenant = id }
export function setDemoActor(id: string)  { _currentActor  = id }
export function getDemoTenant()           { return _currentTenant }
export function getDemoActor()            { return _currentActor  }

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      'X-Demo-Tenant': _currentTenant,
      'X-Demo-Actor':  _currentActor,
      ...init?.headers,
    },
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
export const generatePlan = (plan_date: string, timezone = getTz()) =>
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

// ── U1: Identity ──────────────────────────────────────────────────────────────

export interface PersonaInfo {
  id: string
  display_name: string
  role: string
  has_personal_data: boolean
}

export interface NavItem {
  key: string
  label: string
  path: string
}

export interface IdentityMe {
  actor_id: string
  role: string
  display_name: string
  tenant: string
  has_personal_data: boolean
  capabilities: string[]
  nav: NavItem[]
  auth_mode: string
  disclaimer: string
}

export const getPersonas   = () => request<PersonaInfo[]>('/identity/personas')
export const getIdentityMe = () => request<IdentityMe>('/identity/me')
export const getEffectivePermissions = () =>
  request<Array<{ action: string; allowed: boolean; reason_code: string }>>('/identity/effective-permissions')

// ── U2: Tenant ─────────────────────────────────────────────────────────────────

export interface TenantConfig {
  tenant_id: string
  time_zone: string
  clock: '12h' | '24h'
  week_start: 'sunday' | 'monday'
  course_code_format: string
  room_code_format: string
  credit_unit: string
  role_vocabulary: Record<string, string>
  min_cell_size: number
}

export interface TenantSummary {
  id: string
  name: string
  is_default: boolean
}

export const getTenantConfig  = () => request<TenantConfig>('/tenant/config')
export const listTenants      = () => request<TenantSummary[]>('/tenants')

// ── U4: Inbox + Service Requests ───────────────────────────────────────────

export interface WhyEntry {
  rel: string
  entity_type: string
  entity_id: string
  text: string
}

export interface InboxNotification {
  id: string
  canonical_event_id?: string
  work_item_id?: string
  recipient_person_id: string
  kind: string
  title: string
  body: string
  why: WhyEntry[]
  state: 'unread' | 'read' | 'acknowledged'
  requires_ack: boolean
  data_origin: string
  created_at: string
  read_at?: string
}

export interface NotificationPref {
  id: string
  person_id: string
  category: string
  enabled: boolean
}

export interface ServiceRequest {
  id: string
  tenant_id: string
  requester_person_id: string
  service_id: string
  title: string
  body: string
  status: string
  assigned_team_id?: string
  version: number
  data_origin: string
  created_at: string
  updated_at: string
}

export const fetchInbox           = () => request<InboxNotification[]>('/inbox')
export const fetchInboxUnread     = () => request<{ unread: number }>('/inbox/unread-count')
export const markInboxRead        = (id: string) =>
  request<InboxNotification>(`/inbox/${id}/read`, { method: 'POST' })
export const markInboxAck         = (id: string) =>
  request<InboxNotification>(`/inbox/${id}/ack`, { method: 'POST' })
export const fetchInboxPrefs      = () => request<NotificationPref[]>('/inbox/preferences')
export const updateInboxPref      = (category: string, enabled: boolean) =>
  request<NotificationPref>('/inbox/preferences', {
    method: 'PUT',
    body: JSON.stringify({ category, enabled }),
  })

export const createServiceRequest = (payload: { service_id: string; title: string; body?: string }) =>
  request<ServiceRequest>('/service-requests', { method: 'POST', body: JSON.stringify(payload) })
export const fetchServiceRequests = () => request<ServiceRequest[]>('/service-requests')
export const transitionServiceRequest = (id: string, target_status: string) =>
  request<ServiceRequest>(`/service-requests/${id}/transition`, {
    method: 'POST',
    body: JSON.stringify({ target_status }),
  })

// ── Canonical Events (U5) ──────────────────────────────────────────────────

export interface CanonicalEvent {
  id: string
  tenant_id: string
  type: string
  status: string
  severity: string
  correlation_id?: string
  idempotency_key: string
  source_feed?: string
  source_record_id?: string
  occurred_at?: string
  received_at: string
  entity_refs: Array<{ type: string; id: string }>
  classification: string
  corroborations: number
  schema_version: string
  last_actor?: string
  last_actor_mode: string
  created_at: string
  audience?: Record<string, string[]>
}

export interface ReachResponse {
  canonical_event_id: string
  audience_counts: Record<string, number>
  audience_ids?: Record<string, string[]>
}

export interface ThreadMessage {
  id: string
  thread_id: string
  author_person_id: string
  body: string
  data_origin: string
  created_at: string
}

export interface Thread {
  id: string
  canonical_event_id?: string
  work_item_id?: string
  service_request_id?: string
  title: string
  created_at: string
  messages: ThreadMessage[]
}

export interface WorkItem {
  id: string
  canonical_event_id?: string
  workflow_type: string
  status: string
  version: number
  owner_person_id?: string
  assigned_team_id?: string
  tenant_id: string
  payload: Record<string, unknown>
  required_next_fields: string[]
  created_at: string
  updated_at: string
}

export const getCanonicalEvent     = (id: string) => request<CanonicalEvent>(`/canonical-events/${id}`)
export const getCanonicalEventReach = (id: string) => request<ReachResponse>(`/canonical-events/${id}/reach`)
export const getCanonicalEventThread = (id: string) => request<Thread>(`/canonical-events/${id}/thread`)
export const postThreadMessage     = (id: string, body: string) =>
  request<ThreadMessage>(`/canonical-events/${id}/thread`, {
    method: 'POST',
    body: JSON.stringify({ body }),
  })

export const getWorkItems = (params?: {
  workflow_type?: string
  status?: string
  canonical_event_id?: string
  team?: string
}) => {
  const q = new URLSearchParams()
  if (params?.workflow_type) q.set('workflow_type', params.workflow_type)
  if (params?.status) q.set('status', params.status)
  if (params?.canonical_event_id) q.set('canonical_event_id', params.canonical_event_id)
  if (params?.team) q.set('team', params.team)
  const qs = q.toString()
  return request<WorkItem[]>(`/work-items${qs ? '?' + qs : ''}`)
}

export const transitionWorkItem = (id: string, action: string, payload: Record<string, unknown> = {}, rationale?: string) =>
  request<{ work_item_id: string; from_status: string; to_status: string; version: number; transition_id: string }>(
    `/work-items/${id}/transition`, {
      method: 'POST',
      body: JSON.stringify({ action, payload, rationale }),
    })

// ── Campus Buildings (U5-3) ───────────────────────────────────────────────

export interface Building {
  id: string
  code: string
  name: string
  x: number
  y: number
  floors: number
  kind: string
}

export const getCampusBuildings = () => request<Building[]>('/campus/buildings')
export const getCampusIncidents = () => request<CanonicalEvent[]>('/campus/incidents')

// ── Course Updates (U5-5) ─────────────────────────────────────────────────

export interface DeadlineExtraction {
  title?: string
  due_date?: string
  due_time?: string
  est_minutes?: number
  confidence: number
  quote?: string
}

export interface CourseUpdateDraft {
  id: string
  section_id: string
  text: string
  status: string
  extracted: DeadlineExtraction
  ai_run_id?: string
  created_at: string
  updated_at: string
}

export const createCourseUpdateDraft = (section_id: string, text: string) =>
  request<CourseUpdateDraft>('/course-updates/drafts', {
    method: 'POST',
    body: JSON.stringify({ section_id, text }),
  })

export const getCourseUpdate        = (id: string) => request<CourseUpdateDraft>(`/course-updates/${id}`)
export const previewCourseUpdate    = (id: string) =>
  request<{ preview: string; recipients: number }>(`/course-updates/${id}/preview`, { method: 'POST' })
export const approveCourseUpdate    = (id: string) =>
  request<{ status: string; notifications_created: number }>(`/course-updates/${id}/approve`, { method: 'POST' })

// ── Sim Director (U5-7) ───────────────────────────────────────────────────

export interface DirectorState {
  mode: 'real' | 'scenario'
  scenario_id: string | null
  anchor_date: string | null
  virtual_now: string | null
  applied_signal_ids: string[]
  director_mode: string        // "off" | "autopilot"
  active_persona: string | null
  pending_step_ids: string[]
}

export const getDirectorState  = () => request<DirectorState>('/sim/state')
export const setDirectorMode   = (enabled: boolean) =>
  request<DirectorState>('/sim/director', { method: 'POST', body: JSON.stringify({ mode: enabled ? 'autopilot' : 'off' }) })
export const simTakeOver       = () =>
  request<DirectorState>('/sim/take-over', { method: 'POST' })

// ── Trust & Quality (U6-6) ────────────────────────────────────────────────

export interface TrustQuality {
  authorization: { cases: number; pass_rate: number }
  deadline_extraction: { cases: number; exact_match: number } | { status: string }
  retrieval: { cases: number; coverage_accuracy: number } | { status: string }
  injection: { cases: number; successful_injections: number } | { status: string }
  tenant_leakage: { probes: number; leaks: number } | { status: string }
  determinism: { tenants: number; identical_hashes: boolean } | { status: string }
  ai_provider: string
  watsonx_configured: boolean
}

export const getTrustQuality = () => request<TrustQuality>('/trust/quality')

// ── AI Runs badge (U6-3) ──────────────────────────────────────────────────

export interface AIRun {
  id: string
  task: string
  provider: string
  validated: boolean
  fallback_used: boolean
  latency_ms?: number
  created_at: string
}

// ── Scenarios V4-05 ──────────────────────────────────────────────────────────

export interface ScoreFactors {
  capacity_fit: number
  building_proximity: number
  feature_match: number
  same_building: number
  total: number
  capacity_fit_basis: string
  proximity_basis: string
  feature_match_basis: string
  missing_data: string[]
}

export interface CandidateOption {
  option_id: string
  room_id: string
  room_name: string
  building_id: string
  capacity: number
  features: string[]
  rank: number
  score: number
  score_factors: ScoreFactors
  data_origin: string
}

export interface InfeasibleOption {
  room_id: string
  room_name: string
  failed_constraints: string[]
}

export interface AffectedSection {
  section_id: string
  course_id: string
  enrolled: number
  enrolled_display: string
  meeting_days: string[]
  meeting_start: string
  meeting_end: string
  affected_meetings_in_window: number
}

export interface ScenarioResult {
  scenario_id: string
  engine_version: string
  scenario_type: string
  inputs: Record<string, unknown>
  candidates: CandidateOption[]
  infeasible: InfeasibleOption[]
  affected_sections: AffectedSection[]
  summary: {
    affected_sections_count: number
    affected_students_display: string
    feasible_alternatives: number
    infeasible_rooms_checked: number
    repair_delay_minutes: number
    best_option_id: string | null
    data_completeness: string
  }
  missing_data: string[]
  assumptions: string[]
  result_hash: string
  data_origin: string
}

export interface ScenarioRun {
  id: string
  tenant_id: string
  canonical_event_id: string | null
  engine_version: string
  scenario_type: string
  status: string
  inputs: Record<string, unknown>
  result: ScenarioResult
  result_hash: string | null
  promoted_by: string | null
  promoted_at: string | null
  promoted_option_id: string | null
  promotion_rationale: string | null
  data_origin: string
  created_at: string
}

export const createScenario = (body: {
  canonical_event_id?: string
  affected_room_id: string
  repair_delay_minutes: number
  min_capacity?: number
  required_features?: string[]
}) => request<ScenarioRun>('/scenarios', { method: 'POST', body: JSON.stringify(body) })

export const getScenario = (id: string) =>
  request<ScenarioRun>(`/scenarios/${id}`)

export const listScenarios = (canonical_event_id?: string) =>
  request<ScenarioRun[]>(`/scenarios${canonical_event_id ? `?canonical_event_id=${canonical_event_id}` : ''}`)

export const compareScenarios = (id_a: string, id_b: string, id_c?: string) =>
  request<{ runs: Record<string, unknown>[]; changed_inputs: Record<string, unknown>; shared_inputs: Record<string, unknown>; hashes_match: boolean }>(
    `/scenarios/compare/${id_a}/${id_b}${id_c ? `/${id_c}` : ''}`
  )

export const promoteScenario = (id: string, selected_option_id: string, rationale: string) =>
  request<{ status: string; promoted_option_id: string; note: string }>(
    `/scenarios/${id}/promote`,
    { method: 'POST', body: JSON.stringify({ selected_option_id, rationale }) }
  )

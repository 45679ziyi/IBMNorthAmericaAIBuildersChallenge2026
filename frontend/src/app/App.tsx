import { Routes, Route, NavLink, useLocation, useNavigate } from 'react-router-dom'
import { useState, useEffect } from 'react'
import { Home, CalendarDays, CheckSquare, MapPin, MessageSquare, Shield, Monitor, Sun, Moon } from 'lucide-react'
import TodayScreen from '../features/dashboard/TodayScreen'
import PlannerScreen from '../features/planner/PlannerScreen'
import TasksScreen from '../features/tasks/TasksScreen'
import CampusScreen from '../features/campus/CampusScreen'
import AssistantScreen from '../features/assistant/AssistantScreen'
import PrivacyScreen from '../features/privacy/PrivacyScreen'
import { Toast, ToastProvider } from '../components/Toast'
import { ConfirmProvider } from '../components/ConfirmModal'
import { BadgesProvider, useBadges } from '../state/badges'
import { DemoBar } from '../components/DemoBar'
import { useNow } from '../hooks/useNow'
import './App.css'

// ── Theme management ─────────────────────────────────────────────────────────

type ThemeChoice = 'system' | 'light' | 'dark'

function resolveTheme(choice: ThemeChoice): 'light' | 'dark' {
  if (choice === 'dark') return 'dark'
  if (choice === 'light') return 'light'
  try {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  } catch {
    return 'light'
  }
}

function loadStoredTheme(): ThemeChoice {
  try {
    const s = localStorage.getItem('aurora-theme')
    if (s === 'dark' || s === 'light' || s === 'system') return s
  } catch { /* localStorage unavailable */ }
  return 'system'
}

function saveTheme(choice: ThemeChoice) {
  try { localStorage.setItem('aurora-theme', choice) } catch { /* ignore */ }
}

// ── Nav items ─────────────────────────────────────────────────────────────────

const NAV_ITEMS = [
  { to: '/', label: 'Today',  Icon: Home,         badgeKey: 'overdueTasks'        },
  { to: '/planner', label: 'Plan', Icon: CalendarDays, badgeKey: null             },
  { to: '/tasks',   label: 'Tasks', Icon: CheckSquare, badgeKey: 'overdueTasks'   },
  { to: '/campus',  label: 'Campus', Icon: MapPin,     badgeKey: 'unreadAnnouncements' },
  { to: '/assistant', label: 'Ask', Icon: MessageSquare, badgeKey: null           },
] as const

// ── Theme segmented control ───────────────────────────────────────────────────

function ThemeControl({ choice, onChange }: { choice: ThemeChoice; onChange: (c: ThemeChoice) => void }) {
  const opts: { value: ThemeChoice; Icon: typeof Monitor; label: string }[] = [
    { value: 'system', Icon: Monitor, label: 'System theme' },
    { value: 'light',  Icon: Sun,     label: 'Light theme'  },
    { value: 'dark',   Icon: Moon,    label: 'Dark theme'   },
  ]
  return (
    <div className="theme-control" role="group" aria-label="Theme">
      {opts.map(({ value, Icon, label }) => (
        <button
          key={value}
          className={`theme-btn${choice === value ? ' theme-btn-active' : ''}`}
          onClick={() => onChange(value)}
          aria-label={label}
          aria-pressed={choice === value}
          title={label}
        >
          <Icon size={15} aria-hidden="true" />
        </button>
      ))}
    </div>
  )
}

// ── App shell ─────────────────────────────────────────────────────────────────

const DEMO_BAR_HEIGHT = 44

function AppShell() {
  const [themeChoice, setThemeChoice] = useState<ThemeChoice>(loadStoredTheme)
  const location = useLocation()
  const navigate = useNavigate()
  const { badges } = useBadges()
  const { simState, now: _now } = useNow()
  const demoBarActive = simState?.mode === 'scenario'

  // Apply resolved theme to <html>
  useEffect(() => {
    const resolved = resolveTheme(themeChoice)
    document.documentElement.setAttribute('data-theme', resolved)
    saveTheme(themeChoice)
  }, [themeChoice])

  // Set --demo-bar-height CSS custom property on :root
  useEffect(() => {
    document.documentElement.style.setProperty(
      '--demo-bar-height',
      demoBarActive ? `${DEMO_BAR_HEIGHT}px` : '0px'
    )
  }, [demoBarActive])

  // React to OS theme changes when choice = 'system'
  useEffect(() => {
    if (themeChoice !== 'system') return
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    function onchange() {
      document.documentElement.setAttribute('data-theme', mq.matches ? 'dark' : 'light')
    }
    mq.addEventListener('change', onchange)
    return () => mq.removeEventListener('change', onchange)
  }, [themeChoice])

  // Page title from current route
  const pageTitle = NAV_ITEMS.find(n => n.to === location.pathname)?.label
    ?? (location.pathname === '/privacy' ? 'Privacy' : 'AURORA')

  function getBadge(key: string | null): number {
    if (key === 'overdueTasks') return badges.overdueTasks
    if (key === 'unreadAnnouncements') return badges.unreadAnnouncements
    return 0
  }

  return (
    <div className="app-layout">
      <a href="#main-content" className="skip-link">Skip to main content</a>

      {/* ── Demo / Simulation bar ──────────────────────────────────────── */}
      {demoBarActive && simState && (
        <DemoBar
          simState={simState}
          onAdvance={() => { /* TodayScreen polls via useNow */ }}
          onReset={() => { /* TodayScreen polls via useNow */ }}
          onStop={() => { /* reserved */ }}
          onStaffView={() => navigate('/campus?tab=operations')}
        />
      )}

      {/* ── Desktop / tablet left rail ─────────────────────────────────── */}
      <nav className="app-rail" aria-label="Main navigation">
        <div className="rail-brand">
          <span className="rail-brand-name">AURORA</span>
          <span className="rail-brand-sub">Campus Intel</span>
        </div>

        <ul className="rail-nav">
          {NAV_ITEMS.map(({ to, label, Icon, badgeKey }) => {
            const count = getBadge(badgeKey)
            return (
              <li key={to}>
                <NavLink
                  to={to}
                  end={to === '/'}
                  className={({ isActive }) => `rail-link${isActive ? ' rail-link-active' : ''}`}
                  aria-label={count > 0 ? `${label}, ${count} pending` : label}
                >
                  <Icon size={18} aria-hidden="true" />
                  <span className="rail-label">{label}</span>
                  {count > 0 && (
                    <span className="nav-badge" aria-hidden="true">{count > 99 ? '99+' : count}</span>
                  )}
                </NavLink>
              </li>
            )
          })}
        </ul>

        <div className="rail-bottom">
          <NavLink
            to="/privacy"
            className={({ isActive }) => `rail-link${isActive ? ' rail-link-active' : ''}`}
            aria-label="Privacy"
          >
            <Shield size={18} aria-hidden="true" />
            <span className="rail-label">Privacy</span>
          </NavLink>
          <ThemeControl choice={themeChoice} onChange={setThemeChoice} />
        </div>
      </nav>

      {/* ── Mobile top bar ─────────────────────────────────────────────── */}
      <header className="app-topbar" role="banner">
        <span className="topbar-title">{pageTitle}</span>
        <div className="topbar-actions">
          <ThemeControl choice={themeChoice} onChange={setThemeChoice} />
          <NavLink to="/privacy" className="btn btn-ghost btn-icon" aria-label="Privacy">
            <Shield size={17} aria-hidden="true" />
          </NavLink>
        </div>
      </header>

      {/* ── Main content ───────────────────────────────────────────────── */}
      <main
        id="main-content"
        className="app-main"
        tabIndex={-1}
        style={demoBarActive ? { paddingTop: `${DEMO_BAR_HEIGHT}px` } as React.CSSProperties : undefined}
      >
        <div className="app-main-inner container">
          <Routes>
            <Route path="/" element={<TodayScreen />} />
            <Route path="/planner" element={<PlannerScreen />} />
            <Route path="/tasks" element={<TasksScreen />} />
            <Route path="/campus" element={<CampusScreen />} />
            <Route path="/assistant" element={<AssistantScreen />} />
            <Route path="/privacy" element={<PrivacyScreen />} />
          </Routes>
        </div>
      </main>

      {/* ── Mobile bottom tab bar ──────────────────────────────────────── */}
      <nav className="app-tabbar" aria-label="Main navigation">
        {NAV_ITEMS.map(({ to, label, Icon, badgeKey }) => {
          const count = getBadge(badgeKey)
          return (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) => `tabbar-item${isActive ? ' tabbar-item-active' : ''}`}
              aria-label={count > 0 ? `${label}, ${count} pending` : label}
            >
              <span className="tabbar-icon-wrap">
                <Icon size={20} aria-hidden="true" />
                {count > 0 && (
                  <span className="nav-badge nav-badge-sm" aria-hidden="true">
                    {count > 99 ? '99+' : count}
                  </span>
                )}
              </span>
              <span className="tabbar-label">{label}</span>
            </NavLink>
          )
        })}
      </nav>

      <Toast />
    </div>
  )
}

export default function App() {
  return (
    <ToastProvider>
      <ConfirmProvider>
        <BadgesProvider>
          <AppShell />
        </BadgesProvider>
      </ConfirmProvider>
    </ToastProvider>
  )
}

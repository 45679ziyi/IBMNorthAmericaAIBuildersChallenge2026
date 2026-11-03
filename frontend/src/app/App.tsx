import { Routes, Route, NavLink, useLocation } from 'react-router-dom'
import { useState, useEffect, createContext, useContext } from 'react'
import { Sun, Moon } from 'lucide-react'
import TodayScreen from '../features/dashboard/TodayScreen'
import PlannerScreen from '../features/planner/PlannerScreen'
import TasksScreen from '../features/tasks/TasksScreen'
import CampusScreen from '../features/campus/CampusScreen'
import AssistantScreen from '../features/assistant/AssistantScreen'
import PrivacyScreen from '../features/privacy/PrivacyScreen'
import { Toast, ToastProvider, useToast } from '../components/Toast'
import { ConfirmProvider } from '../components/ConfirmModal'
import './App.css'

// ── Badge counts context ────────────────────────────────────────────────────
interface BadgeCounts { overdueTasks: number; unreadAnnouncements: number }
export const BadgeCtx = createContext<BadgeCounts>({ overdueTasks: 0, unreadAnnouncements: 0 })
export const useBadges = () => useContext(BadgeCtx)

function AppShell() {
  const [theme, setTheme] = useState<'light' | 'dark'>(() =>
    (localStorage.getItem('aurora-theme') as 'light' | 'dark') || 'light'
  )
  const [badges, setBadges] = useState<BadgeCounts>({ overdueTasks: 0, unreadAnnouncements: 0 })

  // Apply theme to <html> element
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('aurora-theme', theme)
  }, [theme])

  // Poll badge counts every 30s
  useEffect(() => {
    async function loadBadges() {
      try {
        const [tasks, ann] = await Promise.all([
          fetch('/api/v1/tasks').then(r => r.json()),
          fetch('/api/v1/announcements').then(r => r.json()),
        ])
        const now = Date.now()
        const overdue = tasks.filter((t: { status: string; due_at_utc?: string }) =>
          t.status !== 'done' && t.due_at_utc && new Date(t.due_at_utc).getTime() < now
        ).length
        setBadges({ overdueTasks: overdue, unreadAnnouncements: ann.length })
      } catch { /* silent */ }
    }
    loadBadges()
    const id = setInterval(loadBadges, 30_000)
    return () => clearInterval(id)
  }, [])

  return (
    <BadgeCtx.Provider value={badges}>
      <div className="app-layout">
        <a href="#main-content" className="skip-link">Skip to main content</a>

        <header className="app-header" role="banner">
          <div className="header-inner container">
            <div className="brand">
              <span className="brand-name">AURORA</span>
              <span className="brand-sub">Campus Intelligence</span>
            </div>
            <nav className="main-nav" aria-label="Main navigation">
              <NavLink to="/" end>Today</NavLink>
              <NavLink to="/planner">Planner</NavLink>
              <NavLink to="/tasks">
                Tasks
                {badges.overdueTasks > 0 && (
                  <span className="nav-badge" aria-label={`${badges.overdueTasks} overdue`}>
                    {badges.overdueTasks}
                  </span>
                )}
              </NavLink>
              <NavLink to="/campus">
                Campus
                {badges.unreadAnnouncements > 0 && (
                  <span className="nav-badge nav-badge-blue" aria-label={`${badges.unreadAnnouncements} announcements`}>
                    {badges.unreadAnnouncements}
                  </span>
                )}
              </NavLink>
              <NavLink to="/assistant">Assistant</NavLink>
              <NavLink to="/privacy">Privacy</NavLink>
            </nav>

            <button
              className="btn btn-ghost btn-icon"
              onClick={() => setTheme(t => t === 'light' ? 'dark' : 'light')}
              aria-label={theme === 'light' ? 'Switch to dark mode' : 'Switch to light mode'}
              title={theme === 'light' ? 'Dark mode' : 'Light mode'}
            >
              {theme === 'light'
                ? <Moon size={17} aria-hidden="true" />
                : <Sun size={17} aria-hidden="true" />
              }
            </button>
          </div>
        </header>

        <main id="main-content" className="app-main container" tabIndex={-1}>
          <Routes>
            <Route path="/" element={<TodayScreen />} />
            <Route path="/planner" element={<PlannerScreen />} />
            <Route path="/tasks" element={<TasksScreen />} />
            <Route path="/campus" element={<CampusScreen />} />
            <Route path="/assistant" element={<AssistantScreen />} />
            <Route path="/privacy" element={<PrivacyScreen />} />
          </Routes>
        </main>

        <footer className="disclaimer-footer">
          AURORA is an independent prototype for educational purposes.
          It is not affiliated with, endorsed by, or operated by Stony Brook University or IBM.
        </footer>

        <Toast />
      </div>
    </BadgeCtx.Provider>
  )
}

export default function App() {
  return (
    <ToastProvider>
      <ConfirmProvider>
        <AppShell />
      </ConfirmProvider>
    </ToastProvider>
  )
}

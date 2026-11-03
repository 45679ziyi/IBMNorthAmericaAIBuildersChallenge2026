import { Routes, Route, NavLink } from 'react-router-dom'
import TodayScreen from '../features/dashboard/TodayScreen'
import PlannerScreen from '../features/planner/PlannerScreen'
import TasksScreen from '../features/tasks/TasksScreen'
import CampusScreen from '../features/campus/CampusScreen'
import AssistantScreen from '../features/assistant/AssistantScreen'
import PrivacyScreen from '../features/privacy/PrivacyScreen'
import './App.css'

export default function App() {
  return (
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
            <NavLink to="/tasks">Tasks</NavLink>
            <NavLink to="/campus">Campus</NavLink>
            <NavLink to="/assistant">Assistant</NavLink>
            <NavLink to="/privacy">Privacy</NavLink>
          </nav>
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
    </div>
  )
}

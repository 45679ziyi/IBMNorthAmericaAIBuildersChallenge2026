import { useEffect, useRef } from 'react'
import type { ReactNode } from 'react'
import './Tabs.css'

export interface TabItem {
  id: string
  label: ReactNode
}

interface TabsProps {
  items: TabItem[]
  activeTab: string
  onTabChange: (id: string) => void
}

export function Tabs({ items, activeTab, onTabChange }: TabsProps): JSX.Element {
  const listRef = useRef<HTMLDivElement>(null)

  // Keyboard navigation within tablist
  function handleKeyDown(e: React.KeyboardEvent<HTMLButtonElement>, index: number) {
    const tabs = listRef.current?.querySelectorAll<HTMLButtonElement>('[role="tab"]')
    if (!tabs) return
    let next = -1
    if (e.key === 'ArrowRight') next = (index + 1) % tabs.length
    if (e.key === 'ArrowLeft')  next = (index - 1 + tabs.length) % tabs.length
    if (e.key === 'Home')       next = 0
    if (e.key === 'End')        next = tabs.length - 1
    if (next >= 0) {
      e.preventDefault()
      tabs[next].focus()
      onTabChange(items[next].id)
    }
  }

  return (
    <div ref={listRef} role="tablist" className="tabs-list">
      {items.map((item, i) => (
        <button
          key={item.id}
          role="tab"
          id={`tab-${item.id}`}
          aria-selected={activeTab === item.id}
          aria-controls={`tabpanel-${item.id}`}
          tabIndex={activeTab === item.id ? 0 : -1}
          className={`tabs-tab${activeTab === item.id ? ' tabs-tab-active' : ''}`}
          onClick={() => onTabChange(item.id)}
          onKeyDown={e => handleKeyDown(e, i)}
        >
          {item.label}
        </button>
      ))}
    </div>
  )
}

interface TabPanelProps {
  id: string
  activeTab: string
  children: ReactNode
}

export function TabPanel({ id, activeTab, children }: TabPanelProps): JSX.Element {
  return (
    <div
      role="tabpanel"
      id={`tabpanel-${id}`}
      aria-labelledby={`tab-${id}`}
      hidden={activeTab !== id}
    >
      {activeTab === id && children}
    </div>
  )
}

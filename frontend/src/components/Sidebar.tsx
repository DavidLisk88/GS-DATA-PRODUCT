import React from 'react'
import {
  MessageSquare,
  Plus,
  Database,
  Code2,
  Settings,
  Moon,
  Sun,
  PanelLeftClose,
  PanelLeftOpen,
} from 'lucide-react'

interface Conversation {
  id: string
  title: string
  updatedAt: Date
}

interface SidebarProps {
  collapsed: boolean
  onToggle: () => void
  activeView: string
  onViewChange: (view: string) => void
  conversations: Conversation[]
  activeConversationId: string | null
  onSelectConversation: (id: string) => void
  onNewChat: () => void
  theme: string
  onThemeToggle: () => void
}

export default function Sidebar({
  collapsed,
  onToggle,
  activeView,
  onViewChange,
  conversations,
  activeConversationId,
  onSelectConversation,
  onNewChat,
  theme,
  onThemeToggle,
}: SidebarProps) {
  return (
    <aside className={`sidebar ${collapsed ? 'collapsed' : ''}`}>
      <div className="sidebar-header">
        <div className="sidebar-logo">
          <div className="sidebar-logo-icon">GS</div>
          <span>LSEG Copilot</span>
        </div>
      </div>

      <div className="sidebar-actions">
        <button className="new-chat-btn" onClick={onNewChat}>
          <Plus size={16} />
          New conversation
        </button>
      </div>

      <nav className="sidebar-nav">
        <button
          className={`nav-item ${activeView === 'chat' ? 'active' : ''}`}
          onClick={() => onViewChange('chat')}
        >
          <MessageSquare size={16} />
          Chat
        </button>
        <button
          className={`nav-item ${activeView === 'schema' ? 'active' : ''}`}
          onClick={() => onViewChange('schema')}
        >
          <Database size={16} />
          Schema Explorer
        </button>
        <button
          className={`nav-item ${activeView === 'sql' ? 'active' : ''}`}
          onClick={() => onViewChange('sql')}
        >
          <Code2 size={16} />
          SQL Playground
        </button>
      </nav>

      <div className="sidebar-conversations">
        {conversations.length > 0 && (
          <>
            <div className="conversations-label">Recent</div>
            {conversations.map(conv => (
              <div
                key={conv.id}
                className={`conversation-item ${conv.id === activeConversationId ? 'active' : ''}`}
                onClick={() => onSelectConversation(conv.id)}
              >
                {conv.title}
              </div>
            ))}
          </>
        )}
      </div>

      <div className="sidebar-footer">
        <button className="icon-btn" onClick={onThemeToggle} title="Toggle theme">
          {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
        </button>
        <button className="icon-btn" onClick={onToggle} title="Toggle sidebar">
          {collapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
        </button>
      </div>
    </aside>
  )
}

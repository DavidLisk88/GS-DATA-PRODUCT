import React, { useState } from 'react'
import { PanelLeftOpen } from 'lucide-react'
import Sidebar from './components/Sidebar'
import ChatPage from './pages/ChatPage'
import SchemaExplorer from './pages/SchemaExplorer'
import SQLPlayground from './pages/SQLPlayground'
import { useTheme } from './hooks/useTheme'

interface Conversation {
  id: string
  title: string
  updatedAt: Date
}

export default function App() {
  const { theme, toggle: toggleTheme } = useTheme()
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [activeView, setActiveView] = useState('chat')
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null)

  const handleNewChat = () => {
    setActiveConversationId(null)
    setActiveView('chat')
  }

  const handleConversationCreated = (id: string, title: string) => {
    setConversations(prev => [
      { id, title, updatedAt: new Date() },
      ...prev,
    ])
    setActiveConversationId(id)
  }

  const handleSelectConversation = (id: string) => {
    setActiveConversationId(id)
    setActiveView('chat')
  }

  const handleTableClick = (fqn: string) => {
    setActiveView('schema')
  }

  return (
    <div className="app-layout">
      <Sidebar
        collapsed={sidebarCollapsed}
        onToggle={() => setSidebarCollapsed(!sidebarCollapsed)}
        activeView={activeView}
        onViewChange={setActiveView}
        conversations={conversations}
        activeConversationId={activeConversationId}
        onSelectConversation={handleSelectConversation}
        onNewChat={handleNewChat}
        theme={theme}
        onThemeToggle={toggleTheme}
      />

      <main className="main-content">
        <div className="main-header">
          <div className="header-left">
            {sidebarCollapsed && (
              <button
                className="icon-btn"
                onClick={() => setSidebarCollapsed(false)}
              >
                <PanelLeftOpen size={18} />
              </button>
            )}
            <span style={{ fontWeight: 600, fontSize: '14px' }}>
              {activeView === 'chat' && 'Chat'}
              {activeView === 'schema' && 'Schema Explorer'}
              {activeView === 'sql' && 'SQL Playground'}
            </span>
          </div>
          <div className="header-right">
            <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
              LSEG Data Copilot v0.2
            </span>
          </div>
        </div>

        {activeView === 'chat' && (
          <ChatPage
            conversationId={activeConversationId}
            onConversationCreated={handleConversationCreated}
            onTableClick={handleTableClick}
          />
        )}
        {activeView === 'schema' && <SchemaExplorer />}
        {activeView === 'sql' && <SQLPlayground />}
      </main>
    </div>
  )
}

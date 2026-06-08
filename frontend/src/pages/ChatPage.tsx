import React, { useState, useRef, useEffect } from 'react'
import ChatMessage from '../components/ChatMessage'
import ChatInput from '../components/ChatInput'
import EmptyState from '../components/EmptyState'
import { api, AskResponse } from '../services/api'

interface Message {
  role: 'user' | 'assistant'
  content: string
  citations?: AskResponse['citations']
  sqlResult?: AskResponse['sql_result']
  relatedTables?: string[]
  processingTime?: number
}

interface ChatPageProps {
  conversationId: string | null
  onConversationCreated: (id: string, title: string) => void
  onTableClick?: (fqn: string) => void
}

export default function ChatPage({
  conversationId,
  onConversationCreated,
  onTableClick,
}: ChatPageProps) {
  const [messages, setMessages] = useState<Message[]>([])
  const [loading, setLoading] = useState(false)
  const [currentConvId, setCurrentConvId] = useState<string | null>(conversationId)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    setCurrentConvId(conversationId)
    if (!conversationId) {
      setMessages([])
    }
  }, [conversationId])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const sendMessage = async (text: string) => {
    const userMsg: Message = { role: 'user', content: text }
    setMessages(prev => [...prev, userMsg])
    setLoading(true)

    try {
      const resp = await api.ask(text, currentConvId || undefined)

      if (!currentConvId) {
        setCurrentConvId(resp.conversation_id)
        const title = text.length > 50 ? text.slice(0, 47) + '...' : text
        onConversationCreated(resp.conversation_id, title)
      }

      const assistantMsg: Message = {
        role: 'assistant',
        content: resp.answer,
        citations: resp.citations,
        sqlResult: resp.sql_result,
        relatedTables: resp.related_tables,
        processingTime: resp.processing_time_ms,
      }
      setMessages(prev => [...prev, assistantMsg])
    } catch (err) {
      const errorMsg: Message = {
        role: 'assistant',
        content: `Sorry, something went wrong: ${err instanceof Error ? err.message : 'Unknown error'}. Please try again.`,
      }
      setMessages(prev => [...prev, errorMsg])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="chat-area">
      {messages.length === 0 ? (
        <EmptyState onPrompt={sendMessage} />
      ) : (
        <div className="chat-messages">
          <div className="message-container">
            {messages.map((msg, i) => (
              <ChatMessage
                key={i}
                role={msg.role}
                content={msg.content}
                citations={msg.citations}
                sqlResult={msg.sqlResult}
                relatedTables={msg.relatedTables}
                processingTime={msg.processingTime}
                onTableClick={onTableClick}
              />
            ))}
            {loading && (
              <div className="message">
                <div className="message-avatar assistant">GS</div>
                <div className="message-body">
                  <div className="message-role">LSEG Copilot</div>
                  <div className="loading-dots">
                    <div className="loading-dot" />
                    <div className="loading-dot" />
                    <div className="loading-dot" />
                  </div>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>
        </div>
      )}
      <ChatInput onSend={sendMessage} loading={loading} />
    </div>
  )
}

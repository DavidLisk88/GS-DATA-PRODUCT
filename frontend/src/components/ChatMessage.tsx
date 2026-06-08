import React, { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism'
import {
  ChevronDown,
  ChevronRight,
  Copy,
  Check,
  CheckCircle,
  XCircle,
  AlertTriangle,
  BookOpen,
} from 'lucide-react'
import type { Citation, SQLResult } from '../services/api'

interface ChatMessageProps {
  role: 'user' | 'assistant'
  content: string
  citations?: Citation[]
  sqlResult?: SQLResult | null
  relatedTables?: string[]
  processingTime?: number
  onTableClick?: (fqn: string) => void
}

export default function ChatMessage({
  role,
  content,
  citations,
  sqlResult,
  relatedTables,
  processingTime,
  onTableClick,
}: ChatMessageProps) {
  const [citationsOpen, setCitationsOpen] = useState(false)
  const [sqlCopied, setSqlCopied] = useState(false)

  const copySql = async () => {
    if (sqlResult?.sql) {
      await navigator.clipboard.writeText(sqlResult.sql)
      setSqlCopied(true)
      setTimeout(() => setSqlCopied(false), 2000)
    }
  }

  return (
    <div className="message">
      <div className={`message-avatar ${role}`}>
        {role === 'user' ? 'You' : 'GS'}
      </div>
      <div className="message-body">
        <div className="message-role">
          {role === 'user' ? 'You' : 'LSEG Copilot'}
        </div>
        <div className="message-content">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              code(props) {
                const { children, className, ...rest } = props
                const match = /language-(\w+)/.exec(className || '')
                const codeStr = String(children).replace(/\n$/, '')
                if (match) {
                  return (
                    <SyntaxHighlighter
                      style={oneDark}
                      language={match[1]}
                      PreTag="div"
                      customStyle={{
                        borderRadius: '10px',
                        fontSize: '13px',
                        margin: '12px 0',
                      }}
                    >
                      {codeStr}
                    </SyntaxHighlighter>
                  )
                }
                return <code className={className} {...rest}>{children}</code>
              },
            }}
          >
            {content}
          </ReactMarkdown>
        </div>

        {/* SQL Result */}
        {sqlResult && (
          <div className="sql-block">
            <div className="sql-block-header">
              <span>Generated SQL</span>
              <span className={`sql-status ${sqlResult.validated ? 'valid' : 'invalid'}`}>
                {sqlResult.validated ? (
                  <><CheckCircle size={12} /> Valid</>
                ) : (
                  <><XCircle size={12} /> Issues found</>
                )}
              </span>
            </div>
            <div className="sql-block-body">
              <SyntaxHighlighter
                style={oneDark}
                language="sql"
                customStyle={{
                  background: 'transparent',
                  padding: 0,
                  margin: 0,
                  fontSize: '13px',
                }}
              >
                {sqlResult.sql}
              </SyntaxHighlighter>
            </div>
            {(sqlResult.errors.length > 0 || sqlResult.warnings.length > 0) && (
              <div style={{ padding: '8px 12px', fontSize: '12px' }}>
                {sqlResult.errors.map((e, i) => (
                  <div key={i} style={{ color: 'var(--accent-error)', display: 'flex', alignItems: 'center', gap: '4px', marginBottom: '2px' }}>
                    <XCircle size={12} /> {e}
                  </div>
                ))}
                {sqlResult.warnings.map((w, i) => (
                  <div key={i} style={{ color: 'var(--accent-warning)', display: 'flex', alignItems: 'center', gap: '4px', marginBottom: '2px' }}>
                    <AlertTriangle size={12} /> {w}
                  </div>
                ))}
              </div>
            )}
            <div className="sql-actions">
              <button className="sql-action-btn" onClick={copySql}>
                {sqlCopied ? <><Check size={12} /> Copied</> : <><Copy size={12} /> Copy</>}
              </button>
            </div>
          </div>
        )}

        {/* Related Tables */}
        {relatedTables && relatedTables.length > 0 && (
          <div className="related-tables">
            {relatedTables.map(fqn => (
              <span
                key={fqn}
                className="table-pill"
                onClick={() => onTableClick?.(fqn)}
              >
                {fqn}
              </span>
            ))}
          </div>
        )}

        {/* Citations */}
        {citations && citations.length > 0 && (
          <div className="citations-panel">
            <div
              className="citations-header"
              onClick={() => setCitationsOpen(!citationsOpen)}
            >
              <BookOpen size={12} />
              {citationsOpen ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
              {citations.length} source{citations.length > 1 ? 's' : ''}
            </div>
            {citationsOpen &&
              citations.map((c, i) => (
                <div key={i} className="citation-item">
                  <div className="citation-source">{c.title || c.source}</div>
                  <div className="citation-snippet">{c.snippet}</div>
                </div>
              ))}
          </div>
        )}

        {/* Processing time */}
        {processingTime != null && role === 'assistant' && (
          <div style={{ marginTop: '8px', fontSize: '11px', color: 'var(--text-muted)' }}>
            {processingTime.toFixed(0)}ms
          </div>
        )}
      </div>
    </div>
  )
}

import React from 'react'
import { Database } from 'lucide-react'

interface QuickAction {
  title: string
  description: string
  prompt: string
}

const QUICK_ACTIONS: QuickAction[] = [
  {
    title: 'Explore Datastream pricing',
    description: 'Find tables for equity time series and total return indices',
    prompt: 'What Datastream tables hold equity pricing data and total return indices?',
  },
  {
    title: 'IBES earnings estimates',
    description: 'Understand consensus and detail-level analyst estimates',
    prompt: 'Which IBES tables contain consensus estimates vs individual analyst forecasts?',
  },
  {
    title: 'Cross-reference identifiers',
    description: 'Map between PermID, RIC, ISIN, CUSIP, GVKEY',
    prompt: 'How do I map from CUSIP to PermID and then to a Datastream code?',
  },
  {
    title: 'Generate a SQL query',
    description: 'Text-to-SQL with automatic schema validation',
    prompt: "Write SQL to get Apple's closing price on 2026-05-28 from the EOD pricing table.",
  },
]

interface EmptyStateProps {
  onPrompt: (prompt: string) => void
}

export default function EmptyState({ onPrompt }: EmptyStateProps) {
  return (
    <div className="empty-state">
      <div className="empty-logo">
        <Database size={32} />
      </div>
      <h2 className="empty-title">LSEG Data Copilot</h2>
      <p className="empty-subtitle">
        Your AI assistant for LSEG Quantitative Analytics data. Ask about schemas,
        tables, fields, queries, joins, and identifiers across 1,600+ real QA tables.
      </p>
      <div className="quick-actions">
        {QUICK_ACTIONS.map((action, i) => (
          <div
            key={i}
            className="quick-action"
            onClick={() => onPrompt(action.prompt)}
          >
            <div className="quick-action-title">{action.title}</div>
            <div className="quick-action-desc">{action.description}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

import React, { useState } from 'react'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism'
import {
  Play,
  Copy,
  Check,
  CheckCircle,
  XCircle,
  AlertTriangle,
  Trash2,
} from 'lucide-react'
import { api, ValidateSQLResponse } from '../services/api'

export default function SQLPlayground() {
  const [sql, setSql] = useState(
    `-- Try validating a SQL query against the LSEG catalog\nSELECT\n  e.entity_legal_name,\n  p.close_price,\n  p.price_date\nFROM lseg_ref.entity_master e\nJOIN lseg_dss.eod_pricing p\n  ON e.org_perm_id = p.org_perm_id\nWHERE p.ric_as_of = 'AAPL.OQ'\n  AND p.price_date = DATE '2026-05-28'\n  AND e.is_current = TRUE`
  )
  const [result, setResult] = useState<ValidateSQLResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [copied, setCopied] = useState(false)

  const validate = async () => {
    setLoading(true)
    try {
      const resp = await api.validateSQL(sql)
      setResult(resp)
    } catch (err) {
      console.error('Validation failed:', err)
    } finally {
      setLoading(false)
    }
  }

  const copyRewritten = async () => {
    if (result?.rewritten_sql) {
      await navigator.clipboard.writeText(result.rewritten_sql)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  return (
    <div className="sql-playground">
      <div className="sql-playground-header">
        <h2 className="sql-playground-title">SQL Playground</h2>
        <p style={{ color: 'var(--text-secondary)', fontSize: '13px', marginTop: '4px' }}>
          Validate SQL against the LSEG catalog ({'>'}1,600 tables). Checks table/column existence,
          injects LIMIT, and flags currency-consistency issues.
        </p>
      </div>

      <div className="sql-editor-wrapper">
        <textarea
          className="sql-editor"
          value={sql}
          onChange={e => setSql(e.target.value)}
          placeholder="Enter your SQL query..."
          spellCheck={false}
        />

        <div className="sql-toolbar">
          <button className="btn btn-primary" onClick={validate} disabled={loading || !sql.trim()}>
            <Play size={14} />
            {loading ? 'Validating...' : 'Validate'}
          </button>
          <button className="btn btn-secondary" onClick={() => { setSql(''); setResult(null) }}>
            <Trash2 size={14} />
            Clear
          </button>
        </div>

        {result && (
          <div className={`validation-result ${result.valid ? 'valid' : 'invalid'}`}>
            <div className={`validation-title ${result.valid ? 'valid' : 'invalid'}`}>
              {result.valid ? (
                <><CheckCircle size={16} /> SQL is valid</>
              ) : (
                <><XCircle size={16} /> Validation errors found</>
              )}
            </div>

            {result.errors.length > 0 && (
              <ul className="validation-list">
                {result.errors.map((e, i) => (
                  <li key={i} style={{ color: 'var(--accent-error)' }}>
                    <XCircle size={12} style={{ display: 'inline', marginRight: '4px', verticalAlign: 'middle' }} />
                    {e}
                  </li>
                ))}
              </ul>
            )}

            {result.warnings.length > 0 && (
              <ul className="validation-list" style={{ marginTop: '8px' }}>
                {result.warnings.map((w, i) => (
                  <li key={i} style={{ color: 'var(--accent-warning)' }}>
                    <AlertTriangle size={12} style={{ display: 'inline', marginRight: '4px', verticalAlign: 'middle' }} />
                    {w}
                  </li>
                ))}
              </ul>
            )}

            {result.tables_referenced.length > 0 && (
              <div style={{ marginTop: '12px' }}>
                <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '6px' }}>
                  Tables referenced:
                </div>
                <div className="related-tables">
                  {result.tables_referenced.map(t => (
                    <span key={t} className="table-pill">{t}</span>
                  ))}
                </div>
              </div>
            )}

            {result.rewritten_sql !== result.original_sql && (
              <div style={{ marginTop: '12px' }}>
                <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '6px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <span>Rewritten SQL (with LIMIT):</span>
                  <button className="sql-action-btn" onClick={copyRewritten}>
                    {copied ? <><Check size={12} /> Copied</> : <><Copy size={12} /> Copy</>}
                  </button>
                </div>
                <SyntaxHighlighter
                  style={oneDark}
                  language="sql"
                  customStyle={{
                    borderRadius: '8px',
                    fontSize: '13px',
                  }}
                >
                  {result.rewritten_sql}
                </SyntaxHighlighter>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

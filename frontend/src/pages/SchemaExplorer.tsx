import React, { useState, useEffect, useCallback } from 'react'
import { Search, ChevronDown, ChevronRight } from 'lucide-react'
import { api, TableInfo, CatalogSearchResponse } from '../services/api'

export default function SchemaExplorer() {
  const [query, setQuery] = useState('')
  const [domain, setDomain] = useState<string>('')
  const [data, setData] = useState<CatalogSearchResponse | null>(null)
  const [expandedTables, setExpandedTables] = useState<Set<string>>(new Set())
  const [loading, setLoading] = useState(false)

  const search = useCallback(async () => {
    setLoading(true)
    try {
      const result = await api.searchCatalog(query, domain || undefined, 50)
      setData(result)
    } catch (err) {
      console.error('Search failed:', err)
    } finally {
      setLoading(false)
    }
  }, [query, domain])

  useEffect(() => {
    const timer = setTimeout(search, 300)
    return () => clearTimeout(timer)
  }, [search])

  const toggleTable = (fqn: string) => {
    setExpandedTables(prev => {
      const next = new Set(prev)
      if (next.has(fqn)) next.delete(fqn)
      else next.add(fqn)
      return next
    })
  }

  return (
    <div className="schema-explorer">
      <div className="schema-header">
        <h2 className="schema-title">Schema Explorer</h2>
        <div className="schema-search">
          <input
            className="schema-search-input"
            type="text"
            placeholder="Search tables, columns, domains..."
            value={query}
            onChange={e => setQuery(e.target.value)}
          />
          <select
            className="domain-filter"
            value={domain}
            onChange={e => setDomain(e.target.value)}
          >
            <option value="">All Domains</option>
            {data?.domains
              ?.sort((a, b) => b.table_count - a.table_count)
              .map(d => (
                <option key={d.code} value={d.code}>
                  {d.name || d.code} ({d.table_count})
                </option>
              ))}
          </select>
        </div>
      </div>

      {data && (
        <div className="schema-stats">
          <div className="stat-item">
            <span className="stat-value">{data.total_count.toLocaleString()}</span>
            <span className="stat-label">total tables</span>
          </div>
          <div className="stat-item">
            <span className="stat-value">{data.domains?.length || 0}</span>
            <span className="stat-label">domains</span>
          </div>
          <div className="stat-item">
            <span className="stat-value">{data.tables.length}</span>
            <span className="stat-label">shown</span>
          </div>
        </div>
      )}

      <div className="schema-content">
        {loading && (
          <div style={{ padding: '20px', textAlign: 'center', color: 'var(--text-tertiary)' }}>
            Searching...
          </div>
        )}
        {data?.tables.map(table => {
          const expanded = expandedTables.has(table.fqn)
          return (
            <div key={table.fqn} className="table-card">
              <div className="table-card-header" onClick={() => toggleTable(table.fqn)}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                  <span className="table-card-name">{table.fqn}</span>
                  <span style={{ color: 'var(--text-muted)', fontSize: '12px' }}>
                    {table.column_count} cols
                  </span>
                </div>
                <span className="table-card-domain">{table.domain}</span>
              </div>
              {table.description && (
                <div className="table-card-desc">
                  {table.description.length > 150
                    ? table.description.slice(0, 147) + '...'
                    : table.description}
                </div>
              )}
              {expanded && table.columns.length > 0 && (
                <div className="table-card-columns">
                  <div className="column-row header">
                    <span>Column</span>
                    <span>Type</span>
                    <span>Null</span>
                    <span>Description</span>
                  </div>
                  {table.columns.map(col => (
                    <div key={col.name} className="column-row">
                      <span className="column-name">{col.name}</span>
                      <span className="column-type">{col.type}</span>
                      <span className="column-nullable">{col.nullable ? 'yes' : 'no'}</span>
                      <span className="column-desc">{col.description || ''}</span>
                    </div>
                  ))}
                </div>
              )}
              {table.tags.length > 0 && expanded && (
                <div style={{ padding: '8px 16px', display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
                  {table.tags.map(tag => (
                    <span key={tag} className="table-pill">{tag}</span>
                  ))}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

const API_BASE = '/api'

export interface Citation {
  source: string
  title: string
  snippet: string
  relevance_score: number
}

export interface SQLResult {
  sql: string
  dialect: string
  validated: boolean
  errors: string[]
  warnings: string[]
}

export interface AskResponse {
  answer: string
  intent: string
  conversation_id: string
  citations: Citation[]
  sql_result: SQLResult | null
  related_tables: string[]
  processing_time_ms: number
}

export interface ColumnInfo {
  name: string
  type: string
  nullable: boolean
  description: string | null
}

export interface TableInfo {
  fqn: string
  domain: string
  description: string | null
  update_cadence: string | null
  temporal_model: string | null
  column_count: number
  columns: ColumnInfo[]
  tags: string[]
}

export interface DomainInfo {
  code: string
  name: string
  table_count: number
  anchor_keys: string[]
}

export interface CatalogSearchResponse {
  tables: TableInfo[]
  total_count: number
  domains: { code: string; name: string; table_count: number }[]
}

export interface ValidateSQLResponse {
  original_sql: string
  rewritten_sql: string
  valid: boolean
  errors: string[]
  warnings: string[]
  tables_referenced: string[]
}

export interface HealthResponse {
  status: string
  catalog_tables: number
  catalog_domains: number
  symbol_index_size: number
}

async function fetchJSON<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${url}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`API error ${res.status}: ${text}`)
  }
  return res.json()
}

export const api = {
  health: () => fetchJSON<HealthResponse>('/health'),

  ask: (question: string, conversationId?: string) =>
    fetchJSON<AskResponse>('/ask', {
      method: 'POST',
      body: JSON.stringify({
        question,
        conversation_id: conversationId,
        include_sql: true,
        include_citations: true,
      }),
    }),

  searchCatalog: (query: string, domain?: string, limit = 20) => {
    const params = new URLSearchParams()
    if (query) params.set('q', query)
    if (domain) params.set('domain', domain)
    params.set('limit', String(limit))
    return fetchJSON<CatalogSearchResponse>(`/catalog/search?${params}`)
  },

  getDomains: () =>
    fetchJSON<{ domains: DomainInfo[]; total_tables: number }>('/catalog/domains'),

  getTable: (fqn: string) => fetchJSON<TableInfo>(`/catalog/tables/${fqn}`),

  validateSQL: (sql: string, rowCap = 1000) =>
    fetchJSON<ValidateSQLResponse>('/validate-sql', {
      method: 'POST',
      body: JSON.stringify({ sql, row_cap: rowCap }),
    }),
}

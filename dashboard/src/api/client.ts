const API_BASE = '/dashboard'

const getAuthToken = (): string | null => {
  const envToken = import.meta.env.VITE_TITAN_TOKEN
  if (envToken) {
    return envToken
  }
  if (typeof window !== 'undefined') {
    return window.localStorage.getItem('titan_token')
  }
  return null
}

const buildHeaders = (headers?: HeadersInit): HeadersInit => {
  const authToken = getAuthToken()
  const authHeader = authToken
    ? authToken.startsWith('Bearer ')
      ? authToken
      : `Bearer ${authToken}`
    : undefined

  return {
    'Content-Type': 'application/json',
    ...(authHeader ? { Authorization: authHeader } : {}),
    ...headers,
  }
}

export interface ComponentHealth {
  name: string
  status: 'healthy' | 'degraded' | 'unhealthy'
  message?: string
  details?: Record<string, unknown>
}

export interface EntityCounts {
  aas: number
  submodels: number
  concept_descriptions: number
}

export interface SystemOverview {
  status: 'healthy' | 'degraded' | 'unhealthy'
  timestamp: string
  uptime_seconds: number
  version: string
  environment: string
  entity_counts: EntityCounts
  components: ComponentHealth[]
}

export interface PoolStats {
  pool_size: number
  checked_out: number
  overflow: number
  checked_in: number
}

export interface TableStats {
  name: string
  row_count: number
  estimated_size?: string
}

export interface DatabaseStats {
  timestamp: string
  pool: PoolStats
  tables: TableStats[]
  query_stats?: {
    total_queries: number
    avg_duration_ms?: number | null
    p50_duration_ms?: number | null
    p95_duration_ms?: number | null
    p99_duration_ms?: number | null
  } | null
}

export interface CacheStats {
  timestamp: string
  memory: {
    used_memory: string
    used_memory_peak: string
    used_memory_rss?: string
    maxmemory?: string
  }
  keyspace: {
    total_keys: number
    expires: number
    avg_ttl?: number
  }
  hit_ratio: {
    hits: number
    misses: number
    hit_ratio: number
  }
  connected_clients: number
  uptime_seconds: number
}

export interface CacheKey {
  key: string
  type: string
  ttl: number
  size_bytes?: number
}

export interface ConnectorStatus {
  name: string
  enabled: boolean
  state: 'connected' | 'disconnected' | 'connecting' | 'failed' | 'disabled'
  endpoint?: string
  error?: string
  metrics?: Record<string, unknown>
}

export interface AllConnectorsStatus {
  timestamp: string
  connectors: ConnectorStatus[]
}

export interface AuditEntry {
  id: string
  timestamp: string
  user_id?: string
  user_email?: string
  action: string
  resource_type?: string
  resource_id?: string
  details?: Record<string, unknown>
  success: boolean
}

export interface ActiveSession {
  session_id: string
  user_id: string
  user_email?: string
  created_at: string
  last_activity: string
  ip_address?: string
  user_agent?: string
  expires_at?: string | null
}

export interface EventEntry {
  id: string
  timestamp: string
  event_type: string
  entity_type?: string
  identifier?: string
  data?: Record<string, unknown>
}

export interface LoggerInfo {
  name: string
  level: string
  effective_level: string
  handlers: string[]
}

export interface LogLevelResult {
  logger: string
  previous_level: string
  new_level: string
  timestamp: string
}

export interface ProfilingStats {
  timestamp: string
  cpu_percent?: number | null
  memory_percent?: number | null
  memory_mb?: number | null
  open_files?: number | null
  threads?: number | null
  async_tasks?: number | null
}

export interface MetricsSummary {
  timestamp: string
  http_requests_total?: number | null
  http_request_duration_p50?: number | null
  http_request_duration_p99?: number | null
  db_queries_total?: number | null
  cache_hits_total?: number | null
  cache_misses_total?: number | null
  error?: string
}

const parseResponse = async <T>(response: Response): Promise<T> => {
  const text = await response.text()
  if (!text) {
    return undefined as T
  }
  try {
    return JSON.parse(text) as T
  } catch {
    return text as T
  }
}

const extractErrorMessage = (data: unknown, fallback: string): string => {
  if (typeof data === 'string' && data.trim()) {
    return data
  }
  if (typeof data === 'object' && data !== null) {
    const record = data as Record<string, unknown>
    const detail = record.detail
    const message = record.message
    if (typeof detail === 'string') {
      return detail
    }
    if (typeof message === 'string') {
      return message
    }
  }
  return fallback
}

async function fetchApi<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers: buildHeaders(options?.headers),
  })

  const data = await parseResponse<T>(response)
  if (!response.ok) {
    const fallback = `${response.status} ${response.statusText}`.trim()
    throw new Error(extractErrorMessage(data, fallback))
  }

  return data
}

export const api = {
  // Overview
  getOverview: () => fetchApi<SystemOverview>('/overview'),

  // Database
  getDatabaseStats: () => fetchApi<DatabaseStats>('/database/stats'),
  getTableStats: () => fetchApi<TableStats[]>('/database/tables'),

  // Cache
  getCacheStats: () => fetchApi<CacheStats>('/cache/stats'),
  getCacheKeys: (pattern = 'titan:*', limit = 100) =>
    fetchApi<CacheKey[]>(`/cache/keys?pattern=${encodeURIComponent(pattern)}&limit=${limit}`),
  invalidateCache: (pattern: string) =>
    fetchApi<{ pattern: string; deleted_count: number; timestamp: string }>(`/cache/invalidate?pattern=${encodeURIComponent(pattern)}`, {
      method: 'DELETE',
    }),

  // Connectors
  getConnectorsStatus: () => fetchApi<AllConnectorsStatus>('/connectors/status'),
  connectOpcUa: () => fetchApi<{ success: boolean }>('/connectors/opcua/connect', { method: 'POST' }),
  disconnectOpcUa: () => fetchApi<{ success: boolean }>('/connectors/opcua/disconnect', { method: 'POST' }),
  connectModbus: () => fetchApi<{ success: boolean }>('/connectors/modbus/connect', { method: 'POST' }),
  disconnectModbus: () => fetchApi<{ success: boolean }>('/connectors/modbus/disconnect', { method: 'POST' }),
  connectMqtt: () => fetchApi<{ success: boolean }>('/connectors/mqtt/connect', { method: 'POST' }),
  disconnectMqtt: () => fetchApi<{ success: boolean }>('/connectors/mqtt/disconnect', { method: 'POST' }),

  // Security
  getAuditLog: (limit = 50, offset = 0) =>
    fetchApi<{ entries: AuditEntry[]; total: number }>(`/security/audit-log?limit=${limit}&offset=${offset}`),
  getSessions: () => fetchApi<{ sessions: ActiveSession[]; total: number }>('/security/sessions'),

  // Events
  getEventHistory: (limit = 50) =>
    fetchApi<EventEntry[]>(`/events/history?limit=${limit}`),

  // Observability
  getLoggers: () => fetchApi<LoggerInfo[]>('/observability/loggers'),
  setLogLevel: (logger: string, level: string) =>
    fetchApi<LogLevelResult>('/observability/log-level', {
      method: 'PUT',
      body: JSON.stringify({ logger, level }),
    }),
  getProfilingStats: () => fetchApi<ProfilingStats>('/observability/profiling'),
  getMetricsSummary: () => fetchApi<MetricsSummary>('/observability/metrics/summary'),
}

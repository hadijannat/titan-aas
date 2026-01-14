import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, LoggerInfo, ProfilingStats } from '../api/client'
import { ErrorState } from '../components/ErrorState'
import { StatCard } from '../components/StatCard'
import { Activity, Terminal, Cpu, MemoryStick, Gauge, RefreshCw } from 'lucide-react'

const LOG_LEVELS = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']

export default function ObservabilityPage() {
  const queryClient = useQueryClient()
  const [currentLogLevel, setCurrentLogLevel] = useState('INFO')
  const [currentLogger, setCurrentLogger] = useState<string>('titan')

  const {
    data: loggers,
    isLoading: loggersLoading,
    error: loggersError,
  } = useQuery<LoggerInfo[]>({
    queryKey: ['observability-loggers'],
    queryFn: api.getLoggers,
    refetchInterval: 30000,
  })

  const {
    data: profilingStats,
    isLoading: profilingLoading,
    error: profilingError,
  } = useQuery<ProfilingStats>({
    queryKey: ['observability-profiling'],
    queryFn: api.getProfilingStats,
    refetchInterval: 15000,
  })

  useEffect(() => {
    if (!loggers || loggers.length === 0) {
      return
    }
    const preferred = loggers.find((logger) => logger.name === 'titan') || loggers[0]
    setCurrentLogger(preferred.name)
    setCurrentLogLevel(preferred.effective_level)
  }, [loggers])

  const logLevelMutation = useMutation({
    mutationFn: (level: string) => api.setLogLevel(currentLogger, level),
    onSuccess: (result) => {
      setCurrentLogLevel(result.new_level)
      queryClient.invalidateQueries({ queryKey: ['observability-loggers'] })
    },
  })

  const handleLogLevelChange = (level: string) => {
    logLevelMutation.mutate(level)
  }

  const isUpdating = logLevelMutation.isPending

  const formatPercent = (value?: number | null) =>
    value === null || value === undefined ? '—' : `${value.toFixed(1)}%`

  const formatNumber = (value?: number | null, unit?: string) =>
    value === null || value === undefined ? '—' : `${value.toFixed(1)}${unit ?? ''}`

  const profilingAvailable = Boolean(
    profilingStats &&
      [
        profilingStats.cpu_percent,
        profilingStats.memory_percent,
        profilingStats.memory_mb,
        profilingStats.open_files,
        profilingStats.threads,
        profilingStats.async_tasks,
      ].some((value) => value !== null && value !== undefined)
  )

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-white">Observability</h1>
        <p className="text-slate-400 mt-1">Logging, tracing, and system profiling</p>
      </div>

      {/* Quick Stats */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          icon={Activity}
          label="Current Log Level"
          value={currentLogLevel}
          subtext={currentLogger}
        />
        <StatCard
          icon={Terminal}
          label="Active Loggers"
          value={loggersLoading ? 'Loading' : loggers?.length ?? 0}
          subtext="System-wide"
        />
        <StatCard icon={Cpu} label="Tracing" value="Enabled" subtext="OpenTelemetry" />
        <StatCard icon={Gauge} label="Metrics" value="Active" subtext="Prometheus" />
      </div>

      {/* Log Level Control */}
      <div className="bg-slate-800 rounded-lg border border-slate-700">
        <div className="p-4 border-b border-slate-700">
          <h2 className="text-lg font-semibold text-white">Runtime Log Level</h2>
          <p className="text-slate-400 text-sm mt-1">
            Adjust the logging verbosity at runtime without restarting the application
          </p>
        </div>
        <div className="p-6">
          {loggersError && (
            <div className="mb-4">
              <ErrorState
                message={
                  loggersError instanceof Error
                    ? loggersError.message
                    : 'Failed to load loggers'
                }
              />
            </div>
          )}
          <div className="flex flex-wrap gap-2">
            {LOG_LEVELS.map((level) => {
              const isActive = level === currentLogLevel
              const colors = {
                DEBUG: 'bg-slate-600 hover:bg-slate-500',
                INFO: 'bg-blue-600 hover:bg-blue-500',
                WARNING: 'bg-yellow-600 hover:bg-yellow-500',
                ERROR: 'bg-orange-600 hover:bg-orange-500',
                CRITICAL: 'bg-red-600 hover:bg-red-500',
              }
              const baseColor = colors[level as keyof typeof colors] || 'bg-slate-600'

              return (
                <button
                  key={level}
                  onClick={() => handleLogLevelChange(level)}
                  disabled={isUpdating || loggersLoading || !currentLogger}
                  className={`px-6 py-3 rounded-lg font-medium transition-all ${
                    isActive
                      ? `${baseColor} text-white ring-2 ring-white ring-offset-2 ring-offset-slate-800`
                      : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                  } disabled:opacity-50 disabled:cursor-not-allowed`}
                >
                  {isUpdating && level === currentLogLevel ? (
                    <RefreshCw className="w-4 h-4 animate-spin inline mr-2" />
                  ) : null}
                  {level}
                </button>
              )
            })}
          </div>
          {logLevelMutation.isError && (
            <div className="mt-4">
              <ErrorState
                message={
                  logLevelMutation.error instanceof Error
                    ? logLevelMutation.error.message
                    : 'Failed to update log level'
                }
              />
            </div>
          )}
          <p className="text-slate-500 text-sm mt-4">
            <strong>DEBUG:</strong> Verbose output for development •{' '}
            <strong>INFO:</strong> Standard operational messages •{' '}
            <strong>WARNING:</strong> Potential issues •{' '}
            <strong>ERROR:</strong> Failures •{' '}
            <strong>CRITICAL:</strong> System-level errors only
          </p>
          <p className="text-slate-500 text-xs mt-2">
            Target logger: <span className="text-slate-300">{currentLogger}</span>
          </p>
        </div>
      </div>

      {/* System Profiling */}
      <div className="bg-slate-800 rounded-lg border border-slate-700">
        <div className="p-4 border-b border-slate-700">
          <h2 className="text-lg font-semibold text-white">System Profile</h2>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 p-6">
          {/* CPU Usage */}
          <div>
            <div className="flex items-center gap-2 mb-4">
              <Cpu className="w-5 h-5 text-titan-500" />
              <h3 className="text-white font-medium">CPU</h3>
            </div>
            <div className="space-y-2">
              <div className="flex justify-between text-sm">
                <span className="text-slate-400">Usage</span>
                <span className="text-white">
                  {profilingLoading ? 'Loading' : formatPercent(profilingStats?.cpu_percent)}
                </span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-slate-400">Threads</span>
                <span className="text-white">
                  {profilingLoading
                    ? 'Loading'
                    : profilingStats?.threads ?? '—'}
                </span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-slate-400">Async Tasks</span>
                <span className="text-white">
                  {profilingLoading
                    ? 'Loading'
                    : profilingStats?.async_tasks ?? '—'}
                </span>
              </div>
            </div>
            <p className="text-slate-500 text-xs mt-2">
              CPU profiling available via /dashboard/observability/profiling
            </p>
          </div>

          {/* Memory Usage */}
          <div>
            <div className="flex items-center gap-2 mb-4">
              <MemoryStick className="w-5 h-5 text-titan-500" />
              <h3 className="text-white font-medium">Memory</h3>
            </div>
            <div className="space-y-2">
              <div className="flex justify-between text-sm">
                <span className="text-slate-400">Usage</span>
                <span className="text-white">
                  {profilingLoading ? 'Loading' : formatPercent(profilingStats?.memory_percent)}
                </span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-slate-400">RSS</span>
                <span className="text-white">
                  {profilingLoading ? 'Loading' : formatNumber(profilingStats?.memory_mb, ' MB')}
                </span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-slate-400">Open Files</span>
                <span className="text-white">
                  {profilingLoading
                    ? 'Loading'
                    : profilingStats?.open_files ?? '—'}
                </span>
              </div>
            </div>
            <p className="text-slate-500 text-xs mt-2">
              Memory details available via /dashboard/observability/profiling
            </p>
          </div>
        </div>
        {profilingError && (
          <div className="p-6 pt-0">
            <ErrorState
              message={
                profilingError instanceof Error
                  ? profilingError.message
                  : 'Profiling is unavailable'
              }
            />
          </div>
        )}
        {!profilingLoading && !profilingError && !profilingAvailable && (
          <div className="p-6 pt-0 text-slate-500 text-sm">
            Profiling data is not available. Install <code className="text-titan-400">psutil</code>{' '}
            or enable profiling in the runtime environment.
          </div>
        )}
      </div>

      {/* External Links */}
      <div className="bg-slate-800 rounded-lg border border-slate-700 p-6">
        <h2 className="text-lg font-semibold text-white mb-4">External Dashboards</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <a
            href="/metrics"
            target="_blank"
            rel="noopener noreferrer"
            className="bg-slate-700 hover:bg-slate-600 rounded-lg p-4 transition-colors group"
          >
            <div className="flex items-center gap-3">
              <Gauge className="w-6 h-6 text-titan-500 group-hover:text-titan-400" />
              <div>
                <p className="text-white font-medium">Prometheus Metrics</p>
                <p className="text-slate-400 text-sm">/metrics endpoint</p>
              </div>
            </div>
          </a>
          <a
            href="/docs"
            target="_blank"
            rel="noopener noreferrer"
            className="bg-slate-700 hover:bg-slate-600 rounded-lg p-4 transition-colors group"
          >
            <div className="flex items-center gap-3">
              <Terminal className="w-6 h-6 text-titan-500 group-hover:text-titan-400" />
              <div>
                <p className="text-white font-medium">API Documentation</p>
                <p className="text-slate-400 text-sm">OpenAPI / Swagger</p>
              </div>
            </div>
          </a>
          <a
            href="/graphql"
            target="_blank"
            rel="noopener noreferrer"
            className="bg-slate-700 hover:bg-slate-600 rounded-lg p-4 transition-colors group"
          >
            <div className="flex items-center gap-3">
              <Activity className="w-6 h-6 text-titan-500 group-hover:text-titan-400" />
              <div>
                <p className="text-white font-medium">GraphQL Playground</p>
                <p className="text-slate-400 text-sm">GraphiQL interface</p>
              </div>
            </div>
          </a>
        </div>
      </div>

      {/* Tracing Info */}
      <div className="bg-slate-800 rounded-lg border border-slate-700 p-6">
        <h2 className="text-lg font-semibold text-white mb-4">Distributed Tracing</h2>
        <p className="text-slate-400">
          Titan-AAS uses OpenTelemetry for distributed tracing. Configure your OTLP collector
          endpoint via the <code className="text-titan-400">OTLP_ENDPOINT</code> environment
          variable to export traces to Jaeger, Zipkin, or any OTLP-compatible backend.
        </p>
        <div className="mt-4 bg-slate-900 rounded-lg p-4">
          <pre className="text-slate-300 text-sm overflow-x-auto">
{`# Environment Variables for Tracing
ENABLE_TRACING=true
OTLP_ENDPOINT=http://localhost:4317
SERVICE_NAME=titan-aas`}
          </pre>
        </div>
      </div>
    </div>
  )
}

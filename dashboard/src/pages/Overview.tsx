import { useQuery } from '@tanstack/react-query'
import { api, SystemOverview } from '../api/client'
import { ErrorState } from '../components/ErrorState'
import { LoadingState } from '../components/LoadingState'
import { StatCard } from '../components/StatCard'
import {
  Activity,
  Database,
  CheckCircle,
  AlertCircle,
  XCircle,
  Clock,
  Server,
} from 'lucide-react'

function StatusIcon({ status }: { status: 'healthy' | 'degraded' | 'unhealthy' }) {
  switch (status) {
    case 'healthy':
      return <CheckCircle className="w-5 h-5 text-green-500" />
    case 'degraded':
      return <AlertCircle className="w-5 h-5 text-yellow-500" />
    case 'unhealthy':
      return <XCircle className="w-5 h-5 text-red-500" />
  }
}

function StatusBadge({ status }: { status: 'healthy' | 'degraded' | 'unhealthy' }) {
  const colors = {
    healthy: 'bg-green-500/20 text-green-400 border-green-500/30',
    degraded: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
    unhealthy: 'bg-red-500/20 text-red-400 border-red-500/30',
  }

  return (
    <span className={`px-3 py-1 rounded-full text-sm font-medium border ${colors[status]}`}>
      {status.charAt(0).toUpperCase() + status.slice(1)}
    </span>
  )
}

function formatUptime(seconds: number): string {
  const days = Math.floor(seconds / 86400)
  const hours = Math.floor((seconds % 86400) / 3600)
  const mins = Math.floor((seconds % 3600) / 60)

  if (days > 0) return `${days}d ${hours}h ${mins}m`
  if (hours > 0) return `${hours}h ${mins}m`
  return `${mins}m`
}

export default function Overview() {
  const { data, isLoading, error } = useQuery<SystemOverview>({
    queryKey: ['overview'],
    queryFn: api.getOverview,
    refetchInterval: 10000, // Refresh every 10 seconds
  })

  if (isLoading) {
    return <LoadingState />
  }

  if (error) {
    return <ErrorState message="Failed to load system overview" />
  }

  if (!data) return null

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">System Overview</h1>
          <p className="text-slate-400 mt-1">Real-time health and status monitoring</p>
        </div>
        <StatusBadge status={data.status} />
      </div>

      {/* System Info Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard icon={Server} label="Version" value={data.version} />
        <StatCard
          icon={Activity}
          label="Environment"
          value={<span className="capitalize">{data.environment}</span>}
        />
        <StatCard
          icon={Clock}
          label="Uptime"
          value={formatUptime(data.uptime_seconds)}
        />
        <StatCard
          icon={Database}
          label="Total Entities"
          value={
            data.entity_counts.aas +
            data.entity_counts.submodels +
            data.entity_counts.concept_descriptions
          }
        />
      </div>

      {/* Entity Counts */}
      <div className="bg-slate-800 rounded-lg border border-slate-700">
        <div className="p-4 border-b border-slate-700">
          <h2 className="text-lg font-semibold text-white">Entity Counts</h2>
        </div>
        <div className="grid grid-cols-3 divide-x divide-slate-700">
          <div className="p-6 text-center">
            <p className="text-3xl font-bold text-titan-500">{data.entity_counts.aas}</p>
            <p className="text-slate-400 mt-1">Asset Administration Shells</p>
          </div>
          <div className="p-6 text-center">
            <p className="text-3xl font-bold text-titan-500">{data.entity_counts.submodels}</p>
            <p className="text-slate-400 mt-1">Submodels</p>
          </div>
          <div className="p-6 text-center">
            <p className="text-3xl font-bold text-titan-500">{data.entity_counts.concept_descriptions}</p>
            <p className="text-slate-400 mt-1">Concept Descriptions</p>
          </div>
        </div>
      </div>

      {/* Component Health */}
      <div className="bg-slate-800 rounded-lg border border-slate-700">
        <div className="p-4 border-b border-slate-700">
          <h2 className="text-lg font-semibold text-white">Component Health</h2>
        </div>
        <div className="divide-y divide-slate-700">
          {data.components.map((component) => (
            <div key={component.name} className="p-4 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <StatusIcon status={component.status} />
                <div>
                  <p className="text-white font-medium">{component.name}</p>
                  {component.message && (
                    <p className="text-slate-400 text-sm">{component.message}</p>
                  )}
                </div>
              </div>
              <StatusBadge status={component.status} />
            </div>
          ))}
        </div>
      </div>

      {/* Last Updated */}
      <p className="text-slate-500 text-sm text-center">
        Last updated: {new Date(data.timestamp).toLocaleString()}
      </p>
    </div>
  )
}

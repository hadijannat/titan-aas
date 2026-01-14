import { useQuery } from '@tanstack/react-query'
import { api, DatabaseStats, TableStats } from '../api/client'
import { ErrorState } from '../components/ErrorState'
import { LoadingState } from '../components/LoadingState'
import { StatCard } from '../components/StatCard'
import { Database, HardDrive, Users, Table } from 'lucide-react'

function ProgressBar({ value, max, color = 'titan' }: { value: number; max: number; color?: string }) {
  const percentage = max > 0 ? (value / max) * 100 : 0
  const colorClass = color === 'titan' ? 'bg-titan-500' : `bg-${color}-500`

  return (
    <div className="w-full bg-slate-700 rounded-full h-2">
      <div
        className={`${colorClass} h-2 rounded-full transition-all duration-300`}
        style={{ width: `${Math.min(percentage, 100)}%` }}
      />
    </div>
  )
}

export default function DatabasePage() {
  const { data: stats, isLoading: statsLoading, error: statsError } = useQuery<DatabaseStats>({
    queryKey: ['database-stats'],
    queryFn: api.getDatabaseStats,
    refetchInterval: 15000,
  })

  const { data: tables, isLoading: tablesLoading, error: tablesError } = useQuery<TableStats[]>({
    queryKey: ['table-stats'],
    queryFn: api.getTableStats,
    refetchInterval: 30000,
  })

  if (statsLoading) {
    return <LoadingState />
  }

  if (statsError) {
    return <ErrorState message="Failed to load database statistics" />
  }

  const pool = stats?.pool
  const overflow = pool ? Math.max(pool.overflow, 0) : 0
  const totalConnections = pool ? pool.pool_size + overflow : 0
  const activeConnections = pool ? pool.checked_out : 0

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-white">Database</h1>
        <p className="text-slate-400 mt-1">PostgreSQL connection pool and table statistics</p>
      </div>

      {/* Connection Pool Stats */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          icon={Database}
          label="Pool Size"
          value={pool?.pool_size ?? 0}
          subtext="Configured connections"
        />
        <StatCard
          icon={Users}
          label="Active Connections"
          value={pool?.checked_out ?? 0}
          subtext={`of ${totalConnections} total`}
        />
        <StatCard
          icon={HardDrive}
          label="Available"
          value={pool?.checked_in ?? 0}
          subtext="Idle connections"
        />
        <StatCard
          icon={Table}
          label="Overflow"
          value={overflow}
          subtext="Extra connections"
        />
      </div>

      {/* Connection Pool Gauge */}
      <div className="bg-slate-800 rounded-lg border border-slate-700 p-6">
        <h2 className="text-lg font-semibold text-white mb-4">Connection Pool Utilization</h2>
        <div className="space-y-4">
          <div>
            <div className="flex justify-between text-sm mb-2">
              <span className="text-slate-400">Active Connections</span>
              <span className="text-white">
                {activeConnections} / {totalConnections}
              </span>
            </div>
            <ProgressBar value={activeConnections} max={totalConnections} />
          </div>
          <div className="grid grid-cols-3 gap-4 text-center pt-4 border-t border-slate-700">
            <div>
              <p className="text-2xl font-bold text-green-500">{pool?.checked_in ?? 0}</p>
              <p className="text-slate-400 text-sm">Idle</p>
            </div>
            <div>
              <p className="text-2xl font-bold text-yellow-500">{pool?.checked_out ?? 0}</p>
              <p className="text-slate-400 text-sm">In Use</p>
            </div>
            <div>
              <p className="text-2xl font-bold text-red-500">{overflow}</p>
              <p className="text-slate-400 text-sm">Overflow</p>
            </div>
          </div>
        </div>
      </div>

      {/* Table Statistics */}
      <div className="bg-slate-800 rounded-lg border border-slate-700">
        <div className="p-4 border-b border-slate-700">
          <h2 className="text-lg font-semibold text-white">Table Statistics</h2>
        </div>
        {tablesLoading ? (
          <div className="p-8 text-center">
            <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-titan-500 mx-auto"></div>
          </div>
        ) : tablesError ? (
          <div className="p-8 text-center text-red-400">
            {tablesError instanceof Error ? tablesError.message : 'Failed to load table stats'}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-slate-700">
                  <th className="text-left p-4 text-slate-400 font-medium">Table Name</th>
                  <th className="text-right p-4 text-slate-400 font-medium">Row Count</th>
                  <th className="text-right p-4 text-slate-400 font-medium">Size</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-700">
                {tables?.map((table) => (
                  <tr key={table.name} className="hover:bg-slate-700/50">
                    <td className="p-4 text-white font-mono text-sm">{table.name}</td>
                    <td className="p-4 text-right text-white">
                      {table.row_count.toLocaleString()}
                    </td>
                    <td className="p-4 text-right text-slate-400">
                      {table.estimated_size || 'N/A'}
                    </td>
                  </tr>
                ))}
                {(!tables || tables.length === 0) && (
                  <tr>
                    <td colSpan={3} className="p-8 text-center text-slate-400">
                      No tables found
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Last Updated */}
      {stats && (
        <p className="text-slate-500 text-sm text-center">
          Last updated: {new Date(stats.timestamp).toLocaleString()}
        </p>
      )}
    </div>
  )
}

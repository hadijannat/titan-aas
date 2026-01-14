import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api, CacheStats, CacheKey } from '../api/client'
import { ErrorState } from '../components/ErrorState'
import { LoadingState } from '../components/LoadingState'
import { StatCard } from '../components/StatCard'
import {
  HardDrive,
  Zap,
  Clock,
  Users,
  Search,
  Trash2,
  RefreshCw,
  AlertCircle,
} from 'lucide-react'

function HitRatioGauge({ ratio }: { ratio: number }) {
  const percentage = ratio * 100
  const color =
    percentage >= 90 ? 'text-green-500' : percentage >= 70 ? 'text-yellow-500' : 'text-red-500'

  return (
    <div className="relative w-32 h-32">
      <svg className="w-full h-full transform -rotate-90">
        <circle
          cx="64"
          cy="64"
          r="56"
          stroke="currentColor"
          strokeWidth="12"
          fill="none"
          className="text-slate-700"
        />
        <circle
          cx="64"
          cy="64"
          r="56"
          stroke="currentColor"
          strokeWidth="12"
          fill="none"
          strokeDasharray={`${percentage * 3.52} 352`}
          className={color}
          strokeLinecap="round"
        />
      </svg>
      <div className="absolute inset-0 flex items-center justify-center">
        <span className={`text-2xl font-bold ${color}`}>{percentage.toFixed(1)}%</span>
      </div>
    </div>
  )
}

export default function CachePage() {
  const [searchPattern, setSearchPattern] = useState('titan:*')
  const [invalidatePattern, setInvalidatePattern] = useState('')
  const queryClient = useQueryClient()

  const { data: stats, isLoading: statsLoading, error: statsError } = useQuery<CacheStats>({
    queryKey: ['cache-stats'],
    queryFn: api.getCacheStats,
    refetchInterval: 10000,
  })

  const normalizedSearchPattern = searchPattern.trim()
  const isSearchPatternValid =
    normalizedSearchPattern.length > 0 && normalizedSearchPattern.startsWith('titan:')

  const {
    data: keys,
    isLoading: keysLoading,
    error: keysError,
    refetch: refetchKeys,
  } = useQuery<CacheKey[]>({
    queryKey: ['cache-keys', normalizedSearchPattern],
    queryFn: () => api.getCacheKeys(normalizedSearchPattern, 100),
    enabled: isSearchPatternValid,
  })

  const invalidateMutation = useMutation({
    mutationFn: (pattern: string) => api.invalidateCache(pattern),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['cache-stats'] })
      queryClient.invalidateQueries({ queryKey: ['cache-keys'] })
      setInvalidatePattern('')
    },
  })

  if (statsLoading) {
    return <LoadingState />
  }

  if (statsError) {
    return <ErrorState message="Failed to load cache statistics" />
  }

  const normalizedInvalidatePattern = invalidatePattern.trim()
  const isInvalidatePatternValid =
    normalizedInvalidatePattern.length > 0 && normalizedInvalidatePattern.startsWith('titan:')

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-white">Cache</h1>
        <p className="text-slate-400 mt-1">Redis cache statistics and key management</p>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          icon={HardDrive}
          label="Memory Used"
          value={stats?.memory.used_memory ?? '0'}
          subtext={`Peak: ${stats?.memory.used_memory_peak ?? '0'}`}
        />
        <StatCard
          icon={Zap}
          label="Total Keys"
          value={stats?.keyspace.total_keys.toLocaleString() ?? 0}
          subtext={`${stats?.keyspace.expires ?? 0} with TTL`}
        />
        <StatCard
          icon={Users}
          label="Connected Clients"
          value={stats?.connected_clients ?? 0}
        />
        <StatCard
          icon={Clock}
          label="Uptime"
          value={`${Math.floor((stats?.uptime_seconds ?? 0) / 3600)}h`}
          subtext={`${stats?.uptime_seconds?.toLocaleString() ?? 0}s total`}
        />
      </div>

      {/* Hit/Miss Stats */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Hit Ratio Gauge */}
        <div className="bg-slate-800 rounded-lg border border-slate-700 p-6">
          <h2 className="text-lg font-semibold text-white mb-4">Cache Hit Ratio</h2>
          <div className="flex items-center justify-center gap-8">
            <HitRatioGauge ratio={stats?.hit_ratio.hit_ratio ?? 0} />
            <div className="space-y-4">
              <div>
                <p className="text-slate-400 text-sm">Hits</p>
                <p className="text-2xl font-bold text-green-500">
                  {stats?.hit_ratio.hits.toLocaleString() ?? 0}
                </p>
              </div>
              <div>
                <p className="text-slate-400 text-sm">Misses</p>
                <p className="text-2xl font-bold text-red-500">
                  {stats?.hit_ratio.misses.toLocaleString() ?? 0}
                </p>
              </div>
            </div>
          </div>
        </div>

        {/* Cache Invalidation */}
        <div className="bg-slate-800 rounded-lg border border-slate-700 p-6">
          <h2 className="text-lg font-semibold text-white mb-4">Cache Invalidation</h2>
          <div className="space-y-4">
            <div>
              <label className="block text-slate-400 text-sm mb-2">Pattern to invalidate</label>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={invalidatePattern}
                  onChange={(e) => setInvalidatePattern(e.target.value)}
                  placeholder="titan:aas:*"
                  className="flex-1 bg-slate-700 border border-slate-600 rounded-lg px-4 py-2 text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-titan-500"
                />
                <button
                  onClick={() => invalidateMutation.mutate(normalizedInvalidatePattern)}
                  disabled={!isInvalidatePatternValid || invalidateMutation.isPending}
                  className="px-4 py-2 bg-red-600 hover:bg-red-700 disabled:bg-slate-600 disabled:cursor-not-allowed text-white rounded-lg flex items-center gap-2 transition-colors"
                >
                  <Trash2 className="w-4 h-4" />
                  Invalidate
                </button>
              </div>
            </div>
            {invalidateMutation.isSuccess && (
              <div className="bg-green-500/10 border border-green-500/30 rounded-lg p-3">
                <p className="text-green-400 text-sm">
                  Deleted {invalidateMutation.data?.deleted_count ?? 0} keys matching pattern
                </p>
              </div>
            )}
            {invalidateMutation.isError && (
              <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-3 flex items-center gap-2">
                <AlertCircle className="w-4 h-4 text-red-400" />
                <p className="text-red-400 text-sm">
                  {invalidateMutation.error instanceof Error
                    ? invalidateMutation.error.message
                    : 'Failed to invalidate cache'}
                </p>
              </div>
            )}
            {!isInvalidatePatternValid && normalizedInvalidatePattern && (
              <div className="bg-yellow-500/10 border border-yellow-500/30 rounded-lg p-3 flex items-center gap-2">
                <AlertCircle className="w-4 h-4 text-yellow-400" />
                <p className="text-yellow-400 text-sm">
                  Pattern must start with <code className="text-yellow-300">titan:</code>
                </p>
              </div>
            )}
            <p className="text-slate-500 text-sm">
              Use patterns like <code className="text-titan-400">titan:*</code> or{' '}
              <code className="text-titan-400">titan:aas:*</code>
            </p>
          </div>
        </div>
      </div>

      {/* Key Browser */}
      <div className="bg-slate-800 rounded-lg border border-slate-700">
        <div className="p-4 border-b border-slate-700 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-white">Key Browser</h2>
          <button
            onClick={() => {
              if (isSearchPatternValid) {
                refetchKeys()
              }
            }}
            disabled={!isSearchPatternValid}
            className="p-2 hover:bg-slate-700 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <RefreshCw className="w-4 h-4 text-slate-400" />
          </button>
        </div>
        <div className="p-4 border-b border-slate-700">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <input
              type="text"
              value={searchPattern}
              onChange={(e) => setSearchPattern(e.target.value)}
              placeholder="Search pattern (e.g., titan:*)"
              className="w-full bg-slate-700 border border-slate-600 rounded-lg pl-10 pr-4 py-2 text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-titan-500"
            />
          </div>
        </div>
        {!isSearchPatternValid && normalizedSearchPattern && (
          <div className="p-4 border-b border-slate-700 text-yellow-400 text-sm flex items-center gap-2">
            <AlertCircle className="w-4 h-4" />
            Pattern must start with <code className="text-yellow-300">titan:</code>
          </div>
        )}
        {keysLoading ? (
          <div className="p-8 text-center">
            <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-titan-500 mx-auto"></div>
          </div>
        ) : keysError ? (
          <div className="p-8 text-center text-red-400">
            {keysError instanceof Error ? keysError.message : 'Failed to load keys'}
          </div>
        ) : (
          <div className="overflow-x-auto max-h-96">
            <table className="w-full">
              <thead className="sticky top-0 bg-slate-800">
                <tr className="border-b border-slate-700">
                  <th className="text-left p-4 text-slate-400 font-medium">Key</th>
                  <th className="text-left p-4 text-slate-400 font-medium">Type</th>
                  <th className="text-right p-4 text-slate-400 font-medium">TTL</th>
                  <th className="text-right p-4 text-slate-400 font-medium">Size</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-700">
                {keys?.map((key) => (
                  <tr key={key.key} className="hover:bg-slate-700/50">
                    <td className="p-4 text-white font-mono text-sm truncate max-w-md">
                      {key.key}
                    </td>
                    <td className="p-4 text-slate-400">{key.type}</td>
                    <td className="p-4 text-right text-slate-400">
                      {key.ttl === -1 ? 'No expiry' : `${key.ttl}s`}
                    </td>
                    <td className="p-4 text-right text-slate-400">
                      {key.size_bytes ? `${key.size_bytes} B` : 'N/A'}
                    </td>
                  </tr>
                ))}
                {(!keys || keys.length === 0) && (
                  <tr>
                    <td colSpan={4} className="p-8 text-center text-slate-400">
                      No keys found matching pattern
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

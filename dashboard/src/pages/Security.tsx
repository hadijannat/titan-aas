import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ActiveSession, api } from '../api/client'
import { ErrorState } from '../components/ErrorState'
import { LoadingState } from '../components/LoadingState'
import { StatCard } from '../components/StatCard'
import {
  Shield,
  Search,
  Clock,
  User,
  CheckCircle,
  XCircle,
  ChevronLeft,
  ChevronRight,
  FileText,
} from 'lucide-react'

function ActionBadge({ action }: { action: string }) {
  const getColor = () => {
    if (action.includes('CREATE')) return 'bg-green-500/20 text-green-400 border-green-500/30'
    if (action.includes('DELETE')) return 'bg-red-500/20 text-red-400 border-red-500/30'
    if (action.includes('UPDATE')) return 'bg-blue-500/20 text-blue-400 border-blue-500/30'
    if (action.includes('LOGIN') || action.includes('AUTH'))
      return 'bg-purple-500/20 text-purple-400 border-purple-500/30'
    return 'bg-slate-500/20 text-slate-400 border-slate-500/30'
  }

  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium border ${getColor()}`}>
      {action}
    </span>
  )
}

function SuccessBadge({ success }: { success: boolean }) {
  return success ? (
    <span className="flex items-center gap-1 text-green-400 text-sm">
      <CheckCircle className="w-4 h-4" />
      Success
    </span>
  ) : (
    <span className="flex items-center gap-1 text-red-400 text-sm">
      <XCircle className="w-4 h-4" />
      Failed
    </span>
  )
}

export default function SecurityPage() {
  const [searchQuery, setSearchQuery] = useState('')
  const [page, setPage] = useState(0)
  const limit = 20

  const {
    data: auditData,
    isLoading: auditLoading,
    error: auditError,
  } = useQuery({
    queryKey: ['audit-log', page],
    queryFn: () => api.getAuditLog(limit, page * limit),
    refetchInterval: 30000,
  })

  const {
    data: sessionsData,
    isLoading: sessionsLoading,
    error: sessionsError,
  } = useQuery({
    queryKey: ['sessions'],
    queryFn: api.getSessions,
    refetchInterval: 30000,
  })

  const filteredEntries = auditData?.entries?.filter(
    (entry) =>
      !searchQuery ||
      entry.action.toLowerCase().includes(searchQuery.toLowerCase()) ||
      entry.user_email?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      entry.resource_type?.toLowerCase().includes(searchQuery.toLowerCase())
  )

  const totalPages = Math.ceil((auditData?.total || 0) / limit)

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-white">Security</h1>
        <p className="text-slate-400 mt-1">Audit log and session management</p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <StatCard icon={Shield} label="Total Audit Entries" value={auditData?.total?.toLocaleString() || 0} />
        <StatCard icon={User} label="Active Sessions" value={sessionsData?.total || 0} />
        <StatCard icon={FileText} label="Page" value={`${page + 1} of ${totalPages || 1}`} />
      </div>

      {/* Audit Log */}
      <div className="bg-slate-800 rounded-lg border border-slate-700">
        <div className="p-4 border-b border-slate-700">
          <h2 className="text-lg font-semibold text-white mb-4">Audit Log</h2>
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search by action, user, or resource..."
              className="w-full bg-slate-700 border border-slate-600 rounded-lg pl-10 pr-4 py-2 text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-titan-500"
            />
          </div>
        </div>

        {auditLoading ? (
          <LoadingState heightClassName="h-40" />
        ) : auditError ? (
          <div className="p-4">
            <ErrorState
              message={auditError instanceof Error ? auditError.message : 'Failed to load audit log'}
            />
          </div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-slate-700">
                    <th className="text-left p-4 text-slate-400 font-medium">Timestamp</th>
                    <th className="text-left p-4 text-slate-400 font-medium">User</th>
                    <th className="text-left p-4 text-slate-400 font-medium">Action</th>
                    <th className="text-left p-4 text-slate-400 font-medium">Resource</th>
                    <th className="text-left p-4 text-slate-400 font-medium">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-700">
                  {filteredEntries?.map((entry) => (
                    <tr key={entry.id} className="hover:bg-slate-700/50">
                      <td className="p-4 text-slate-300 text-sm whitespace-nowrap">
                        <div className="flex items-center gap-1">
                          <Clock className="w-3 h-3 text-slate-500" />
                          {new Date(entry.timestamp).toLocaleString()}
                        </div>
                      </td>
                      <td className="p-4 text-white">
                        {entry.user_email || (
                          <span className="text-slate-500 italic">Anonymous</span>
                        )}
                      </td>
                      <td className="p-4">
                        <ActionBadge action={entry.action} />
                      </td>
                      <td className="p-4 text-slate-300">
                        {entry.resource_type && (
                          <span className="font-mono text-sm">
                            {entry.resource_type}
                            {entry.resource_id && `:${entry.resource_id.slice(0, 20)}...`}
                          </span>
                        )}
                        {!entry.resource_type && (
                          <span className="text-slate-500 italic">—</span>
                        )}
                      </td>
                      <td className="p-4">
                        <SuccessBadge success={entry.success} />
                      </td>
                    </tr>
                  ))}
                  {(!filteredEntries || filteredEntries.length === 0) && (
                    <tr>
                      <td colSpan={5} className="p-8 text-center text-slate-400">
                        No audit entries found
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            <div className="p-4 border-t border-slate-700 flex items-center justify-between">
              <p className="text-slate-400 text-sm">
                Showing {page * limit + 1} to{' '}
                {Math.min((page + 1) * limit, auditData?.total || 0)} of{' '}
                {auditData?.total || 0} entries
              </p>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setPage(Math.max(0, page - 1))}
                  disabled={page === 0}
                  className="p-2 hover:bg-slate-700 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg transition-colors"
                >
                  <ChevronLeft className="w-5 h-5 text-slate-400" />
                </button>
                <span className="text-white px-3">
                  {page + 1} / {totalPages || 1}
                </span>
                <button
                  onClick={() => setPage(Math.min(totalPages - 1, page + 1))}
                  disabled={page >= totalPages - 1}
                  className="p-2 hover:bg-slate-700 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg transition-colors"
                >
                  <ChevronRight className="w-5 h-5 text-slate-400" />
                </button>
              </div>
            </div>
          </>
        )}
      </div>

      {/* Active Sessions */}
      <div className="bg-slate-800 rounded-lg border border-slate-700">
        <div className="p-4 border-b border-slate-700">
          <h2 className="text-lg font-semibold text-white">Active Sessions</h2>
        </div>
        {sessionsLoading ? (
          <LoadingState heightClassName="h-32" />
        ) : sessionsError ? (
          <div className="p-4">
            <ErrorState
              message={
                sessionsError instanceof Error ? sessionsError.message : 'Failed to load sessions'
              }
            />
          </div>
        ) : (
          <div className="p-4">
            {sessionsData?.sessions && sessionsData.sessions.length > 0 ? (
              <div className="space-y-2">
                {sessionsData.sessions.map((session: ActiveSession) => (
                  <div
                    key={session.session_id}
                    className="bg-slate-700/50 rounded-lg p-3 flex flex-col gap-2 md:flex-row md:items-center md:justify-between"
                  >
                    <div className="flex items-center gap-3">
                      <User className="w-5 h-5 text-titan-500" />
                      <div>
                        <p className="text-white text-sm">
                          {session.user_email || session.user_id}
                        </p>
                        <p className="text-slate-400 text-xs font-mono">
                          {session.session_id}
                        </p>
                      </div>
                    </div>
                    <div className="text-slate-400 text-xs space-y-1">
                      <p>Last activity: {new Date(session.last_activity).toLocaleString()}</p>
                      <p>Created: {new Date(session.created_at).toLocaleString()}</p>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-slate-400 text-center py-4">No active sessions</p>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

import { useState, useEffect, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api, EventEntry } from '../api/client'
import { ErrorState } from '../components/ErrorState'
import { LoadingState } from '../components/LoadingState'
import { Zap, Play, Pause, Trash2, Clock, Filter } from 'lucide-react'

const EVENT_TYPE_COLORS: Record<string, string> = {
  CREATED: 'bg-green-500/20 text-green-400 border-green-500/30',
  UPDATED: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
  DELETED: 'bg-red-500/20 text-red-400 border-red-500/30',
  default: 'bg-slate-500/20 text-slate-400 border-slate-500/30',
}

function EventTypeBadge({ type }: { type: string }) {
  const color = EVENT_TYPE_COLORS[type] || EVENT_TYPE_COLORS.default
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium border ${color}`}>
      {type}
    </span>
  )
}

function EntityTypeBadge({ type }: { type?: string }) {
  if (!type) return null
  return (
    <span className="px-2 py-0.5 rounded text-xs font-medium bg-titan-500/20 text-titan-400 border border-titan-500/30">
      {type}
    </span>
  )
}

export default function EventsPage() {
  const [isStreaming, setIsStreaming] = useState(false)
  const [liveEvents, setLiveEvents] = useState<EventEntry[]>([])
  const [filter, setFilter] = useState('')
  const [streamError, setStreamError] = useState<string | null>(null)
  const eventSourceRef = useRef<EventSource | null>(null)

  // Historical events
  const { data: historyEvents, isLoading, error } = useQuery<EventEntry[]>({
    queryKey: ['event-history'],
    queryFn: () => api.getEventHistory(100),
    refetchInterval: isStreaming ? false : 30000,
  })

  // SSE streaming
  useEffect(() => {
    if (isStreaming) {
      const eventSource = new EventSource('/dashboard/events/stream')
      eventSourceRef.current = eventSource
      setStreamError(null)

      eventSource.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          setLiveEvents((prev) => [data, ...prev].slice(0, 200))
        } catch (e) {
          console.error('Failed to parse event:', e)
        }
      }

      eventSource.onerror = () => {
        console.error('SSE connection error')
        setStreamError('Streaming connection lost')
        setIsStreaming(false)
      }

      return () => {
        eventSource.close()
      }
    } else {
      if (eventSourceRef.current) {
        eventSourceRef.current.close()
        eventSourceRef.current = null
      }
    }
  }, [isStreaming])

  const allEvents = isStreaming ? liveEvents : historyEvents || []
  const filteredEvents = filter
    ? allEvents.filter(
        (e) =>
          e.event_type.toLowerCase().includes(filter.toLowerCase()) ||
          e.entity_type?.toLowerCase().includes(filter.toLowerCase()) ||
          e.identifier?.toLowerCase().includes(filter.toLowerCase())
      )
    : allEvents

  const clearLiveEvents = () => {
    setLiveEvents([])
  }

  if (isLoading && !isStreaming) {
    return <LoadingState />
  }

  if (error && !isStreaming) {
    return (
      <ErrorState
        message={error instanceof Error ? error.message : 'Failed to load events'}
      />
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Events</h1>
          <p className="text-slate-400 mt-1">
            {isStreaming ? 'Live event stream' : 'Event history'}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {isStreaming && (
            <button
              onClick={clearLiveEvents}
              className="px-3 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded-lg flex items-center gap-2 transition-colors"
            >
              <Trash2 className="w-4 h-4" />
              Clear
            </button>
          )}
          <button
            onClick={() => setIsStreaming(!isStreaming)}
            className={`px-4 py-2 rounded-lg flex items-center gap-2 transition-colors ${
              isStreaming
                ? 'bg-red-600 hover:bg-red-700 text-white'
                : 'bg-green-600 hover:bg-green-700 text-white'
            }`}
          >
            {isStreaming ? (
              <>
                <Pause className="w-4 h-4" />
                Stop Stream
              </>
            ) : (
              <>
                <Play className="w-4 h-4" />
                Start Stream
              </>
            )}
          </button>
        </div>
      </div>

      {/* Status Bar */}
      {isStreaming && (
        <div className="bg-green-500/10 border border-green-500/30 rounded-lg p-3 flex items-center gap-2">
          <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse" />
          <span className="text-green-400 text-sm">
            Streaming live events... ({liveEvents.length} received)
          </span>
        </div>
      )}
      {!isStreaming && streamError && (
        <ErrorState message={streamError} />
      )}

      {/* Filter */}
      <div className="relative">
        <Filter className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
        <input
          type="text"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Filter by event type, entity type, or identifier..."
          className="w-full bg-slate-800 border border-slate-700 rounded-lg pl-10 pr-4 py-2 text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-titan-500"
        />
      </div>

      {/* Events List */}
      <div className="bg-slate-800 rounded-lg border border-slate-700 overflow-hidden">
        <div className="p-4 border-b border-slate-700 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-white flex items-center gap-2">
            <Zap className="w-5 h-5 text-titan-500" />
            {isStreaming ? 'Live Events' : 'Recent Events'}
          </h2>
          <span className="text-slate-400 text-sm">
            {filteredEvents.length} events
          </span>
        </div>
        <div className="max-h-[600px] overflow-y-auto">
          {filteredEvents.length === 0 ? (
            <div className="p-8 text-center text-slate-400">
              {isStreaming ? 'Waiting for events...' : 'No events found'}
            </div>
          ) : (
            <div className="divide-y divide-slate-700">
              {filteredEvents.map((event) => (
                <div
                  key={event.id}
                  className="p-4 hover:bg-slate-700/50 transition-colors"
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-2">
                        <EventTypeBadge type={event.event_type} />
                        <EntityTypeBadge type={event.entity_type} />
                      </div>
                      {event.identifier && (
                        <p className="text-white font-mono text-sm truncate">
                          {event.identifier}
                        </p>
                      )}
                      {event.data && (
                        <details className="mt-2">
                          <summary className="text-slate-400 text-sm cursor-pointer hover:text-white">
                            View payload
                          </summary>
                          <pre className="mt-2 p-2 bg-slate-900 rounded text-xs text-slate-300 overflow-x-auto">
                            {JSON.stringify(event.data, null, 2)}
                          </pre>
                        </details>
                      )}
                    </div>
                    <div className="flex items-center gap-1 text-slate-500 text-sm whitespace-nowrap">
                      <Clock className="w-3 h-3" />
                      {new Date(event.timestamp).toLocaleTimeString()}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Event Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {['CREATED', 'UPDATED', 'DELETED'].map((type) => {
          const count = allEvents.filter((e) => e.event_type === type).length
          return (
            <div
              key={type}
              className="bg-slate-800 rounded-lg border border-slate-700 p-4 text-center"
            >
              <p className="text-2xl font-bold text-white">{count}</p>
              <EventTypeBadge type={type} />
            </div>
          )
        })}
        <div className="bg-slate-800 rounded-lg border border-slate-700 p-4 text-center">
          <p className="text-2xl font-bold text-white">{allEvents.length}</p>
          <p className="text-slate-400 text-sm">Total</p>
        </div>
      </div>
    </div>
  )
}

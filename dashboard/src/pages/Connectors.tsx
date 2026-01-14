import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api, AllConnectorsStatus, ConnectorStatus } from '../api/client'
import { ErrorState } from '../components/ErrorState'
import { LoadingState } from '../components/LoadingState'
import { StatCard } from '../components/StatCard'
import {
  Radio,
  Wifi,
  WifiOff,
  Power,
  PowerOff,
  RefreshCw,
  AlertCircle,
  CheckCircle,
  Loader2,
  Server,
} from 'lucide-react'

const STATE_CONFIG = {
  connected: {
    color: 'bg-green-500/20 text-green-400 border-green-500/30',
    icon: CheckCircle,
    iconColor: 'text-green-500',
  },
  disconnected: {
    color: 'bg-slate-500/20 text-slate-400 border-slate-500/30',
    icon: WifiOff,
    iconColor: 'text-slate-500',
  },
  connecting: {
    color: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
    icon: Loader2,
    iconColor: 'text-yellow-500',
  },
  failed: {
    color: 'bg-red-500/20 text-red-400 border-red-500/30',
    icon: AlertCircle,
    iconColor: 'text-red-500',
  },
  disabled: {
    color: 'bg-slate-700/50 text-slate-500 border-slate-600/30',
    icon: PowerOff,
    iconColor: 'text-slate-600',
  },
}

const ENABLE_HINTS: Record<string, string> = {
  'opcua': 'OPCUA_ENABLED=true',
  'modbus': 'MODBUS_ENABLED=true',
  'mqtt': 'MQTT_BROKER=broker.local',
}

const getEnableHint = (name: string) => {
  const key = name.toLowerCase()
  const match = Object.keys(ENABLE_HINTS).find((hint) => key.includes(hint))
  return match ? ENABLE_HINTS[match] : null
}

function ConnectorCard({ connector }: { connector: ConnectorStatus }) {
  const queryClient = useQueryClient()
  const config = STATE_CONFIG[connector.state] || STATE_CONFIG.disconnected
  const StatusIcon = config.icon

  const connectMutation = useMutation({
    mutationFn: () => {
      if (connector.name.toLowerCase().includes('opcua')) {
        return api.connectOpcUa()
      } else if (connector.name.toLowerCase().includes('modbus')) {
        return api.connectModbus()
      } else if (connector.name.toLowerCase().includes('mqtt')) {
        return api.connectMqtt()
      }
      return Promise.reject(new Error('Unknown connector type'))
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['connectors-status'] })
    },
  })

  const disconnectMutation = useMutation({
    mutationFn: () => {
      if (connector.name.toLowerCase().includes('opcua')) {
        return api.disconnectOpcUa()
      } else if (connector.name.toLowerCase().includes('modbus')) {
        return api.disconnectModbus()
      } else if (connector.name.toLowerCase().includes('mqtt')) {
        return api.disconnectMqtt()
      }
      return Promise.reject(new Error('Unknown connector type'))
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['connectors-status'] })
    },
  })

  const isPending = connectMutation.isPending || disconnectMutation.isPending
  const canControl =
    connector.name.toLowerCase().includes('opcua') ||
    connector.name.toLowerCase().includes('modbus') ||
    connector.name.toLowerCase().includes('mqtt')

  return (
    <div className="bg-slate-800 rounded-lg border border-slate-700 overflow-hidden">
      <div className="p-4 border-b border-slate-700">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className={`p-2 rounded-lg ${config.color}`}>
              <StatusIcon
                className={`w-5 h-5 ${config.iconColor} ${
                  connector.state === 'connecting' ? 'animate-spin' : ''
                }`}
              />
            </div>
            <div>
              <h3 className="text-white font-semibold">{connector.name}</h3>
              {connector.endpoint && (
                <p className="text-slate-400 text-sm font-mono">{connector.endpoint}</p>
              )}
            </div>
          </div>
          <span className={`px-3 py-1 rounded-full text-sm font-medium border ${config.color}`}>
            {connector.state}
          </span>
        </div>
      </div>

      <div className="p-4">
        {connector.error && (
          <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-3 mb-4">
            <p className="text-red-400 text-sm">{connector.error}</p>
          </div>
        )}

        {connector.metrics && Object.keys(connector.metrics).length > 0 && (
          <div className="grid grid-cols-2 gap-3 mb-4">
            {Object.entries(connector.metrics).map(([key, value]) => (
              <div key={key} className="bg-slate-700/50 rounded p-2">
                <p className="text-slate-400 text-xs">{key}</p>
                <p className="text-white text-sm font-medium">
                  {typeof value === 'number' ? value.toLocaleString() : String(value)}
                </p>
              </div>
            ))}
          </div>
        )}

        {canControl && (
          <div className="flex gap-2">
            {connector.state === 'connected' ? (
              <button
                onClick={() => disconnectMutation.mutate()}
                disabled={isPending}
                className="flex-1 px-4 py-2 bg-red-600 hover:bg-red-700 disabled:bg-slate-600 disabled:cursor-not-allowed text-white rounded-lg flex items-center justify-center gap-2 transition-colors"
              >
                {disconnectMutation.isPending ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <PowerOff className="w-4 h-4" />
                )}
                Disconnect
              </button>
            ) : connector.state !== 'disabled' ? (
              <button
                onClick={() => connectMutation.mutate()}
                disabled={isPending || connector.state === 'connecting'}
                className="flex-1 px-4 py-2 bg-green-600 hover:bg-green-700 disabled:bg-slate-600 disabled:cursor-not-allowed text-white rounded-lg flex items-center justify-center gap-2 transition-colors"
              >
                {connectMutation.isPending ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Power className="w-4 h-4" />
                )}
                Connect
              </button>
            ) : null}
          </div>
        )}

        {!connector.enabled && (
          <div className="text-slate-500 text-sm text-center">
            <p>Connector is disabled in configuration</p>
            {getEnableHint(connector.name) && (
              <p className="text-slate-600 text-xs mt-1">
                Set <code className="text-titan-400">{getEnableHint(connector.name)}</code>
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

export default function ConnectorsPage() {
  const queryClient = useQueryClient()

  const { data, isLoading, error } = useQuery<AllConnectorsStatus>({
    queryKey: ['connectors-status'],
    queryFn: api.getConnectorsStatus,
    refetchInterval: 5000,
  })

  if (isLoading) {
    return <LoadingState />
  }

  if (error) {
    return <ErrorState message="Failed to load connector status" />
  }

  const connectors = data?.connectors || []
  const connectedCount = connectors.filter((c) => c.state === 'connected').length
  const failedCount = connectors.filter((c) => c.state === 'failed').length

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Connectors</h1>
          <p className="text-slate-400 mt-1">Industrial protocol connectors</p>
        </div>
        <button
          onClick={() => queryClient.invalidateQueries({ queryKey: ['connectors-status'] })}
          className="p-2 hover:bg-slate-700 rounded-lg transition-colors"
        >
          <RefreshCw className="w-5 h-5 text-slate-400" />
        </button>
      </div>

      {/* Summary */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <StatCard icon={Server} label="Total Connectors" value={connectors.length} />
        <StatCard icon={Wifi} label="Connected" value={connectedCount} iconClassName="text-green-500" />
        <StatCard icon={AlertCircle} label="Failed" value={failedCount} iconClassName="text-red-500" />
      </div>

      {/* Connector Cards */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {connectors.map((connector) => (
          <ConnectorCard key={connector.name} connector={connector} />
        ))}
        {connectors.length === 0 && (
          <div className="col-span-2 bg-slate-800 rounded-lg border border-slate-700 p-8 text-center">
            <Radio className="w-12 h-12 text-slate-600 mx-auto mb-4" />
            <p className="text-slate-400">No connectors configured</p>
            <p className="text-slate-500 text-sm mt-1">
              Enable OPC-UA, Modbus, or MQTT in your configuration
            </p>
          </div>
        )}
      </div>

      {/* Last Updated */}
      {data && (
        <p className="text-slate-500 text-sm text-center">
          Last updated: {new Date(data.timestamp).toLocaleString()}
        </p>
      )}
    </div>
  )
}

import { useQuery } from '@tanstack/react-query';
import { Settings, Database, Server, HardDrive, CheckCircle, XCircle } from 'lucide-react';
import { api } from '../api/client';

interface HealthComponent {
  status: string;
  error?: string;
  type?: string;
}

interface HealthData {
  status: string;
  components: Record<string, HealthComponent>;
  timestamp: string;
}

export default function SettingsPage() {
  const { data: health, isLoading } = useQuery<HealthData>({
    queryKey: ['health'],
    queryFn: () => api.getHealth() as Promise<HealthData>,
    refetchInterval: 10000,
  });

  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-900 mb-6">Settings</h1>

      {/* System Health */}
      <div className="card mb-6">
        <div className="flex items-center gap-2 mb-4">
          <Server className="h-5 w-5 text-gray-500" />
          <h2 className="text-lg font-semibold text-gray-900">System Health</h2>
        </div>

        {isLoading ? (
          <div className="flex items-center justify-center py-8">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600"></div>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="flex items-center gap-3">
              <StatusBadge status={health?.status || 'unknown'} />
              <span className="text-gray-700">
                System Status: <span className="font-medium capitalize">{health?.status}</span>
              </span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {health?.components &&
                Object.entries(health.components).map(([name, component]) => (
                  <HealthCard key={name} name={name} component={component} />
                ))}
            </div>

            {health?.timestamp && (
              <p className="text-sm text-gray-500">
                Last checked: {new Date(health.timestamp).toLocaleString()}
              </p>
            )}
          </div>
        )}
      </div>

      {/* API Information */}
      <div className="card mb-6">
        <div className="flex items-center gap-2 mb-4">
          <Settings className="h-5 w-5 text-gray-500" />
          <h2 className="text-lg font-semibold text-gray-900">API Information</h2>
        </div>

        <div className="space-y-3">
          <InfoRow label="API Base URL" value={window.location.origin + '/api'} />
          <InfoRow label="OpenAPI Spec" value="/openapi.json" link />
          <InfoRow label="Health Endpoint" value="/health/ready" link />
          <InfoRow label="Metrics Endpoint" value="/metrics" link />
        </div>
      </div>

      {/* IDTA Conformance */}
      <div className="card">
        <div className="flex items-center gap-2 mb-4">
          <CheckCircle className="h-5 w-5 text-gray-500" />
          <h2 className="text-lg font-semibold text-gray-900">IDTA Conformance</h2>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <ConformanceItem name="AAS Repository" status="conformant" spec="IDTA-01002" />
          <ConformanceItem name="Submodel Repository" status="conformant" spec="IDTA-01002" />
          <ConformanceItem name="AAS Registry" status="conformant" spec="IDTA-01002" />
          <ConformanceItem name="Submodel Registry" status="conformant" spec="IDTA-01002" />
          <ConformanceItem name="AASX File Server" status="conformant" spec="SSP-001" />
          <ConformanceItem name="Registry Bulk" status="conformant" spec="SSP-003" />
          <ConformanceItem name="Registry Query" status="conformant" spec="SSP-004" />
          <ConformanceItem name="Template Profiles" status="conformant" spec="SSP-003/004" />
        </div>
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const isHealthy = status === 'healthy';
  return (
    <div
      className={`flex items-center gap-1 px-2 py-1 rounded-full text-sm font-medium ${
        isHealthy ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
      }`}
    >
      {isHealthy ? (
        <CheckCircle className="h-4 w-4" />
      ) : (
        <XCircle className="h-4 w-4" />
      )}
      {status}
    </div>
  );
}

function HealthCard({ name, component }: { name: string; component: HealthComponent }) {
  const isHealthy = component.status === 'healthy';
  const Icon = name === 'database' ? Database : name === 'storage' ? HardDrive : Server;

  return (
    <div
      className={`p-4 rounded-lg border ${
        isHealthy ? 'bg-green-50 border-green-200' : 'bg-red-50 border-red-200'
      }`}
    >
      <div className="flex items-center gap-2 mb-2">
        <Icon className={`h-5 w-5 ${isHealthy ? 'text-green-600' : 'text-red-600'}`} />
        <span className="font-medium capitalize">{name}</span>
      </div>
      <p className={`text-sm ${isHealthy ? 'text-green-700' : 'text-red-700'}`}>
        {component.status}
      </p>
      {component.type && <p className="text-xs text-gray-500 mt-1">{component.type}</p>}
      {component.error && <p className="text-xs text-red-600 mt-1">{component.error}</p>}
    </div>
  );
}

function InfoRow({ label, value, link }: { label: string; value: string; link?: boolean }) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-gray-100 last:border-0">
      <span className="text-gray-600">{label}</span>
      {link ? (
        <a
          href={value}
          target="_blank"
          rel="noopener noreferrer"
          className="text-primary-600 hover:text-primary-700 font-mono text-sm"
        >
          {value}
        </a>
      ) : (
        <span className="font-mono text-sm text-gray-900">{value}</span>
      )}
    </div>
  );
}

function ConformanceItem({
  name,
  status,
  spec,
}: {
  name: string;
  status: 'conformant' | 'partial' | 'not-conformant';
  spec: string;
}) {
  return (
    <div className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
      <div>
        <p className="font-medium text-gray-900">{name}</p>
        <p className="text-xs text-gray-500">{spec}</p>
      </div>
      <span
        className={`px-2 py-1 text-xs font-medium rounded ${
          status === 'conformant'
            ? 'bg-green-100 text-green-700'
            : status === 'partial'
            ? 'bg-yellow-100 text-yellow-700'
            : 'bg-red-100 text-red-700'
        }`}
      >
        {status}
      </span>
    </div>
  );
}

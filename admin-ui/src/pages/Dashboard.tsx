import { useQuery } from '@tanstack/react-query';
import { Box, Layers, FileText, Package, HardDrive, Activity } from 'lucide-react';
import { api } from '../api/client';

interface StatCardProps {
  title: string;
  value: number;
  icon: React.ReactNode;
  subtitle?: string;
}

function StatCard({ title, value, icon, subtitle }: StatCardProps) {
  return (
    <div className="card">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium text-gray-500">{title}</p>
          <p className="text-3xl font-bold text-gray-900 mt-1">{value.toLocaleString()}</p>
          {subtitle && <p className="text-sm text-gray-500 mt-1">{subtitle}</p>}
        </div>
        <div className="p-3 bg-primary-50 rounded-lg">{icon}</div>
      </div>
    </div>
  );
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

export default function Dashboard() {
  const { data: stats, isLoading, error } = useQuery({
    queryKey: ['stats'],
    queryFn: () => api.getStats(),
    refetchInterval: 30000, // Refresh every 30 seconds
  });

  const { data: activity } = useQuery({
    queryKey: ['activity'],
    queryFn: () => api.getActivity(10),
    refetchInterval: 30000,
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="card bg-red-50 border-red-200">
        <p className="text-red-700">Failed to load dashboard data</p>
      </div>
    );
  }

  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-900 mb-6">Dashboard</h1>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        <StatCard
          title="Asset Administration Shells"
          value={stats?.repository.shells ?? 0}
          icon={<Box className="h-6 w-6 text-primary-600" />}
          subtitle={`+${stats?.recentActivity.shellsToday ?? 0} today`}
        />
        <StatCard
          title="Submodels"
          value={stats?.repository.submodels ?? 0}
          icon={<Layers className="h-6 w-6 text-primary-600" />}
          subtitle={`+${stats?.recentActivity.submodelsToday ?? 0} today`}
        />
        <StatCard
          title="Concept Descriptions"
          value={stats?.repository.conceptDescriptions ?? 0}
          icon={<FileText className="h-6 w-6 text-primary-600" />}
        />
        <StatCard
          title="AASX Packages"
          value={stats?.packages.count ?? 0}
          icon={<Package className="h-6 w-6 text-primary-600" />}
        />
      </div>

      {/* Registry Stats */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mb-8">
        <StatCard
          title="Shell Descriptors"
          value={stats?.registry.shellDescriptors ?? 0}
          icon={<Box className="h-6 w-6 text-green-600" />}
        />
        <StatCard
          title="Submodel Descriptors"
          value={stats?.registry.submodelDescriptors ?? 0}
          icon={<Layers className="h-6 w-6 text-green-600" />}
        />
        <StatCard
          title="Blob Storage"
          value={stats?.storage.blobCount ?? 0}
          icon={<HardDrive className="h-6 w-6 text-purple-600" />}
          subtitle={formatBytes(stats?.storage.blobSizeBytes ?? 0)}
        />
      </div>

      {/* Recent Activity */}
      <div className="card">
        <div className="flex items-center gap-2 mb-4">
          <Activity className="h-5 w-5 text-gray-500" />
          <h2 className="text-lg font-semibold text-gray-900">Recent Activity</h2>
        </div>
        <div className="space-y-3">
          {activity?.activities.map((item, index) => (
            <div
              key={index}
              className="flex items-center justify-between py-2 border-b border-gray-100 last:border-0"
            >
              <div className="flex items-center gap-3">
                <span
                  className={`px-2 py-1 text-xs font-medium rounded ${
                    item.type === 'shell'
                      ? 'bg-blue-100 text-blue-700'
                      : item.type === 'submodel'
                      ? 'bg-green-100 text-green-700'
                      : 'bg-purple-100 text-purple-700'
                  }`}
                >
                  {item.type}
                </span>
                <span className="text-sm text-gray-900">
                  {item.action} <span className="font-mono text-gray-500">{item.identifier}</span>
                </span>
              </div>
              <span className="text-sm text-gray-500">
                {new Date(item.timestamp).toLocaleString()}
              </span>
            </div>
          ))}
          {(!activity?.activities || activity.activities.length === 0) && (
            <p className="text-gray-500 text-center py-4">No recent activity</p>
          )}
        </div>
      </div>
    </div>
  );
}

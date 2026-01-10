import { useQuery } from '@tanstack/react-query';
import { Box, Search, ExternalLink } from 'lucide-react';
import { useState } from 'react';
import { api, Shell } from '../api/client';

export default function Shells() {
  const [search, setSearch] = useState('');

  const { data, isLoading, error } = useQuery({
    queryKey: ['shells'],
    queryFn: () => api.getShells(100),
  });

  const shells = data?.result ?? [];
  const filteredShells = shells.filter(
    (shell) =>
      shell.id.toLowerCase().includes(search.toLowerCase()) ||
      shell.idShort?.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Asset Administration Shells</h1>
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
          <input
            type="text"
            placeholder="Search shells..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="input pl-10 w-64"
          />
        </div>
      </div>

      {isLoading && (
        <div className="flex items-center justify-center h-64">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600"></div>
        </div>
      )}

      {error && (
        <div className="card bg-red-50 border-red-200">
          <p className="text-red-700">Failed to load shells</p>
        </div>
      )}

      {!isLoading && !error && (
        <div className="card overflow-hidden p-0">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  ID Short
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Identifier
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Asset Kind
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Global Asset ID
                </th>
                <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {filteredShells.map((shell) => (
                <ShellRow key={shell.id} shell={shell} />
              ))}
              {filteredShells.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-6 py-8 text-center text-gray-500">
                    No shells found
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function ShellRow({ shell }: { shell: Shell }) {
  const encodedId = btoa(shell.id).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');

  return (
    <tr className="hover:bg-gray-50">
      <td className="px-6 py-4 whitespace-nowrap">
        <div className="flex items-center gap-2">
          <Box className="h-4 w-4 text-primary-500" />
          <span className="font-medium text-gray-900">{shell.idShort || '-'}</span>
        </div>
      </td>
      <td className="px-6 py-4">
        <span className="text-sm font-mono text-gray-500 break-all">{shell.id}</span>
      </td>
      <td className="px-6 py-4 whitespace-nowrap">
        <span
          className={`px-2 py-1 text-xs font-medium rounded ${
            shell.assetInformation?.assetKind === 'Instance'
              ? 'bg-green-100 text-green-700'
              : 'bg-blue-100 text-blue-700'
          }`}
        >
          {shell.assetInformation?.assetKind || '-'}
        </span>
      </td>
      <td className="px-6 py-4">
        <span className="text-sm text-gray-500 break-all">
          {shell.assetInformation?.globalAssetId || '-'}
        </span>
      </td>
      <td className="px-6 py-4 whitespace-nowrap text-right">
        <a
          href={`/api/shells/${encodedId}`}
          target="_blank"
          rel="noopener noreferrer"
          className="text-primary-600 hover:text-primary-700"
        >
          <ExternalLink className="h-4 w-4" />
        </a>
      </td>
    </tr>
  );
}

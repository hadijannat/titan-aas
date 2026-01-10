import { useQuery } from '@tanstack/react-query';
import { Layers, Search, ExternalLink } from 'lucide-react';
import { useState } from 'react';
import { api, Submodel } from '../api/client';

export default function Submodels() {
  const [search, setSearch] = useState('');
  const [kindFilter, setKindFilter] = useState<string>('');

  const { data, isLoading, error } = useQuery({
    queryKey: ['submodels'],
    queryFn: () => api.getSubmodels(100),
  });

  const submodels = data?.result ?? [];
  const filteredSubmodels = submodels.filter((sm) => {
    const matchesSearch =
      sm.id.toLowerCase().includes(search.toLowerCase()) ||
      sm.idShort?.toLowerCase().includes(search.toLowerCase());
    const matchesKind = !kindFilter || sm.kind === kindFilter;
    return matchesSearch && matchesKind;
  });

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Submodels</h1>
        <div className="flex items-center gap-4">
          <select
            value={kindFilter}
            onChange={(e) => setKindFilter(e.target.value)}
            className="input w-40"
          >
            <option value="">All Kinds</option>
            <option value="Instance">Instance</option>
            <option value="Template">Template</option>
          </select>
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
            <input
              type="text"
              placeholder="Search submodels..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="input pl-10 w-64"
            />
          </div>
        </div>
      </div>

      {isLoading && (
        <div className="flex items-center justify-center h-64">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600"></div>
        </div>
      )}

      {error && (
        <div className="card bg-red-50 border-red-200">
          <p className="text-red-700">Failed to load submodels</p>
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
                  Kind
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Semantic ID
                </th>
                <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {filteredSubmodels.map((sm) => (
                <SubmodelRow key={sm.id} submodel={sm} />
              ))}
              {filteredSubmodels.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-6 py-8 text-center text-gray-500">
                    No submodels found
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

function SubmodelRow({ submodel }: { submodel: Submodel }) {
  const encodedId = btoa(submodel.id).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  const semanticId = submodel.semanticId?.keys?.[0]?.value;

  return (
    <tr className="hover:bg-gray-50">
      <td className="px-6 py-4 whitespace-nowrap">
        <div className="flex items-center gap-2">
          <Layers className="h-4 w-4 text-green-500" />
          <span className="font-medium text-gray-900">{submodel.idShort || '-'}</span>
        </div>
      </td>
      <td className="px-6 py-4">
        <span className="text-sm font-mono text-gray-500 break-all">{submodel.id}</span>
      </td>
      <td className="px-6 py-4 whitespace-nowrap">
        <span
          className={`px-2 py-1 text-xs font-medium rounded ${
            submodel.kind === 'Template'
              ? 'bg-purple-100 text-purple-700'
              : 'bg-green-100 text-green-700'
          }`}
        >
          {submodel.kind || 'Instance'}
        </span>
      </td>
      <td className="px-6 py-4">
        <span className="text-sm text-gray-500 break-all">{semanticId || '-'}</span>
      </td>
      <td className="px-6 py-4 whitespace-nowrap text-right">
        <a
          href={`/api/submodels/${encodedId}`}
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

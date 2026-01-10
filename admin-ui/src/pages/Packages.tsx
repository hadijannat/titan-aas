import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Package, Upload, Download, Play, Trash2 } from 'lucide-react';
import { useState, useRef } from 'react';
import { api, Package as PackageType } from '../api/client';

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

export default function Packages() {
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);

  const { data, isLoading, error } = useQuery({
    queryKey: ['packages'],
    queryFn: () => api.getPackages(100),
  });

  const uploadMutation = useMutation({
    mutationFn: (file: File) => api.uploadPackage(file),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['packages'] });
      setUploading(false);
    },
    onError: () => {
      setUploading(false);
    },
  });

  const importMutation = useMutation({
    mutationFn: (packageId: string) => api.importPackage(packageId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['packages'] });
      queryClient.invalidateQueries({ queryKey: ['shells'] });
      queryClient.invalidateQueries({ queryKey: ['submodels'] });
      queryClient.invalidateQueries({ queryKey: ['stats'] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (packageId: string) => api.deletePackage(packageId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['packages'] });
      queryClient.invalidateQueries({ queryKey: ['stats'] });
    },
  });

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setUploading(true);
      uploadMutation.mutate(file);
    }
  };

  const packages = data?.result ?? [];

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900">AASX Packages</h1>
        <div>
          <input
            type="file"
            ref={fileInputRef}
            onChange={handleFileSelect}
            accept=".aasx"
            className="hidden"
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
            className="btn btn-primary flex items-center gap-2"
          >
            {uploading ? (
              <>
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                Uploading...
              </>
            ) : (
              <>
                <Upload className="h-4 w-4" />
                Upload Package
              </>
            )}
          </button>
        </div>
      </div>

      {isLoading && (
        <div className="flex items-center justify-center h-64">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600"></div>
        </div>
      )}

      {error && (
        <div className="card bg-red-50 border-red-200">
          <p className="text-red-700">Failed to load packages</p>
        </div>
      )}

      {!isLoading && !error && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {packages.map((pkg) => (
            <PackageCard
              key={pkg.packageId}
              package={pkg}
              onImport={() => importMutation.mutate(pkg.packageId)}
              onDelete={() => {
                if (confirm('Are you sure you want to delete this package?')) {
                  deleteMutation.mutate(pkg.packageId);
                }
              }}
              importing={importMutation.isPending}
            />
          ))}
          {packages.length === 0 && (
            <div className="col-span-full card text-center py-12">
              <Package className="h-12 w-12 text-gray-300 mx-auto mb-4" />
              <p className="text-gray-500">No packages uploaded yet</p>
              <p className="text-sm text-gray-400 mt-1">
                Upload an AASX package to get started
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

interface PackageCardProps {
  package: PackageType;
  onImport: () => void;
  onDelete: () => void;
  importing: boolean;
}

function PackageCard({ package: pkg, onImport, onDelete, importing }: PackageCardProps) {
  return (
    <div className="card">
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-purple-100 rounded-lg">
            <Package className="h-6 w-6 text-purple-600" />
          </div>
          <div>
            <h3 className="font-medium text-gray-900 truncate max-w-48">{pkg.filename}</h3>
            <p className="text-sm text-gray-500">{formatBytes(pkg.sizeBytes)}</p>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4 mb-4">
        <div className="text-center p-3 bg-gray-50 rounded-lg">
          <p className="text-2xl font-bold text-gray-900">{pkg.shellCount}</p>
          <p className="text-xs text-gray-500">Shells</p>
        </div>
        <div className="text-center p-3 bg-gray-50 rounded-lg">
          <p className="text-2xl font-bold text-gray-900">{pkg.submodelCount}</p>
          <p className="text-xs text-gray-500">Submodels</p>
        </div>
      </div>

      <p className="text-sm text-gray-500 mb-4">
        Uploaded {new Date(pkg.createdAt).toLocaleDateString()}
      </p>

      <div className="flex items-center gap-2">
        <button
          onClick={onImport}
          disabled={importing}
          className="btn btn-primary flex-1 flex items-center justify-center gap-2"
        >
          {importing ? (
            <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
          ) : (
            <Play className="h-4 w-4" />
          )}
          Import
        </button>
        <a
          href={`/api/packages/${pkg.packageId}`}
          download={pkg.filename}
          className="btn btn-secondary"
        >
          <Download className="h-4 w-4" />
        </a>
        <button onClick={onDelete} className="btn btn-secondary text-red-600 hover:bg-red-50">
          <Trash2 className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}

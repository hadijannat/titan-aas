/**
 * API client for Titan-AAS backend.
 */

const API_BASE = '/api';

export interface Stats {
  repository: {
    shells: number;
    submodels: number;
    conceptDescriptions: number;
  };
  registry: {
    shellDescriptors: number;
    submodelDescriptors: number;
  };
  packages: {
    count: number;
  };
  storage: {
    blobCount: number;
    blobSizeBytes: number;
  };
  recentActivity: {
    shellsToday: number;
    submodelsToday: number;
  };
  timestamp: string;
}

export interface Activity {
  type: string;
  action: string;
  identifier: string;
  filename?: string;
  timestamp: string;
}

export interface Shell {
  id: string;
  idShort?: string;
  assetInformation: {
    assetKind: string;
    globalAssetId?: string;
  };
}

export interface Submodel {
  id: string;
  idShort?: string;
  semanticId?: {
    keys?: Array<{ value: string }>;
  };
  kind?: string;
}

export interface Package {
  packageId: string;
  filename: string;
  sizeBytes: number;
  shellCount: number;
  submodelCount: number;
  createdAt: string;
}

export interface PagedResult<T> {
  result: T[];
  paging_metadata: {
    cursor: string | null;
  };
}

class ApiClient {
  private async fetch<T>(endpoint: string, options?: RequestInit): Promise<T> {
    const response = await fetch(`${API_BASE}${endpoint}`, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...options?.headers,
      },
    });

    if (!response.ok) {
      const error = await response.text();
      throw new Error(`API Error: ${response.status} - ${error}`);
    }

    return response.json();
  }

  // Admin endpoints
  async getStats(): Promise<Stats> {
    return this.fetch('/admin/stats');
  }

  async getActivity(limit = 20): Promise<{ activities: Activity[]; count: number }> {
    return this.fetch(`/admin/activity?limit=${limit}`);
  }

  async getHealth(): Promise<Record<string, unknown>> {
    return this.fetch('/admin/health');
  }

  // Repository endpoints
  async getShells(limit = 100): Promise<PagedResult<Shell>> {
    return this.fetch(`/shells?limit=${limit}`);
  }

  async getSubmodels(limit = 100): Promise<PagedResult<Submodel>> {
    return this.fetch(`/submodels?limit=${limit}`);
  }

  async getPackages(limit = 100): Promise<PagedResult<Package>> {
    return this.fetch(`/packages?limit=${limit}`);
  }

  // Package operations
  async uploadPackage(file: File): Promise<Package> {
    const formData = new FormData();
    formData.append('file', file);

    const response = await fetch(`${API_BASE}/packages`, {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      throw new Error(`Upload failed: ${response.status}`);
    }

    return response.json();
  }

  async importPackage(packageId: string): Promise<Record<string, unknown>> {
    return this.fetch(`/packages/${packageId}/import`, {
      method: 'POST',
    });
  }

  async deletePackage(packageId: string): Promise<void> {
    await fetch(`${API_BASE}/packages/${packageId}`, {
      method: 'DELETE',
    });
  }
}

export const api = new ApiClient();

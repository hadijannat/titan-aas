# IDTA Conformance Matrix

This document tracks Titan-AAS service profile support against the IDTA Release 25-01
baseline (Part 2 API v3.1.1). Evidence references the routers that implement each
API area.

Legend:
- **Implemented**: Endpoints for the profile are present in the runtime.
- **Partial**: Some endpoints are implemented; gaps are documented.
- **Planned**: Not implemented yet.

| Service Profile (v3.1.1) | Status | Evidence / Notes |
| --- | --- | --- |
| AssetAdministrationShellRepositoryServiceSpecification/SSP-001 | Implemented | CRUD in `src/titan/api/routers/aas_repository.py`; serialization in `src/titan/api/routers/serialization.py`; self-description in `src/titan/api/routers/description.py`. |
| AssetAdministrationShellRepositoryServiceSpecification/SSP-002 | Implemented | Read-only subset of SSP-001. |
| AssetAdministrationShellRepositoryServiceSpecification/SSP-003 | Partial | Basic query filters (`idShort`, `assetIds`) in `src/titan/api/routers/aas_repository.py`. |
| SubmodelRepositoryServiceSpecification/SSP-001 | Implemented | CRUD in `src/titan/api/routers/submodel_repository.py`; serialization + self-description present. |
| SubmodelRepositoryServiceSpecification/SSP-002 | Implemented | Read-only subset of SSP-001. |
| SubmodelRepositoryServiceSpecification/SSP-003 | Planned | Template-only profile not implemented. |
| SubmodelRepositoryServiceSpecification/SSP-004 | Planned | Template-only read profile not implemented. |
| SubmodelRepositoryServiceSpecification/SSP-005 | Partial | Basic query filter (`semanticId`) in `src/titan/api/routers/submodel_repository.py`. |
| AssetAdministrationShellRegistryServiceSpecification/SSP-001 | Implemented | CRUD for AAS descriptors in `src/titan/api/routers/registry.py`. |
| AssetAdministrationShellRegistryServiceSpecification/SSP-002 | Implemented | Read-only subset of SSP-001. |
| AssetAdministrationShellRegistryServiceSpecification/SSP-003 | Planned | Bulk operations not implemented. |
| AssetAdministrationShellRegistryServiceSpecification/SSP-004 | Planned | Query operations not implemented. |
| AssetAdministrationShellRegistryServiceSpecification/SSP-005 | Planned | Minimal read profile not explicitly implemented. |
| SubmodelRegistryServiceSpecification/SSP-001 | Implemented | CRUD for Submodel descriptors in `src/titan/api/routers/registry.py`. |
| SubmodelRegistryServiceSpecification/SSP-002 | Implemented | Read-only subset of SSP-001. |
| SubmodelRegistryServiceSpecification/SSP-003 | Planned | Bulk operations not implemented. |
| SubmodelRegistryServiceSpecification/SSP-004 | Planned | Query operations not implemented. |
| DiscoveryServiceSpecification/SSP-002 | Implemented | Read operations in `src/titan/api/routers/discovery.py`. |
| DiscoveryServiceSpecification/SSP-001 | Partial | Deprecated legacy read operation not implemented. |
| ConceptDescriptionRepositoryServiceSpecification/SSP-001 | Implemented | CRUD endpoints for /concept-descriptions. |
| ConceptDescriptionRepositoryServiceSpecification/SSP-002 | Implemented | Query endpoint with `idShort`, `isCaseOf`, and `dataSpecificationRef` filters. |
| AasxFileServerServiceSpecification/SSP-001 | Planned | AASX file server not implemented. |

## Security Conformance (IDTA-01004)

| Feature | Status | Evidence / Notes |
| --- | --- | --- |
| OIDC Authentication | Implemented | `src/titan/security/oidc.py` with JWT validation, role extraction. |
| RBAC Authorization | Implemented | `src/titan/security/rbac.py` with role-based permissions. |
| ABAC Authorization | Partial | Policy engine available in `src/titan/security/abac.py`; not yet enforced in API deps. |
| Security Headers | Implemented | `src/titan/api/middleware/security_headers.py` - X-Content-Type-Options, X-Frame-Options, HSTS, CSP. |
| Rate Limiting | Implemented | `src/titan/api/middleware/rate_limit.py` with Redis-backed limiting. |

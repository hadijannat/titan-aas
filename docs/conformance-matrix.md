# IDTA Conformance Matrix

This document tracks Titan-AAS service profile support against the IDTA Release 25-01
baseline (Part 2 API v3.1.1). Evidence references the routers that implement each
API area.

Legend:
- **Implemented**: Endpoints for the profile are present in the runtime.
- **Partial**: Some endpoints are implemented; gaps are documented.
- **Planned**: Not implemented yet.

---

## Part 2 API v3.1.1 Endpoint Coverage

### AAS Repository Service (SSP-001)

| Endpoint | Method | Status | Test Reference |
|----------|--------|--------|----------------|
| `/shells` | GET | Implemented | `tests/contract/test_openapi.py::test_shells_list` |
| `/shells` | POST | Implemented | `tests/integration/test_api.py::test_create_aas` |
| `/shells/{aasIdentifier}` | GET | Implemented | `tests/contract/test_openapi.py::test_get_aas` |
| `/shells/{aasIdentifier}` | PUT | Implemented | `tests/integration/test_api.py::test_update_aas` |
| `/shells/{aasIdentifier}` | DELETE | Implemented | `tests/integration/test_api.py::test_delete_aas` |
| `/shells/{aasIdentifier}/asset-information` | GET | Implemented | `tests/unit/api/test_aas_repository.py` |
| `/shells/{aasIdentifier}/asset-information` | PUT | Implemented | `tests/unit/api/test_aas_repository.py` |
| `/shells/{aasIdentifier}/submodel-refs` | GET | Implemented | `tests/unit/api/test_aas_repository.py` |
| `/shells/{aasIdentifier}/submodel-refs` | POST | Implemented | `tests/unit/api/test_aas_repository.py` |
| `/shells/{aasIdentifier}/submodel-refs/{submodelIdentifier}` | DELETE | Implemented | `tests/unit/api/test_aas_repository.py` |

**Coverage: 10/10 endpoints (100%)**

### Submodel Repository Service (SSP-001)

| Endpoint | Method | Status | Test Reference |
|----------|--------|--------|----------------|
| `/submodels` | GET | Implemented | `tests/contract/test_openapi.py::test_submodels_list` |
| `/submodels` | POST | Implemented | `tests/integration/test_api.py::test_create_submodel` |
| `/submodels/{submodelIdentifier}` | GET | Implemented | `tests/contract/test_openapi.py::test_get_submodel` |
| `/submodels/{submodelIdentifier}` | PUT | Implemented | `tests/integration/test_api.py::test_update_submodel` |
| `/submodels/{submodelIdentifier}` | DELETE | Implemented | `tests/integration/test_api.py::test_delete_submodel` |
| `/submodels/{submodelIdentifier}/$metadata` | GET | Implemented | `tests/unit/api/test_submodel_repository.py` |
| `/submodels/{submodelIdentifier}/$value` | GET | Implemented | `tests/unit/api/test_submodel_repository.py` |
| `/submodels/{submodelIdentifier}/submodel-elements` | GET | Implemented | `tests/unit/api/test_submodel_repository.py` |
| `/submodels/{submodelIdentifier}/submodel-elements` | POST | Implemented | `tests/unit/api/test_submodel_repository.py` |
| `/submodels/{submodelIdentifier}/submodel-elements/{idShortPath}` | GET | Implemented | `tests/unit/api/test_submodel_repository.py` |
| `/submodels/{submodelIdentifier}/submodel-elements/{idShortPath}` | PUT | Implemented | `tests/unit/api/test_submodel_repository.py` |
| `/submodels/{submodelIdentifier}/submodel-elements/{idShortPath}` | DELETE | Implemented | `tests/unit/api/test_submodel_repository.py` |

**Coverage: 12/12 endpoints (100%)**

### AAS Registry Service (SSP-001)

| Endpoint | Method | Status | Test Reference |
|----------|--------|--------|----------------|
| `/shell-descriptors` | GET | Implemented | `tests/unit/api/test_registry.py` |
| `/shell-descriptors` | POST | Implemented | `tests/unit/api/test_registry.py` |
| `/shell-descriptors/{aasIdentifier}` | GET | Implemented | `tests/unit/api/test_registry.py` |
| `/shell-descriptors/{aasIdentifier}` | PUT | Implemented | `tests/unit/api/test_registry.py` |
| `/shell-descriptors/{aasIdentifier}` | DELETE | Implemented | `tests/unit/api/test_registry.py` |
| `/shell-descriptors/{aasIdentifier}/submodel-descriptors` | GET | Implemented | `tests/unit/api/test_registry.py` |
| `/shell-descriptors/{aasIdentifier}/submodel-descriptors` | POST | Implemented | `tests/unit/api/test_registry.py` |
| `/shell-descriptors/{aasIdentifier}/submodel-descriptors/{submodelIdentifier}` | GET | Implemented | `tests/unit/api/test_registry.py` |
| `/shell-descriptors/{aasIdentifier}/submodel-descriptors/{submodelIdentifier}` | PUT | Planned | Bulk operations not yet implemented |
| `/shell-descriptors/{aasIdentifier}/submodel-descriptors/{submodelIdentifier}` | DELETE | Implemented | `tests/unit/api/test_registry.py` |

**Coverage: 9/10 endpoints (90%)**

### Submodel Registry Service (SSP-001)

| Endpoint | Method | Status | Test Reference |
|----------|--------|--------|----------------|
| `/submodel-descriptors` | GET | Implemented | `tests/unit/api/test_registry.py` |
| `/submodel-descriptors` | POST | Implemented | `tests/unit/api/test_registry.py` |
| `/submodel-descriptors/{submodelIdentifier}` | GET | Implemented | `tests/unit/api/test_registry.py` |
| `/submodel-descriptors/{submodelIdentifier}` | PUT | Implemented | `tests/unit/api/test_registry.py` |
| `/submodel-descriptors/{submodelIdentifier}` | DELETE | Implemented | `tests/unit/api/test_registry.py` |

**Coverage: 5/5 endpoints (100%)**

### Discovery Service (SSP-002)

| Endpoint | Method | Status | Test Reference |
|----------|--------|--------|----------------|
| `/lookup/shells` | GET | Implemented | `tests/unit/api/test_discovery.py` |
| `/lookup/shells` | POST | Implemented | `tests/unit/api/test_discovery.py` |
| `/lookup/shells/{aasIdentifier}` | GET | Implemented | `tests/unit/api/test_discovery.py` |
| `/lookup/shells/{aasIdentifier}` | DELETE | Partial | Cleanup not fully implemented |

**Coverage: 3/4 endpoints (75%)**

### ConceptDescription Repository Service (SSP-001)

| Endpoint | Method | Status | Test Reference |
|----------|--------|--------|----------------|
| `/concept-descriptions` | GET | Implemented | `tests/unit/api/test_concept_description.py` |
| `/concept-descriptions` | POST | Implemented | `tests/unit/api/test_concept_description.py` |
| `/concept-descriptions/{cdIdentifier}` | GET | Implemented | `tests/unit/api/test_concept_description.py` |
| `/concept-descriptions/{cdIdentifier}` | PUT | Implemented | `tests/unit/api/test_concept_description.py` |
| `/concept-descriptions/{cdIdentifier}` | DELETE | Implemented | `tests/unit/api/test_concept_description.py` |

**Coverage: 5/5 endpoints (100%)**

---

## Service Profile Summary

| Service Profile (v3.1.1) | Status | Evidence / Notes |
| --- | --- | --- |
| AssetAdministrationShellRepositoryServiceSpecification/SSP-001 | Implemented | CRUD in `src/titan/api/routers/aas_repository.py`; serialization in `src/titan/api/routers/serialization.py`; self-description in `src/titan/api/routers/description.py`. |
| AssetAdministrationShellRepositoryServiceSpecification/SSP-002 | Implemented | Read-only subset of SSP-001. |
| AssetAdministrationShellRepositoryServiceSpecification/SSP-003 | Partial | Basic query filters (`idShort`, `assetIds`) in `src/titan/api/routers/aas_repository.py`. |
| SubmodelRepositoryServiceSpecification/SSP-001 | Implemented | CRUD in `src/titan/api/routers/submodel_repository.py`; serialization + self-description present. |
| SubmodelRepositoryServiceSpecification/SSP-002 | Implemented | Read-only subset of SSP-001. |
| SubmodelRepositoryServiceSpecification/SSP-003 | Planned | Template-only profile not implemented. |
| SubmodelRepositoryServiceSpecification/SSP-004 | Planned | Template-only read profile not implemented. |
| SubmodelRepositoryServiceSpecification/SSP-005 | Partial | Basic query filters (`semanticId`, `idShort`, `kind`) in `src/titan/api/routers/submodel_repository.py`. |
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

---

## Overall Conformance Summary

| Service Area | Implemented | Total | Coverage |
|--------------|-------------|-------|----------|
| AAS Repository | 10 | 10 | 100% |
| Submodel Repository | 12 | 12 | 100% |
| AAS Registry | 9 | 10 | 90% |
| Submodel Registry | 5 | 5 | 100% |
| Discovery | 3 | 4 | 75% |
| ConceptDescription | 5 | 5 | 100% |
| **Total** | **44** | **46** | **96%** |

## Data Specification Conformance (IDTA-01003-a)

| Feature | Status | Evidence / Notes |
| --- | --- | --- |
| IEC 61360 content model | Implemented | `DataSpecificationIec61360` in `src/titan/core/model/administrative.py`. |
| Embedded data specs | Implemented | `EmbeddedDataSpecification` + `HasDataSpecificationMixin` support embedded IEC 61360 specs. |
| ConceptDescription filters | Implemented | `dataSpecificationRef` filter in `src/titan/api/routers/concept_description_repository.py`. |
| External vocab / semantic validation | Planned | No external vocabulary validation or code list enforcement yet. |

## Security Conformance (IDTA-01004)

| Feature | Status | Evidence / Notes |
| --- | --- | --- |
| OIDC Authentication | Implemented | `src/titan/security/oidc.py` with JWT validation, role extraction. |
| RBAC Authorization | Implemented | `src/titan/security/rbac.py` with role-based permissions. |
| ABAC Authorization | Implemented (optional) | Enabled via `ENABLE_ABAC`; enforced in `src/titan/security/deps.py`. |
| Security Headers | Implemented | `src/titan/api/middleware/security_headers.py` - X-Content-Type-Options, X-Frame-Options, HSTS, CSP. |
| Rate Limiting | Implemented | `src/titan/api/middleware/rate_limit.py` with Redis-backed limiting. |

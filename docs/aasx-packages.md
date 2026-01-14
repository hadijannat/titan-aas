# AASX Package Management in Titan-AAS

This guide covers AASX package lifecycle management in Titan-AAS, including upload, versioning, comparison, and advanced features.

## Table of Contents

1. [Overview of AASX Format](#overview-of-aasx-format)
2. [Package Management Guide](#package-management-guide)
3. [Version Control](#version-control)
4. [Version Comparison and Diff](#version-comparison-and-diff)
5. [Version Tagging](#version-tagging)
6. [API Reference](#api-reference)
7. [Advanced Features](#advanced-features)
8. [Interoperability](#interoperability)
9. [Performance and Best Practices](#performance-and-best-practices)
10. [Troubleshooting](#troubleshooting)

---

## Overview of AASX Format

### What is AASX?

AASX (Asset Administration Shell Exchange) is the standardized package format for AAS defined in **IDTA-01005 Part 5: AAS Package File Format**. It enables portable exchange of Asset Administration Shells, Submodels, and associated files.

### AASX Structure

AASX packages are ZIP files following the OPC (Open Packaging Convention) specification:

```
my-package.aasx
├── [Content_Types].xml          # OPC content type definitions
├── _rels/                        # OPC relationships directory
│   └── .rels                     # Root relationships
├── aasx/                         # Main AAS content directory
│   ├── aasx-origin               # Package origin marker
│   ├── _rels/
│   │   └── aasx-origin.rels      # Relationships to AAS files
│   └── data.json                 # AAS/Submodel definitions (JSON)
└── files/                        # Supplementary files (PDFs, images, etc.)
    ├── thumbnail.png
    └── documentation.pdf
```

### Key Components

1. **OPC Structure**: AASX follows OPC conventions for relationships and content types
2. **AAS Data**: Asset Administration Shells, Submodels, and Concept Descriptions in JSON or XML
3. **Supplementary Files**: Referenced documents, images, 3D models, certificates
4. **Relationships**: OPC relationships linking components together

### Compliance

Titan-AAS implements:
- **IDTA-01001**: Metamodel (Asset Administration Shell structure)
- **IDTA-01002**: Part 2 (HTTP/REST API for AAS)
- **IDTA-01005**: Part 5 (AASX Package File Format)

---

## Package Management Guide

### Uploading Packages

#### Basic Upload

Upload an AASX package to Titan-AAS:

```bash
curl -X POST http://localhost:8080/packages \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@my-package.aasx"
```

Response:
```json
{
  "packageId": "550e8400-e29b-41d4-a716-446655440000",
  "filename": "my-package.aasx",
  "shells": ["https://example.com/ids/aas/1234"],
  "submodels": ["https://example.com/ids/sm/5678"],
  "uploaded": "2026-01-11T10:30:00Z"
}
```

#### Upload with Validation

Titan-AAS automatically validates AASX structure during upload:

- **OPC Compliance**: Verifies ZIP structure, relationships, content types
- **AAS Metamodel**: Validates AAS/Submodel structure against IDTA-01001
- **Semantic Validation**: Lenient checks; missing ConceptDescriptions or vocabularies
  generate warnings (not hard failures). IEC 61360 content is validated only when present.

Validation failures return HTTP 400 with detailed error messages.

### Listing Packages

#### List All Packages

```bash
curl http://localhost:8080/packages \
  -H "Authorization: Bearer $TOKEN"
```

Response:
```json
{
  "result": [
    {
      "packageId": "550e8400-e29b-41d4-a716-446655440000",
      "filename": "motor-aas.aasx",
      "sizeBytes": 1048576,
      "shellCount": 1,
      "submodelCount": 5,
      "createdAt": "2026-01-11T10:30:00Z"
    }
  ],
  "paging_metadata": {
    "cursor": "next-page-token"
  }
}
```

#### Pagination

Use `limit` and `cursor` for large result sets:

```bash
curl "http://localhost:8080/packages?limit=50&cursor=next-page-token" \
  -H "Authorization: Bearer $TOKEN"
```

### Downloading Packages

#### Download Full Package

```bash
curl http://localhost:8080/packages/{packageId} \
  -H "Authorization: Bearer $TOKEN" \
  -o downloaded.aasx
```

The response streams the AASX file with appropriate headers:
- `Content-Type: application/asset-administration-shell-package+xml`
- `Content-Disposition: attachment; filename="motor-aas.aasx"`
- `ETag: "sha256-hash"`

### Updating Packages

#### Overwrite (Default Behavior)

Replace an existing package:

```bash
curl -X PUT http://localhost:8080/packages/{packageId} \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@updated-package.aasx"
```

This **overwrites** the existing package. The old content is lost.

#### Update with Versioning

Create a new version instead of overwriting:

```bash
curl -X PUT "http://localhost:8080/packages/{packageId}?create_version=true" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@updated-package.aasx" \
  -F "comment=Added temperature sensors"
```

This creates version 2, preserving version 1. See [Version Control](#version-control) for details.

### Deleting Packages

```bash
curl -X DELETE http://localhost:8080/packages/{packageId} \
  -H "Authorization: Bearer $TOKEN"
```

**Warning**: Deletion is permanent. All versions in the version chain are deleted.

### Inspecting Package Contents

#### List Shells in Package

```bash
curl http://localhost:8080/packages/{packageId}/shells \
  -H "Authorization: Bearer $TOKEN"
```

Response:
```json
{
  "packageId": "550e8400-e29b-41d4-a716-446655440000",
  "shells": [
    {
      "id": "https://example.com/ids/aas/1234",
      "idShort": "MotorAAS",
      "assetKind": "Instance"
    }
  ]
}
```

---

## Version Control

Titan-AAS provides versioned snapshots for AASX packages to support audit trails,
rollback workflows, and controlled deployments.

### Version Chain Architecture

Versions are stored as a **linked list** using the `previous_version_id` foreign key:

```
Version 1 (root) ← Version 2 ← Version 3 ← Version 4 (HEAD)
```

Each version is a complete, immutable snapshot of the package stored in blob storage.

### Creating Versions

#### Method 1: Explicit Version Creation

Upload a new version of an existing package:

```bash
curl -X POST http://localhost:8080/packages/{packageId}/versions \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@updated-package.aasx" \
  -F "comment=Added pressure sensors to Submodel Technical Data"
```

Response:
```json
{
  "packageId": "550e8400-e29b-41d4-a716-446655440000",
  "version": 2,
  "comment": "Added pressure sensors to Submodel Technical Data",
  "createdBy": "user@example.com",
  "createdAt": "2026-01-11T11:15:00Z"
}
```

#### Method 2: Version on Update

Use the `create_version` query parameter with PUT:

```bash
curl -X PUT "http://localhost:8080/packages/{packageId}?create_version=true" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@updated-package.aasx" \
  -F "comment=Updated documentation files"
```

This is equivalent to Method 1 but uses the PUT endpoint.

### Listing Version History

#### Get All Versions

```bash
curl http://localhost:8080/packages/{packageId}/versions \
  -H "Authorization: Bearer $TOKEN"
```

Response:
```json
{
  "packageId": "550e8400-e29b-41d4-a716-446655440000",
  "totalVersions": 4,
  "result": [
    {
      "version": 4,
      "comment": "Production release v2.1.0",
      "createdBy": "admin@example.com",
      "createdAt": "2026-01-11T14:00:00Z",
      "contentHash": "a1b2c3d4...",
      "parentVersion": 3
    },
    {
      "version": 3,
      "comment": "Added pressure sensors",
      "createdBy": "engineer@example.com",
      "createdAt": "2026-01-11T12:30:00Z",
      "contentHash": "e5f6g7h8...",
      "parentVersion": 2
    },
    {
      "version": 2,
      "comment": "Updated technical data",
      "createdBy": "user@example.com",
      "createdAt": "2026-01-11T10:15:00Z",
      "contentHash": "i9j0k1l2...",
      "parentVersion": 1
    },
    {
      "version": 1,
      "comment": null,
      "createdBy": "user@example.com",
      "createdAt": "2026-01-10T09:00:00Z",
      "contentHash": "m3n4o5p6...",
      "parentVersion": null
    }
  ],
  "paging_metadata": {
    "cursor": null
  }
}
```

#### Pagination for Large Version Histories

For packages with 100+ versions:

```bash
curl "http://localhost:8080/packages/{packageId}/versions?limit=20&cursor=token" \
  -H "Authorization: Bearer $TOKEN"
```

### Downloading Specific Versions

Download any version from the history:

```bash
curl http://localhost:8080/packages/{packageId}/versions/2 \
  -H "Authorization: Bearer $TOKEN" \
  -o package-v2.aasx
```

Response headers include:
- `X-Package-Version: 2`
- `X-Package-Total-Versions: 4`

### Rollback to Previous Version

**Non-destructive rollback** creates a new version that copies the content of a previous version:

```bash
curl -X POST http://localhost:8080/packages/{packageId}/versions/2/rollback \
  -H "Authorization: Bearer $TOKEN" \
  -F "comment=Rollback to stable version due to production issue"
```

What happens:
1. Current HEAD is version 4
2. Rollback to version 2 creates version 5
3. Version 5 is a copy of version 2's content
4. Versions 3 and 4 remain accessible

Version chain after rollback:
```
v1 ← v2 ← v3 ← v4 ← v5 (copy of v2)
```

Response:
```json
{
  "packageId": "550e8400-e29b-41d4-a716-446655440000",
  "newVersion": 5,
  "rolledBackFrom": 4,
  "rolledBackTo": 2,
  "comment": "Rollback to stable version due to production issue",
  "createdAt": "2026-01-11T15:30:00Z"
}
```

### Version Best Practices

1. **Always add comments**: Meaningful version comments enable audit trails
2. **Use versioning for production**: Enable `create_version=true` for production updates
3. **Tag important versions**: Tag releases as "production", "staging", etc. (see [Version Tagging](#version-tagging))
4. **Test before rollback**: Download and verify the target version before rolling back
5. **Monitor storage**: Each version consumes blob storage (use content deduplication)

---

## Version Comparison and Diff

Titan-AAS provides powerful version comparison tools to understand changes between package versions.

### High-Level Comparison

Get a structural summary of differences:

```bash
curl http://localhost:8080/packages/{packageId}/versions/2/compare/3 \
  -H "Authorization: Bearer $TOKEN"
```

Response:
```json
{
  "packageId": "550e8400-e29b-41d4-a716-446655440000",
  "version1": 2,
  "version2": 3,
  "hasChanges": true,
  "shellsAdded": [],
  "shellsRemoved": [],
  "shellsModified": ["https://example.com/ids/aas/1234"],
  "submodelsAdded": ["https://example.com/ids/sm/9999"],
  "submodelsRemoved": [],
  "submodelsModified": ["https://example.com/ids/sm/5678"],
  "conceptDescriptionsAdded": ["https://example.com/ids/cd/pressure"],
  "conceptDescriptionsRemoved": [],
  "supplementaryFilesChanged": true
}
```

**Use cases**:
- Quick validation before deployment
- Change logs for release notes
- Audit reports

### Detailed Diff (JSON Patch)

Generate a JSON Patch (RFC 6902) diff showing exact changes:

```bash
curl http://localhost:8080/packages/{packageId}/versions/2/diff/3 \
  -H "Authorization: Bearer $TOKEN"
```

Response:
```json
{
  "packageId": "550e8400-e29b-41d4-a716-446655440000",
  "version1": 2,
  "version2": 3,
  "format": "json",
  "operationCount": 5,
  "operations": [
    {
      "op": "add",
      "path": "/submodels/-",
      "value": {
        "id": "https://example.com/ids/sm/9999",
        "idShort": "PressureSensors"
      }
    },
    {
      "op": "replace",
      "path": "/assetAdministrationShells/0",
      "value": {
        "id": "https://example.com/ids/aas/1234",
        "idShort": "MotorAAS_v2"
      }
    }
  ]
}
```

**Use cases**:
- Programmatic change detection
- Automated testing pipelines
- Migration tooling

### Comparison Performance

**Illustrative estimates only** (replace with measured results):
- **Small packages** (< 10 MB, < 50 entities): ~500ms
- **Medium packages** (10-50 MB, 50-200 entities): ~2s
- **Large packages** (> 50 MB, > 200 entities): ~5-10s

Results are **not cached** by default. For repeated comparisons, consider caching at the application level.

---

## Version Tagging

Version tags enable semantic versioning and deployment stage tracking.

### Adding Tags

Tag a specific version:

```bash
curl -X POST http://localhost:8080/packages/{packageId}/versions/3/tags \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"tags": ["production", "v2.1.0", "stable"]}'
```

Response:
```json
{
  "packageId": "550e8400-e29b-41d4-a716-446655440000",
  "version": 3,
  "tags": ["production", "v2.1.0", "stable"],
  "updatedAt": "2026-01-11T16:00:00Z"
}
```

**Tag Merging**: Tags are merged with existing tags (duplicates removed).

### Retrieving Versions by Tag

Find a version by tag name:

```bash
curl http://localhost:8080/packages/{packageId}/versions/tags/production \
  -H "Authorization: Bearer $TOKEN"
```

Response:
```json
{
  "packageId": "550e8400-e29b-41d4-a716-446655440000",
  "version": 3,
  "tags": ["production", "v2.1.0", "stable"],
  "comment": "Production release",
  "createdBy": "admin@example.com",
  "createdAt": "2026-01-11T12:30:00Z",
  "downloadUrl": "/packages/550e8400-e29b-41d4-a716-446655440000"
}
```

### Tag Naming Conventions

Recommended tag patterns:

- **Deployment Stages**: `production`, `staging`, `development`
- **Semantic Versions**: `v1.0.0`, `v2.1.3`
- **Release Candidates**: `rc1`, `beta2`
- **Feature Branches**: `feature-xyz`
- **Dates**: `2026-01-11`

### Tag Query Performance

Tags are stored in a **JSONB column with GIN index**, enabling fast lookups:
**Illustrative estimates only** (replace with measured results):
- Tag query: ~10ms (indexed)
- Version chain traversal: ~50ms for 100 versions

---

## API Reference

### Package Lifecycle Endpoints

#### POST /packages
Upload a new AASX package.

**Request**:
```bash
curl -X POST http://localhost:8080/packages \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@package.aasx"
```

**Response**: `201 Created`
```json
{
  "packageId": "uuid",
  "filename": "package.aasx",
  "shells": ["shell-id-1"],
  "submodels": ["sm-id-1", "sm-id-2"],
  "uploaded": "2026-01-11T10:00:00Z"
}
```

---

#### GET /packages
List all packages.

**Query Parameters**:
- `limit` (optional): Results per page (default: 50, max: 1000)
- `cursor` (optional): Pagination token

**Response**: `200 OK`

---

#### GET /packages/{packageId}
Download AASX package.

**Response**: `200 OK` (binary AASX file)

**Headers**:
- `Content-Type: application/asset-administration-shell-package+xml`
- `ETag: "sha256-hash"`

---

#### PUT /packages/{packageId}
Update package (overwrite or version).

**Query Parameters**:
- `create_version` (optional): If `true`, create new version instead of overwriting

**Request**:
```bash
curl -X PUT "http://localhost:8080/packages/{id}?create_version=true" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@updated.aasx" \
  -F "comment=Updated sensors"
```

---

#### DELETE /packages/{packageId}
Delete package and all versions.

**Response**: `204 No Content`

---

### Versioning Endpoints

#### POST /packages/{packageId}/versions
Create new version.

**Request**:
```bash
curl -X POST http://localhost:8080/packages/{id}/versions \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@new-version.aasx" \
  -F "comment=Version 2"
```

**Response**: `201 Created`

---

#### GET /packages/{packageId}/versions
List version history.

**Query Parameters**:
- `limit`: Results per page
- `cursor`: Pagination token

**Response**: `200 OK`

---

#### GET /packages/{packageId}/versions/{version}
Download specific version.

**Response**: `200 OK` (binary AASX file)

**Headers**:
- `X-Package-Version: {version}`
- `X-Package-Total-Versions: {count}`

---

#### POST /packages/{packageId}/versions/{version}/rollback
Rollback to specific version (non-destructive).

**Request**:
```bash
curl -X POST http://localhost:8080/packages/{id}/versions/2/rollback \
  -H "Authorization: Bearer $TOKEN" \
  -F "comment=Rollback due to issue"
```

**Response**: `201 Created`

---

### Comparison Endpoints

#### GET /packages/{packageId}/versions/{v1}/compare/{v2}
Compare two versions (high-level summary).

**Response**: `200 OK`
```json
{
  "hasChanges": true,
  "shellsAdded": ["id1"],
  "submodelsModified": ["id2"]
}
```

---

#### GET /packages/{packageId}/versions/{v1}/diff/{v2}
Generate JSON Patch diff.

**Query Parameters**:
- `format` (optional): Output format (`json`, default: `json`)

**Response**: `200 OK`

---

### Tagging Endpoints

#### POST /packages/{packageId}/versions/{version}/tags
Add tags to version.

**Request**:
```bash
curl -X POST http://localhost:8080/packages/{id}/versions/3/tags \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"tags": ["production"]}'
```

**Response**: `200 OK`

---

#### GET /packages/{packageId}/versions/tags/{tag}
Retrieve version by tag.

**Response**: `200 OK`

---

## Advanced Features

### Content Deduplication

Titan-AAS uses **SHA256 content hashing** to deduplicate packages with identical content:

1. Calculate `content_hash = SHA256(aasx_bytes)`
2. Check if package with this hash already exists
3. If exists: Return existing package (no new storage)
4. If new: Store in blob storage

**Storage savings (estimate)**: ~30-50% in environments with repeated uploads of the same package.

### Event Broadcasting

All package operations emit events to:
- **MQTT**: Topic `titan/packages/{packageId}/events`
- **WebSocket**: Channel `/ws/packages/{packageId}`

Event types:
- `package.uploaded`
- `package.version_created`
- `package.version_rolled_back`
- `package.deleted`

Subscribe to real-time package changes in your applications.

---

## Interoperability

### AASX Package Explorer

Titan-AAS packages are compatible with the **AASX Package Explorer** GUI tool:

1. Download package from Titan: `curl http://localhost:8080/packages/{id} -o pkg.aasx`
2. Open in AASX Package Explorer
3. Edit in GUI
4. Upload back to Titan: `curl -X PUT http://localhost:8080/packages/{id} -F "file=@pkg.aasx"`

### BaSyx SDK 2.0.0

Titan-AAS is interoperable with Eclipse BaSyx:

```python
from basyx.aas import model
from basyx.aas.adapter.aasx import read_aas_from_aasx

# Download from Titan
# curl http://localhost:8080/packages/{id} -o pkg.aasx

# Read with BaSyx SDK
obj_store = read_aas_from_aasx("pkg.aasx")
```

### FA³ST Service

Export packages from Titan to FA³ST:

```bash
# Download from Titan
curl http://localhost:8080/packages/{id} -o package.aasx

# Import to FA³ST
java -jar faaast-service.jar -m package.aasx
```

---

## Performance and Best Practices

**All timings below are illustrative estimates** and must be validated with benchmarks for your
deployment environment.

### Upload Performance

| Package Size | Upload Time | Validation Time |
|--------------|-------------|-----------------|
| < 1 MB       | ~200ms      | ~100ms          |
| 1-10 MB      | ~500ms      | ~300ms          |
| 10-50 MB     | ~2s         | ~1s             |
| 50-100 MB    | ~5s         | ~3s             |

**Optimization tips**:
- Compress supplementary files before packaging
- Use GZIP if AASX contains large text files
- Limit supplementary files to essential documents

### Version Creation Overhead

Creating a version adds:
- **Storage**: Full package copy (no delta storage currently)
- **Time**: ~300ms for 10 MB packages (estimate)
- **Database**: One additional row in `aasx_packages` table

**Best practices**:
- Only version significant changes
- Use tags for deployment stages instead of creating versions
- Implement retention policies (keep last N versions)

### Storage Planning

Example storage calculation for 100 packages, 5 versions each:

```
Average package size: 10 MB
Total packages: 100
Average versions per package: 5

Total storage = 100 × 5 × 10 MB = 5 GB
```

With 30% deduplication savings: ~3.5 GB

### Caching Strategy

Titan-AAS uses Redis caching for:
- Package metadata (5-minute TTL)
- Shell/Submodel lookups (10-minute TTL)
- Version lists (1-minute TTL)

Cache freshness currently relies on TTL expiration. Explicit invalidation for
package-related keys is not wired by default.

### CI/CD Integration

Example GitLab CI pipeline:

```yaml
deploy_to_staging:
  stage: deploy
  script:
    # Upload new version to staging
    - |
      curl -X POST http://titan-staging/packages/$PACKAGE_ID/versions \
        -H "Authorization: Bearer $CI_TOKEN" \
        -F "file=@build/output.aasx" \
        -F "comment=Deploy from commit $CI_COMMIT_SHA"
    # Tag as staging
    - |
      curl -X POST http://titan-staging/packages/$PACKAGE_ID/versions/$(get_version)/tags \
        -H "Authorization: Bearer $CI_TOKEN" \
        -H "Content-Type: application/json" \
        -d '{"tags": ["staging", "build-'$CI_PIPELINE_ID'"]}'
  only:
    - develop

deploy_to_production:
  stage: deploy
  script:
    # Download staging version
    - |
      curl http://titan-staging/packages/$PACKAGE_ID/versions/tags/staging \
        -H "Authorization: Bearer $CI_TOKEN" -o staging.aasx
    # Upload to production
    - |
      curl -X POST http://titan-prod/packages/$PACKAGE_ID/versions \
        -H "Authorization: Bearer $CI_TOKEN" \
        -F "file=@staging.aasx" \
        -F "comment=Production release $CI_COMMIT_TAG"
    # Tag as production
    - |
      curl -X POST http://titan-prod/packages/$PACKAGE_ID/versions/$(get_version)/tags \
        -H "Authorization: Bearer $CI_TOKEN" \
        -H "Content-Type: application/json" \
        -d '{"tags": ["production", "'$CI_COMMIT_TAG'"]}'
  only:
    - tags
```

---

## Troubleshooting

### Common Issues

#### 1. Upload Fails with "Invalid AASX structure"

**Cause**: AASX does not follow OPC conventions.

**Solution**: Validate with AASX Package Explorer before uploading.

---

#### 2. Version Not Found

**Error**: `404 - Version 5 not found for package {id}`

**Cause**: Version chain traversal didn't find the target version.

**Solution**:
- List all versions: `GET /packages/{id}/versions`
- Verify version number exists
- Check if you're using the correct `packageId`

---

#### 3. Rollback Creates Unexpected Version Number

**Scenario**: Current version is 4, rollback to version 2 creates version 5 (not version 2).

**Explanation**: Rollbacks are **non-destructive** and always create a new version at the end of the chain.

---

#### 4. Tag Not Found

**Error**: `404 - No version found with tag 'production'`

**Cause**: Tag doesn't exist in version chain, or wrong `packageId`.

**Solution**:
- List all versions to see existing tags
- Verify tag spelling (case-sensitive)

---

#### 5. Slow Comparison Performance

**Symptom**: Version comparison takes > 10 seconds.

**Cause**: Large packages with 500+ entities.

**Solution**:
- Use high-level comparison instead of full diff for quick checks
- Consider package splitting (break large packages into smaller modules)

---

### Debug Logging

Enable debug logging for package operations:

```bash
export TITAN_LOG_LEVEL=DEBUG
uvicorn titan.api.app:create_app --factory --log-level debug
```

Look for:
- `[AASX] Uploading package: {filename}`
- `[PackageManager] Creating version {n} for package {id}`
- `[PackageDiffer] Comparing versions {v1} vs {v2}`

---

### Health Checks

Verify package storage backend:

```bash
# Check blob storage connectivity
curl http://localhost:8080/health

# Expected response
{
  "status": "healthy",
  "blobStorage": "connected",
  "database": "connected"
}
```

---

## Migration from Other Systems

### From Eclipse BaSyx

1. Export packages from BaSyx file server
2. Upload to Titan with versioning enabled:
   ```bash
   for file in basyx-exports/*.aasx; do
     curl -X POST http://titan/packages \
       -H "Authorization: Bearer $TOKEN" \
       -F "file=@$file"
   done
   ```

### From FA³ST Service

FA³ST stores AAS data in JSON/XML. Convert to AASX using AASX Package Explorer or BaSyx SDK, then upload to Titan.

---

## Future Enhancements

Planned features (not yet implemented):

- **Version Retention Policies**: Automatic cleanup of old versions
- **Delta Storage**: Store only changes between versions (reduce storage by ~70%)
- **Version Branching**: Create parallel version branches (like Git branches)
- **Approval Workflows**: Multi-stage approval before production deployment
- **Package Templates**: Version-controlled templates for new packages
- **Cross-Instance Sync**: Replicate packages across Titan instances

---

## Additional Resources

- **IDTA Specifications**: https://industrialdigitaltwin.org/content-hub/aas-specifications
- **AASX Package Explorer**: https://github.com/admin-shell-io/aasx-package-explorer
- **BaSyx Documentation**: https://wiki.eclipse.org/BaSyx
- **Titan-AAS GitHub**: https://github.com/titan-aas/titan-aas

---

**Last Updated**: 2026-01-11
**Titan-AAS Version**: 2.3.0 (Package Versioning Release)

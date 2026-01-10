# Release Process

This document defines the release engineering procedures for Titan-AAS.

---

## Versioning Policy

Titan-AAS follows [Semantic Versioning 2.0.0](https://semver.org/):

```
MAJOR.MINOR.PATCH[-PRERELEASE]

Examples:
- 0.1.0      - Initial pre-1.0 release
- 0.1.1      - Patch release
- 0.2.0      - Minor release with new features
- 1.0.0      - First stable release
- 1.0.0-rc.1 - Release candidate
```

### Pre-1.0 Releases (v0.x.x)

During pre-1.0 development:

- **MINOR** increments may include breaking changes
- **PATCH** increments are backward-compatible bug fixes
- API stability is not guaranteed
- SSP profile coverage may change between versions

### Post-1.0 Releases (v1.x.x+)

After v1.0.0:

- **MAJOR** - Breaking API changes
- **MINOR** - New features, backward-compatible
- **PATCH** - Bug fixes, backward-compatible

Breaking changes include:
- Removing or renaming API endpoints
- Changing request/response schemas incompatibly
- Removing configuration options
- Dropping SSP profile support

---

## Pre-release Labels

| Label | Meaning | Example |
|-------|---------|---------|
| `alpha` | Early development, unstable | `v1.0.0-alpha.1` |
| `beta` | Feature complete, testing | `v1.0.0-beta.1` |
| `rc` | Release candidate, final testing | `v1.0.0-rc.1` |

Pre-releases are marked automatically in GitHub based on the tag name.

---

## Changelog Guidelines

Titan-AAS uses [Keep a Changelog](https://keepachangelog.com/) format.

### Changelog Structure

```markdown
# Changelog

## [Unreleased]

### Added
- New features

### Changed
- Changes in existing functionality

### Deprecated
- Features to be removed in future versions

### Removed
- Features removed in this release

### Fixed
- Bug fixes

### Security
- Security patches

## [x.y.z] - YYYY-MM-DD

...
```

### Changelog Entry Guidelines

1. **Write for users, not developers**
   - Good: "Added support for SSP-003 bulk operations"
   - Bad: "Refactored BulkOperationHandler class"

2. **Include issue/PR references**
   - Good: "Fixed rate limiting bypass for WebSocket connections (#123)"
   - Bad: "Fixed rate limiting bug"

3. **Group related changes**
   - Combine multiple related commits into one entry

4. **Be specific about breaking changes**
   - Prefix with `**BREAKING:**`
   - Include migration instructions

### Example Entries

```markdown
### Added
- SSP-002 read-only profile support for Submodel Repository (#45)
- ABAC policy: IP allowlist for production environments (#67)

### Changed
- **BREAKING:** Renamed `REDIS_HOST` to `REDIS_URL` for consistency (#89)
  - Migration: Update environment variables from `REDIS_HOST=localhost`
    to `REDIS_URL=redis://localhost:6379/0`

### Fixed
- Rate limiting now correctly handles X-Forwarded-For headers (#112)

### Security
- Updated jose library to address CVE-2024-XXXX (#134)
```

---

## Release Notes Template

Each GitHub release includes structured release notes:

```markdown
## Titan-AAS vX.Y.Z

Brief summary of the release (1-2 sentences).

### Highlights

- Key feature or improvement 1
- Key feature or improvement 2

### SSP Profile Status

| Profile | Status | Notes |
|---------|--------|-------|
| AAS Repository SSP-001 | Supported | Full CRUD |
| AAS Repository SSP-002 | Supported | Read-only |
| Submodel Repository SSP-001 | Supported | Full CRUD |
| Submodel Repository SSP-002 | Supported | Read-only |
| Registry SSP-001 | Supported | Full CRUD |
| Discovery SSP-001 | Partial | Basic lookup only |

### Known Limitations

- Limitation 1 with workaround if applicable
- Limitation 2

### Breaking Changes

List any breaking changes with migration instructions.

### Security Advisories

List any security fixes or advisories.

### Upgrade Instructions

```bash
# Pull new image
docker pull ghcr.io/hadijannat/titan-aas:vX.Y.Z

# Apply database migrations
titan db upgrade

# Restart services
docker-compose up -d
```

### Full Changelog

See [CHANGELOG.md](./CHANGELOG.md) for complete details.
```

---

## Release Workflow

### 1. Prepare Release

```bash
# Ensure main branch is up to date
git checkout main
git pull origin main

# Verify all CI checks pass
gh run list --branch main

# Update CHANGELOG.md
# Move items from [Unreleased] to new version section
```

### 2. Update Version

Update version in `pyproject.toml`:

```toml
[project]
version = "X.Y.Z"
```

### 3. Create Release Commit

```bash
# Stage changes
git add pyproject.toml CHANGELOG.md

# Commit with conventional format
git commit -m "chore: release vX.Y.Z"

# Push to main
git push origin main
```

### 4. Create and Push Tag

```bash
# Create annotated tag
git tag -a vX.Y.Z -m "Release vX.Y.Z"

# Push tag to trigger release workflow
git push origin vX.Y.Z
```

### 5. Verify Release

The release workflow automatically:

1. Builds Docker images (amd64 + arm64)
2. Pushes to `ghcr.io/hadijannat/titan-aas`
3. Creates GitHub release with auto-generated notes

Verify after completion:

```bash
# Check release workflow status
gh run list --workflow=release.yml

# Verify Docker image
docker pull ghcr.io/hadijannat/titan-aas:X.Y.Z
docker run --rm ghcr.io/hadijannat/titan-aas:X.Y.Z titan --version

# Verify GitHub release
gh release view vX.Y.Z
```

---

## Release Artifacts

Each release includes:

| Artifact | Location | Description |
|----------|----------|-------------|
| Docker Image | `ghcr.io/hadijannat/titan-aas:vX.Y.Z` | Multi-arch container image |
| SBOM | GitHub release assets | CycloneDX software bill of materials |
| Conformance Report | GitHub release assets | SSP conformance test results |
| Benchmark Results | GitHub release assets | Load test performance data |

### Docker Image Tags

| Tag Pattern | Example | Description |
|-------------|---------|-------------|
| `vX.Y.Z` | `v1.2.3` | Exact version |
| `vX.Y` | `v1.2` | Latest patch for minor |
| `vX` | `v1` | Latest for major |
| `sha-XXXXXXX` | `sha-abc1234` | Git commit SHA |
| `latest` | - | Latest stable release |

### SBOM Verification

The SBOM (Software Bill of Materials) is generated using CycloneDX:

```bash
# Download SBOM from release
gh release download vX.Y.Z --pattern '*.sbom.json'

# Verify SBOM format
cyclonedx-cli validate --input-file titan-aas-vX.Y.Z.sbom.json

# Check for known vulnerabilities
grype sbom:titan-aas-vX.Y.Z.sbom.json
```

### Conformance Report Verification

```bash
# Download conformance report
gh release download vX.Y.Z --pattern 'conformance-report.json'

# View SSP test results
cat conformance-report.json | jq '.ssp_results'
```

---

## Hotfix Process

For critical patches that cannot wait for the next regular release:

### 1. Create Hotfix Branch

```bash
# From the release tag
git checkout vX.Y.Z
git checkout -b hotfix/vX.Y.(Z+1)
```

### 2. Apply Fix

```bash
# Make minimal changes for the fix
# Add tests for the issue
# Update CHANGELOG.md
```

### 3. Release Hotfix

```bash
# Update version
# pyproject.toml: version = "X.Y.(Z+1)"

git add -A
git commit -m "fix: critical issue description (#issue)"

# Tag and push
git tag -a vX.Y.(Z+1) -m "Hotfix: description"
git push origin hotfix/vX.Y.(Z+1) --tags

# Create PR to merge hotfix back to main
gh pr create --base main --head hotfix/vX.Y.(Z+1)
```

---

## Release Checklist

Before releasing, verify:

### Pre-Release Checks

- [ ] All CI jobs pass on main branch
- [ ] CHANGELOG.md is updated with new version section
- [ ] Version in pyproject.toml matches release tag
- [ ] Known limitations are documented
- [ ] Breaking changes have migration instructions
- [ ] Security advisories are included if applicable

### Post-Release Checks

- [ ] GitHub release is created with notes
- [ ] Docker image is available on ghcr.io
- [ ] SBOM is attached to release
- [ ] Conformance report is attached to release
- [ ] Benchmark results are attached to release
- [ ] Announcement posted (if applicable)

---

## Rollback Procedure

If a release causes issues:

### 1. Identify Scope

Determine if the issue requires:
- Configuration change only
- Hotfix release
- Full rollback to previous version

### 2. Rollback Deployment

```bash
# Pull previous version
docker pull ghcr.io/hadijannat/titan-aas:vX.Y.(Z-1)

# Update deployment
kubectl set image deployment/titan-aas \
  titan-aas=ghcr.io/hadijannat/titan-aas:vX.Y.(Z-1)

# Or with Docker Compose
docker-compose pull
docker-compose up -d
```

### 3. Database Rollback (if needed)

```bash
# Check current migration
titan db current

# Downgrade to previous migration
titan db downgrade -1
```

### 4. Post-Rollback

- Document the issue in GitHub
- Create hotfix if needed
- Update release notes with known issue

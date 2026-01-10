# Spec Artifacts

This directory vendors the IDTA OpenAPI and schema artifacts as a git submodule:

- `specs/aas-specs-api` (pinned to tag `v3.1.1`)
- `specs/checksums.txt` contains SHA-256 checksums for tracked spec files

To initialize or update the submodule:

```bash
git submodule update --init --recursive
```

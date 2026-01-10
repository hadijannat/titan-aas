# Security Advisories

This document tracks security vulnerabilities that have been reviewed and deliberately excluded from automated scanning, along with justification and mitigation strategies.

## Ignored CVEs in pip-audit

The following vulnerabilities are excluded from the pip-audit CI check. Each exclusion has been reviewed and documented with risk assessment.

| CVE | Package | Severity | Reason | Mitigation | Review Date |
|-----|---------|----------|--------|------------|-------------|
| PYSEC-2024-230 | certifi | Medium | Transitive dependency; GLOBALTRUST CA removal | Updated to latest certifi; no GLOBALTRUST certs used | 2026-01-10 |
| PYSEC-2024-225 | cryptography | High | Crash only occurs with mismatched cert/key in PKCS12 | Usage pattern validated; no PKCS12 serialization used | 2026-01-10 |
| CVE-2024-23342 | ecdsa | High | Timing attack requires measuring signature operations | Transitive via python-jose; ECDSA signing not used | 2026-01-10 |

## Detailed Analysis

### PYSEC-2024-230 (CVE-2024-39689) - Certifi GLOBALTRUST CA

**Package:** certifi
**Severity:** Medium
**Published:** 2024-07-05

**Description:**
GLOBALTRUST root certificates were removed from certifi due to compliance issues identified in Mozilla's investigation. Systems trusting GLOBALTRUST-issued certificates may fail validation after upgrading.

**Impact Assessment:**
- Titan-AAS does not specifically trust GLOBALTRUST-issued certificates
- TLS connections use standard CA bundle validation
- No customer integrations rely on GLOBALTRUST chain

**Mitigation:**
- Keep certifi updated to latest version
- Standard Mozilla trust store changes are acceptable

**Action:** Monitor for customer impact; accept as low-risk.

---

### PYSEC-2024-225 (CVE-2024-26130) - Cryptography PKCS12 Crash

**Package:** cryptography
**Severity:** High (CVSS 7.5)
**Published:** 2024-02-21

**Description:**
When calling `pkcs12.serialize_key_and_certificates` with a certificate whose public key does not match the provided private key AND an `encryption_algorithm` with `hmac_hash` set, a NULL pointer dereference causes the Python process to crash.

**Impact Assessment:**
- Titan-AAS does not use `pkcs12.serialize_key_and_certificates`
- PKCS12 operations are not part of the AAS runtime workflow
- Cryptography is a transitive dependency via python-jose for JWT operations
- JWT operations use RSA/EC key handling, not PKCS12

**Mitigation:**
- Usage audit confirms no PKCS12 serialization paths
- Upgrade cryptography when compatible fix available

**Action:** Accept as not-exploitable in current usage pattern.

---

### CVE-2024-23342 - Python-ECDSA Minerva Timing Attack

**Package:** ecdsa
**Severity:** High (CVSS 7.4)
**Published:** 2024-01-16

**Description:**
The python-ecdsa package is vulnerable to the Minerva timing attack on P-256 curve. An attacker who can measure the duration of hundreds to thousands of signing operations of known messages can potentially recover the private key.

**Impact Assessment:**
- python-ecdsa is a transitive dependency via python-jose
- Titan-AAS uses python-jose for JWT **verification** (signature checking), not signing
- No ECDSA private keys are used for signing operations in the runtime
- JWT tokens are issued by external OIDC providers (Keycloak, Auth0, etc.)
- Timing attack requires measuring signature creation, not verification

**Mitigation:**
- Verified that no ECDSA signing operations occur in Titan-AAS
- JWT verification uses public keys only
- If future signing needs arise, use pyca/cryptography instead

**Action:** Accept as not-exploitable; ECDSA signing is not used.

---

## Review Process

Security advisories are reviewed:
1. When new CVEs are reported by pip-audit in CI
2. Quarterly as part of security review
3. Before major releases

Each ignored CVE requires:
- Documented justification
- Impact assessment for Titan-AAS usage patterns
- Defined mitigation strategy
- Scheduled review date

## Audit History

| Date | Reviewer | Action |
|------|----------|--------|
| 2026-01-10 | Initial | Created security advisories documentation |

## References

- [PYSEC-2024-230 (OSV)](https://osv.dev/vulnerability/PYSEC-2024-230)
- [PYSEC-2024-225 (OSV)](https://osv.dev/vulnerability/PYSEC-2024-225)
- [CVE-2024-23342 (NVD)](https://nvd.nist.gov/vuln/detail/cve-2024-23342)
- [Python Advisory Database](https://github.com/pypa/advisory-database)

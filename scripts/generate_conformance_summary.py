#!/usr/bin/env python3
"""Generate human-readable conformance summary from JSON report.

This script reads the machine-readable conformance-report.json and generates
a markdown summary suitable for release notes and documentation.

Usage:
    python scripts/generate_conformance_summary.py \
        --input conformance-report.json \
        --output conformance-summary.md
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Profile ID to human-readable name mapping
PROFILE_NAMES = {
    "AAS-REPO": "AAS Repository Service",
    "SM-REPO": "Submodel Repository Service",
    "AAS-REG": "AAS Registry Service",
    "SM-REG": "Submodel Registry Service",
    "DISC": "Discovery Service",
    "CD-REPO": "ConceptDescription Repository Service",
    "DESC": "Description Service",
}

# Profile to IDTA SSP reference
PROFILE_SSP_REFS = {
    "AAS-REPO": "AssetAdministrationShellRepositoryServiceSpecification/SSP-001",
    "SM-REPO": "SubmodelRepositoryServiceSpecification/SSP-001",
    "AAS-REG": "AssetAdministrationShellRegistryServiceSpecification/SSP-001",
    "SM-REG": "SubmodelRegistryServiceSpecification/SSP-001",
    "DISC": "DiscoveryServiceSpecification/SSP-002",
    "CD-REPO": "ConceptDescriptionRepositoryServiceSpecification/SSP-001",
    "DESC": "DescriptionServiceSpecification/SSP-001",
}


def load_report(input_path: Path) -> dict:
    """Load conformance report from JSON file."""
    with open(input_path) as f:
        return json.load(f)


def get_status_emoji(status: str) -> str:
    """Get emoji for status."""
    return {
        "pass": "\u2705",  # ✅
        "partial": "\u26a0\ufe0f",  # ⚠️
        "fail": "\u274c",  # ❌
        "skip": "\u23ed\ufe0f",  # ⏭️
    }.get(status, "\u2753")  # ❓


def generate_summary(report: dict) -> str:
    """Generate markdown summary from report."""
    lines = []

    # Header
    lines.append(f"# Conformance Report v{report['version']}")
    lines.append("")
    lines.append("## IDTA-01002 Part 2 API v3.1.1 Conformance")
    lines.append("")

    # Overall summary
    summary = report["summary"]
    conformance_pct = summary["conformance_rate"] * 100
    lines.append(f"**Overall Conformance: {conformance_pct:.1f}%**")
    lines.append("")
    lines.append(f"- Total Tests: {summary['total_tests']}")
    lines.append(f"- Passed: {summary['passed']}")
    lines.append(f"- Failed: {summary['failed']}")
    lines.append(f"- Skipped: {summary['skipped']}")
    lines.append("")

    # Profile table
    lines.append("## Service Profile Status")
    lines.append("")
    lines.append("| Profile | SSP Reference | Status | Tests |")
    lines.append("|---------|---------------|--------|-------|")

    profiles = report.get("profiles", {})
    for profile_id in sorted(profiles.keys()):
        profile = profiles[profile_id]
        name = PROFILE_NAMES.get(profile_id, profile_id)
        ssp_ref = PROFILE_SSP_REFS.get(profile_id, "N/A")
        status_emoji = get_status_emoji(profile["status"])
        tests = f"{profile['tests_passed']}/{profile['tests_total']}"

        status = f"{status_emoji} {profile['status'].title()}"
        lines.append(f"| {name} | {ssp_ref} | {status} | {tests} |")

    lines.append("")

    # Failed tests (if any)
    failed_tests = [
        (tc_id, tc)
        for tc_id, tc in report.get("test_cases", {}).items()
        if tc["status"] in ("fail", "error")
    ]

    if failed_tests:
        lines.append("## Failed Tests")
        lines.append("")
        lines.append("| Test Case | Status | Message |")
        lines.append("|-----------|--------|---------|")

        for tc_id, tc in sorted(failed_tests):
            message = tc.get("message", "")[:80] if tc.get("message") else ""
            message = message.replace("|", "\\|").replace("\n", " ")
            lines.append(f"| {tc_id} | {tc['status']} | {message} |")

        lines.append("")

    # Footer
    lines.append("---")
    lines.append("")
    lines.append(f"*Generated at: {report['generated_at']}*")
    lines.append("")
    lines.append(
        "*Generated with [Titan-AAS](https://github.com/titan-aas/titan-aas) conformance tooling*"
    )

    return "\n".join(lines)


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate conformance summary markdown from JSON report"
    )
    parser.add_argument(
        "--input",
        "-i",
        required=True,
        help="Path to conformance-report.json",
    )
    parser.add_argument(
        "--output",
        "-o",
        default="conformance-summary.md",
        help="Output path for markdown summary (default: conformance-summary.md)",
    )

    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}", file=sys.stderr)
        return 1

    # Load report
    print(f"Loading conformance report from: {input_path}")
    report = load_report(input_path)

    # Generate summary
    summary = generate_summary(report)

    # Write output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        f.write(summary)

    print(f"Conformance summary written to: {output_path}")

    # Print preview
    print("\n=== Summary Preview ===")
    preview_lines = summary.split("\n")[:20]
    print("\n".join(preview_lines))
    if len(summary.split("\n")) > 20:
        print("...")

    return 0


if __name__ == "__main__":
    sys.exit(main())

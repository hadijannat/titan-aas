#!/usr/bin/env python3
"""Generate IDTA conformance report from pytest results.

This script parses JUnit XML test results and generates a machine-readable
conformance report mapping SSP test case IDs to pass/fail status.

Usage:
    python scripts/generate_conformance_report.py \
        --input test-results/contract.xml \
        --output conformance-report.json

The output JSON follows this structure:
{
    "version": "0.1.0",
    "generated_at": "2026-01-10T12:34:56Z",
    "profiles": {
        "AAS-REPO-SSP-001": { "status": "pass", "tests_passed": 10, "tests_total": 10 },
        ...
    },
    "test_cases": {
        "SSP-AAS-REPO-GET-001": { "status": "pass", "duration_ms": 45 },
        ...
    },
    "summary": {
        "total_tests": 50,
        "passed": 48,
        "failed": 2,
        "skipped": 0,
        "conformance_rate": 0.96
    }
}
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET  # noqa: S405 - Input is trusted CI artifact
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path


@dataclass
class TestCaseResult:
    """Result of a single test case."""

    test_case_id: str
    status: str  # pass, fail, skip, error
    duration_ms: float
    message: str | None = None


@dataclass
class ProfileResult:
    """Aggregated result for a profile."""

    status: str  # pass, partial, fail
    tests_passed: int = 0
    tests_failed: int = 0
    tests_skipped: int = 0
    tests_total: int = 0


@dataclass
class ConformanceReport:
    """Complete conformance report."""

    version: str
    generated_at: str
    profiles: dict[str, ProfileResult] = field(default_factory=dict)
    test_cases: dict[str, TestCaseResult] = field(default_factory=dict)
    summary: dict[str, float | int] = field(default_factory=dict)


def parse_junit_xml(xml_path: Path) -> list[TestCaseResult]:
    """Parse JUnit XML and extract SSP test case results."""
    tree = ET.parse(xml_path)  # noqa: S314 - Input is trusted CI artifact
    root = tree.getroot()

    results: list[TestCaseResult] = []

    # Handle both <testsuites> and <testsuite> as root
    testsuites = root.findall(".//testsuite") if root.tag == "testsuites" else [root]

    for testsuite in testsuites:
        for testcase in testsuite.findall("testcase"):
            name = testcase.get("name", "")
            classname = testcase.get("classname", "")
            time_str = testcase.get("time", "0")

            # Extract SSP test case ID from test name or markers
            # Convention: test function name includes SSP ID or marker
            ssp_id = extract_ssp_id(name, classname)
            if not ssp_id:
                continue

            duration_ms = float(time_str) * 1000

            # Determine status
            failure = testcase.find("failure")
            error = testcase.find("error")
            skipped = testcase.find("skipped")

            if failure is not None:
                status = "fail"
                message = failure.get("message", failure.text or "")
            elif error is not None:
                status = "error"
                message = error.get("message", error.text or "")
            elif skipped is not None:
                status = "skip"
                message = skipped.get("message", skipped.text or "")
            else:
                status = "pass"
                message = None

            results.append(
                TestCaseResult(
                    test_case_id=ssp_id,
                    status=status,
                    duration_ms=duration_ms,
                    message=message[:200] if message else None,  # Truncate long messages
                )
            )

    return results


def extract_ssp_id(test_name: str, classname: str) -> str | None:
    """Extract SSP test case ID from test name or classname.

    Looks for patterns like:
    - test_ssp_aas_repo_get_001
    - test_SSP_AAS_REPO_GET_001
    - [SSP-AAS-REPO-GET-001]
    """
    # Pattern: SSP-{profile}-{category}-{sequence}
    pattern = r"SSP[-_]([A-Z0-9]+[-_][A-Z0-9]+[-_][A-Z0-9]+[-_][0-9]+)"

    # Check test name first
    match = re.search(pattern, test_name.upper().replace("_", "-"))
    if match:
        return f"SSP-{match.group(1)}"

    # Check classname
    match = re.search(pattern, classname.upper().replace("_", "-"))
    if match:
        return f"SSP-{match.group(1)}"

    # Try simpler pattern for test names like test_shells_list_returns_paginated_response
    # Map known test names to SSP IDs
    test_to_ssp = {
        "test_shells_list_returns_paginated_response": "SSP-AAS-REPO-LIST-001",
        "test_shell_not_found_returns_404": "SSP-AAS-REPO-ERR-001",
        "test_invalid_base64_returns_400": "SSP-AAS-REPO-ERR-002",
        "test_submodels_list_returns_paginated_response": "SSP-SM-REPO-LIST-001",
        "test_submodel_not_found_returns_404": "SSP-SM-REPO-ERR-001",
        "test_description_returns_profiles": "SSP-DESC-001",
        "test_description_returns_modifiers": "SSP-DESC-002",
        "test_description_profiles_list": "SSP-DESC-003",
    }

    return test_to_ssp.get(test_name)


def _extract_profile(test_case_id: str) -> str:
    """Extract profile name from test case ID."""
    parts = test_case_id.split("-")
    if len(parts) >= 4:
        return f"{parts[1]}-{parts[2]}"
    return "UNKNOWN"


def _compute_status(pr: ProfileResult) -> str:
    """Compute profile status from test counts."""
    if pr.tests_failed > 0:
        return "partial" if pr.tests_passed > 0 else "fail"
    if pr.tests_passed == pr.tests_total:
        return "pass"
    if pr.tests_passed > 0:
        return "partial"
    return "skip"


def compute_profile_results(
    test_results: list[TestCaseResult],
) -> dict[str, ProfileResult]:
    """Aggregate test results by profile."""
    profiles: dict[str, ProfileResult] = {}

    for result in test_results:
        profile = _extract_profile(result.test_case_id)

        if profile not in profiles:
            profiles[profile] = ProfileResult(status="pending")

        pr = profiles[profile]
        pr.tests_total += 1

        if result.status == "pass":
            pr.tests_passed += 1
        elif result.status in ("fail", "error"):
            pr.tests_failed += 1
        else:
            pr.tests_skipped += 1

    # Compute profile status
    for _profile, pr in profiles.items():
        pr.status = _compute_status(pr)

    return profiles


def generate_report(
    test_results: list[TestCaseResult],
    version: str = "0.1.0",
) -> ConformanceReport:
    """Generate complete conformance report from test results."""
    profiles = compute_profile_results(test_results)

    # Build test case dictionary
    test_cases = {
        r.test_case_id: TestCaseResult(
            test_case_id=r.test_case_id,
            status=r.status,
            duration_ms=r.duration_ms,
            message=r.message,
        )
        for r in test_results
    }

    # Compute summary
    total = len(test_results)
    passed = sum(1 for r in test_results if r.status == "pass")
    failed = sum(1 for r in test_results if r.status in ("fail", "error"))
    skipped = sum(1 for r in test_results if r.status == "skip")
    conformance_rate = passed / total if total > 0 else 0.0

    summary = {
        "total_tests": total,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "conformance_rate": round(conformance_rate, 4),
    }

    return ConformanceReport(
        version=version,
        generated_at=datetime.now(UTC).isoformat(),
        profiles=profiles,
        test_cases=test_cases,
        summary=summary,
    )


def report_to_dict(report: ConformanceReport) -> dict:
    """Convert report to JSON-serializable dictionary."""
    return {
        "version": report.version,
        "generated_at": report.generated_at,
        "profiles": {k: asdict(v) for k, v in report.profiles.items()},
        "test_cases": {k: asdict(v) for k, v in report.test_cases.items()},
        "summary": report.summary,
    }


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate IDTA conformance report from pytest results"
    )
    parser.add_argument(
        "--input",
        "-i",
        required=True,
        help="Path to JUnit XML test results",
    )
    parser.add_argument(
        "--output",
        "-o",
        default="conformance-report.json",
        help="Output path for conformance report (default: conformance-report.json)",
    )
    parser.add_argument(
        "--version",
        "-v",
        default="0.1.0",
        help="Titan-AAS version to include in report",
    )
    parser.add_argument(
        "--fail-on-missing",
        action="store_true",
        help="Exit with error if no SSP test cases found",
    )
    parser.add_argument(
        "--min-conformance",
        type=float,
        default=0.0,
        help="Minimum conformance rate (0.0-1.0) to pass",
    )

    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}", file=sys.stderr)
        return 1

    # Parse test results
    print(f"Parsing test results from: {input_path}")
    test_results = parse_junit_xml(input_path)

    if not test_results:
        if args.fail_on_missing:
            print("Error: No SSP test cases found in results", file=sys.stderr)
            return 1
        print("Warning: No SSP test cases found in results")

    # Generate report
    report = generate_report(test_results, version=args.version)

    # Write output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(report_to_dict(report), f, indent=2)

    print(f"Conformance report written to: {output_path}")

    # Print summary
    print("\n=== Conformance Summary ===")
    print(f"Version: {report.version}")
    print(f"Total Tests: {report.summary['total_tests']}")
    print(f"Passed: {report.summary['passed']}")
    print(f"Failed: {report.summary['failed']}")
    print(f"Skipped: {report.summary['skipped']}")
    print(f"Conformance Rate: {report.summary['conformance_rate']:.1%}")

    print("\n=== Profile Status ===")
    for profile, result in sorted(report.profiles.items()):
        status_icon = {"pass": "[PASS]", "partial": "[PARTIAL]", "fail": "[FAIL]"}.get(
            result.status, "[SKIP]"
        )
        print(f"  {status_icon} {profile}: {result.tests_passed}/{result.tests_total}")

    # Check minimum conformance
    if report.summary["conformance_rate"] < args.min_conformance:
        print(
            f"\nError: Conformance rate {report.summary['conformance_rate']:.1%} "
            f"below minimum {args.min_conformance:.1%}",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Main benchmark runner for Titan-AAS vs BaSyx Python SDK comparison.

Orchestrates:
1. Server health checks
2. Data loading
3. Performance benchmarks
4. Report generation

Usage:
    python benchmarks/compare_basyx.py                    # Run full comparison
    python benchmarks/compare_basyx.py --load-data        # Load test data only
    python benchmarks/compare_basyx.py --benchmark        # Run benchmarks only
    python benchmarks/compare_basyx.py --report           # Generate report from existing results
"""

from __future__ import annotations

import argparse
import base64
import json
import statistics
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import httpx


@dataclass
class ServerConfig:
    """Server configuration."""

    name: str
    base_url: str
    shells_path: str = "/shells"
    submodels_path: str = "/submodels"


@dataclass
class BenchmarkResult:
    """Results from a benchmark run."""

    operation: str
    server: str
    requests: int
    success: int
    failed: int
    latencies_ms: list[float] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        return (self.success / self.requests * 100) if self.requests > 0 else 0.0

    @property
    def p50_ms(self) -> float:
        if not self.latencies_ms:
            return 0.0
        sorted_latencies = sorted(self.latencies_ms)
        idx = int(len(sorted_latencies) * 0.5)
        return sorted_latencies[idx]

    @property
    def p95_ms(self) -> float:
        if not self.latencies_ms:
            return 0.0
        sorted_latencies = sorted(self.latencies_ms)
        idx = int(len(sorted_latencies) * 0.95)
        return sorted_latencies[min(idx, len(sorted_latencies) - 1)]

    @property
    def p99_ms(self) -> float:
        if not self.latencies_ms:
            return 0.0
        sorted_latencies = sorted(self.latencies_ms)
        idx = int(len(sorted_latencies) * 0.99)
        return sorted_latencies[min(idx, len(sorted_latencies) - 1)]

    @property
    def mean_ms(self) -> float:
        return statistics.mean(self.latencies_ms) if self.latencies_ms else 0.0

    @property
    def throughput_rps(self) -> float:
        if not self.latencies_ms:
            return 0.0
        total_time_s = sum(self.latencies_ms) / 1000
        return self.requests / total_time_s if total_time_s > 0 else 0.0


TITAN_CONFIG = ServerConfig(
    name="Titan-AAS",
    base_url="http://localhost:8080",
)

BASYX_CONFIG = ServerConfig(
    name="BaSyx Python SDK",
    base_url="http://localhost:8081",
)


def encode_id(identifier: str) -> str:
    """Encode identifier to Base64URL."""
    encoded = base64.urlsafe_b64encode(identifier.encode("utf-8")).decode("ascii")
    return encoded.rstrip("=")


def check_server_health(config: ServerConfig) -> bool:
    """Check if server is healthy."""
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(f"{config.base_url}{config.shells_path}")
            return resp.status_code in (200, 404)
    except Exception as e:
        print(f"  {config.name}: UNHEALTHY ({e})")
        return False


def load_test_data(config: ServerConfig, data_dir: Path) -> dict[str, int]:
    """Load test data into a server."""
    stats = {"aas_loaded": 0, "aas_failed": 0, "submodels_loaded": 0, "submodels_failed": 0}

    with httpx.Client(base_url=config.base_url, timeout=30.0) as client:
        # Load AAS
        aas_file = data_dir / "benchmark_aas.json"
        if aas_file.exists():
            with open(aas_file) as f:
                aas_list = json.load(f)

            print(f"  Loading {len(aas_list)} AAS into {config.name}...")
            for aas in aas_list:
                try:
                    resp = client.post(
                        config.shells_path,
                        json=aas,
                        headers={"Content-Type": "application/json"},
                    )
                    if resp.status_code == 201:
                        stats["aas_loaded"] += 1
                    else:
                        stats["aas_failed"] += 1
                except Exception:
                    stats["aas_failed"] += 1

        # Load Submodels
        sm_file = data_dir / "benchmark_submodels.json"
        if sm_file.exists():
            with open(sm_file) as f:
                submodels = json.load(f)

            print(f"  Loading {len(submodels)} Submodels into {config.name}...")
            for sm in submodels:
                try:
                    resp = client.post(
                        config.submodels_path,
                        json=sm,
                        headers={"Content-Type": "application/json"},
                    )
                    if resp.status_code == 201:
                        stats["submodels_loaded"] += 1
                    else:
                        stats["submodels_failed"] += 1
                except Exception:
                    stats["submodels_failed"] += 1

    return stats


def run_benchmark(
    config: ServerConfig,
    operation: str,
    endpoint: str,
    method: str = "GET",
    iterations: int = 100,
    payload: dict | None = None,
) -> BenchmarkResult:
    """Run a benchmark for a specific operation."""
    result = BenchmarkResult(
        operation=operation,
        server=config.name,
        requests=iterations,
        success=0,
        failed=0,
    )

    with httpx.Client(base_url=config.base_url, timeout=30.0) as client:
        for _ in range(iterations):
            start = time.perf_counter()
            try:
                if method == "GET":
                    resp = client.get(endpoint)
                elif method == "POST":
                    resp = client.post(
                        endpoint,
                        json=payload,
                        headers={"Content-Type": "application/json"},
                    )
                else:
                    resp = client.request(method, endpoint)

                latency_ms = (time.perf_counter() - start) * 1000
                result.latencies_ms.append(latency_ms)

                if resp.status_code < 400:
                    result.success += 1
                else:
                    result.failed += 1
            except Exception:
                latency_ms = (time.perf_counter() - start) * 1000
                result.latencies_ms.append(latency_ms)
                result.failed += 1

    return result


def run_benchmarks(
    configs: list[ServerConfig], iterations: int = 100
) -> dict[str, list[BenchmarkResult]]:
    """Run all benchmarks against all servers."""
    all_results: dict[str, list[BenchmarkResult]] = {}

    for config in configs:
        print(f"\nBenchmarking {config.name}...")
        results = []

        # List AAS
        print("  - List AAS (GET /shells)...")
        result = run_benchmark(config, "List AAS", config.shells_path, "GET", iterations)
        results.append(result)
        print(
            f"    p50={result.p50_ms:.1f}ms, p95={result.p95_ms:.1f}ms, "
            f"success={result.success_rate:.1f}%"
        )

        # List Submodels
        print("  - List Submodels (GET /submodels)...")
        result = run_benchmark(config, "List Submodels", config.submodels_path, "GET", iterations)
        results.append(result)
        print(
            f"    p50={result.p50_ms:.1f}ms, p95={result.p95_ms:.1f}ms, "
            f"success={result.success_rate:.1f}%"
        )

        all_results[config.name] = results

    return all_results


def generate_report(
    results: dict[str, list[BenchmarkResult]], output_path: Path
) -> None:
    """Generate markdown comparison report."""
    report = []
    report.append("# Titan-AAS vs BaSyx Python SDK Benchmark Results")
    report.append("")
    report.append(f"Generated: {datetime.now().isoformat()}")
    report.append("")

    # Summary table
    report.append("## Summary")
    report.append("")
    report.append("| Server | Operations | Success Rate | Avg Latency (ms) |")
    report.append("|--------|------------|--------------|------------------|")

    for server, server_results in results.items():
        total_requests = sum(r.requests for r in server_results)
        total_success = sum(r.success for r in server_results)
        success_rate = (total_success / total_requests * 100) if total_requests > 0 else 0
        avg_latency = (
            statistics.mean([r.mean_ms for r in server_results]) if server_results else 0
        )
        report.append(f"| {server} | {total_requests} | {success_rate:.1f}% | {avg_latency:.1f} |")

    report.append("")

    # Detailed results
    report.append("## Detailed Results")
    report.append("")

    # Get all operations
    operations = set()
    for server_results in results.values():
        for r in server_results:
            operations.add(r.operation)

    for operation in sorted(operations):
        report.append(f"### {operation}")
        report.append("")
        report.append("| Server | Requests | Success | p50 (ms) | p95 (ms) | p99 (ms) |")
        report.append("|--------|----------|---------|----------|----------|----------|")

        for server, server_results in results.items():
            for r in server_results:
                if r.operation == operation:
                    report.append(
                        f"| {server} | {r.requests} | {r.success_rate:.1f}% | "
                        f"{r.p50_ms:.1f} | {r.p95_ms:.1f} | {r.p99_ms:.1f} |"
                    )

        report.append("")

    # Write report
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        f.write("\n".join(report))

    print(f"\nReport generated: {output_path}")


def export_json_results(
    results: dict[str, list[BenchmarkResult]], output_path: Path
) -> None:
    """Export results to JSON for further analysis."""
    export_data = {}
    for server, server_results in results.items():
        export_data[server] = [
            {
                "operation": r.operation,
                "requests": r.requests,
                "success": r.success,
                "failed": r.failed,
                "success_rate": r.success_rate,
                "p50_ms": r.p50_ms,
                "p95_ms": r.p95_ms,
                "p99_ms": r.p99_ms,
                "mean_ms": r.mean_ms,
            }
            for r in server_results
        ]

    with open(output_path, "w") as f:
        json.dump(export_data, f, indent=2)

    print(f"JSON results exported: {output_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Titan-AAS vs BaSyx benchmark comparison")
    parser.add_argument(
        "--load-data",
        action="store_true",
        help="Load test data into servers",
    )
    parser.add_argument(
        "--benchmark",
        action="store_true",
        help="Run performance benchmarks",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Generate report from existing results",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=100,
        help="Number of iterations per benchmark",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("benchmarks/data"),
        help="Directory containing test data",
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=Path("benchmarks/results"),
        help="Directory for results output",
    )
    parser.add_argument(
        "--titan-only",
        action="store_true",
        help="Only benchmark Titan-AAS",
    )
    parser.add_argument(
        "--basyx-only",
        action="store_true",
        help="Only benchmark BaSyx Python SDK",
    )
    args = parser.parse_args()

    # If no specific action, run all
    run_all = not (args.load_data or args.benchmark or args.report)

    configs = []
    if not args.basyx_only:
        configs.append(TITAN_CONFIG)
    if not args.titan_only:
        configs.append(BASYX_CONFIG)

    # Check server health
    print("\nChecking server health...")
    healthy_configs = []
    for config in configs:
        if check_server_health(config):
            print(f"  {config.name}: HEALTHY")
            healthy_configs.append(config)
        else:
            print(f"  {config.name}: UNHEALTHY (skipping)")

    if not healthy_configs:
        print("\nNo healthy servers found. Please start the servers first:")
        print("  docker compose -f benchmarks/docker-compose.benchmark.yml up -d")
        return 1

    # Load test data
    if args.load_data or run_all:
        print("\n" + "=" * 60)
        print("Loading Test Data")
        print("=" * 60)

        for config in healthy_configs:
            stats = load_test_data(config, args.data_dir)
            print(f"\n  {config.name}:")
            print(f"    AAS loaded: {stats['aas_loaded']}, failed: {stats['aas_failed']}")
            print(
                f"    Submodels loaded: {stats['submodels_loaded']}, "
                f"failed: {stats['submodels_failed']}"
            )

    # Run benchmarks
    results = {}
    if args.benchmark or run_all:
        print("\n" + "=" * 60)
        print("Running Performance Benchmarks")
        print("=" * 60)

        results = run_benchmarks(healthy_configs, args.iterations)

        # Save results
        args.results_dir.mkdir(parents=True, exist_ok=True)
        export_json_results(results, args.results_dir / "benchmark_results.json")

    # Generate report
    if args.report or run_all:
        print("\n" + "=" * 60)
        print("Generating Report")
        print("=" * 60)

        # Load results if not already in memory
        if not results:
            results_file = args.results_dir / "benchmark_results.json"
            if results_file.exists():
                with open(results_file) as f:
                    raw_results = json.load(f)
                # Convert to BenchmarkResult objects
                results = {}
                for server, ops in raw_results.items():
                    results[server] = [
                        BenchmarkResult(
                            operation=op["operation"],
                            server=server,
                            requests=op["requests"],
                            success=op["success"],
                            failed=op["failed"],
                            latencies_ms=[op["mean_ms"]] * op["requests"],  # Approximate
                        )
                        for op in ops
                    ]
            else:
                print("No results found. Run --benchmark first.")
                return 1

        generate_report(results, args.results_dir / "comparison_report.md")

    print("\n" + "=" * 60)
    print("Benchmark Complete!")
    print("=" * 60)
    print(f"\nResults available in: {args.results_dir}/")

    return 0


if __name__ == "__main__":
    sys.exit(main())

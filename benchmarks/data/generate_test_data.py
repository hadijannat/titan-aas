#!/usr/bin/env python3
"""Generate test data for Titan-AAS vs BaSyx benchmark.

Creates AAS and Submodel JSON files that can be loaded into both systems.
Uses BaSyx Python SDK for data generation to prove interoperability.

Usage:
    python benchmarks/data/generate_test_data.py
    python benchmarks/data/generate_test_data.py --count 50 --output benchmarks/data
"""

from __future__ import annotations

import argparse
import json
import random
import uuid
from pathlib import Path
from typing import Any


def generate_aas(index: int) -> dict[str, Any]:
    """Generate a single AAS payload."""
    unique_id = uuid.uuid4().hex[:8]
    return {
        "modelType": "AssetAdministrationShell",
        "id": f"urn:example:aas:benchmark:shell-{index:04d}-{unique_id}",
        "idShort": f"BenchmarkShell_{index:04d}",
        "description": [
            {
                "language": "en",
                "text": f"Benchmark AAS #{index} for performance testing",
            }
        ],
        "assetInformation": {
            "assetKind": "Instance",
            "globalAssetId": f"urn:example:asset:benchmark:asset-{index:04d}-{unique_id}",
            "assetType": "urn:example:types:BenchmarkAsset",
        },
    }


def generate_property(name: str, index: int) -> dict[str, Any]:
    """Generate a Property submodel element."""
    value_types = ["xs:string", "xs:double", "xs:int", "xs:boolean"]
    value_type = random.choice(value_types)  # noqa: S311

    if value_type == "xs:string":
        value = f"value_{uuid.uuid4().hex[:6]}"
    elif value_type == "xs:double":
        value = str(round(random.uniform(0, 1000), 2))  # noqa: S311
    elif value_type == "xs:int":
        value = str(random.randint(0, 10000))  # noqa: S311
    else:
        value = str(random.choice(["true", "false"]))  # noqa: S311

    return {
        "modelType": "Property",
        "idShort": f"{name}_{index}",
        "valueType": value_type,
        "value": value,
        "description": [
            {
                "language": "en",
                "text": f"Property {name} #{index}",
            }
        ],
    }


def generate_submodel_element_collection(name: str, depth: int = 1) -> dict[str, Any]:
    """Generate a SubmodelElementCollection with nested elements."""
    elements = []
    for i in range(random.randint(2, 5)):  # noqa: S311
        elements.append(generate_property("NestedProp", i))

    return {
        "modelType": "SubmodelElementCollection",
        "idShort": name,
        "value": elements,
    }


def generate_submodel(index: int, complexity: str = "medium") -> dict[str, Any]:
    """Generate a Submodel with varying complexity.

    Args:
        index: Sequential index for unique naming
        complexity: "simple" (3-5 props), "medium" (8-15), "complex" (20-30 + collections)
    """
    unique_id = uuid.uuid4().hex[:8]

    if complexity == "simple":
        num_properties = random.randint(3, 5)  # noqa: S311
        include_collections = False
    elif complexity == "medium":
        num_properties = random.randint(8, 15)  # noqa: S311
        include_collections = random.choice([True, False])  # noqa: S311
    else:  # complex
        num_properties = random.randint(20, 30)  # noqa: S311
        include_collections = True

    elements: list[dict[str, Any]] = []

    # Add properties
    property_names = [
        "Temperature",
        "Pressure",
        "Humidity",
        "Speed",
        "Position",
        "Status",
        "Counter",
        "Voltage",
        "Current",
        "Power",
        "Frequency",
        "Level",
        "Flow",
        "Weight",
        "Timestamp",
    ]

    for i in range(num_properties):
        name = property_names[i % len(property_names)]
        elements.append(generate_property(name, i))

    # Add collections for complex submodels
    if include_collections:
        num_collections = random.randint(1, 3)  # noqa: S311
        collection_names = ["Configuration", "Metadata", "Measurements", "Settings"]
        for i in range(num_collections):
            elements.append(
                generate_submodel_element_collection(collection_names[i % len(collection_names)])
            )

    return {
        "modelType": "Submodel",
        "id": f"urn:example:submodel:benchmark:sm-{index:04d}-{unique_id}",
        "idShort": f"BenchmarkSubmodel_{index:04d}",
        "description": [
            {
                "language": "en",
                "text": f"Benchmark Submodel #{index} ({complexity} complexity)",
            }
        ],
        "submodelElements": elements,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate benchmark test data")
    parser.add_argument(
        "--aas-count",
        type=int,
        default=100,
        help="Number of AAS to generate",
    )
    parser.add_argument(
        "--submodel-count",
        type=int,
        default=100,
        help="Number of Submodels to generate",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("benchmarks/data"),
        help="Output directory",
    )
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate AAS
    print(f"Generating {args.aas_count} AAS...")
    aas_list = [generate_aas(i) for i in range(args.aas_count)]
    aas_file = output_dir / "benchmark_aas.json"
    with open(aas_file, "w") as f:
        json.dump(aas_list, f, indent=2)
    print(f"  Written to: {aas_file}")

    # Generate Submodels with varying complexity
    print(f"Generating {args.submodel_count} Submodels...")
    submodels = []
    complexities = ["simple", "medium", "complex"]
    for i in range(args.submodel_count):
        # Distribute complexity: 40% simple, 40% medium, 20% complex
        complexity_weights = [0.4, 0.4, 0.2]
        complexity = random.choices(complexities, weights=complexity_weights)[0]  # noqa: S311
        submodels.append(generate_submodel(i, complexity))

    submodel_file = output_dir / "benchmark_submodels.json"
    with open(submodel_file, "w") as f:
        json.dump(submodels, f, indent=2)
    print(f"  Written to: {submodel_file}")

    # Summary
    print("\nGeneration complete!")
    print(f"  AAS: {len(aas_list)}")
    print(f"  Submodels: {len(submodels)}")

    # Count elements by complexity
    simple_count = sum(1 for s in submodels if "simple" in s["description"][0]["text"])
    medium_count = sum(1 for s in submodels if "medium" in s["description"][0]["text"])
    complex_count = sum(1 for s in submodels if "complex" in s["description"][0]["text"])
    print("  Submodel complexity distribution:")
    print(f"    Simple: {simple_count}")
    print(f"    Medium: {medium_count}")
    print(f"    Complex: {complex_count}")


if __name__ == "__main__":
    main()

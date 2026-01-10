"""CLI command for validating AAS/Submodel JSON files.

Usage:
    titan validate model.json
    titan validate *.json --strict
    titan validate models/ --recursive
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, TypedDict

import typer

if TYPE_CHECKING:
    from rich.console import Console


class ValidationResult(TypedDict):
    file: str
    valid: bool
    type: str | None
    id: str | None
    errors: list[str]


app = typer.Typer(help="Validate AAS/Submodel JSON files")


@app.callback(invoke_without_command=True)
def validate(
    paths: list[Path] = typer.Argument(
        ...,
        help="Paths to JSON files or directories to validate",
    ),
    recursive: bool = typer.Option(
        False,
        "--recursive",
        "-r",
        help="Recursively search directories for JSON files",
    ),
    strict: bool = typer.Option(
        False,
        "--strict",
        "-s",
        help="Enable strict validation (fail on extra fields)",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show detailed validation output",
    ),
    output_format: str = typer.Option(
        "text",
        "--format",
        "-f",
        help="Output format: text, json",
    ),
) -> None:
    """Validate AAS and Submodel JSON files.

    Parses files and validates them against the IDTA metamodel.
    Supports single files, multiple files, or directories.
    """
    import json

    from rich.console import Console

    console = Console()

    # Collect all files to validate
    files_to_validate: list[Path] = []
    for path in paths:
        if path.is_file():
            if path.suffix.lower() == ".json":
                files_to_validate.append(path)
            else:
                console.print(f"[yellow]Skipping non-JSON file:[/yellow] {path}")
        elif path.is_dir():
            pattern = "**/*.json" if recursive else "*.json"
            files_to_validate.extend(path.glob(pattern))
        else:
            console.print(f"[red]Path not found:[/red] {path}")

    if not files_to_validate:
        console.print("[yellow]No JSON files found to validate[/yellow]")
        raise typer.Exit(code=1)

    console.print(f"[blue]Validating {len(files_to_validate)} file(s)...[/blue]")
    console.print()

    # Validation results
    results: list[ValidationResult] = []
    passed = 0
    failed = 0

    for file_path in files_to_validate:
        result = _validate_file(file_path, strict, verbose, console)
        results.append(result)

        if result["valid"]:
            passed += 1
        else:
            failed += 1

    # Output summary
    console.print()
    if output_format == "json":
        console.print(json.dumps(results, indent=2))
    else:
        console.print("[bold]Summary:[/bold]")
        console.print(f"  [green]Passed:[/green] {passed}")
        console.print(f"  [red]Failed:[/red] {failed}")
        console.print(f"  [blue]Total:[/blue]  {len(results)}")

    if failed > 0:
        raise typer.Exit(code=1)


def _validate_file(
    file_path: Path,
    strict: bool,
    verbose: bool,
    console: Console,
) -> ValidationResult:
    """Validate a single file and return result."""
    import orjson
    from pydantic import ValidationError

    from titan.core.model import AssetAdministrationShell, Submodel

    result: ValidationResult = {
        "file": str(file_path),
        "valid": False,
        "type": None,
        "id": None,
        "errors": [],
    }

    try:
        # Read file
        content = file_path.read_bytes()
        data = orjson.loads(content)

        if not isinstance(data, dict):
            result["errors"].append("Root must be a JSON object")
            console.print(f"[red]✗[/red] {file_path}: Root must be a JSON object")
            return result

        # Determine type
        model_type = data.get("modelType", "")

        if model_type == "AssetAdministrationShell" or "assetInformation" in data:
            result["type"] = "AssetAdministrationShell"
            try:
                if strict:
                    # Pydantic strict mode with extra forbid
                    shell = AssetAdministrationShell.model_validate(
                        data,
                        strict=True,
                    )
                else:
                    shell = AssetAdministrationShell.model_validate(data)
                result["valid"] = True
                result["id"] = shell.id
                console.print(f"[green]✓[/green] {file_path}: AAS '{shell.id_short or shell.id}'")
            except ValidationError as e:
                for error in e.errors():
                    loc = ".".join(str(x) for x in error["loc"])
                    msg = f"{loc}: {error['msg']}"
                    result["errors"].append(msg)
                    if verbose:
                        console.print(f"    [red]└[/red] {msg}")
                err_count = len(result["errors"])
                console.print(f"[red]✗[/red] {file_path}: {err_count} validation error(s)")

        elif model_type == "Submodel" or "submodelElements" in data:
            result["type"] = "Submodel"
            try:
                if strict:
                    sm = Submodel.model_validate(data, strict=True)
                else:
                    sm = Submodel.model_validate(data)
                result["valid"] = True
                result["id"] = sm.id
                console.print(f"[green]✓[/green] {file_path}: Submodel '{sm.id_short or sm.id}'")
            except ValidationError as e:
                for error in e.errors():
                    loc = ".".join(str(x) for x in error["loc"])
                    msg = f"{loc}: {error['msg']}"
                    result["errors"].append(msg)
                    if verbose:
                        console.print(f"    [red]└[/red] {msg}")
                err_count = len(result["errors"])
                console.print(f"[red]✗[/red] {file_path}: {err_count} validation error(s)")

        elif "assetAdministrationShells" in data:
            # Environment format
            result["type"] = "Environment"
            shells = data.get("assetAdministrationShells", [])
            submodels = data.get("submodels", [])
            all_valid = True
            total_errors = 0

            for i, shell_data in enumerate(shells):
                try:
                    AssetAdministrationShell.model_validate(shell_data)
                except ValidationError as e:
                    all_valid = False
                    for error in e.errors():
                        loc = f"shells[{i}].{'.'.join(str(x) for x in error['loc'])}"
                        msg = f"{loc}: {error['msg']}"
                        result["errors"].append(msg)
                        total_errors += 1
                        if verbose:
                            console.print(f"    [red]└[/red] {msg}")

            for i, sm_data in enumerate(submodels):
                try:
                    Submodel.model_validate(sm_data)
                except ValidationError as e:
                    all_valid = False
                    for error in e.errors():
                        loc = f"submodels[{i}].{'.'.join(str(x) for x in error['loc'])}"
                        msg = f"{loc}: {error['msg']}"
                        result["errors"].append(msg)
                        total_errors += 1
                        if verbose:
                            console.print(f"    [red]└[/red] {msg}")

            result["valid"] = all_valid
            if all_valid:
                console.print(
                    f"[green]✓[/green] {file_path}: Environment "
                    f"({len(shells)} shells, {len(submodels)} submodels)"
                )
            else:
                console.print(f"[red]✗[/red] {file_path}: {total_errors} validation error(s)")

        else:
            result["errors"].append("Unknown model type")
            console.print(f"[yellow]?[/yellow] {file_path}: Unknown model type")

    except orjson.JSONDecodeError as e:
        result["errors"].append(f"Invalid JSON: {e}")
        console.print(f"[red]✗[/red] {file_path}: Invalid JSON - {e}")

    except Exception as e:
        result["errors"].append(str(e))
        console.print(f"[red]✗[/red] {file_path}: {e}")

    return result

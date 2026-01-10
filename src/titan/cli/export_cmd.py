"""CLI command for exporting to AASX packages.

Usage:
    titan export-aasx output.aasx --api-url http://localhost:8080
    titan export-aasx output.aasx --shell-id "urn:example:aas:1"
    titan export-aasx output.aasx --all
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer

app = typer.Typer(help="Export to AASX packages")


@app.callback(invoke_without_command=True)
def export_aasx(
    output: Path = typer.Argument(
        ...,
        help="Output path for the AASX file",
    ),
    api_url: str = typer.Option(
        "http://localhost:8080",
        "--api-url",
        "-u",
        help="Titan-AAS API URL to export from",
    ),
    shell_ids: list[str] | None = typer.Option(
        None,
        "--shell-id",
        "-s",
        help="Shell IDs to export (can be specified multiple times)",
    ),
    submodel_ids: list[str] | None = typer.Option(
        None,
        "--submodel-id",
        "-m",
        help="Submodel IDs to export (can be specified multiple times)",
    ),
    all_resources: bool = typer.Option(
        False,
        "--all",
        "-a",
        help="Export all shells and submodels",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show verbose output",
    ),
) -> None:
    """Export shells and submodels to an AASX package.

    Fetches specified shells and submodels from a Titan-AAS server
    and packages them into an AASX file.
    """
    if not shell_ids and not submodel_ids and not all_resources:
        typer.echo(
            "Error: Specify --shell-id, --submodel-id, or --all",
            err=True,
        )
        raise typer.Exit(code=1)

    asyncio.run(_export_aasx(output, api_url, shell_ids, submodel_ids, all_resources, verbose))


async def _export_aasx(
    output: Path,
    api_url: str,
    shell_ids: list[str] | None,
    submodel_ids: list[str] | None,
    all_resources: bool,
    verbose: bool,
) -> None:
    """Async implementation of export command."""
    import base64

    import httpx
    from rich.console import Console

    from titan.compat import AasxExporter
    from titan.core.model import AssetAdministrationShell, Submodel

    console = Console()
    shells: list[AssetAdministrationShell] = []
    submodels: list[Submodel] = []

    console.print(f"[blue]Fetching from:[/blue] {api_url}")

    try:
        async with httpx.AsyncClient(base_url=api_url, timeout=30.0) as client:
            if all_resources:
                # Fetch all shells
                console.print("  Fetching all shells...")
                response = await client.get("/shells")
                response.raise_for_status()
                shell_list = response.json().get("result", [])

                for shell_data in shell_list:
                    try:
                        shell = AssetAdministrationShell.model_validate(shell_data)
                        shells.append(shell)
                        if verbose:
                            console.print(f"    [green]✓[/green] {shell.id_short or shell.id}")
                    except Exception as e:
                        console.print(f"    [red]✗[/red] Failed to parse shell: {e}")

                # Fetch all submodels
                console.print("  Fetching all submodels...")
                response = await client.get("/submodels")
                response.raise_for_status()
                sm_list = response.json().get("result", [])

                for sm_data in sm_list:
                    try:
                        sm = Submodel.model_validate(sm_data)
                        submodels.append(sm)
                        if verbose:
                            console.print(f"    [green]✓[/green] {sm.id_short or sm.id}")
                    except Exception as e:
                        console.print(f"    [red]✗[/red] Failed to parse submodel: {e}")

            else:
                # Fetch specific shells
                if shell_ids:
                    console.print("  Fetching shells...")
                    for shell_id in shell_ids:
                        # Encode ID for URL
                        encoded_id = (
                            base64.urlsafe_b64encode(shell_id.encode()).decode().rstrip("=")
                        )
                        response = await client.get(f"/shells/{encoded_id}")

                        if response.status_code == 200:
                            try:
                                shell = AssetAdministrationShell.model_validate(response.json())
                                shells.append(shell)
                                console.print(f"    [green]✓[/green] {shell.id_short or shell.id}")
                            except Exception as e:
                                console.print(f"    [red]✗[/red] Failed to parse: {e}")
                        else:
                            console.print(f"    [red]✗[/red] Not found: {shell_id}")

                # Fetch specific submodels
                if submodel_ids:
                    console.print("  Fetching submodels...")
                    for sm_id in submodel_ids:
                        encoded_id = base64.urlsafe_b64encode(sm_id.encode()).decode().rstrip("=")
                        response = await client.get(f"/submodels/{encoded_id}")

                        if response.status_code == 200:
                            try:
                                sm = Submodel.model_validate(response.json())
                                submodels.append(sm)
                                console.print(f"    [green]✓[/green] {sm.id_short or sm.id}")
                            except Exception as e:
                                console.print(f"    [red]✗[/red] Failed to parse: {e}")
                        else:
                            console.print(f"    [red]✗[/red] Not found: {sm_id}")

    except httpx.HTTPError as e:
        console.print(f"[red]HTTP error:[/red] {e}")
        raise typer.Exit(code=1) from e

    if not shells and not submodels:
        console.print("[yellow]No resources to export[/yellow]")
        raise typer.Exit(code=1)

    # Export to AASX
    console.print()
    console.print(f"[blue]Exporting to:[/blue] {output}")

    try:
        exporter = AasxExporter()
        await exporter.export_package(shells, submodels, output)

        console.print()
        console.print(
            f"[green]Export complete![/green] {len(shells)} shells, {len(submodels)} submodels"
        )

    except Exception as e:
        console.print(f"[red]Export error:[/red] {e}")
        raise typer.Exit(code=1) from e

"""CLI command for importing AASX packages.

Usage:
    titan import-aasx package.aasx
    titan import-aasx package.aasx --api-url http://localhost:8080
    titan import-aasx package.aasx --dry-run
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer

app = typer.Typer(help="Import AASX packages into Titan-AAS")


@app.callback(invoke_without_command=True)
def import_aasx(
    path: Path = typer.Argument(
        ...,
        help="Path to the AASX file to import",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
    ),
    api_url: str | None = typer.Option(
        None,
        "--api-url",
        "-u",
        help="Titan-AAS API URL to import to (if not provided, validates only)",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        "-n",
        help="Parse and validate without importing",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show verbose output",
    ),
) -> None:
    """Import an AASX package.

    Parses the AASX package and either validates it (dry-run mode) or
    imports the shells and submodels to a Titan-AAS server.
    """
    asyncio.run(_import_aasx(path, api_url, dry_run, verbose))


async def _import_aasx(
    path: Path,
    api_url: str | None,
    dry_run: bool,
    verbose: bool,
) -> None:
    """Async implementation of import command."""
    from rich.console import Console
    from rich.table import Table

    from titan.compat import AasxImporter

    console = Console()

    # Parse the package
    console.print(f"[blue]Parsing AASX package:[/blue] {path}")

    try:
        importer = AasxImporter()
        package = await importer.import_package(path)
    except Exception as e:
        console.print(f"[red]Error parsing package:[/red] {e}")
        raise typer.Exit(code=1) from e

    # Display summary
    console.print()
    console.print("[green]Package Contents:[/green]")

    # Shells table
    if package.shells:
        table = Table(title="Asset Administration Shells")
        table.add_column("ID", style="cyan")
        table.add_column("idShort", style="green")
        table.add_column("Asset ID", style="yellow")

        for shell in package.shells:
            asset_id = ""
            if shell.asset_information and shell.asset_information.global_asset_id:
                asset_id = shell.asset_information.global_asset_id
            table.add_row(shell.id, shell.id_short or "-", asset_id or "-")

        console.print(table)

    # Submodels table
    if package.submodels:
        table = Table(title="Submodels")
        table.add_column("ID", style="cyan")
        table.add_column("idShort", style="green")
        table.add_column("Semantic ID", style="yellow")
        table.add_column("Elements", style="magenta")

        for sm in package.submodels:
            semantic_id = ""
            if sm.semantic_id and sm.semantic_id.keys:
                semantic_id = sm.semantic_id.keys[0].value
            elem_count = len(sm.submodel_elements) if sm.submodel_elements else 0
            table.add_row(sm.id, sm.id_short or "-", semantic_id or "-", str(elem_count))

        console.print(table)

    # Summary
    console.print()
    console.print(
        f"[bold]Summary:[/bold] {len(package.shells)} shells, "
        f"{len(package.submodels)} submodels, "
        f"{len(package.supplementary_files)} supplementary files"
    )

    if dry_run:
        console.print("[yellow]Dry run mode - no changes made[/yellow]")
        return

    if api_url is None:
        console.print("[yellow]No API URL provided - validation only[/yellow]")
        return

    # Import to API
    console.print()
    console.print(f"[blue]Importing to:[/blue] {api_url}")

    try:
        import httpx

        async with httpx.AsyncClient(base_url=api_url, timeout=30.0) as client:
            # Import shells
            for shell in package.shells:
                shell_data = shell.model_dump(mode="json", by_alias=True, exclude_none=True)
                response = await client.post("/shells", json=shell_data)

                if response.status_code == 201:
                    console.print(f"  [green]✓[/green] Shell: {shell.id_short or shell.id}")
                elif response.status_code == 409:
                    msg = f"  [yellow]⊘[/yellow] Shell exists: {shell.id_short or shell.id}"
                    console.print(msg)
                else:
                    msg = f"  [red]✗[/red] Shell failed: {shell.id_short or shell.id}"
                    console.print(f"{msg} - {response.text}")

            # Import submodels
            for sm in package.submodels:
                sm_data = sm.model_dump(mode="json", by_alias=True, exclude_none=True)
                response = await client.post("/submodels", json=sm_data)

                if response.status_code == 201:
                    console.print(f"  [green]✓[/green] Submodel: {sm.id_short or sm.id}")
                elif response.status_code == 409:
                    msg = f"  [yellow]⊘[/yellow] Submodel exists: {sm.id_short or sm.id}"
                    console.print(msg)
                else:
                    msg = f"  [red]✗[/red] Submodel failed: {sm.id_short or sm.id}"
                    console.print(f"{msg} - {response.text}")

        console.print()
        console.print("[green]Import complete![/green]")

    except httpx.HTTPError as e:
        console.print(f"[red]HTTP error:[/red] {e}")
        raise typer.Exit(code=1) from e

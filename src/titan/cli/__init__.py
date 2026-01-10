"""CLI commands for Titan-AAS.

Provides command-line interface using Typer:
- titan import-aasx: Import AASX packages
- titan export-aasx: Export to AASX packages
- titan validate: Validate AAS/Submodel JSON files
- titan serve: Run the API server

Usage:
    titan --help
    titan import-aasx package.aasx
    titan export-aasx output.aasx --shell-id "..." --submodel-id "..."
    titan validate model.json
    titan serve --port 8080
"""

import typer

from titan.cli.export_cmd import app as export_app
from titan.cli.import_cmd import app as import_app
from titan.cli.serve import app as serve_app
from titan.cli.validate_cmd import app as validate_app

# Main CLI application
app = typer.Typer(
    name="titan",
    help="Titan-AAS: Industrial-grade Asset Administration Shell runtime",
    no_args_is_help=True,
)

# Add subcommands
app.add_typer(import_app, name="import-aasx")
app.add_typer(export_app, name="export-aasx")
app.add_typer(validate_app, name="validate")
app.add_typer(serve_app, name="serve")


@app.callback()
def callback() -> None:
    """Titan-AAS: Industrial-grade Asset Administration Shell runtime."""
    pass


def main() -> None:
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()

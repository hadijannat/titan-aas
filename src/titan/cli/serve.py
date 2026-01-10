"""CLI command for running the API server.

Usage:
    titan serve
    titan serve --port 8080 --host 0.0.0.0
    titan serve --reload --log-level debug
"""

from __future__ import annotations

import typer

app = typer.Typer(help="Run the Titan-AAS API server")


@app.callback(invoke_without_command=True)
def serve(
    host: str = typer.Option(
        "0.0.0.0",
        "--host",
        "-h",
        help="Host to bind to",
    ),
    port: int = typer.Option(
        8080,
        "--port",
        "-p",
        help="Port to listen on",
    ),
    reload: bool = typer.Option(
        False,
        "--reload",
        "-r",
        help="Enable auto-reload for development",
    ),
    workers: int = typer.Option(
        1,
        "--workers",
        "-w",
        help="Number of worker processes",
    ),
    log_level: str = typer.Option(
        "info",
        "--log-level",
        "-l",
        help="Log level: debug, info, warning, error",
    ),
    access_log: bool = typer.Option(
        True,
        "--access-log/--no-access-log",
        help="Enable/disable access logging",
    ),
) -> None:
    """Run the Titan-AAS API server.

    Starts the uvicorn server with the FastAPI application.
    """
    import uvicorn

    # Configure uvicorn
    config = {
        "app": "titan.api.app:create_app",
        "factory": True,
        "host": host,
        "port": port,
        "reload": reload,
        "workers": workers if not reload else 1,  # Reload requires single worker
        "log_level": log_level.lower(),
        "access_log": access_log,
    }

    # Print startup info
    typer.echo("Starting Titan-AAS server...")
    typer.echo(f"  Host: {host}")
    typer.echo(f"  Port: {port}")
    typer.echo(f"  Workers: {config['workers']}")
    typer.echo(f"  Log level: {log_level}")
    if reload:
        typer.echo("  Reload: enabled")
    typer.echo()
    typer.echo(f"API documentation: http://{host}:{port}/docs")
    typer.echo()

    # Run server
    uvicorn.run(**config)

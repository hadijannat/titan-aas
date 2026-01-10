"""CLI command for running the API server.

Usage:
    titan serve
    titan serve --port 8080 --host 0.0.0.0
    titan serve --reload --log-level debug
"""

from __future__ import annotations

import typer

# Install uvloop for 2-4x faster event loop performance
try:
    import uvloop

    uvloop.install()
except ImportError:
    pass  # Fall back to standard asyncio

app = typer.Typer(help="Run the Titan-AAS API server")


@app.callback(invoke_without_command=True)
def serve(
    host: str = typer.Option(
        "0.0.0.0",  # nosec B104 - intentional for container deployments
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

    workers_effective = workers if not reload else 1  # Reload requires single worker

    # Print startup info
    typer.echo("Starting Titan-AAS server...")
    typer.echo(f"  Host: {host}")
    typer.echo(f"  Port: {port}")
    typer.echo(f"  Workers: {workers_effective}")
    typer.echo(f"  Log level: {log_level}")
    if reload:
        typer.echo("  Reload: enabled")
    typer.echo()
    typer.echo(f"API documentation: http://{host}:{port}/docs")
    typer.echo()

    # Run server
    uvicorn.run(
        app="titan.api.app:create_app",
        factory=True,
        host=host,
        port=port,
        reload=reload,
        workers=workers_effective,
        log_level=log_level.lower(),
        access_log=access_log,
    )

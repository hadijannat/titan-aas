"""Docker helpers for integration tests."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

if TYPE_CHECKING:
    from docker.client import DockerClient
    from docker.models.containers import Container
else:
    DockerClient = Any  # type: ignore[misc,assignment]
    Container = Any  # type: ignore[misc,assignment]


def get_docker_client() -> DockerClient:
    """Create a Docker client from environment settings."""
    import docker

    return docker.from_env()


def get_docker_host(client: DockerClient) -> str:
    """Resolve the host to connect to published container ports."""
    base_url = client.api.base_url
    if base_url.startswith(("unix://", "npipe://", "http+docker://")):
        return "localhost"
    parsed = urlparse(base_url)
    return parsed.hostname or "localhost"


@dataclass
class DockerService:
    """Handle for a running container and its connection info."""

    container: Container
    host: str

    def port(self, container_port: int, protocol: str = "tcp") -> int:
        """Get the bound host port for a container port."""
        self.container.reload()
        key = f"{container_port}/{protocol}"
        ports = self.container.attrs["NetworkSettings"]["Ports"].get(key)
        if not ports:
            raise RuntimeError(f"Port {key} not exposed on container {self.container.short_id}")
        return int(ports[0]["HostPort"])

    def stop(self) -> None:
        """Stop and remove the container."""
        self.container.remove(force=True, v=True)


@contextmanager
def run_container(
    client: DockerClient,
    image: str,
    *,
    env: dict[str, str] | None = None,
    ports: Mapping[str, int | None] | None = None,
    command: str | None = None,
) -> Iterator[DockerService]:
    """Run a container and yield a service handle."""
    container = client.containers.run(
        image,
        detach=True,
        environment=env,
        ports=ports,
        command=command,
    )
    service = DockerService(container=container, host=get_docker_host(client))
    try:
        yield service
    finally:
        service.stop()

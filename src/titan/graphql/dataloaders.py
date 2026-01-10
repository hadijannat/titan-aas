"""DataLoaders for N+1 query prevention.

Provides batch loading capabilities:
- ShellLoader: Batch load shells by identifier
- SubmodelLoader: Batch load submodels by identifier
- SubmodelsByShellLoader: Load submodels for multiple shells

Example:
    from titan.graphql.dataloaders import create_dataloaders

    @strawberry.type
    class Query:
        @strawberry.field
        async def shell(self, info: Info, id: str) -> Shell | None:
            loader = info.context["shell_loader"]
            return await loader.load(id)
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from strawberry.dataloader import DataLoader

from titan.graphql.schema import Shell, Submodel


async def load_shells(keys: list[str]) -> Sequence[Shell | None]:
    """Batch load shells by identifier.

    Args:
        keys: List of shell identifiers to load

    Returns:
        List of shells in same order as keys (None for not found)
    """
    # TODO: Implement actual database batch loading
    # This is a placeholder that returns empty results
    return [None] * len(keys)


async def load_submodels(keys: list[str]) -> Sequence[Submodel | None]:
    """Batch load submodels by identifier.

    Args:
        keys: List of submodel identifiers to load

    Returns:
        List of submodels in same order as keys (None for not found)
    """
    # TODO: Implement actual database batch loading
    return [None] * len(keys)


async def load_submodels_by_shell(
    shell_ids: list[str],
) -> Sequence[list[Submodel]]:
    """Batch load submodels for multiple shells.

    Args:
        shell_ids: List of shell identifiers

    Returns:
        List of submodel lists, one per shell
    """
    # TODO: Implement actual database batch loading
    return [[] for _ in shell_ids]


def create_dataloaders() -> dict[str, Any]:
    """Create fresh dataloaders for a request context.

    Returns:
        Dictionary of dataloaders keyed by name

    Example:
        @app.middleware("http")
        async def add_dataloaders(request, call_next):
            request.state.dataloaders = create_dataloaders()
            return await call_next(request)
    """
    return {
        "shell_loader": DataLoader(load_fn=load_shells),
        "submodel_loader": DataLoader(load_fn=load_submodels),
        "submodels_by_shell_loader": DataLoader(load_fn=load_submodels_by_shell),
    }


class DataLoaderContext:
    """Context class for GraphQL requests with dataloaders.

    Provides typed access to dataloaders and request context.
    """

    def __init__(self) -> None:
        """Initialize context with fresh dataloaders."""
        self._loaders = create_dataloaders()

    @property
    def shell_loader(self) -> DataLoader[str, Shell | None]:
        """Get the shell dataloader."""
        return self._loaders["shell_loader"]

    @property
    def submodel_loader(self) -> DataLoader[str, Submodel | None]:
        """Get the submodel dataloader."""
        return self._loaders["submodel_loader"]

    @property
    def submodels_by_shell_loader(self) -> DataLoader[str, list[Submodel]]:
        """Get the submodels-by-shell dataloader."""
        return self._loaders["submodels_by_shell_loader"]

"""DataLoaders for N+1 query prevention.

Provides batch loading capabilities:
- ShellLoader: Batch load shells by identifier
- SubmodelLoader: Batch load submodels by identifier
- SubmodelsByShellLoader: Load submodels for multiple shells

Example:
    from titan.graphql.dataloaders import DataLoaderContext

    async def get_context(session: AsyncSession = Depends(get_session)):
        return DataLoaderContext(session)

    @strawberry.type
    class Query:
        @strawberry.field
        async def shell(self, info: Info, id: str) -> Shell | None:
            ctx: DataLoaderContext = info.context
            return await ctx.shell_loader.load(id)
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from strawberry.dataloader import DataLoader

from titan.graphql.converters import shell_to_graphql, submodel_to_graphql
from titan.graphql.schema import Shell, Submodel
from titan.persistence.repositories import AasRepository, SubmodelRepository

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def load_shells(
    keys: list[str],
    session: AsyncSession,
) -> Sequence[Shell | None]:
    """Batch load shells by identifier.

    Args:
        keys: List of shell identifiers to load
        session: Database session for queries

    Returns:
        List of shells in same order as keys (None for not found)
    """
    repo = AasRepository(session)
    models = await repo.get_models_batch(keys)
    return [shell_to_graphql(models.get(key)) for key in keys]


async def load_submodels(
    keys: list[str],
    session: AsyncSession,
) -> Sequence[Submodel | None]:
    """Batch load submodels by identifier.

    Args:
        keys: List of submodel identifiers to load
        session: Database session for queries

    Returns:
        List of submodels in same order as keys (None for not found)
    """
    repo = SubmodelRepository(session)
    models = await repo.get_models_batch(keys)
    return [submodel_to_graphql(models.get(key)) for key in keys]


async def load_submodels_by_shell(
    shell_ids: list[str],
    session: AsyncSession,
) -> Sequence[list[Submodel]]:
    """Batch load submodels for multiple shells.

    Args:
        shell_ids: List of shell identifiers
        session: Database session for queries

    Returns:
        List of submodel lists, one per shell
    """
    repo = SubmodelRepository(session)
    shell_to_submodels = await repo.get_submodels_for_shells_batch(shell_ids)

    result: list[list[Submodel]] = []
    for shell_id in shell_ids:
        pydantic_submodels = shell_to_submodels.get(shell_id, [])
        graphql_submodels = [
            submodel_to_graphql(sm)
            for sm in pydantic_submodels
            if sm is not None
        ]
        # Filter out any None results from conversion
        result.append([sm for sm in graphql_submodels if sm is not None])

    return result


class DataLoaderContext:
    """Context class for GraphQL requests with dataloaders.

    Provides typed access to dataloaders and request context.
    Requires a database session for batch loading.
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize context with session and fresh dataloaders.

        Args:
            session: Database session for queries
        """
        self.session = session
        self._loaders = self._create_loaders()

    def _create_loaders(self) -> dict[str, DataLoader]:
        """Create dataloaders bound to this context's session."""
        return {
            "shell_loader": DataLoader(
                load_fn=lambda keys: load_shells(keys, self.session)
            ),
            "submodel_loader": DataLoader(
                load_fn=lambda keys: load_submodels(keys, self.session)
            ),
            "submodels_by_shell_loader": DataLoader(
                load_fn=lambda keys: load_submodels_by_shell(keys, self.session)
            ),
        }

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


# Backwards compatibility - create dataloaders without session
# (returns stub loaders for testing)
def create_dataloaders() -> dict[str, DataLoader]:
    """Create dataloaders without session (stub mode).

    This is provided for backwards compatibility and testing.
    For production use, create DataLoaderContext with a session.

    Returns:
        Dictionary of dataloaders that return empty results
    """
    async def stub_load_shells(keys: list[str]) -> Sequence[Shell | None]:
        return [None] * len(keys)

    async def stub_load_submodels(keys: list[str]) -> Sequence[Submodel | None]:
        return [None] * len(keys)

    async def stub_load_submodels_by_shell(
        shell_ids: list[str],
    ) -> Sequence[list[Submodel]]:
        return [[] for _ in shell_ids]

    return {
        "shell_loader": DataLoader(load_fn=stub_load_shells),
        "submodel_loader": DataLoader(load_fn=stub_load_submodels),
        "submodels_by_shell_loader": DataLoader(load_fn=stub_load_submodels_by_shell),
    }

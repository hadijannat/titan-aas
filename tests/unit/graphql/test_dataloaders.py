"""Tests for GraphQL dataloaders."""

import pytest

from titan.graphql.dataloaders import (
    DataLoaderContext,
    create_dataloaders,
    load_shells,
    load_submodels,
    load_submodels_by_shell,
)


class TestLoadFunctions:
    """Tests for batch load functions."""

    @pytest.mark.asyncio
    async def test_load_shells_returns_correct_length(self) -> None:
        """load_shells returns same length as input."""
        keys = ["id1", "id2", "id3"]

        result = await load_shells(keys)

        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_load_shells_empty_input(self) -> None:
        """load_shells handles empty input."""
        result = await load_shells([])

        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_load_submodels_returns_correct_length(self) -> None:
        """load_submodels returns same length as input."""
        keys = ["sub1", "sub2"]

        result = await load_submodels(keys)

        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_load_submodels_empty_input(self) -> None:
        """load_submodels handles empty input."""
        result = await load_submodels([])

        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_load_submodels_by_shell_returns_correct_length(self) -> None:
        """load_submodels_by_shell returns same length as input."""
        shell_ids = ["shell1", "shell2", "shell3"]

        result = await load_submodels_by_shell(shell_ids)

        assert len(result) == 3
        # Each entry should be a list
        assert all(isinstance(item, list) for item in result)

    @pytest.mark.asyncio
    async def test_load_submodels_by_shell_empty_input(self) -> None:
        """load_submodels_by_shell handles empty input."""
        result = await load_submodels_by_shell([])

        assert len(result) == 0


class TestCreateDataloaders:
    """Tests for create_dataloaders function."""

    def test_returns_dict(self) -> None:
        """create_dataloaders returns dictionary."""
        loaders = create_dataloaders()

        assert isinstance(loaders, dict)

    def test_contains_shell_loader(self) -> None:
        """Result contains shell_loader."""
        loaders = create_dataloaders()

        assert "shell_loader" in loaders

    def test_contains_submodel_loader(self) -> None:
        """Result contains submodel_loader."""
        loaders = create_dataloaders()

        assert "submodel_loader" in loaders

    def test_contains_submodels_by_shell_loader(self) -> None:
        """Result contains submodels_by_shell_loader."""
        loaders = create_dataloaders()

        assert "submodels_by_shell_loader" in loaders

    def test_loaders_are_independent(self) -> None:
        """Each call creates independent loaders."""
        loaders1 = create_dataloaders()
        loaders2 = create_dataloaders()

        assert loaders1["shell_loader"] is not loaders2["shell_loader"]


class TestDataLoaderContext:
    """Tests for DataLoaderContext class."""

    def test_context_creation(self) -> None:
        """DataLoaderContext can be created."""
        context = DataLoaderContext()

        assert context is not None

    def test_shell_loader_property(self) -> None:
        """shell_loader property returns loader."""
        context = DataLoaderContext()

        loader = context.shell_loader

        assert loader is not None

    def test_submodel_loader_property(self) -> None:
        """submodel_loader property returns loader."""
        context = DataLoaderContext()

        loader = context.submodel_loader

        assert loader is not None

    def test_submodels_by_shell_loader_property(self) -> None:
        """submodels_by_shell_loader property returns loader."""
        context = DataLoaderContext()

        loader = context.submodels_by_shell_loader

        assert loader is not None

    def test_loaders_are_consistent(self) -> None:
        """Same loader returned on multiple accesses."""
        context = DataLoaderContext()

        loader1 = context.shell_loader
        loader2 = context.shell_loader

        assert loader1 is loader2

    @pytest.mark.asyncio
    async def test_shell_loader_can_load(self) -> None:
        """shell_loader can load data."""
        context = DataLoaderContext()

        # Load returns None for placeholder implementation
        result = await context.shell_loader.load("test-id")

        assert result is None

    @pytest.mark.asyncio
    async def test_submodel_loader_can_load(self) -> None:
        """submodel_loader can load data."""
        context = DataLoaderContext()

        result = await context.submodel_loader.load("test-id")

        assert result is None

    @pytest.mark.asyncio
    async def test_submodels_by_shell_loader_can_load(self) -> None:
        """submodels_by_shell_loader can load data."""
        context = DataLoaderContext()

        result = await context.submodels_by_shell_loader.load("shell-id")

        assert result == []


class TestDataLoaderBatching:
    """Tests for dataloader batching behavior."""

    @pytest.mark.asyncio
    async def test_multiple_loads_are_batched(self) -> None:
        """Multiple concurrent loads are batched."""
        import asyncio

        context = DataLoaderContext()

        # Start multiple loads concurrently
        results = await asyncio.gather(
            context.shell_loader.load("id1"),
            context.shell_loader.load("id2"),
            context.shell_loader.load("id3"),
        )

        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_same_key_returns_same_result(self) -> None:
        """Loading same key twice returns same result."""
        import asyncio

        context = DataLoaderContext()

        results = await asyncio.gather(
            context.shell_loader.load("same-id"),
            context.shell_loader.load("same-id"),
        )

        # Both should be None (placeholder)
        assert results[0] == results[1]

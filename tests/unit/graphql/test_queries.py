"""Tests for GraphQL query execution."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from strawberry.types import ExecutionResult

from titan.graphql import schema
from titan.graphql.dataloaders import DataLoaderContext


@pytest.fixture
def mock_session() -> MagicMock:
    """Create a mock async session for tests."""
    session = MagicMock()
    # Mock execute to return empty results
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=mock_result)
    return session


@pytest.fixture
def mock_context(mock_session: MagicMock) -> DataLoaderContext:
    """Create a mock DataLoaderContext for tests."""
    return DataLoaderContext(mock_session)


class TestShellQueries:
    """Tests for shell query operations."""

    @pytest.mark.asyncio
    async def test_query_shells_empty(self, mock_context: DataLoaderContext) -> None:
        """Query shells returns empty connection."""
        query = """
            query {
                shells {
                    edges {
                        id
                    }
                    pageInfo {
                        hasNextPage
                        hasPreviousPage
                    }
                    totalCount
                }
            }
        """

        result: ExecutionResult = await schema.execute(query, context_value=mock_context)

        assert result.errors is None
        assert result.data["shells"]["edges"] == []
        assert result.data["shells"]["totalCount"] == 0
        assert result.data["shells"]["pageInfo"]["hasNextPage"] is False

    @pytest.mark.asyncio
    async def test_query_shells_with_filter(self, mock_context: DataLoaderContext) -> None:
        """Query shells with id_short filter."""
        query = """
            query {
                shells(idShort: "TestShell") {
                    edges {
                        id
                        idShort
                    }
                    totalCount
                }
            }
        """

        result: ExecutionResult = await schema.execute(query, context_value=mock_context)

        assert result.errors is None
        assert result.data["shells"]["edges"] == []

    @pytest.mark.asyncio
    async def test_query_shells_with_pagination(self, mock_context: DataLoaderContext) -> None:
        """Query shells with pagination parameters."""
        query = """
            query {
                shells(first: 10, after: "2024-01-01T00:00:00+00:00") {
                    edges {
                        id
                    }
                    pageInfo {
                        hasNextPage
                        startCursor
                        endCursor
                    }
                }
            }
        """

        result: ExecutionResult = await schema.execute(query, context_value=mock_context)

        assert result.errors is None
        assert result.data["shells"]["edges"] == []

    @pytest.mark.asyncio
    async def test_query_shells_with_asset_kind_filter(
        self, mock_context: DataLoaderContext
    ) -> None:
        """Query shells with asset kind filter."""
        query = """
            query {
                shells(assetKind: INSTANCE) {
                    edges {
                        id
                        assetInformation {
                            assetKind
                        }
                    }
                    totalCount
                }
            }
        """

        result: ExecutionResult = await schema.execute(query, context_value=mock_context)

        assert result.errors is None

    @pytest.mark.asyncio
    async def test_query_shell_by_id(self, mock_context: DataLoaderContext) -> None:
        """Query single shell by identifier."""
        query = """
            query {
                shell(id: "urn:example:aas:1") {
                    id
                    idShort
                    assetInformation {
                        assetKind
                        globalAssetId
                    }
                }
            }
        """

        result: ExecutionResult = await schema.execute(query, context_value=mock_context)

        assert result.errors is None
        # Returns None when not found
        assert result.data["shell"] is None

    @pytest.mark.asyncio
    async def test_query_shell_with_description(self, mock_context: DataLoaderContext) -> None:
        """Query shell with description field."""
        query = """
            query {
                shell(id: "urn:example:aas:1") {
                    id
                    description {
                        language
                        text
                    }
                }
            }
        """

        result: ExecutionResult = await schema.execute(query, context_value=mock_context)

        assert result.errors is None


class TestSubmodelQueries:
    """Tests for submodel query operations."""

    @pytest.mark.asyncio
    async def test_query_submodels_empty(self, mock_context: DataLoaderContext) -> None:
        """Query submodels returns empty connection."""
        query = """
            query {
                submodels {
                    edges {
                        id
                    }
                    pageInfo {
                        hasNextPage
                    }
                    totalCount
                }
            }
        """

        result: ExecutionResult = await schema.execute(query, context_value=mock_context)

        assert result.errors is None
        assert result.data["submodels"]["edges"] == []
        assert result.data["submodels"]["totalCount"] == 0

    @pytest.mark.asyncio
    async def test_query_submodels_with_semantic_id_filter(
        self, mock_context: DataLoaderContext
    ) -> None:
        """Query submodels with semantic ID filter."""
        query = """
            query {
                submodels(semanticId: "urn:example:semantic:1") {
                    edges {
                        id
                        idShort
                    }
                    totalCount
                }
            }
        """

        result: ExecutionResult = await schema.execute(query, context_value=mock_context)

        assert result.errors is None

    @pytest.mark.asyncio
    async def test_query_submodels_with_id_short_filter(
        self, mock_context: DataLoaderContext
    ) -> None:
        """Query submodels with id_short filter."""
        query = """
            query {
                submodels(idShort: "TechnicalData") {
                    edges {
                        id
                        idShort
                    }
                }
            }
        """

        result: ExecutionResult = await schema.execute(query, context_value=mock_context)

        assert result.errors is None

    @pytest.mark.asyncio
    async def test_query_submodel_by_id(self, mock_context: DataLoaderContext) -> None:
        """Query single submodel by identifier."""
        query = """
            query {
                submodel(id: "urn:example:submodel:1") {
                    id
                    idShort
                    kind
                    administration {
                        version
                        revision
                    }
                }
            }
        """

        result: ExecutionResult = await schema.execute(query, context_value=mock_context)

        assert result.errors is None
        # Returns None when not found
        assert result.data["submodel"] is None

    @pytest.mark.asyncio
    async def test_query_submodel_with_elements(self, mock_context: DataLoaderContext) -> None:
        """Query submodel with submodel elements."""
        query = """
            query {
                submodel(id: "urn:example:submodel:1") {
                    id
                    submodelElements {
                        ... on Property {
                            idShort
                            valueType
                            value
                        }
                        ... on Range {
                            idShort
                            min
                            max
                        }
                    }
                }
            }
        """

        result: ExecutionResult = await schema.execute(query, context_value=mock_context)

        assert result.errors is None


class TestNestedQueries:
    """Tests for nested query operations."""

    @pytest.mark.asyncio
    async def test_query_shell_with_submodels(self, mock_context: DataLoaderContext) -> None:
        """Query shell with nested submodels."""
        query = """
            query {
                shell(id: "urn:example:aas:1") {
                    id
                    submodels {
                        id
                        idShort
                    }
                }
            }
        """

        result: ExecutionResult = await schema.execute(query, context_value=mock_context)

        assert result.errors is None

    @pytest.mark.asyncio
    async def test_query_deeply_nested_structure(self, mock_context: DataLoaderContext) -> None:
        """Query with deeply nested structure."""
        query = """
            query {
                shells {
                    edges {
                        id
                        assetInformation {
                            assetKind
                            globalAssetId
                        }
                        administration {
                            version
                        }
                    }
                    pageInfo {
                        hasNextPage
                        hasPreviousPage
                        startCursor
                        endCursor
                    }
                }
            }
        """

        result: ExecutionResult = await schema.execute(query, context_value=mock_context)

        assert result.errors is None


class TestQueryValidation:
    """Tests for query validation."""

    @pytest.mark.asyncio
    async def test_invalid_field_name(self, mock_context: DataLoaderContext) -> None:
        """Invalid field name returns error."""
        query = """
            query {
                shells {
                    invalidField
                }
            }
        """

        result: ExecutionResult = await schema.execute(query, context_value=mock_context)

        assert result.errors is not None
        assert len(result.errors) > 0

    @pytest.mark.asyncio
    async def test_invalid_argument(self, mock_context: DataLoaderContext) -> None:
        """Invalid argument returns error."""
        query = """
            query {
                shells(invalidArg: "test") {
                    edges {
                        id
                    }
                }
            }
        """

        result: ExecutionResult = await schema.execute(query, context_value=mock_context)

        assert result.errors is not None

    @pytest.mark.asyncio
    async def test_missing_required_selection(self, mock_context: DataLoaderContext) -> None:
        """Missing required selection set returns error."""
        query = """
            query {
                shells
            }
        """

        result: ExecutionResult = await schema.execute(query, context_value=mock_context)

        assert result.errors is not None


class TestFragments:
    """Tests for GraphQL fragments."""

    @pytest.mark.asyncio
    async def test_query_with_fragment(self, mock_context: DataLoaderContext) -> None:
        """Query using fragments."""
        query = """
            fragment ShellFields on Shell {
                id
                idShort
                assetInformation {
                    assetKind
                }
            }

            query {
                shell(id: "urn:example:aas:1") {
                    ...ShellFields
                }
            }
        """

        result: ExecutionResult = await schema.execute(query, context_value=mock_context)

        assert result.errors is None

    @pytest.mark.asyncio
    async def test_query_with_inline_fragment(self, mock_context: DataLoaderContext) -> None:
        """Query using inline fragments."""
        query = """
            query {
                submodel(id: "urn:example:submodel:1") {
                    submodelElements {
                        ... on Property {
                            modelType
                            idShort
                            value
                        }
                        ... on Blob {
                            modelType
                            idShort
                            contentType
                        }
                    }
                }
            }
        """

        result: ExecutionResult = await schema.execute(query, context_value=mock_context)

        assert result.errors is None

"""Tests for GraphQL mutation execution."""

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
    # Mock all async session methods
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    return session


@pytest.fixture
def mock_user() -> MagicMock:
    """Create a mock user with all permissions for tests."""
    user = MagicMock()
    # Mock user properties
    user.id = "test-user-id"
    user.email = "test@example.com"
    user.roles = ["admin"]
    return user


@pytest.fixture
def mock_context(mock_session: MagicMock, mock_user: MagicMock) -> DataLoaderContext:
    """Create a mock DataLoaderContext for tests."""
    return DataLoaderContext(mock_session, user=mock_user)


class TestShellMutations:
    """Tests for shell mutation operations."""

    @pytest.mark.asyncio
    async def test_create_shell(self, mock_context: DataLoaderContext) -> None:
        """Create shell mutation."""
        query = """
            mutation {
                createShell(input: {
                    id: "urn:example:aas:new"
                    idShort: "NewShell"
                    assetKind: INSTANCE
                    globalAssetId: "urn:example:asset:1"
                }) {
                    success
                    shell {
                        id
                        idShort
                        assetInformation {
                            assetKind
                            globalAssetId
                        }
                    }
                    error {
                        code
                        message
                    }
                }
            }
        """

        result: ExecutionResult = await schema.execute(query, context_value=mock_context)

        assert result.errors is None
        assert result.data["createShell"]["success"] is True
        assert result.data["createShell"]["shell"]["id"] == "urn:example:aas:new"
        assert result.data["createShell"]["shell"]["idShort"] == "NewShell"
        assert result.data["createShell"]["shell"]["assetInformation"]["assetKind"] == "INSTANCE"
        assert (
            result.data["createShell"]["shell"]["assetInformation"]["globalAssetId"]
            == "urn:example:asset:1"
        )

    @pytest.mark.asyncio
    async def test_create_shell_minimal(self, mock_context: DataLoaderContext) -> None:
        """Create shell with minimal fields."""
        query = """
            mutation {
                createShell(input: {
                    id: "urn:example:aas:minimal"
                }) {
                    success
                    shell {
                        id
                        idShort
                        assetInformation {
                            assetKind
                        }
                    }
                }
            }
        """

        result: ExecutionResult = await schema.execute(query, context_value=mock_context)

        assert result.errors is None
        assert result.data["createShell"]["success"] is True
        assert result.data["createShell"]["shell"]["id"] == "urn:example:aas:minimal"
        assert result.data["createShell"]["shell"]["idShort"] is None
        # Default asset kind is INSTANCE
        assert result.data["createShell"]["shell"]["assetInformation"]["assetKind"] == "INSTANCE"

    @pytest.mark.asyncio
    async def test_create_shell_with_type_asset(self, mock_context: DataLoaderContext) -> None:
        """Create shell with TYPE asset kind."""
        query = """
            mutation {
                createShell(input: {
                    id: "urn:example:aas:type"
                    assetKind: TYPE
                }) {
                    success
                    shell {
                        id
                        assetInformation {
                            assetKind
                        }
                    }
                }
            }
        """

        result: ExecutionResult = await schema.execute(query, context_value=mock_context)

        assert result.errors is None
        assert result.data["createShell"]["success"] is True
        assert result.data["createShell"]["shell"]["assetInformation"]["assetKind"] == "TYPE"

    @pytest.mark.asyncio
    async def test_delete_shell(self, mock_context: DataLoaderContext) -> None:
        """Delete shell mutation."""
        query = """
            mutation {
                deleteShell(id: "urn:example:aas:1") {
                    success
                    id
                }
            }
        """

        result: ExecutionResult = await schema.execute(query, context_value=mock_context)

        assert result.errors is None
        assert result.data["deleteShell"]["success"] is True

    @pytest.mark.asyncio
    async def test_delete_shell_returns_boolean(self, mock_context: DataLoaderContext) -> None:
        """Delete shell returns boolean result."""
        query = """
            mutation DeleteShell($id: String!) {
                deleteShell(id: $id) {
                    success
                    id
                }
            }
        """

        result: ExecutionResult = await schema.execute(
            query, context_value=mock_context, variable_values={"id": "urn:example:aas:delete"}
        )

        assert result.errors is None
        assert result.data["deleteShell"]["success"] is True


class TestSubmodelMutations:
    """Tests for submodel mutation operations."""

    @pytest.mark.asyncio
    async def test_create_submodel(self, mock_context: DataLoaderContext) -> None:
        """Create submodel mutation."""
        query = """
            mutation {
                createSubmodel(input: {
                    id: "urn:example:submodel:new"
                    idShort: "TechnicalData"
                    semanticId: "urn:example:semantic:1"
                }) {
                    success
                    submodel {
                        id
                        idShort
                    }
                }
            }
        """

        result: ExecutionResult = await schema.execute(query, context_value=mock_context)

        assert result.errors is None
        assert result.data["createSubmodel"]["success"] is True
        assert result.data["createSubmodel"]["submodel"]["id"] == "urn:example:submodel:new"
        assert result.data["createSubmodel"]["submodel"]["idShort"] == "TechnicalData"

    @pytest.mark.asyncio
    async def test_create_submodel_minimal(self, mock_context: DataLoaderContext) -> None:
        """Create submodel with minimal fields."""
        query = """
            mutation {
                createSubmodel(input: {
                    id: "urn:example:submodel:minimal"
                }) {
                    success
                    submodel {
                        id
                        idShort
                    }
                }
            }
        """

        result: ExecutionResult = await schema.execute(query, context_value=mock_context)

        assert result.errors is None
        assert result.data["createSubmodel"]["success"] is True
        assert result.data["createSubmodel"]["submodel"]["id"] == "urn:example:submodel:minimal"
        assert result.data["createSubmodel"]["submodel"]["idShort"] is None

    @pytest.mark.asyncio
    async def test_delete_submodel(self, mock_context: DataLoaderContext) -> None:
        """Delete submodel mutation."""
        query = """
            mutation {
                deleteSubmodel(id: "urn:example:submodel:1") {
                    success
                    id
                }
            }
        """

        result: ExecutionResult = await schema.execute(query, context_value=mock_context)

        assert result.errors is None
        assert result.data["deleteSubmodel"]["success"] is True


class TestMutationWithVariables:
    """Tests for mutations using variables."""

    @pytest.mark.asyncio
    async def test_create_shell_with_variables(self, mock_context: DataLoaderContext) -> None:
        """Create shell using query variables."""
        query = """
            mutation CreateShell($input: ShellInput!) {
                createShell(input: $input) {
                    success
                    shell {
                        id
                        idShort
                        assetInformation {
                            assetKind
                        }
                    }
                }
            }
        """

        variables = {
            "input": {
                "id": "urn:example:aas:variable",
                "idShort": "VariableShell",
                "assetKind": "INSTANCE",
            }
        }

        result: ExecutionResult = await schema.execute(
            query, context_value=mock_context, variable_values=variables
        )

        assert result.errors is None
        assert result.data["createShell"]["success"] is True
        assert result.data["createShell"]["shell"]["id"] == "urn:example:aas:variable"
        assert result.data["createShell"]["shell"]["idShort"] == "VariableShell"

    @pytest.mark.asyncio
    async def test_create_submodel_with_variables(self, mock_context: DataLoaderContext) -> None:
        """Create submodel using query variables."""
        query = """
            mutation CreateSubmodel($input: SubmodelInput!) {
                createSubmodel(input: $input) {
                    success
                    submodel {
                        id
                        idShort
                    }
                }
            }
        """

        variables = {
            "input": {
                "id": "urn:example:submodel:variable",
                "idShort": "VariableSubmodel",
            }
        }

        result: ExecutionResult = await schema.execute(
            query, context_value=mock_context, variable_values=variables
        )

        assert result.errors is None
        assert result.data["createSubmodel"]["success"] is True
        assert result.data["createSubmodel"]["submodel"]["id"] == "urn:example:submodel:variable"


class TestMutationValidation:
    """Tests for mutation validation."""

    @pytest.mark.asyncio
    async def test_create_shell_missing_required_field(self) -> None:
        """Create shell without required id field fails."""
        query = """
            mutation {
                createShell(input: {
                    idShort: "NoId"
                }) {
                    id
                }
            }
        """

        result: ExecutionResult = await schema.execute(query, context_value=mock_context)

        assert result.errors is not None

    @pytest.mark.asyncio
    async def test_create_submodel_missing_required_field(self) -> None:
        """Create submodel without required id field fails."""
        query = """
            mutation {
                createSubmodel(input: {
                    idShort: "NoId"
                }) {
                    id
                }
            }
        """

        result: ExecutionResult = await schema.execute(query, context_value=mock_context)

        assert result.errors is not None

    @pytest.mark.asyncio
    async def test_invalid_asset_kind_value(self) -> None:
        """Invalid asset kind enum value fails."""
        query = """
            mutation {
                createShell(input: {
                    id: "urn:example:aas:1"
                    assetKind: INVALID
                }) {
                    id
                }
            }
        """

        result: ExecutionResult = await schema.execute(query, context_value=mock_context)

        assert result.errors is not None


class TestMutationSequence:
    """Tests for mutation sequences."""

    @pytest.mark.asyncio
    async def test_create_and_delete_shell(self, mock_context: DataLoaderContext) -> None:
        """Create then delete shell in sequence."""
        create_query = """
            mutation {
                createShell(input: {
                    id: "urn:example:aas:sequence"
                }) {
                    success
                    shell {
                        id
                    }
                }
            }
        """

        result = await schema.execute(create_query, context_value=mock_context)
        assert result.errors is None
        assert result.data["createShell"]["success"] is True

        delete_query = """
            mutation {
                deleteShell(id: "urn:example:aas:sequence") {
                    success
                }
            }
        """

        result = await schema.execute(delete_query, context_value=mock_context)
        assert result.errors is None
        assert result.data["deleteShell"]["success"] is True

    @pytest.mark.asyncio
    async def test_multiple_mutations_in_one_request(self, mock_context: DataLoaderContext) -> None:
        """Multiple mutations in single request."""
        query = """
            mutation {
                shell1: createShell(input: { id: "urn:example:aas:1" }) {
                    success
                    shell {
                        id
                    }
                }
                shell2: createShell(input: { id: "urn:example:aas:2" }) {
                    success
                    shell {
                        id
                    }
                }
            }
        """

        result: ExecutionResult = await schema.execute(query, context_value=mock_context)

        assert result.errors is None
        assert result.data["shell1"]["success"] is True
        assert result.data["shell1"]["shell"]["id"] == "urn:example:aas:1"
        assert result.data["shell2"]["success"] is True
        assert result.data["shell2"]["shell"]["id"] == "urn:example:aas:2"

"""Tests for GraphQL mutation execution."""

import pytest
from strawberry.types import ExecutionResult

from titan.graphql import schema


class TestShellMutations:
    """Tests for shell mutation operations."""

    @pytest.mark.asyncio
    async def test_create_shell(self) -> None:
        """Create shell mutation."""
        query = """
            mutation {
                createShell(input: {
                    id: "urn:example:aas:new"
                    idShort: "NewShell"
                    assetKind: INSTANCE
                    globalAssetId: "urn:example:asset:1"
                }) {
                    id
                    idShort
                    assetInformation {
                        assetKind
                        globalAssetId
                    }
                }
            }
        """

        result: ExecutionResult = await schema.execute(query)

        assert result.errors is None
        assert result.data["createShell"]["id"] == "urn:example:aas:new"
        assert result.data["createShell"]["idShort"] == "NewShell"
        assert result.data["createShell"]["assetInformation"]["assetKind"] == "INSTANCE"
        assert (
            result.data["createShell"]["assetInformation"]["globalAssetId"] == "urn:example:asset:1"
        )

    @pytest.mark.asyncio
    async def test_create_shell_minimal(self) -> None:
        """Create shell with minimal fields."""
        query = """
            mutation {
                createShell(input: {
                    id: "urn:example:aas:minimal"
                }) {
                    id
                    idShort
                    assetInformation {
                        assetKind
                    }
                }
            }
        """

        result: ExecutionResult = await schema.execute(query)

        assert result.errors is None
        assert result.data["createShell"]["id"] == "urn:example:aas:minimal"
        assert result.data["createShell"]["idShort"] is None
        # Default asset kind is INSTANCE
        assert result.data["createShell"]["assetInformation"]["assetKind"] == "INSTANCE"

    @pytest.mark.asyncio
    async def test_create_shell_with_type_asset(self) -> None:
        """Create shell with TYPE asset kind."""
        query = """
            mutation {
                createShell(input: {
                    id: "urn:example:aas:type"
                    assetKind: TYPE
                }) {
                    id
                    assetInformation {
                        assetKind
                    }
                }
            }
        """

        result: ExecutionResult = await schema.execute(query)

        assert result.errors is None
        assert result.data["createShell"]["assetInformation"]["assetKind"] == "TYPE"

    @pytest.mark.asyncio
    async def test_delete_shell(self) -> None:
        """Delete shell mutation."""
        query = """
            mutation {
                deleteShell(id: "urn:example:aas:1")
            }
        """

        result: ExecutionResult = await schema.execute(query)

        assert result.errors is None
        # Placeholder returns True
        assert result.data["deleteShell"] is True

    @pytest.mark.asyncio
    async def test_delete_shell_returns_boolean(self) -> None:
        """Delete shell returns boolean result."""
        query = """
            mutation DeleteShell($id: String!) {
                deleteShell(id: $id)
            }
        """

        result: ExecutionResult = await schema.execute(
            query, variable_values={"id": "urn:example:aas:delete"}
        )

        assert result.errors is None
        assert isinstance(result.data["deleteShell"], bool)


class TestSubmodelMutations:
    """Tests for submodel mutation operations."""

    @pytest.mark.asyncio
    async def test_create_submodel(self) -> None:
        """Create submodel mutation."""
        query = """
            mutation {
                createSubmodel(input: {
                    id: "urn:example:submodel:new"
                    idShort: "TechnicalData"
                    semanticId: "urn:example:semantic:1"
                }) {
                    id
                    idShort
                }
            }
        """

        result: ExecutionResult = await schema.execute(query)

        assert result.errors is None
        assert result.data["createSubmodel"]["id"] == "urn:example:submodel:new"
        assert result.data["createSubmodel"]["idShort"] == "TechnicalData"

    @pytest.mark.asyncio
    async def test_create_submodel_minimal(self) -> None:
        """Create submodel with minimal fields."""
        query = """
            mutation {
                createSubmodel(input: {
                    id: "urn:example:submodel:minimal"
                }) {
                    id
                    idShort
                }
            }
        """

        result: ExecutionResult = await schema.execute(query)

        assert result.errors is None
        assert result.data["createSubmodel"]["id"] == "urn:example:submodel:minimal"
        assert result.data["createSubmodel"]["idShort"] is None

    @pytest.mark.asyncio
    async def test_delete_submodel(self) -> None:
        """Delete submodel mutation."""
        query = """
            mutation {
                deleteSubmodel(id: "urn:example:submodel:1")
            }
        """

        result: ExecutionResult = await schema.execute(query)

        assert result.errors is None
        assert result.data["deleteSubmodel"] is True


class TestMutationWithVariables:
    """Tests for mutations using variables."""

    @pytest.mark.asyncio
    async def test_create_shell_with_variables(self) -> None:
        """Create shell using query variables."""
        query = """
            mutation CreateShell($input: ShellInput!) {
                createShell(input: $input) {
                    id
                    idShort
                    assetInformation {
                        assetKind
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

        result: ExecutionResult = await schema.execute(query, variable_values=variables)

        assert result.errors is None
        assert result.data["createShell"]["id"] == "urn:example:aas:variable"
        assert result.data["createShell"]["idShort"] == "VariableShell"

    @pytest.mark.asyncio
    async def test_create_submodel_with_variables(self) -> None:
        """Create submodel using query variables."""
        query = """
            mutation CreateSubmodel($input: SubmodelInput!) {
                createSubmodel(input: $input) {
                    id
                    idShort
                }
            }
        """

        variables = {
            "input": {
                "id": "urn:example:submodel:variable",
                "idShort": "VariableSubmodel",
            }
        }

        result: ExecutionResult = await schema.execute(query, variable_values=variables)

        assert result.errors is None
        assert result.data["createSubmodel"]["id"] == "urn:example:submodel:variable"


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

        result: ExecutionResult = await schema.execute(query)

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

        result: ExecutionResult = await schema.execute(query)

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

        result: ExecutionResult = await schema.execute(query)

        assert result.errors is not None


class TestMutationSequence:
    """Tests for mutation sequences."""

    @pytest.mark.asyncio
    async def test_create_and_delete_shell(self) -> None:
        """Create then delete shell in sequence."""
        create_query = """
            mutation {
                createShell(input: {
                    id: "urn:example:aas:sequence"
                }) {
                    id
                }
            }
        """

        result = await schema.execute(create_query)
        assert result.errors is None

        delete_query = """
            mutation {
                deleteShell(id: "urn:example:aas:sequence")
            }
        """

        result = await schema.execute(delete_query)
        assert result.errors is None
        assert result.data["deleteShell"] is True

    @pytest.mark.asyncio
    async def test_multiple_mutations_in_one_request(self) -> None:
        """Multiple mutations in single request."""
        query = """
            mutation {
                shell1: createShell(input: { id: "urn:example:aas:1" }) {
                    id
                }
                shell2: createShell(input: { id: "urn:example:aas:2" }) {
                    id
                }
            }
        """

        result: ExecutionResult = await schema.execute(query)

        assert result.errors is None
        assert result.data["shell1"]["id"] == "urn:example:aas:1"
        assert result.data["shell2"]["id"] == "urn:example:aas:2"

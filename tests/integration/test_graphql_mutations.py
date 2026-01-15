"""Integration tests for GraphQL mutations.

Tests the GraphQL mutation API with real database and GraphQL execution.

NOTE: These tests are currently skipped in CI because they require
authentication setup. Enable after implementing auth in integration tests.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

# Skip all tests in this module until authentication is properly configured
pytestmark = pytest.mark.skip(
    reason="GraphQL mutations require authentication - TODO: add auth setup"
)


@pytest.mark.asyncio
async def test_create_shell_mutation_success(
    test_client: AsyncClient,
    session: AsyncSession,
) -> None:
    """Test successful shell creation via GraphQL mutation."""
    mutation = """
        mutation CreateShell($input: ShellInput!) {
            createShell(input: $input) {
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

    variables = {
        "input": {
            "id": "https://example.com/shells/test-shell-1",
            "idShort": "TestShell",
            "assetKind": "INSTANCE",
            "globalAssetId": "https://example.com/assets/test-asset-1",
        }
    }

    response = await test_client.post(
        "/graphql",
        json={"query": mutation, "variables": variables},
    )

    assert response.status_code == 200
    data = response.json()

    # Check for GraphQL errors
    assert "errors" not in data, f"GraphQL errors: {data.get('errors')}"

    # Check mutation result
    result = data["data"]["createShell"]
    assert result["success"] is True
    assert result["error"] is None
    assert result["shell"] is not None
    assert result["shell"]["id"] == "https://example.com/shells/test-shell-1"
    assert result["shell"]["idShort"] == "TestShell"
    assert result["shell"]["assetInformation"]["assetKind"] == "INSTANCE"
    assert (
        result["shell"]["assetInformation"]["globalAssetId"]
        == "https://example.com/assets/test-asset-1"
    )


@pytest.mark.asyncio
async def test_create_shell_mutation_duplicate_id(
    test_client: AsyncClient,
    session: AsyncSession,
) -> None:
    """Test shell creation with duplicate ID returns error."""
    mutation = """
        mutation CreateShell($input: ShellInput!) {
            createShell(input: $input) {
                success
                shell {
                    id
                }
                error {
                    code
                    message
                }
            }
        }
    """

    variables = {
        "input": {
            "id": "https://example.com/shells/duplicate-test",
            "idShort": "DuplicateShell",
            "assetKind": "INSTANCE",
            "globalAssetId": "https://example.com/assets/duplicate-test",
        }
    }

    # Create first shell
    response1 = await test_client.post(
        "/graphql",
        json={"query": mutation, "variables": variables},
    )
    assert response1.status_code == 200
    result1 = response1.json()["data"]["createShell"]
    assert result1["success"] is True

    # Attempt to create duplicate
    response2 = await test_client.post(
        "/graphql",
        json={"query": mutation, "variables": variables},
    )
    assert response2.status_code == 200
    result2 = response2.json()["data"]["createShell"]

    # Should return error, not success
    assert result2["success"] is False
    assert result2["shell"] is None
    assert result2["error"] is not None
    assert result2["error"]["code"] == "DUPLICATE_ID"


@pytest.mark.asyncio
async def test_delete_shell_mutation_success(
    test_client: AsyncClient,
    session: AsyncSession,
) -> None:
    """Test successful shell deletion via GraphQL mutation."""
    # First create a shell
    create_mutation = """
        mutation CreateShell($input: ShellInput!) {
            createShell(input: $input) {
                success
                shell {
                    id
                }
            }
        }
    """

    create_variables = {
        "input": {
            "id": "https://example.com/shells/to-delete",
            "idShort": "ToDelete",
            "assetKind": "INSTANCE",
        }
    }

    create_response = await test_client.post(
        "/graphql",
        json={"query": create_mutation, "variables": create_variables},
    )
    assert create_response.status_code == 200
    assert create_response.json()["data"]["createShell"]["success"] is True

    # Now delete it
    delete_mutation = """
        mutation DeleteShell($id: String!) {
            deleteShell(id: $id) {
                success
                id
                error {
                    code
                    message
                }
            }
        }
    """

    delete_variables = {"id": "https://example.com/shells/to-delete"}

    delete_response = await test_client.post(
        "/graphql",
        json={"query": delete_mutation, "variables": delete_variables},
    )

    assert delete_response.status_code == 200
    result = delete_response.json()["data"]["deleteShell"]
    assert result["success"] is True
    assert result["id"] == "https://example.com/shells/to-delete"
    assert result["error"] is None


@pytest.mark.asyncio
async def test_delete_shell_mutation_not_found(
    test_client: AsyncClient,
    session: AsyncSession,
) -> None:
    """Test deletion of non-existent shell returns error."""
    delete_mutation = """
        mutation DeleteShell($id: String!) {
            deleteShell(id: $id) {
                success
                id
                error {
                    code
                    message
                }
            }
        }
    """

    variables = {"id": "https://example.com/shells/non-existent"}

    response = await test_client.post(
        "/graphql",
        json={"query": delete_mutation, "variables": variables},
    )

    assert response.status_code == 200
    result = response.json()["data"]["deleteShell"]
    assert result["success"] is False
    assert result["error"] is not None
    assert result["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_create_submodel_mutation_success(
    test_client: AsyncClient,
    session: AsyncSession,
) -> None:
    """Test successful submodel creation via GraphQL mutation."""
    mutation = """
        mutation CreateSubmodel($input: SubmodelInput!) {
            createSubmodel(input: $input) {
                success
                submodel {
                    id
                    idShort
                }
                error {
                    code
                    message
                }
            }
        }
    """

    variables = {
        "input": {
            "id": "https://example.com/submodels/test-submodel-1",
            "idShort": "TestSubmodel",
        }
    }

    response = await test_client.post(
        "/graphql",
        json={"query": mutation, "variables": variables},
    )

    assert response.status_code == 200
    data = response.json()

    assert "errors" not in data
    result = data["data"]["createSubmodel"]
    assert result["success"] is True
    assert result["error"] is None
    assert result["submodel"] is not None
    assert result["submodel"]["id"] == "https://example.com/submodels/test-submodel-1"
    assert result["submodel"]["idShort"] == "TestSubmodel"

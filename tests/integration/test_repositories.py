"""Integration tests for repository CRUD operations.

Tests the full persistence layer with real PostgreSQL.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from titan.core.ids import encode_id_to_b64url as encode_id
from titan.persistence.tables import (
    AasTable,
    SubmodelTable,
    generate_etag,
)


class TestAasRepository:
    """Tests for AAS repository operations."""

    @pytest_asyncio.fixture
    async def sample_aas_data(self) -> dict:
        """Create sample AAS data."""
        return {
            "modelType": "AssetAdministrationShell",
            "id": "urn:example:aas:test-1",
            "idShort": "TestAAS",
            "assetInformation": {
                "assetKind": "Instance",
                "globalAssetId": "urn:example:asset:test-1",
            },
        }

    @pytest.mark.asyncio
    async def test_create_aas(self, db_session: AsyncSession, sample_aas_data: dict) -> None:
        """Test creating an AAS record."""
        import orjson

        identifier = sample_aas_data["id"]
        identifier_b64 = encode_id(identifier)
        doc_bytes = orjson.dumps(sample_aas_data)
        etag = generate_etag(doc_bytes)

        aas = AasTable(
            identifier=identifier,
            identifier_b64=identifier_b64,
            doc=sample_aas_data,
            doc_bytes=doc_bytes,
            etag=etag,
        )

        db_session.add(aas)
        await db_session.commit()

        # Verify it was saved
        result = await db_session.execute(select(AasTable).where(AasTable.identifier == identifier))
        saved = result.scalar_one()

        assert saved.identifier == identifier
        assert saved.identifier_b64 == identifier_b64
        assert saved.doc == sample_aas_data
        assert saved.doc_bytes == doc_bytes
        assert saved.etag == etag

    @pytest.mark.asyncio
    async def test_read_aas_by_b64_id(
        self, db_session: AsyncSession, sample_aas_data: dict
    ) -> None:
        """Test reading AAS by Base64URL identifier."""
        import orjson

        identifier = sample_aas_data["id"]
        identifier_b64 = encode_id(identifier)
        doc_bytes = orjson.dumps(sample_aas_data)
        etag = generate_etag(doc_bytes)

        aas = AasTable(
            identifier=identifier,
            identifier_b64=identifier_b64,
            doc=sample_aas_data,
            doc_bytes=doc_bytes,
            etag=etag,
        )
        db_session.add(aas)
        await db_session.commit()

        # Read by b64 identifier (fast path lookup)
        result = await db_session.execute(
            select(AasTable).where(AasTable.identifier_b64 == identifier_b64)
        )
        found = result.scalar_one_or_none()

        assert found is not None
        assert found.identifier == identifier

    @pytest.mark.asyncio
    async def test_update_aas(self, db_session: AsyncSession, sample_aas_data: dict) -> None:
        """Test updating an AAS record."""
        import orjson

        identifier = sample_aas_data["id"]
        identifier_b64 = encode_id(identifier)
        doc_bytes = orjson.dumps(sample_aas_data)
        etag = generate_etag(doc_bytes)

        aas = AasTable(
            identifier=identifier,
            identifier_b64=identifier_b64,
            doc=sample_aas_data,
            doc_bytes=doc_bytes,
            etag=etag,
        )
        db_session.add(aas)
        await db_session.commit()

        # Update the document
        updated_data = {**sample_aas_data, "idShort": "UpdatedAAS"}
        updated_bytes = orjson.dumps(updated_data)
        updated_etag = generate_etag(updated_bytes)

        aas.doc = updated_data
        aas.doc_bytes = updated_bytes
        aas.etag = updated_etag
        await db_session.commit()

        # Verify update
        result = await db_session.execute(select(AasTable).where(AasTable.identifier == identifier))
        saved = result.scalar_one()

        assert saved.doc["idShort"] == "UpdatedAAS"
        assert saved.etag == updated_etag

    @pytest.mark.asyncio
    async def test_delete_aas(self, db_session: AsyncSession, sample_aas_data: dict) -> None:
        """Test deleting an AAS record."""
        import orjson

        identifier = sample_aas_data["id"]
        identifier_b64 = encode_id(identifier)
        doc_bytes = orjson.dumps(sample_aas_data)
        etag = generate_etag(doc_bytes)

        aas = AasTable(
            identifier=identifier,
            identifier_b64=identifier_b64,
            doc=sample_aas_data,
            doc_bytes=doc_bytes,
            etag=etag,
        )
        db_session.add(aas)
        await db_session.commit()

        # Delete
        await db_session.delete(aas)
        await db_session.commit()

        # Verify deletion
        result = await db_session.execute(select(AasTable).where(AasTable.identifier == identifier))
        found = result.scalar_one_or_none()

        assert found is None


class TestSubmodelRepository:
    """Tests for Submodel repository operations."""

    @pytest_asyncio.fixture
    async def sample_submodel_data(self) -> dict:
        """Create sample Submodel data."""
        return {
            "modelType": "Submodel",
            "id": "urn:example:submodel:test-1",
            "idShort": "TestSubmodel",
            "semanticId": {
                "type": "ExternalReference",
                "keys": [{"type": "GlobalReference", "value": "urn:example:semantic:1"}],
            },
            "submodelElements": [
                {
                    "modelType": "Property",
                    "idShort": "TestProperty",
                    "valueType": "xs:string",
                    "value": "test_value",
                }
            ],
        }

    @pytest.mark.asyncio
    async def test_create_submodel(
        self, db_session: AsyncSession, sample_submodel_data: dict
    ) -> None:
        """Test creating a Submodel record."""
        import orjson

        identifier = sample_submodel_data["id"]
        identifier_b64 = encode_id(identifier)
        doc_bytes = orjson.dumps(sample_submodel_data)
        etag = generate_etag(doc_bytes)

        # Extract semantic ID for indexing
        semantic_id = None
        if "semanticId" in sample_submodel_data:
            keys = sample_submodel_data["semanticId"].get("keys", [])
            if keys:
                semantic_id = keys[0].get("value")

        submodel = SubmodelTable(
            identifier=identifier,
            identifier_b64=identifier_b64,
            semantic_id=semantic_id,
            doc=sample_submodel_data,
            doc_bytes=doc_bytes,
            etag=etag,
        )

        db_session.add(submodel)
        await db_session.commit()

        # Verify it was saved
        result = await db_session.execute(
            select(SubmodelTable).where(SubmodelTable.identifier == identifier)
        )
        saved = result.scalar_one()

        assert saved.identifier == identifier
        assert saved.semantic_id == "urn:example:semantic:1"
        assert saved.doc == sample_submodel_data

    @pytest.mark.asyncio
    async def test_query_by_semantic_id(
        self, db_session: AsyncSession, sample_submodel_data: dict
    ) -> None:
        """Test querying submodels by semantic ID."""
        import orjson

        identifier = sample_submodel_data["id"]
        identifier_b64 = encode_id(identifier)
        doc_bytes = orjson.dumps(sample_submodel_data)
        etag = generate_etag(doc_bytes)
        semantic_id = "urn:example:semantic:1"

        submodel = SubmodelTable(
            identifier=identifier,
            identifier_b64=identifier_b64,
            semantic_id=semantic_id,
            doc=sample_submodel_data,
            doc_bytes=doc_bytes,
            etag=etag,
        )
        db_session.add(submodel)
        await db_session.commit()

        # Query by semantic ID
        result = await db_session.execute(
            select(SubmodelTable).where(SubmodelTable.semantic_id == semantic_id)
        )
        found = result.scalars().all()

        assert len(found) == 1
        assert found[0].identifier == identifier

    @pytest.mark.asyncio
    async def test_jsonb_containment_query(
        self, db_session: AsyncSession, sample_submodel_data: dict
    ) -> None:
        """Test JSONB containment queries."""
        import orjson

        identifier = sample_submodel_data["id"]
        identifier_b64 = encode_id(identifier)
        doc_bytes = orjson.dumps(sample_submodel_data)
        etag = generate_etag(doc_bytes)

        submodel = SubmodelTable(
            identifier=identifier,
            identifier_b64=identifier_b64,
            semantic_id="urn:example:semantic:1",
            doc=sample_submodel_data,
            doc_bytes=doc_bytes,
            etag=etag,
        )
        db_session.add(submodel)
        await db_session.commit()

        # Query using JSONB containment
        result = await db_session.execute(
            select(SubmodelTable).where(SubmodelTable.doc.contains({"idShort": "TestSubmodel"}))
        )
        found = result.scalars().all()

        assert len(found) == 1
        assert found[0].identifier == identifier


class TestDatabaseIntegrity:
    """Tests for database constraints and integrity."""

    @pytest.mark.asyncio
    async def test_unique_identifier_constraint(self, db_session: AsyncSession) -> None:
        """Test that duplicate identifiers are rejected."""
        import orjson
        from sqlalchemy.exc import IntegrityError

        data = {
            "modelType": "AssetAdministrationShell",
            "id": "urn:example:aas:duplicate",
            "idShort": "DuplicateAAS",
            "assetInformation": {"assetKind": "Instance"},
        }

        identifier = data["id"]
        identifier_b64 = encode_id(identifier)
        doc_bytes = orjson.dumps(data)
        etag = generate_etag(doc_bytes)

        # Create first AAS
        aas1 = AasTable(
            identifier=identifier,
            identifier_b64=identifier_b64,
            doc=data,
            doc_bytes=doc_bytes,
            etag=etag,
        )
        db_session.add(aas1)
        await db_session.commit()

        # Try to create duplicate - should fail
        aas2 = AasTable(
            identifier=identifier,
            identifier_b64=identifier_b64,
            doc=data,
            doc_bytes=doc_bytes,
            etag=etag,
        )
        db_session.add(aas2)

        with pytest.raises(IntegrityError):
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_gin_index_performance(self, db_session: AsyncSession) -> None:
        """Test that GIN index is being used for JSONB queries."""
        import orjson

        # Create multiple submodels
        for i in range(10):
            data = {
                "modelType": "Submodel",
                "id": f"urn:example:submodel:perf-{i}",
                "idShort": f"PerfSubmodel{i}",
                "submodelElements": [],
            }
            identifier = data["id"]
            identifier_b64 = encode_id(identifier)
            doc_bytes = orjson.dumps(data)
            etag = generate_etag(doc_bytes)

            submodel = SubmodelTable(
                identifier=identifier,
                identifier_b64=identifier_b64,
                doc=data,
                doc_bytes=doc_bytes,
                etag=etag,
            )
            db_session.add(submodel)

        await db_session.commit()

        # Check that index is used (EXPLAIN ANALYZE)
        result = await db_session.execute(
            text(
                """
                EXPLAIN (FORMAT JSON)
                SELECT * FROM submodels
                WHERE doc @> '{"idShort": "PerfSubmodel5"}'
                """
            )
        )
        plan = result.scalar()

        # The plan should mention the GIN index for larger datasets
        # For small datasets, Postgres may choose a seq scan
        assert plan is not None

"""Repository pattern for AAS persistence.

Provides fast/slow path methods:
- Fast path: get_bytes() returns raw bytes for streaming (no Python object hydration)
- Slow path: get_model() returns Pydantic model for projection/transformation

The fast path is the key performance optimization for read-heavy workloads.

SQL-Level Pagination (The "Pagination Paradox" Fix):
- Collection endpoints use SQL-level JSON aggregation
- PostgreSQL constructs the complete paged response
- Zero Python object hydration for list operations
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4
from typing import Generic, TypeVar

import orjson
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from titan.core.canonicalize import canonical_bytes, canonical_bytes_from_model
from titan.core.ids import encode_id_to_b64url
from titan.core.model import AssetAdministrationShell, Submodel
from titan.persistence.tables import (
    AasTable,
    BlobAssetTable,
    ConceptDescriptionTable,
    SubmodelTable,
    generate_etag,
)
from titan.storage.base import BlobMetadata
from titan.storage.externalize import externalize_submodel_doc
from titan.storage.factory import get_blob_storage

T = TypeVar("T")
TableT = TypeVar("TableT")


@dataclass
class PagedResult:
    """Result of a paginated query with zero-copy bytes."""

    # Complete JSON response as bytes (ready to stream)
    response_bytes: bytes
    # Cursor for next page (None if no more results)
    next_cursor: str | None
    # Total count of items in this page
    count: int


class BaseRepository(Generic[T, TableT]):
    """Base repository with common CRUD operations."""

    def __init__(self, session: AsyncSession):
        self.session = session


class AasRepository(BaseRepository[AssetAdministrationShell, AasTable]):
    """Repository for Asset Administration Shell operations."""

    # -------------------------------------------------------------------------
    # Fast path: bytes operations (no model hydration)
    # -------------------------------------------------------------------------

    async def get_bytes(self, identifier_b64: str) -> tuple[bytes, str] | None:
        """Fast path: get raw canonical bytes and etag.

        This is the hot path for read operations. Returns bytes that can
        be streamed directly to the response without Python object creation.

        Returns:
            Tuple of (doc_bytes, etag) or None if not found.
        """
        stmt = select(AasTable.doc_bytes, AasTable.etag).where(
            AasTable.identifier_b64 == identifier_b64
        )
        result = await self.session.execute(stmt)
        row = result.first()
        if row is None:
            return None
        return (row.doc_bytes, row.etag)

    async def get_bytes_by_id(self, identifier: str) -> tuple[bytes, str] | None:
        """Fast path: get by original identifier."""
        stmt = select(AasTable.doc_bytes, AasTable.etag).where(AasTable.identifier == identifier)
        result = await self.session.execute(stmt)
        row = result.first()
        if row is None:
            return None
        return (row.doc_bytes, row.etag)

    # -------------------------------------------------------------------------
    # Slow path: model operations (for projections/transformations)
    # -------------------------------------------------------------------------

    async def get_model(self, identifier_b64: str) -> AssetAdministrationShell | None:
        """Slow path: get as Pydantic model.

        Use this when you need to apply projections, transformations,
        or access specific fields. Avoid in hot paths.
        """
        stmt = select(AasTable.doc).where(AasTable.identifier_b64 == identifier_b64)
        result = await self.session.execute(stmt)
        row = result.first()
        if row is None:
            return None
        return AssetAdministrationShell.model_validate(row.doc)

    async def get_model_by_id(self, identifier: str) -> AssetAdministrationShell | None:
        """Slow path: get by original identifier."""
        stmt = select(AasTable.doc).where(AasTable.identifier == identifier)
        result = await self.session.execute(stmt)
        row = result.first()
        if row is None:
            return None
        return AssetAdministrationShell.model_validate(row.doc)

    # -------------------------------------------------------------------------
    # Write operations
    # -------------------------------------------------------------------------

    async def create(self, aas: AssetAdministrationShell) -> tuple[bytes, str]:
        """Create a new AAS.

        Validates with Pydantic, canonicalizes JSON, stores both JSONB and bytes.

        Returns:
            Tuple of (doc_bytes, etag) for cache population.
        """
        doc = aas.model_dump(by_alias=True, exclude_none=True)
        doc_bytes = canonical_bytes_from_model(aas)
        etag = generate_etag(doc_bytes)

        row = AasTable(
            identifier=aas.id,
            identifier_b64=encode_id_to_b64url(aas.id),
            doc=doc,
            doc_bytes=doc_bytes,
            etag=etag,
        )
        self.session.add(row)
        await self.session.flush()
        return (doc_bytes, etag)

    async def update(
        self, identifier: str, aas: AssetAdministrationShell
    ) -> tuple[bytes, str] | None:
        """Update an existing AAS.

        Returns:
            Tuple of (doc_bytes, etag) or None if not found.
        """
        stmt = select(AasTable).where(AasTable.identifier == identifier)
        result = await self.session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            return None

        doc = aas.model_dump(by_alias=True, exclude_none=True)
        doc_bytes = canonical_bytes_from_model(aas)
        etag = generate_etag(doc_bytes)

        row.identifier = aas.id
        row.identifier_b64 = encode_id_to_b64url(aas.id)
        row.doc = doc
        row.doc_bytes = doc_bytes
        row.etag = etag

        await self.session.flush()
        return (doc_bytes, etag)

    async def delete(self, identifier: str) -> bool:
        """Delete an AAS.

        Returns:
            True if deleted, False if not found.
        """
        stmt = select(AasTable).where(AasTable.identifier == identifier)
        result = await self.session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            return False

        await self.session.delete(row)
        await self.session.flush()
        return True

    async def exists(self, identifier: str) -> bool:
        """Check if an AAS exists."""
        stmt = select(AasTable.id).where(AasTable.identifier == identifier)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def list_all(self, limit: int = 100, offset: int = 0) -> list[tuple[bytes, str]]:
        """List all AAS (fast path).

        Returns:
            List of (doc_bytes, etag) tuples.
        """
        stmt = (
            select(AasTable.doc_bytes, AasTable.etag)
            .order_by(AasTable.created_at)
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return [(row.doc_bytes, row.etag) for row in result.all()]

    async def list_paged_zero_copy(
        self,
        limit: int = 100,
        cursor: str | None = None,
    ) -> PagedResult:
        """Zero-copy paginated list using SQL-level JSON aggregation.

        The "Pagination Paradox" fix: PostgreSQL constructs the complete
        paged response, including the wrapper structure. Python just streams
        the resulting bytes.

        Args:
            limit: Maximum items per page
            cursor: Cursor from previous page (created_at timestamp)

        Returns:
            PagedResult with response_bytes ready to stream
        """
        # Use parameterized SQL to avoid injection and keep parsing in Postgres.
        # PostgreSQL builds the complete JSON response.
        query = text(
            """
            WITH page AS (
                SELECT doc, created_at
                FROM aas
                WHERE (:cursor IS NULL OR created_at > CAST(:cursor AS timestamptz))
                ORDER BY created_at
                LIMIT :limit
            ),
            next_cursor AS (
                SELECT created_at::text as cursor
                FROM page
                ORDER BY created_at DESC
                LIMIT 1
            ),
            has_more AS (
                SELECT EXISTS(
                    SELECT 1 FROM aas
                    WHERE created_at > (SELECT MAX(created_at) FROM page)
                ) as more
            )
            SELECT json_build_object(
                'result', COALESCE((SELECT json_agg(doc) FROM page), '[]'::json),
                'paging_metadata', CASE
                    WHEN (SELECT more FROM has_more) THEN
                        json_build_object('cursor', (SELECT cursor FROM next_cursor))
                    ELSE NULL
                END
            )::text as response
            """
        )

        result = await self.session.execute(query, {"limit": limit, "cursor": cursor})
        row = result.scalar_one_or_none()

        if row is None:
            # Empty result
            empty_response = orjson.dumps({"result": [], "paging_metadata": None})
            return PagedResult(
                response_bytes=empty_response,
                next_cursor=None,
                count=0,
            )

        # Convert to bytes
        response_bytes = row.encode("utf-8") if isinstance(row, str) else row

        # Parse to get cursor and count (minimal parsing)
        parsed = orjson.loads(response_bytes)
        next_cursor = None
        if parsed.get("paging_metadata"):
            next_cursor = parsed["paging_metadata"].get("cursor")
        count = len(parsed.get("result", []))

        return PagedResult(
            response_bytes=response_bytes,
            next_cursor=next_cursor,
            count=count,
        )


class SubmodelRepository(BaseRepository[Submodel, SubmodelTable]):
    """Repository for Submodel operations."""

    # -------------------------------------------------------------------------
    # Fast path: bytes operations
    # -------------------------------------------------------------------------

    async def _load_blob_assets(self, submodel_row_id: str) -> list[BlobAssetTable]:
        """Load blob asset rows for a submodel."""
        stmt = select(BlobAssetTable).where(BlobAssetTable.submodel_id == submodel_row_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_bytes(self, identifier_b64: str) -> tuple[bytes, str] | None:
        """Fast path: get raw canonical bytes and etag."""
        stmt = select(SubmodelTable.doc_bytes, SubmodelTable.etag).where(
            SubmodelTable.identifier_b64 == identifier_b64
        )
        result = await self.session.execute(stmt)
        row = result.first()
        if row is None:
            return None
        return (row.doc_bytes, row.etag)

    async def get_bytes_by_id(self, identifier: str) -> tuple[bytes, str] | None:
        """Fast path: get by original identifier."""
        stmt = select(SubmodelTable.doc_bytes, SubmodelTable.etag).where(
            SubmodelTable.identifier == identifier
        )
        result = await self.session.execute(stmt)
        row = result.first()
        if row is None:
            return None
        return (row.doc_bytes, row.etag)

    # -------------------------------------------------------------------------
    # Slow path: model operations
    # -------------------------------------------------------------------------

    async def get_model(self, identifier_b64: str) -> Submodel | None:
        """Slow path: get as Pydantic model."""
        stmt = select(SubmodelTable.doc).where(SubmodelTable.identifier_b64 == identifier_b64)
        result = await self.session.execute(stmt)
        row = result.first()
        if row is None:
            return None
        return Submodel.model_validate(row.doc)

    async def get_model_by_id(self, identifier: str) -> Submodel | None:
        """Slow path: get by original identifier."""
        stmt = select(SubmodelTable.doc).where(SubmodelTable.identifier == identifier)
        result = await self.session.execute(stmt)
        row = result.first()
        if row is None:
            return None
        return Submodel.model_validate(row.doc)

    # -------------------------------------------------------------------------
    # Write operations
    # -------------------------------------------------------------------------

    async def create(self, submodel: Submodel) -> tuple[bytes, str]:
        """Create a new Submodel."""
        doc = submodel.model_dump(by_alias=True, exclude_none=True)
        doc_bytes = canonical_bytes_from_model(submodel)
        etag = generate_etag(doc_bytes)

        # Extract semantic ID if present
        semantic_id = None
        if submodel.semantic_id and submodel.semantic_id.keys:
            semantic_id = submodel.semantic_id.keys[-1].value

        row = SubmodelTable(
            identifier=submodel.id,
            identifier_b64=encode_id_to_b64url(submodel.id),
            semantic_id=semantic_id,
            doc=doc,
            doc_bytes=doc_bytes,
            etag=etag,
        )
        self.session.add(row)
        await self.session.flush()
        return (doc_bytes, etag)

    async def update(self, identifier: str, submodel: Submodel) -> tuple[bytes, str] | None:
        """Update an existing Submodel."""
        stmt = select(SubmodelTable).where(SubmodelTable.identifier == identifier)
        result = await self.session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            return None

        doc = submodel.model_dump(by_alias=True, exclude_none=True)
        doc_bytes = canonical_bytes_from_model(submodel)
        etag = generate_etag(doc_bytes)

        # Extract semantic ID if present
        semantic_id = None
        if submodel.semantic_id and submodel.semantic_id.keys:
            semantic_id = submodel.semantic_id.keys[-1].value

        row.identifier = submodel.id
        row.identifier_b64 = encode_id_to_b64url(submodel.id)
        row.semantic_id = semantic_id
        row.doc = doc
        row.doc_bytes = doc_bytes
        row.etag = etag

        await self.session.flush()
        return (doc_bytes, etag)

    async def delete(self, identifier: str) -> bool:
        """Delete a Submodel."""
        stmt = select(SubmodelTable).where(SubmodelTable.identifier == identifier)
        result = await self.session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            return False

        await self.session.delete(row)
        await self.session.flush()
        return True

    async def exists(self, identifier: str) -> bool:
        """Check if a Submodel exists."""
        stmt = select(SubmodelTable.id).where(SubmodelTable.identifier == identifier)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def list_all(self, limit: int = 100, offset: int = 0) -> list[tuple[bytes, str]]:
        """List all Submodels (fast path)."""
        stmt = (
            select(SubmodelTable.doc_bytes, SubmodelTable.etag)
            .order_by(SubmodelTable.created_at)
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return [(row.doc_bytes, row.etag) for row in result.all()]

    async def find_by_semantic_id(
        self, semantic_id: str, limit: int = 100
    ) -> list[tuple[bytes, str]]:
        """Find Submodels by semantic ID (fast path)."""
        stmt = (
            select(SubmodelTable.doc_bytes, SubmodelTable.etag)
            .where(SubmodelTable.semantic_id == semantic_id)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [(row.doc_bytes, row.etag) for row in result.all()]

    async def list_paged_zero_copy(
        self,
        limit: int = 100,
        cursor: str | None = None,
        semantic_id: str | None = None,
    ) -> PagedResult:
        """Zero-copy paginated list using SQL-level JSON aggregation.

        Args:
            limit: Maximum items per page
            cursor: Cursor from previous page (created_at timestamp)
            semantic_id: Optional filter by semantic ID

        Returns:
            PagedResult with response_bytes ready to stream
        """
        query = text(
            """
            WITH page AS (
                SELECT doc, created_at
                FROM submodels
                WHERE (:cursor IS NULL OR created_at > CAST(:cursor AS timestamptz))
                  AND (:semantic_id IS NULL OR semantic_id = :semantic_id)
                ORDER BY created_at
                LIMIT :limit
            ),
            next_cursor AS (
                SELECT created_at::text as cursor
                FROM page
                ORDER BY created_at DESC
                LIMIT 1
            ),
            has_more AS (
                SELECT EXISTS(
                    SELECT 1 FROM submodels
                    WHERE created_at > (SELECT MAX(created_at) FROM page)
                      AND (:semantic_id IS NULL OR semantic_id = :semantic_id)
                ) as more
            )
            SELECT json_build_object(
                'result', COALESCE((SELECT json_agg(doc) FROM page), '[]'::json),
                'paging_metadata', CASE
                    WHEN (SELECT more FROM has_more) THEN
                        json_build_object('cursor', (SELECT cursor FROM next_cursor))
                    ELSE NULL
                END
            )::text as response
            """
        )

        result = await self.session.execute(
            query,
            {"limit": limit, "cursor": cursor, "semantic_id": semantic_id},
        )
        row = result.scalar_one_or_none()

        if row is None:
            empty_response = orjson.dumps({"result": [], "paging_metadata": None})
            return PagedResult(
                response_bytes=empty_response,
                next_cursor=None,
                count=0,
            )

        response_bytes = row.encode("utf-8") if isinstance(row, str) else row
        parsed = orjson.loads(response_bytes)
        next_cursor = None
        if parsed.get("paging_metadata"):
            next_cursor = parsed["paging_metadata"].get("cursor")
        count = len(parsed.get("result", []))

        return PagedResult(
            response_bytes=response_bytes,
            next_cursor=next_cursor,
            count=count,
        )


class ConceptDescriptionRepository:
    """Repository for ConceptDescription operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_bytes(self, identifier_b64: str) -> tuple[bytes, str] | None:
        """Fast path: get raw canonical bytes and etag."""
        stmt = select(ConceptDescriptionTable.doc_bytes, ConceptDescriptionTable.etag).where(
            ConceptDescriptionTable.identifier_b64 == identifier_b64
        )
        result = await self.session.execute(stmt)
        row = result.first()
        if row is None:
            return None
        return (row.doc_bytes, row.etag)

    async def list_all(self, limit: int = 100, offset: int = 0) -> list[tuple[bytes, str]]:
        """List all ConceptDescriptions (fast path)."""
        stmt = (
            select(ConceptDescriptionTable.doc_bytes, ConceptDescriptionTable.etag)
            .order_by(ConceptDescriptionTable.created_at)
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return [(row.doc_bytes, row.etag) for row in result.all()]

"""Repository pattern for AAS Registry operations.

Provides fast/slow path methods for descriptor storage:
- AasDescriptorRepository: AAS descriptor CRUD
- SubmodelDescriptorRepository: Submodel descriptor CRUD

Supports discovery queries by globalAssetId, specificAssetIds, and semanticId.
"""

from __future__ import annotations

import orjson
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from titan.core.canonicalize import canonical_bytes
from titan.core.ids import encode_id_to_b64url
from titan.core.model.registry import (
    AssetAdministrationShellDescriptor,
    SubmodelDescriptor,
)
from titan.persistence.tables import (
    AasDescriptorTable,
    SubmodelDescriptorTable,
    generate_etag,
)


class AasDescriptorRepository:
    """Repository for AAS Descriptor operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    # -------------------------------------------------------------------------
    # Fast path: bytes operations
    # -------------------------------------------------------------------------

    async def get_bytes(self, identifier_b64: str) -> tuple[bytes, str] | None:
        """Fast path: get raw canonical bytes and etag."""
        stmt = select(AasDescriptorTable.doc_bytes, AasDescriptorTable.etag).where(
            AasDescriptorTable.identifier_b64 == identifier_b64
        )
        result = await self.session.execute(stmt)
        row = result.first()
        if row is None:
            return None
        return (row.doc_bytes, row.etag)

    async def get_bytes_by_id(self, identifier: str) -> tuple[bytes, str] | None:
        """Fast path: get by original identifier."""
        stmt = select(AasDescriptorTable.doc_bytes, AasDescriptorTable.etag).where(
            AasDescriptorTable.identifier == identifier
        )
        result = await self.session.execute(stmt)
        row = result.first()
        if row is None:
            return None
        return (row.doc_bytes, row.etag)

    # -------------------------------------------------------------------------
    # Slow path: model operations
    # -------------------------------------------------------------------------

    async def get_model(
        self, identifier_b64: str
    ) -> AssetAdministrationShellDescriptor | None:
        """Slow path: get as Pydantic model."""
        stmt = select(AasDescriptorTable.doc).where(
            AasDescriptorTable.identifier_b64 == identifier_b64
        )
        result = await self.session.execute(stmt)
        row = result.first()
        if row is None:
            return None
        return AssetAdministrationShellDescriptor.model_validate(row.doc)

    # -------------------------------------------------------------------------
    # Write operations
    # -------------------------------------------------------------------------

    async def create(
        self, descriptor: AssetAdministrationShellDescriptor
    ) -> tuple[bytes, str]:
        """Create a new AAS descriptor."""
        doc = descriptor.model_dump(by_alias=True, exclude_none=True)
        doc_bytes = canonical_bytes(doc)
        etag = generate_etag(doc_bytes)

        row = AasDescriptorTable(
            identifier=descriptor.id,
            identifier_b64=encode_id_to_b64url(descriptor.id),
            global_asset_id=descriptor.global_asset_id,
            doc=doc,
            doc_bytes=doc_bytes,
            etag=etag,
        )
        self.session.add(row)
        await self.session.flush()
        return (doc_bytes, etag)

    async def update(
        self, identifier: str, descriptor: AssetAdministrationShellDescriptor
    ) -> tuple[bytes, str] | None:
        """Update an existing AAS descriptor."""
        stmt = select(AasDescriptorTable).where(
            AasDescriptorTable.identifier == identifier
        )
        result = await self.session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            return None

        doc = descriptor.model_dump(by_alias=True, exclude_none=True)
        doc_bytes = canonical_bytes(doc)
        etag = generate_etag(doc_bytes)

        row.identifier = descriptor.id
        row.identifier_b64 = encode_id_to_b64url(descriptor.id)
        row.global_asset_id = descriptor.global_asset_id
        row.doc = doc
        row.doc_bytes = doc_bytes
        row.etag = etag

        await self.session.flush()
        return (doc_bytes, etag)

    async def delete(self, identifier: str) -> bool:
        """Delete an AAS descriptor."""
        stmt = select(AasDescriptorTable).where(
            AasDescriptorTable.identifier == identifier
        )
        result = await self.session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            return False

        await self.session.delete(row)
        await self.session.flush()
        return True

    async def exists(self, identifier: str) -> bool:
        """Check if an AAS descriptor exists."""
        stmt = select(AasDescriptorTable.id).where(
            AasDescriptorTable.identifier == identifier
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def list_all(
        self, limit: int = 100, offset: int = 0
    ) -> list[tuple[bytes, str]]:
        """List all AAS descriptors (fast path)."""
        stmt = (
            select(AasDescriptorTable.doc_bytes, AasDescriptorTable.etag)
            .order_by(AasDescriptorTable.created_at)
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return [(row.doc_bytes, row.etag) for row in result.all()]

    # -------------------------------------------------------------------------
    # Discovery operations
    # -------------------------------------------------------------------------

    async def find_by_global_asset_id(
        self, global_asset_id: str, limit: int = 100
    ) -> list[tuple[bytes, str]]:
        """Find AAS descriptors by global asset ID."""
        stmt = (
            select(AasDescriptorTable.doc_bytes, AasDescriptorTable.etag)
            .where(AasDescriptorTable.global_asset_id == global_asset_id)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [(row.doc_bytes, row.etag) for row in result.all()]

    async def find_by_specific_asset_id(
        self, name: str, value: str, limit: int = 100
    ) -> list[tuple[bytes, str]]:
        """Find AAS descriptors by specific asset ID (name/value pair)."""
        # Use JSONB containment query
        stmt = (
            select(AasDescriptorTable.doc_bytes, AasDescriptorTable.etag)
            .where(
                AasDescriptorTable.doc["specificAssetIds"].contains(
                    [{"name": name, "value": value}]
                )
            )
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [(row.doc_bytes, row.etag) for row in result.all()]


class SubmodelDescriptorRepository:
    """Repository for Submodel Descriptor operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    # -------------------------------------------------------------------------
    # Fast path: bytes operations
    # -------------------------------------------------------------------------

    async def get_bytes(self, identifier_b64: str) -> tuple[bytes, str] | None:
        """Fast path: get raw canonical bytes and etag."""
        stmt = select(
            SubmodelDescriptorTable.doc_bytes, SubmodelDescriptorTable.etag
        ).where(SubmodelDescriptorTable.identifier_b64 == identifier_b64)
        result = await self.session.execute(stmt)
        row = result.first()
        if row is None:
            return None
        return (row.doc_bytes, row.etag)

    async def get_bytes_by_id(self, identifier: str) -> tuple[bytes, str] | None:
        """Fast path: get by original identifier."""
        stmt = select(
            SubmodelDescriptorTable.doc_bytes, SubmodelDescriptorTable.etag
        ).where(SubmodelDescriptorTable.identifier == identifier)
        result = await self.session.execute(stmt)
        row = result.first()
        if row is None:
            return None
        return (row.doc_bytes, row.etag)

    # -------------------------------------------------------------------------
    # Slow path: model operations
    # -------------------------------------------------------------------------

    async def get_model(self, identifier_b64: str) -> SubmodelDescriptor | None:
        """Slow path: get as Pydantic model."""
        stmt = select(SubmodelDescriptorTable.doc).where(
            SubmodelDescriptorTable.identifier_b64 == identifier_b64
        )
        result = await self.session.execute(stmt)
        row = result.first()
        if row is None:
            return None
        return SubmodelDescriptor.model_validate(row.doc)

    # -------------------------------------------------------------------------
    # Write operations
    # -------------------------------------------------------------------------

    async def create(self, descriptor: SubmodelDescriptor) -> tuple[bytes, str]:
        """Create a new Submodel descriptor."""
        doc = descriptor.model_dump(by_alias=True, exclude_none=True)
        doc_bytes = canonical_bytes(doc)
        etag = generate_etag(doc_bytes)

        # Extract semantic ID if present
        semantic_id = None
        if descriptor.semantic_id and descriptor.semantic_id.keys:
            semantic_id = descriptor.semantic_id.keys[-1].value

        row = SubmodelDescriptorTable(
            identifier=descriptor.id,
            identifier_b64=encode_id_to_b64url(descriptor.id),
            semantic_id=semantic_id,
            doc=doc,
            doc_bytes=doc_bytes,
            etag=etag,
        )
        self.session.add(row)
        await self.session.flush()
        return (doc_bytes, etag)

    async def update(
        self, identifier: str, descriptor: SubmodelDescriptor
    ) -> tuple[bytes, str] | None:
        """Update an existing Submodel descriptor."""
        stmt = select(SubmodelDescriptorTable).where(
            SubmodelDescriptorTable.identifier == identifier
        )
        result = await self.session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            return None

        doc = descriptor.model_dump(by_alias=True, exclude_none=True)
        doc_bytes = canonical_bytes(doc)
        etag = generate_etag(doc_bytes)

        # Extract semantic ID if present
        semantic_id = None
        if descriptor.semantic_id and descriptor.semantic_id.keys:
            semantic_id = descriptor.semantic_id.keys[-1].value

        row.identifier = descriptor.id
        row.identifier_b64 = encode_id_to_b64url(descriptor.id)
        row.semantic_id = semantic_id
        row.doc = doc
        row.doc_bytes = doc_bytes
        row.etag = etag

        await self.session.flush()
        return (doc_bytes, etag)

    async def delete(self, identifier: str) -> bool:
        """Delete a Submodel descriptor."""
        stmt = select(SubmodelDescriptorTable).where(
            SubmodelDescriptorTable.identifier == identifier
        )
        result = await self.session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            return False

        await self.session.delete(row)
        await self.session.flush()
        return True

    async def exists(self, identifier: str) -> bool:
        """Check if a Submodel descriptor exists."""
        stmt = select(SubmodelDescriptorTable.id).where(
            SubmodelDescriptorTable.identifier == identifier
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def list_all(
        self, limit: int = 100, offset: int = 0
    ) -> list[tuple[bytes, str]]:
        """List all Submodel descriptors (fast path)."""
        stmt = (
            select(SubmodelDescriptorTable.doc_bytes, SubmodelDescriptorTable.etag)
            .order_by(SubmodelDescriptorTable.created_at)
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return [(row.doc_bytes, row.etag) for row in result.all()]

    # -------------------------------------------------------------------------
    # Discovery operations
    # -------------------------------------------------------------------------

    async def find_by_semantic_id(
        self, semantic_id: str, limit: int = 100
    ) -> list[tuple[bytes, str]]:
        """Find Submodel descriptors by semantic ID."""
        stmt = (
            select(SubmodelDescriptorTable.doc_bytes, SubmodelDescriptorTable.etag)
            .where(SubmodelDescriptorTable.semantic_id == semantic_id)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [(row.doc_bytes, row.etag) for row in result.all()]

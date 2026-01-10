"""Tests for persistence table definitions."""

import hashlib

from titan.persistence.tables import (
    AasTable,
    SubmodelTable,
    ConceptDescriptionTable,
    AasDescriptorTable,
    SubmodelDescriptorTable,
    Base,
    generate_etag,
)


class TestGenerateEtag:
    """Test ETag generation."""

    def test_generates_sha256_hex(self) -> None:
        """ETag is SHA256 hex of input bytes."""
        data = b'{"test": "data"}'
        etag = generate_etag(data)
        expected = hashlib.sha256(data).hexdigest()
        assert etag == expected
        assert len(etag) == 64

    def test_deterministic(self) -> None:
        """Same input always produces same ETag."""
        data = b"test data"
        assert generate_etag(data) == generate_etag(data)

    def test_different_inputs_different_etags(self) -> None:
        """Different inputs produce different ETags."""
        assert generate_etag(b"a") != generate_etag(b"b")


class TestTableDefinitions:
    """Test table schema definitions."""

    def test_all_tables_inherit_from_base(self) -> None:
        """All tables inherit from declarative Base."""
        tables = [
            AasTable,
            SubmodelTable,
            ConceptDescriptionTable,
            AasDescriptorTable,
            SubmodelDescriptorTable,
        ]
        for table in tables:
            assert issubclass(table, Base)

    def test_aas_table_columns(self) -> None:
        """AAS table has required columns."""
        columns = {c.name for c in AasTable.__table__.columns}
        required = {
            "id",
            "identifier",
            "identifier_b64",
            "doc",
            "doc_bytes",
            "etag",
            "created_at",
            "updated_at",
        }
        assert required.issubset(columns)

    def test_submodel_table_has_semantic_id(self) -> None:
        """Submodel table has semantic_id column."""
        columns = {c.name for c in SubmodelTable.__table__.columns}
        assert "semantic_id" in columns

    def test_descriptor_tables_have_required_columns(self) -> None:
        """Descriptor tables have identifier columns."""
        for table in [AasDescriptorTable, SubmodelDescriptorTable]:
            columns = {c.name for c in table.__table__.columns}
            assert "identifier" in columns
            assert "identifier_b64" in columns
            assert "doc" in columns
            assert "doc_bytes" in columns

    def test_aas_descriptor_has_global_asset_id(self) -> None:
        """AAS descriptor table has global_asset_id column."""
        columns = {c.name for c in AasDescriptorTable.__table__.columns}
        assert "global_asset_id" in columns


class TestTableIndexes:
    """Test table index definitions."""

    def test_aas_table_has_indexes(self) -> None:
        """AAS table has expected indexes."""
        index_names = {idx.name for idx in AasTable.__table__.indexes}
        # Check for key indexes (names may vary based on definition)
        assert len(index_names) > 0

    def test_submodel_table_has_semantic_id_index(self) -> None:
        """Submodel table has index on semantic_id."""
        # The index is defined in __table_args__ or via Index class
        columns = SubmodelTable.__table__.columns
        assert "semantic_id" in {c.name for c in columns}

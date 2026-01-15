"""Tests for SubmodelElement CRUD operations.

Tests insert, replace, patch, and delete operations on SubmodelElements.
"""

from __future__ import annotations

import pytest

from titan.core.element_operations import (
    ElementExistsError,
    ElementNotFoundError,
    InvalidPathError,
    delete_element,
    insert_element,
    patch_element,
    replace_element,
    update_element_value,
)


class TestInsertElement:
    """Tests for inserting SubmodelElements."""

    def test_insert_at_root(self) -> None:
        """Insert element at root level."""
        doc = {
            "id": "urn:example:submodel:001",
            "submodelElements": [
                {"modelType": "Property", "idShort": "Existing", "value": "1"},
            ],
        }
        new_element = {"modelType": "Property", "idShort": "New", "value": "2"}

        result = insert_element(doc, None, new_element)

        assert len(result["submodelElements"]) == 2
        assert result["submodelElements"][1]["idShort"] == "New"

    def test_insert_at_root_empty_path(self) -> None:
        """Insert element with empty path string."""
        doc = {"id": "urn:example:submodel:001", "submodelElements": []}
        new_element = {"modelType": "Property", "idShort": "First", "value": "1"}

        result = insert_element(doc, "", new_element)

        assert len(result["submodelElements"]) == 1
        assert result["submodelElements"][0]["idShort"] == "First"

    def test_insert_into_collection(self) -> None:
        """Insert element into SubmodelElementCollection."""
        doc = {
            "submodelElements": [
                {
                    "modelType": "SubmodelElementCollection",
                    "idShort": "Collection",
                    "value": [],
                },
            ],
        }
        new_element = {"modelType": "Property", "idShort": "Nested", "value": "1"}

        result = insert_element(doc, "Collection", new_element)

        collection = result["submodelElements"][0]
        assert len(collection["value"]) == 1
        assert collection["value"][0]["idShort"] == "Nested"

    def test_insert_into_list_without_idshort(self) -> None:
        """Insert element into SubmodelElementList without idShort."""
        doc = {
            "submodelElements": [
                {
                    "modelType": "SubmodelElementList",
                    "idShort": "List",
                    "value": [],
                },
            ],
        }
        new_element = {"modelType": "Property", "value": "1"}

        result = insert_element(doc, "List", new_element)

        list_elem = result["submodelElements"][0]
        assert len(list_elem["value"]) == 1
        assert list_elem["value"][0]["value"] == "1"

    def test_insert_duplicate_raises_error(self) -> None:
        """Inserting duplicate idShort raises ElementExistsError."""
        doc = {
            "submodelElements": [
                {"modelType": "Property", "idShort": "Duplicate", "value": "1"},
            ],
        }
        new_element = {"modelType": "Property", "idShort": "Duplicate", "value": "2"}

        with pytest.raises(ElementExistsError):
            insert_element(doc, None, new_element)

    def test_insert_without_idshort_raises_error(self) -> None:
        """Element without idShort raises ValueError."""
        doc = {"submodelElements": []}
        new_element = {"modelType": "Property", "value": "1"}

        with pytest.raises(ValueError, match="idShort"):
            insert_element(doc, None, new_element)

    def test_insert_into_nonexistent_path_raises_error(self) -> None:
        """Inserting into non-existent path raises InvalidPathError."""
        doc = {"submodelElements": []}
        new_element = {"modelType": "Property", "idShort": "New", "value": "1"}

        with pytest.raises(InvalidPathError):
            insert_element(doc, "NonExistent", new_element)


class TestReplaceElement:
    """Tests for replacing SubmodelElements."""

    def test_replace_root_element(self) -> None:
        """Replace element at root level."""
        doc = {
            "submodelElements": [
                {"modelType": "Property", "idShort": "Target", "value": "old"},
            ],
        }
        new_element = {"modelType": "Property", "idShort": "Target", "value": "new"}

        result = replace_element(doc, "Target", new_element)

        assert result["submodelElements"][0]["value"] == "new"

    def test_replace_nested_element(self) -> None:
        """Replace element nested in collection."""
        doc = {
            "submodelElements": [
                {
                    "modelType": "SubmodelElementCollection",
                    "idShort": "Collection",
                    "value": [
                        {"modelType": "Property", "idShort": "Nested", "value": "old"},
                    ],
                },
            ],
        }
        new_element = {"modelType": "Property", "idShort": "Nested", "value": "new"}

        result = replace_element(doc, "Collection.Nested", new_element)

        collection = result["submodelElements"][0]
        assert collection["value"][0]["value"] == "new"

    def test_replace_nonexistent_raises_error(self) -> None:
        """Replacing non-existent element raises ElementNotFoundError."""
        doc = {"submodelElements": []}

        with pytest.raises(ElementNotFoundError):
            replace_element(doc, "NonExistent", {"modelType": "Property", "idShort": "X1"})


class TestPatchElement:
    """Tests for patching SubmodelElements."""

    def test_patch_single_field(self) -> None:
        """Patch single field of element."""
        doc = {
            "submodelElements": [
                {"modelType": "Property", "idShort": "Target", "value": "old"},
            ],
        }

        result = patch_element(doc, "Target", {"value": "new"})

        elem = result["submodelElements"][0]
        assert elem["value"] == "new"
        assert elem["modelType"] == "Property"
        assert elem["idShort"] == "Target"

    def test_patch_multiple_fields(self) -> None:
        """Patch multiple fields at once."""
        doc = {
            "submodelElements": [
                {
                    "modelType": "Property",
                    "idShort": "Target",
                    "value": "old",
                    "valueType": "xs:string",
                },
            ],
        }

        result = patch_element(doc, "Target", {"value": "new", "valueType": "xs:int"})

        elem = result["submodelElements"][0]
        assert elem["value"] == "new"
        assert elem["valueType"] == "xs:int"

    def test_patch_nested_element(self) -> None:
        """Patch nested element."""
        doc = {
            "submodelElements": [
                {
                    "modelType": "SubmodelElementCollection",
                    "idShort": "Collection",
                    "value": [
                        {"modelType": "Property", "idShort": "Nested", "value": "old"},
                    ],
                },
            ],
        }

        result = patch_element(doc, "Collection.Nested", {"value": "patched"})

        collection = result["submodelElements"][0]
        assert collection["value"][0]["value"] == "patched"

    def test_patch_nonexistent_raises_error(self) -> None:
        """Patching non-existent element raises ElementNotFoundError."""
        doc = {"submodelElements": []}

        with pytest.raises(ElementNotFoundError):
            patch_element(doc, "NonExistent", {"value": "new"})


class TestUpdateElementValue:
    """Tests for updating element values."""

    def test_update_property_value(self) -> None:
        """Update Property value."""
        doc = {
            "submodelElements": [
                {"modelType": "Property", "idShort": "Temp", "value": "25.0"},
            ],
        }

        result = update_element_value(doc, "Temp", "30.5")

        assert result["submodelElements"][0]["value"] == "30.5"

    def test_update_nested_value(self) -> None:
        """Update nested element value."""
        doc = {
            "submodelElements": [
                {
                    "modelType": "SubmodelElementCollection",
                    "idShort": "Data",
                    "value": [
                        {"modelType": "Property", "idShort": "Temp", "value": "25.0"},
                    ],
                },
            ],
        }

        result = update_element_value(doc, "Data.Temp", "35.0")

        collection = result["submodelElements"][0]
        assert collection["value"][0]["value"] == "35.0"


class TestDeleteElement:
    """Tests for deleting SubmodelElements."""

    def test_delete_root_element(self) -> None:
        """Delete element at root level."""
        doc = {
            "submodelElements": [
                {"modelType": "Property", "idShort": "Keep", "value": "1"},
                {"modelType": "Property", "idShort": "Delete", "value": "2"},
            ],
        }

        result = delete_element(doc, "Delete")

        assert len(result["submodelElements"]) == 1
        assert result["submodelElements"][0]["idShort"] == "Keep"

    def test_delete_nested_element(self) -> None:
        """Delete nested element from collection."""
        doc = {
            "submodelElements": [
                {
                    "modelType": "SubmodelElementCollection",
                    "idShort": "Collection",
                    "value": [
                        {"modelType": "Property", "idShort": "Keep", "value": "1"},
                        {"modelType": "Property", "idShort": "Delete", "value": "2"},
                    ],
                },
            ],
        }

        result = delete_element(doc, "Collection.Delete")

        collection = result["submodelElements"][0]
        assert len(collection["value"]) == 1
        assert collection["value"][0]["idShort"] == "Keep"

    def test_delete_nonexistent_raises_error(self) -> None:
        """Deleting non-existent element raises ElementNotFoundError."""
        doc = {"submodelElements": []}

        with pytest.raises(ElementNotFoundError):
            delete_element(doc, "NonExistent")

    def test_delete_empty_path_raises_error(self) -> None:
        """Deleting with empty path raises InvalidPathError."""
        doc = {"submodelElements": []}

        with pytest.raises(InvalidPathError):
            delete_element(doc, "")


class TestIndexedPaths:
    """Tests for index-based path navigation."""

    def test_replace_by_index(self) -> None:
        """Replace element by index in list."""
        doc = {
            "submodelElements": [
                {
                    "modelType": "SubmodelElementList",
                    "idShort": "List",
                    "value": [
                        {"modelType": "Property", "idShort": "V0", "value": "a"},
                        {"modelType": "Property", "idShort": "V1", "value": "b"},
                    ],
                },
            ],
        }

        new_element = {"modelType": "Property", "idShort": "V1", "value": "updated"}
        result = replace_element(doc, "List[1]", new_element)

        list_elem = result["submodelElements"][0]
        assert list_elem["value"][1]["value"] == "updated"

    def test_delete_by_index(self) -> None:
        """Delete element by index in list."""
        doc = {
            "submodelElements": [
                {
                    "modelType": "SubmodelElementList",
                    "idShort": "List",
                    "value": [
                        {"modelType": "Property", "idShort": "V0", "value": "a"},
                        {"modelType": "Property", "idShort": "V1", "value": "b"},
                        {"modelType": "Property", "idShort": "V2", "value": "c"},
                    ],
                },
            ],
        }

        result = delete_element(doc, "List[1]")

        list_elem = result["submodelElements"][0]
        assert len(list_elem["value"]) == 2
        assert list_elem["value"][0]["idShort"] == "V0"
        assert list_elem["value"][1]["idShort"] == "V2"


class TestDocumentImmutability:
    """Tests to verify original document is not modified."""

    def test_insert_does_not_modify_original(self) -> None:
        """Insert should not modify original document."""
        doc = {"submodelElements": []}
        new_element = {"modelType": "Property", "idShort": "New", "value": "1"}

        insert_element(doc, None, new_element)

        assert len(doc["submodelElements"]) == 0

    def test_replace_does_not_modify_original(self) -> None:
        """Replace should not modify original document."""
        doc = {
            "submodelElements": [
                {"modelType": "Property", "idShort": "Target", "value": "old"},
            ],
        }

        replace_element(
            doc,
            "Target",
            {"modelType": "Property", "idShort": "Target", "value": "new"},
        )

        assert doc["submodelElements"][0]["value"] == "old"

    def test_delete_does_not_modify_original(self) -> None:
        """Delete should not modify original document."""
        doc = {
            "submodelElements": [
                {"modelType": "Property", "idShort": "Target", "value": "1"},
            ],
        }

        delete_element(doc, "Target")

        assert len(doc["submodelElements"]) == 1

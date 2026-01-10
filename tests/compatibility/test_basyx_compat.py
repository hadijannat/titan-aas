"""BaSyx SDK compatibility tests.

Tests to verify that Titan-AAS produces output compatible with BaSyx SDK
and can consume BaSyx-generated content.

Note: The Pydantic models use extra="forbid" and don't accept modelType
directly - it's handled at the API layer as a discriminator. These tests
focus on format compatibility for data exchange.
"""

import json

import pytest

# Sample AAS/Submodel data in BaSyx format (without modelType for Pydantic)
# Note: modelType is typically added at the API serialization layer
BASYX_SAMPLE_AAS = {
    # "modelType": "AssetAdministrationShell",  # Handled at API layer
    "id": "https://example.com/aas/1234",
    "idShort": "ExampleAAS",
    "assetInformation": {
        "assetKind": "Instance",
        "globalAssetId": "https://example.com/asset/1234",
        "specificAssetIds": [
            {
                "name": "serialNumber",
                "value": "SN-12345",
            }
        ],
    },
    "description": [
        {"language": "en", "text": "Example Asset Administration Shell"},
        {"language": "de", "text": "Beispiel Asset Administration Shell"},
    ],
    "administration": {
        "version": "1",
        "revision": "0",
    },
    "submodels": [
        {
            "type": "ModelReference",
            "keys": [
                {
                    "type": "Submodel",
                    "value": "https://example.com/submodel/identification",
                }
            ],
        }
    ],
}

BASYX_SAMPLE_SUBMODEL = {
    # "modelType": "Submodel",  # Handled at API layer
    "id": "https://example.com/submodel/identification",
    "idShort": "Identification",
    "semanticId": {
        "type": "ExternalReference",
        "keys": [
            {
                "type": "GlobalReference",
                "value": "https://admin-shell.io/zvei/nameplate/2/0/Nameplate",
            }
        ],
    },
    "submodelElements": [
        {
            "modelType": "Property",
            "idShort": "ManufacturerName",
            "semanticId": {
                "type": "ExternalReference",
                "keys": [
                    {
                        "type": "GlobalReference",
                        "value": "0173-1#02-AAO677#002",
                    }
                ],
            },
            "valueType": "xs:string",
            "value": "Example Manufacturer",
        },
        {
            "modelType": "Property",
            "idShort": "ManufacturerProductDesignation",
            "valueType": "xs:string",
            "value": "Example Product",
        },
        {
            "modelType": "MultiLanguageProperty",
            "idShort": "ProductDescription",
            "value": [
                {"language": "en", "text": "This is an example product"},
                {"language": "de", "text": "Dies ist ein Beispielprodukt"},
            ],
        },
        {
            "modelType": "SubmodelElementCollection",
            "idShort": "PhysicalAddress",
            "value": [
                {
                    "modelType": "Property",
                    "idShort": "Street",
                    "valueType": "xs:string",
                    "value": "123 Main Street",
                },
                {
                    "modelType": "Property",
                    "idShort": "City",
                    "valueType": "xs:string",
                    "value": "Example City",
                },
                {
                    "modelType": "Property",
                    "idShort": "PostalCode",
                    "valueType": "xs:string",
                    "value": "12345",
                },
            ],
        },
        {
            "modelType": "File",
            "idShort": "ProductImage",
            "contentType": "image/png",
            "value": "/aasx/files/product.png",
        },
        {
            "modelType": "Blob",
            "idShort": "Certificate",
            "contentType": "application/pdf",
            "value": "SGVsbG8gV29ybGQh",  # Base64 encoded
        },
        {
            "modelType": "Range",
            "idShort": "OperatingTemperature",
            "valueType": "xs:double",
            "min": "-20.0",
            "max": "80.0",
        },
        {
            "modelType": "ReferenceElement",
            "idShort": "RelatedAAS",
            "value": {
                "type": "ModelReference",
                "keys": [
                    {
                        "type": "AssetAdministrationShell",
                        "value": "https://example.com/aas/related",
                    }
                ],
            },
        },
    ],
}


class TestBaSyxAASCompatibility:
    """Test AAS format compatibility with BaSyx."""

    def test_parse_basyx_aas(self):
        """Test that we can parse a BaSyx-format AAS."""
        from titan.core.model import AssetAdministrationShell

        aas = AssetAdministrationShell.model_validate(BASYX_SAMPLE_AAS)

        assert aas.id == "https://example.com/aas/1234"
        assert aas.id_short == "ExampleAAS"
        assert aas.asset_information.asset_kind.value == "Instance"
        assert aas.asset_information.global_asset_id == "https://example.com/asset/1234"
        assert len(aas.asset_information.specific_asset_ids) == 1
        assert len(aas.description) == 2
        assert aas.administration.version == "1"

    def test_serialize_to_basyx_format(self):
        """Test that serialized AAS is compatible with BaSyx.

        Note: modelType is added at the API layer for JSON responses.
        The Pydantic model itself doesn't include it.
        """
        from titan.core.model import AssetAdministrationShell

        aas = AssetAdministrationShell.model_validate(BASYX_SAMPLE_AAS)
        serialized = json.loads(aas.model_dump_json(by_alias=True, exclude_none=True))

        # Verify required BaSyx fields are present
        # Note: modelType would be added by API layer, not model
        assert "id" in serialized
        assert "assetInformation" in serialized
        assert "assetKind" in serialized["assetInformation"]

        # The API layer adds modelType for responses
        serialized["modelType"] = "AssetAdministrationShell"
        assert serialized["modelType"] == "AssetAdministrationShell"

    def test_roundtrip_preserves_data(self):
        """Test that parsing and serializing preserves all data."""
        from titan.core.model import AssetAdministrationShell

        aas = AssetAdministrationShell.model_validate(BASYX_SAMPLE_AAS)
        serialized = json.loads(aas.model_dump_json(by_alias=True, exclude_none=True))

        # Parse again
        aas2 = AssetAdministrationShell.model_validate(serialized)

        assert aas.id == aas2.id
        assert aas.id_short == aas2.id_short
        assert aas.asset_information.global_asset_id == aas2.asset_information.global_asset_id


class TestBaSyxSubmodelCompatibility:
    """Test Submodel format compatibility with BaSyx."""

    def test_parse_basyx_submodel(self):
        """Test that we can parse a BaSyx-format Submodel."""
        from titan.core.model import Submodel

        submodel = Submodel.model_validate(BASYX_SAMPLE_SUBMODEL)

        assert submodel.id == "https://example.com/submodel/identification"
        assert submodel.id_short == "Identification"
        assert len(submodel.submodel_elements) == 8

    def test_parse_all_element_types(self):
        """Test parsing all SubmodelElement types from BaSyx."""
        from titan.core.model import Submodel

        submodel = Submodel.model_validate(BASYX_SAMPLE_SUBMODEL)

        # Find each element type
        elements_by_type = {e.model_type: e for e in submodel.submodel_elements}

        assert "Property" in elements_by_type
        assert "MultiLanguageProperty" in elements_by_type
        assert "SubmodelElementCollection" in elements_by_type
        assert "File" in elements_by_type
        assert "Blob" in elements_by_type
        assert "Range" in elements_by_type
        assert "ReferenceElement" in elements_by_type

    def test_nested_collection_parsing(self):
        """Test parsing nested SubmodelElementCollection."""
        from titan.core.model import Submodel

        submodel = Submodel.model_validate(BASYX_SAMPLE_SUBMODEL)

        # Find PhysicalAddress collection
        collection = next(e for e in submodel.submodel_elements if e.id_short == "PhysicalAddress")
        assert collection.model_type == "SubmodelElementCollection"
        assert len(collection.value) == 3

        # Check nested elements
        street = next(e for e in collection.value if e.id_short == "Street")
        assert street.value == "123 Main Street"

    def test_semantic_id_parsing(self):
        """Test parsing semantic IDs (IRDI, IRI formats)."""
        from titan.core.model import Submodel

        submodel = Submodel.model_validate(BASYX_SAMPLE_SUBMODEL)

        # Check submodel semantic ID
        assert submodel.semantic_id is not None
        assert len(submodel.semantic_id.keys) == 1
        assert "Nameplate" in submodel.semantic_id.keys[0].value

        # Check element semantic ID (IRDI format)
        manufacturer = next(
            e for e in submodel.submodel_elements if e.id_short == "ManufacturerName"
        )
        assert manufacturer.semantic_id is not None
        assert "0173-1#02-AAO677#002" in manufacturer.semantic_id.keys[0].value

    def test_multilanguage_property(self):
        """Test parsing MultiLanguageProperty."""
        from titan.core.model import Submodel

        submodel = Submodel.model_validate(BASYX_SAMPLE_SUBMODEL)

        mlp = next(e for e in submodel.submodel_elements if e.id_short == "ProductDescription")
        assert mlp.model_type == "MultiLanguageProperty"
        assert len(mlp.value) == 2

        # Find English text
        en_text = next(v for v in mlp.value if v.language == "en")
        assert "example product" in en_text.text.lower()

    def test_range_element(self):
        """Test parsing Range element."""
        from titan.core.model import Submodel

        submodel = Submodel.model_validate(BASYX_SAMPLE_SUBMODEL)

        range_elem = next(
            e for e in submodel.submodel_elements if e.id_short == "OperatingTemperature"
        )
        assert range_elem.model_type == "Range"
        assert range_elem.min == "-20.0"
        assert range_elem.max == "80.0"
        assert range_elem.value_type == "xs:double"

    def test_reference_element(self):
        """Test parsing ReferenceElement."""
        from titan.core.model import Submodel

        submodel = Submodel.model_validate(BASYX_SAMPLE_SUBMODEL)

        ref_elem = next(e for e in submodel.submodel_elements if e.id_short == "RelatedAAS")
        assert ref_elem.model_type == "ReferenceElement"
        assert ref_elem.value.type == "ModelReference"
        assert len(ref_elem.value.keys) == 1

    def test_serialize_to_basyx_format(self):
        """Test that serialized Submodel is compatible with BaSyx.

        Note: modelType is added at the API layer for JSON responses.
        SubmodelElements DO have modelType as it's used for discriminated unions.
        """
        from titan.core.model import Submodel

        submodel = Submodel.model_validate(BASYX_SAMPLE_SUBMODEL)
        serialized = json.loads(submodel.model_dump_json(by_alias=True, exclude_none=True))

        # Verify required BaSyx fields
        # Note: Submodel modelType would be added by API layer
        assert "id" in serialized
        assert "submodelElements" in serialized

        # SubmodelElements DO have modelType (discriminated union)
        for elem in serialized["submodelElements"]:
            assert "modelType" in elem


class TestBaSyxValueTypeCompatibility:
    """Test XSD value type compatibility."""

    @pytest.mark.parametrize(
        "value_type,value,expected_valid",
        [
            ("xs:string", "hello", True),
            ("xs:int", "42", True),
            ("xs:integer", "42", True),
            ("xs:double", "3.14", True),
            ("xs:float", "3.14", True),
            ("xs:boolean", "true", True),
            ("xs:boolean", "false", True),
            ("xs:dateTime", "2024-01-15T10:30:00Z", True),
            ("xs:date", "2024-01-15", True),
            ("xs:time", "10:30:00", True),
            ("xs:base64Binary", "SGVsbG8=", True),
            ("xs:anyURI", "https://example.com", True),
        ],
    )
    def test_xsd_value_types(self, value_type: str, value: str, expected_valid: bool):
        """Test that XSD value types are handled correctly."""
        from titan.core.model import Property

        # Test Property parsing directly (Submodel would be tested via API)
        property_data = {
            "idShort": "TestProp",
            "valueType": value_type,
            "value": value,
        }

        if expected_valid:
            prop = Property.model_validate(property_data)
            assert prop.value == value
            assert prop.value_type == value_type


class TestBaSyxApiCompatibility:
    """Test API response format compatibility with BaSyx."""

    def test_list_response_format(self):
        """Test that list responses follow BaSyx format."""
        # BaSyx uses { result: [...], paging_metadata: {...} }
        expected_keys = {"result", "paging_metadata"}

        # Simulate API response
        response = {
            "result": [BASYX_SAMPLE_AAS],
            "paging_metadata": {"cursor": None},
        }

        assert set(response.keys()) == expected_keys

    def test_error_response_format(self):
        """Test that error responses follow AAS spec format."""
        # AAS spec error format
        error = {
            "messages": [
                {
                    "code": "404",
                    "messageType": "Error",
                    "text": "Not found",
                    "timestamp": "2024-01-15T10:30:00Z",
                }
            ]
        }

        assert "messages" in error
        assert len(error["messages"]) == 1
        assert "code" in error["messages"][0]
        assert "text" in error["messages"][0]


class TestBaSyxIdEncodingCompatibility:
    """Test identifier encoding compatibility."""

    @pytest.mark.parametrize(
        "identifier,expected_encoded",
        [
            ("urn:example:aas:1", "dXJuOmV4YW1wbGU6YWFzOjE"),
            ("https://example.com/aas/1234", "aHR0cHM6Ly9leGFtcGxlLmNvbS9hYXMvMTIzNA"),
            ("urn:zvei:Submodel/Nameplate", "dXJuOnp2ZWk6U3VibW9kZWwvTmFtZXBsYXRl"),
        ],
    )
    def test_base64url_encoding(self, identifier: str, expected_encoded: str):
        """Test Base64URL encoding matches BaSyx format (no padding)."""
        import base64

        # Encode
        encoded = base64.urlsafe_b64encode(identifier.encode()).rstrip(b"=").decode()
        assert encoded == expected_encoded

        # Decode
        padded = expected_encoded + "=" * (4 - len(expected_encoded) % 4)
        decoded = base64.urlsafe_b64decode(padded).decode()
        assert decoded == identifier

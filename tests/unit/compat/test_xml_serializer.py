"""Tests for XML serialization following IDTA-01001 v3.1."""

from titan.compat.xml_serializer import AAS_NS, XmlDeserializer, XmlSerializer
from titan.core.model import (
    AssetAdministrationShell,
    AssetInformation,
    AssetKind,
    ConceptDescription,
    Property,
    Submodel,
)


class TestXmlSerializer:
    """Tests for XmlSerializer."""

    def test_serialize_empty_environment(self):
        """Serialize an empty environment."""
        serializer = XmlSerializer()
        xml_bytes = serializer.serialize_environment([], [], [])

        assert xml_bytes is not None
        assert b"environment" in xml_bytes
        assert b"aas:" in xml_bytes or AAS_NS.encode() in xml_bytes

    def test_serialize_shell(self):
        """Serialize a single AAS."""
        shell = AssetAdministrationShell(
            id="urn:example:aas:1",
            id_short="TestAAS",
            asset_information=AssetInformation(
                asset_kind=AssetKind.INSTANCE,
                global_asset_id="urn:example:asset:1",
            ),
        )

        serializer = XmlSerializer()
        xml_bytes = serializer.serialize_environment([shell], [], [])

        xml_str = xml_bytes.decode("utf-8")
        assert "urn:example:aas:1" in xml_str
        assert "TestAAS" in xml_str
        assert "assetAdministrationShell" in xml_str

    def test_serialize_submodel_with_elements(self):
        """Serialize a submodel with elements."""
        submodel = Submodel(
            id="urn:example:submodel:1",
            id_short="TestSubmodel",
            submodel_elements=[
                Property(
                    id_short="Temperature",
                    value_type="xs:double",
                    value="25.5",
                ),
            ],
        )

        serializer = XmlSerializer()
        xml_bytes = serializer.serialize_environment([], [submodel], [])

        xml_str = xml_bytes.decode("utf-8")
        assert "TestSubmodel" in xml_str
        assert "Temperature" in xml_str
        assert "25.5" in xml_str

    def test_serialize_concept_description(self):
        """Serialize a concept description."""
        cd = ConceptDescription(
            id="urn:example:cd:temperature",
            id_short="Temperature",
            description=[{"language": "en", "text": "Measured temperature"}],
        )

        serializer = XmlSerializer()
        xml_bytes = serializer.serialize_environment([], [], [cd])

        xml_str = xml_bytes.decode("utf-8")
        assert "conceptDescription" in xml_str
        assert "Temperature" in xml_str
        assert "Measured temperature" in xml_str


class TestXmlDeserializer:
    """Tests for XmlDeserializer."""

    def test_parse_empty_environment(self):
        """Parse an empty environment."""
        xml_bytes = b"""<?xml version='1.0' encoding='utf-8'?>
        <aas:environment xmlns:aas="https://admin-shell.io/aas/3/0">
        </aas:environment>"""

        deserializer = XmlDeserializer()
        shells, submodels, cds = deserializer.parse_environment(xml_bytes)

        assert shells == []
        assert submodels == []
        assert cds == []

    def test_parse_shell(self):
        """Parse a single AAS from XML."""
        xml_bytes = b"""<?xml version='1.0' encoding='utf-8'?>
        <aas:environment xmlns:aas="https://admin-shell.io/aas/3/0">
            <aas:assetAdministrationShells>
                <aas:assetAdministrationShell>
                    <aas:id>urn:example:aas:1</aas:id>
                    <aas:idShort>TestAAS</aas:idShort>
                    <aas:assetInformation>
                        <aas:assetKind>Instance</aas:assetKind>
                        <aas:globalAssetId>urn:example:asset:1</aas:globalAssetId>
                    </aas:assetInformation>
                </aas:assetAdministrationShell>
            </aas:assetAdministrationShells>
        </aas:environment>"""

        deserializer = XmlDeserializer()
        shells, submodels, cds = deserializer.parse_environment(xml_bytes)

        assert len(shells) == 1
        assert shells[0].id == "urn:example:aas:1"
        assert shells[0].id_short == "TestAAS"
        assert shells[0].asset_information.asset_kind == AssetKind.INSTANCE

    def test_parse_submodel_with_property(self):
        """Parse a submodel with a Property element.

        Note: The XML must include modelType for discriminated union parsing.
        """
        xml_bytes = b"""<?xml version='1.0' encoding='utf-8'?>
        <aas:environment xmlns:aas="https://admin-shell.io/aas/3/0">
            <aas:submodels>
                <aas:submodel>
                    <aas:id>urn:example:submodel:1</aas:id>
                    <aas:idShort>TestSubmodel</aas:idShort>
                    <aas:submodelElements>
                        <aas:property>
                            <aas:modelType>Property</aas:modelType>
                            <aas:idShort>Temperature</aas:idShort>
                            <aas:valueType>xs:double</aas:valueType>
                            <aas:value>25.5</aas:value>
                        </aas:property>
                    </aas:submodelElements>
                </aas:submodel>
            </aas:submodels>
        </aas:environment>"""

        deserializer = XmlDeserializer()
        shells, submodels, cds = deserializer.parse_environment(xml_bytes)

        assert len(submodels) == 1
        sm = submodels[0]
        assert sm.id == "urn:example:submodel:1"
        assert sm.id_short == "TestSubmodel"
        assert len(sm.submodel_elements) == 1

        prop = sm.submodel_elements[0]
        assert prop.id_short == "Temperature"
        assert prop.value == "25.5"

    def test_parse_concept_description(self):
        """Parse a concept description from XML."""
        xml_bytes = b"""<?xml version='1.0' encoding='utf-8'?>
        <aas:environment xmlns:aas="https://admin-shell.io/aas/3/0">
            <aas:conceptDescriptions>
                <aas:conceptDescription>
                    <aas:id>urn:example:cd:1</aas:id>
                    <aas:idShort>TestConcept</aas:idShort>
                    <aas:description>
                        <aas:langStringTextType>
                            <aas:language>en</aas:language>
                            <aas:text>A test concept</aas:text>
                        </aas:langStringTextType>
                    </aas:description>
                </aas:conceptDescription>
            </aas:conceptDescriptions>
        </aas:environment>"""

        deserializer = XmlDeserializer()
        shells, submodels, cds = deserializer.parse_environment(xml_bytes)

        assert len(cds) == 1
        cd = cds[0]
        assert cd.id == "urn:example:cd:1"
        assert cd.id_short == "TestConcept"


class TestXmlRoundTrip:
    """Tests for XML serialization round-trip."""

    def test_shell_roundtrip(self):
        """Serialize and deserialize a shell."""
        original = AssetAdministrationShell(
            id="urn:example:aas:roundtrip",
            id_short="RoundtripAAS",
            asset_information=AssetInformation(
                asset_kind=AssetKind.INSTANCE,
                global_asset_id="urn:example:asset:roundtrip",
            ),
        )

        serializer = XmlSerializer()
        deserializer = XmlDeserializer()

        xml_bytes = serializer.serialize_environment([original], [], [])
        shells, _, _ = deserializer.parse_environment(xml_bytes)

        assert len(shells) == 1
        assert shells[0].id == original.id
        assert shells[0].id_short == original.id_short
        assert (
            shells[0].asset_information.global_asset_id
            == original.asset_information.global_asset_id
        )

    def test_submodel_roundtrip(self):
        """Serialize and deserialize a submodel with elements."""
        original = Submodel(
            id="urn:example:submodel:roundtrip",
            id_short="RoundtripSubmodel",
            submodel_elements=[
                Property(
                    id_short="Value1",
                    value_type="xs:string",
                    value="test-value",
                ),
            ],
        )

        serializer = XmlSerializer()
        deserializer = XmlDeserializer()

        xml_bytes = serializer.serialize_environment([], [original], [])
        _, submodels, _ = deserializer.parse_environment(xml_bytes)

        assert len(submodels) == 1
        assert submodels[0].id == original.id
        assert len(submodels[0].submodel_elements) == 1
        assert submodels[0].submodel_elements[0].value == "test-value"

    def test_concept_description_roundtrip(self):
        """Serialize and deserialize a concept description."""
        original = ConceptDescription(
            id="urn:example:cd:roundtrip",
            id_short="RoundtripConcept",
            description=[{"language": "en", "text": "Roundtrip test"}],
        )

        serializer = XmlSerializer()
        deserializer = XmlDeserializer()

        xml_bytes = serializer.serialize_environment([], [], [original])
        _, _, cds = deserializer.parse_environment(xml_bytes)

        assert len(cds) == 1
        assert cds[0].id == original.id
        assert cds[0].id_short == original.id_short

    def test_full_environment_roundtrip(self):
        """Serialize and deserialize a complete environment."""
        shell = AssetAdministrationShell(
            id="urn:example:aas:full",
            id_short="FullAAS",
            asset_information=AssetInformation(
                asset_kind=AssetKind.TYPE,
                global_asset_id="urn:example:asset:full",
            ),
        )

        submodel = Submodel(
            id="urn:example:submodel:full",
            id_short="FullSubmodel",
        )

        cd = ConceptDescription(
            id="urn:example:cd:full",
            id_short="FullConcept",
        )

        serializer = XmlSerializer()
        deserializer = XmlDeserializer()

        xml_bytes = serializer.serialize_environment([shell], [submodel], [cd])
        shells, submodels, cds = deserializer.parse_environment(xml_bytes)

        assert len(shells) == 1
        assert len(submodels) == 1
        assert len(cds) == 1
        assert shells[0].id == "urn:example:aas:full"
        assert submodels[0].id == "urn:example:submodel:full"
        assert cds[0].id == "urn:example:cd:full"

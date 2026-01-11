"""AASX package import/export for Titan-AAS.

AASX is the package format for exchanging AAS data between systems.
It's a ZIP archive following the Open Packaging Conventions (OPC).

Supports:
- JSON serialization (IDTA-01001 Part 2)
- AASX package structure
- Supplementary files (attachments)

Example:
    # Import
    importer = AasxImporter()
    package = await importer.import_package("/path/to/package.aasx")
    for aas in package.shells:
        print(aas.id_short)

    # Export
    exporter = AasxExporter()
    await exporter.export_package(
        shells=[aas1, aas2],
        submodels=[sm1, sm2],
        output_path="/path/to/export.aasx"
    )
"""

from __future__ import annotations

import logging
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any, BinaryIO
from xml.etree import ElementTree as ET

import orjson

from titan.core.model import AssetAdministrationShell, ConceptDescription, Submodel

logger = logging.getLogger(__name__)


@dataclass
class PackageMetadata:
    """OPC core properties metadata for AASX package.

    Follows the OPC Core Properties specification for package metadata.
    """

    title: str | None = None
    creator: str | None = None
    created: datetime | None = None
    modified: datetime | None = None
    description: str | None = None
    version: str | None = None


@dataclass
class AasxPackage:
    """Represents an AASX package with AAS, submodels, and concept descriptions."""

    shells: list[AssetAdministrationShell] = field(default_factory=list)
    submodels: list[Submodel] = field(default_factory=list)
    concept_descriptions: list[ConceptDescription] = field(default_factory=list)
    supplementary_files: dict[str, bytes] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)  # Generic metadata
    thumbnail: bytes | None = None  # Package thumbnail image (PNG/JPEG)
    core_properties: PackageMetadata | None = None  # OPC core properties metadata


class AasxImporter:
    """Imports AASX packages into Titan-AAS models."""

    # Content types XML template
    CONTENT_TYPES_NS = "http://schemas.openxmlformats.org/package/2006/content-types"

    async def import_package(self, path: str | Path) -> AasxPackage:
        """Import an AASX package from file.

        Args:
            path: Path to the AASX file

        Returns:
            AasxPackage with parsed shells and submodels

        Raises:
            ValueError: If package structure is invalid
            FileNotFoundError: If file doesn't exist
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"AASX file not found: {path}")

        with open(path, "rb") as f:
            return await self.import_from_stream(f)

    async def import_from_stream(self, stream: BinaryIO) -> AasxPackage:
        """Import an AASX package from a binary stream.

        Args:
            stream: Binary stream containing AASX data

        Returns:
            AasxPackage with parsed shells and submodels
        """
        package = AasxPackage()

        try:
            with zipfile.ZipFile(stream, "r") as zf:
                # List all files in package
                file_list = zf.namelist()
                logger.debug(f"AASX contains {len(file_list)} files")

                # Find AAS and submodel files
                for name in file_list:
                    lower_name = name.lower()

                    # Skip OPC metadata files
                    if name.startswith("_rels/") or name == "[Content_Types].xml":
                        continue

                    # Import JSON files
                    if lower_name.endswith(".json"):
                        content = zf.read(name)
                        await self._import_json(content, name, package)

                    # Import XML files (but not core-properties.xml)
                    elif lower_name.endswith(".xml") and "core-properties" not in lower_name:
                        content = zf.read(name)
                        await self._import_xml(content, name, package)

                    # Extract core properties
                    elif "core-properties" in lower_name and lower_name.endswith(".xml"):
                        content = zf.read(name)
                        package.core_properties = self._parse_core_properties(content)
                        logger.debug(f"Extracted core properties: {name}")

                    # Extract thumbnail (PNG or JPEG in aasx directory)
                    elif "thumbnail" in lower_name and (
                        lower_name.endswith(".png") or lower_name.endswith(".jpg") or lower_name.endswith(".jpeg")
                    ):
                        package.thumbnail = zf.read(name)
                        logger.debug(f"Extracted thumbnail: {name}")

                    # Collect supplementary files
                    elif "supplementary" in lower_name or "files" in lower_name:
                        content = zf.read(name)
                        package.supplementary_files[name] = content

        except zipfile.BadZipFile as e:
            raise ValueError(f"Invalid AASX package: {e}") from e

        logger.info(f"Imported {len(package.shells)} shells, {len(package.submodels)} submodels")
        return package

    async def _import_json(self, content: bytes, filename: str, package: AasxPackage) -> None:
        """Parse JSON content and add to package."""
        try:
            data = orjson.loads(content)
        except orjson.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON {filename}: {e}")
            return

        # Handle different JSON structures
        if isinstance(data, dict):
            # Single object or wrapped collection
            if "assetAdministrationShells" in data:
                # Environment format
                await self._import_environment(data, package)
            elif "modelType" in data:
                # Single object with modelType
                await self._import_single_object(data, package)
            else:
                # Try to detect type from structure
                if "assetInformation" in data:
                    await self._import_shell(data, package)
                elif "submodelElements" in data:
                    await self._import_submodel(data, package)

        elif isinstance(data, list):
            # List of objects
            for item in data:
                if isinstance(item, dict):
                    await self._import_single_object(item, package)

    async def _import_xml(self, content: bytes, filename: str, package: AasxPackage) -> None:
        """Parse XML content following IDTA-01001 v3.1."""
        from titan.compat.xml_serializer import XmlDeserializer

        try:
            deserializer = XmlDeserializer()
            shells, submodels, concept_descs = deserializer.parse_environment(content)
            package.shells.extend(shells)
            package.submodels.extend(submodels)
            package.concept_descriptions.extend(concept_descs)
            logger.debug(
                f"Imported from XML {filename}: "
                f"{len(shells)} shells, {len(submodels)} submodels, "
                f"{len(concept_descs)} concept descriptions"
            )
        except Exception as e:
            logger.warning(f"Failed to parse XML {filename}: {e}")

    async def _import_environment(self, data: dict[str, Any], package: AasxPackage) -> None:
        """Import AAS environment format with shells, submodels, and concept descriptions."""
        # Import shells
        shells = data.get("assetAdministrationShells", [])
        for shell_data in shells:
            await self._import_shell(shell_data, package)

        # Import submodels
        submodels = data.get("submodels", [])
        for sm_data in submodels:
            await self._import_submodel(sm_data, package)

        # Import concept descriptions
        concept_descs = data.get("conceptDescriptions", [])
        for cd_data in concept_descs:
            await self._import_concept_description(cd_data, package)

    async def _import_single_object(self, data: dict[str, Any], package: AasxPackage) -> None:
        """Import a single object based on modelType."""
        model_type = data.get("modelType", "")

        if model_type == "AssetAdministrationShell":
            await self._import_shell(data, package)
        elif model_type == "Submodel":
            await self._import_submodel(data, package)
        elif model_type == "ConceptDescription":
            await self._import_concept_description(data, package)
        else:
            logger.debug(f"Skipping unknown modelType: {model_type}")

    async def _import_shell(self, data: dict[str, Any], package: AasxPackage) -> None:
        """Parse and add an AssetAdministrationShell."""
        try:
            shell = AssetAdministrationShell.model_validate(data)
            package.shells.append(shell)
            logger.debug(f"Imported shell: {shell.id_short or shell.id}")
        except Exception as e:
            logger.warning(f"Failed to parse shell: {e}")

    async def _import_submodel(self, data: dict[str, Any], package: AasxPackage) -> None:
        """Parse and add a Submodel."""
        try:
            submodel = Submodel.model_validate(data)
            package.submodels.append(submodel)
            logger.debug(f"Imported submodel: {submodel.id_short or submodel.id}")
        except Exception as e:
            logger.warning(f"Failed to parse submodel: {e}")

    async def _import_concept_description(self, data: dict[str, Any], package: AasxPackage) -> None:
        """Parse and add a ConceptDescription."""
        try:
            concept = ConceptDescription.model_validate(data)
            package.concept_descriptions.append(concept)
            logger.debug(f"Imported concept description: {concept.id_short or concept.id}")
        except Exception as e:
            logger.warning(f"Failed to parse concept description: {e}")

    def _parse_core_properties(self, content: bytes) -> PackageMetadata:
        """Parse OPC core properties XML.

        Args:
            content: XML content bytes

        Returns:
            PackageMetadata object
        """
        # OPC Core Properties namespaces
        cp_ns = "http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
        dc_ns = "http://purl.org/dc/elements/1.1/"
        dcterms_ns = "http://purl.org/dc/terms/"

        # nosec B314 - XML from trusted AASX packages
        root = ET.fromstring(content)  # nosec B314

        metadata = PackageMetadata()

        # Extract properties
        title_elem = root.find(f".//{{{dc_ns}}}title")
        if title_elem is not None and title_elem.text:
            metadata.title = title_elem.text

        creator_elem = root.find(f".//{{{dc_ns}}}creator")
        if creator_elem is not None and creator_elem.text:
            metadata.creator = creator_elem.text

        desc_elem = root.find(f".//{{{dc_ns}}}description")
        if desc_elem is not None and desc_elem.text:
            metadata.description = desc_elem.text

        created_elem = root.find(f".//{{{dcterms_ns}}}created")
        if created_elem is not None and created_elem.text:
            try:
                metadata.created = datetime.fromisoformat(created_elem.text)
            except ValueError:
                logger.warning(f"Failed to parse created date: {created_elem.text}")

        modified_elem = root.find(f".//{{{dcterms_ns}}}modified")
        if modified_elem is not None and modified_elem.text:
            try:
                metadata.modified = datetime.fromisoformat(modified_elem.text)
            except ValueError:
                logger.warning(f"Failed to parse modified date: {modified_elem.text}")

        version_elem = root.find(f".//{{{cp_ns}}}version")
        if version_elem is not None and version_elem.text:
            metadata.version = version_elem.text

        return metadata


class AasxExporter:
    """Exports Titan-AAS models to AASX packages."""

    # OPC relationship types
    AAS_SPEC_REL_TYPE = "http://admin-shell.io/aasx/relationships/aas-spec"
    AASX_ORIGIN_REL_TYPE = "http://admin-shell.io/aasx/relationships/aasx-origin"

    async def export_package(
        self,
        shells: list[AssetAdministrationShell],
        submodels: list[Submodel],
        output_path: str | Path,
        concept_descriptions: list[ConceptDescription] | None = None,
        supplementary_files: dict[str, bytes] | None = None,
        use_json: bool = True,
        thumbnail: bytes | None = None,
        core_properties: PackageMetadata | None = None,
    ) -> None:
        """Export shells and submodels to an AASX package.

        Args:
            shells: List of shells to export
            submodels: List of submodels to export
            output_path: Path for the output AASX file
            concept_descriptions: Optional list of concept descriptions to export
            supplementary_files: Optional dict of path -> bytes for attachments
            use_json: If True, use JSON format; if False, use XML
            thumbnail: Optional thumbnail image bytes (PNG/JPEG)
            core_properties: Optional OPC core properties metadata
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        buffer = await self.export_to_stream(
            shells=shells,
            submodels=submodels,
            concept_descriptions=concept_descriptions,
            supplementary_files=supplementary_files,
            use_json=use_json,
            thumbnail=thumbnail,
            core_properties=core_properties,
        )

        with open(output_path, "wb") as f:
            f.write(buffer.getvalue())

        logger.info(f"Exported AASX package to {output_path}")

    async def export_to_stream(
        self,
        shells: list[AssetAdministrationShell],
        submodels: list[Submodel],
        concept_descriptions: list[ConceptDescription] | None = None,
        supplementary_files: dict[str, bytes] | None = None,
        use_json: bool = True,
        thumbnail: bytes | None = None,
        core_properties: PackageMetadata | None = None,
    ) -> BytesIO:
        """Export shells and submodels to a binary stream.

        Args:
            shells: List of shells to export
            submodels: List of submodels to export
            concept_descriptions: Optional list of concept descriptions to export
            supplementary_files: Optional dict of path -> bytes for attachments
            use_json: If True, use JSON format; if False, use XML
            thumbnail: Optional thumbnail image bytes (PNG/JPEG)
            core_properties: Optional OPC core properties metadata

        Returns:
            BytesIO containing the AASX package
        """
        buffer = BytesIO()
        supplementary_files = supplementary_files or {}
        concept_descriptions = concept_descriptions or []

        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            # Track parts for relationships
            parts: list[tuple[str, str]] = []

            # Write environment JSON/XML
            # Use "data.json" / "data.xml" for BaSyx compatibility
            # (IDTA Part 5 allows both data.* and aas-environment.* naming)
            if use_json:
                env_path = "aasx/data.json"
                env_content = self._create_environment_json(shells, submodels, concept_descriptions)
                zf.writestr(env_path, env_content)
                parts.append((env_path, "application/json"))
            else:
                # XML export using XmlSerializer
                from titan.compat.xml_serializer import XmlSerializer

                env_path = "aasx/data.xml"
                serializer = XmlSerializer()
                env_content = serializer.serialize_environment(
                    shells, submodels, concept_descriptions
                )
                zf.writestr(env_path, env_content)
                parts.append((env_path, "application/xml"))

            # Write supplementary files
            for file_path, content in supplementary_files.items():
                full_path = f"aasx/supplementary-files/{file_path}"
                zf.writestr(full_path, content)

            # Write thumbnail if provided
            thumbnail_path = None
            if thumbnail:
                # Detect image format from magic bytes
                if thumbnail.startswith(b"\x89PNG"):
                    thumbnail_path = "aasx/thumbnail.png"
                    content_type = "image/png"
                elif thumbnail.startswith(b"\xff\xd8\xff"):
                    thumbnail_path = "aasx/thumbnail.jpg"
                    content_type = "image/jpeg"
                else:
                    # Default to PNG if unknown
                    thumbnail_path = "aasx/thumbnail.png"
                    content_type = "image/png"

                zf.writestr(thumbnail_path, thumbnail)
                parts.append((thumbnail_path, content_type))

            # Write core properties if provided
            if core_properties:
                core_props_path = "aasx/core-properties.xml"
                core_props_content = self._create_core_properties(core_properties)
                zf.writestr(core_props_path, core_props_content)
                parts.append((core_props_path, "application/xml"))

            # Write aasx-origin file (marker for AASX packages)
            zf.writestr("aasx/aasx-origin", "")

            # Write OPC metadata
            content_types = self._create_content_types(parts)
            zf.writestr("[Content_Types].xml", content_types)

            # Write package-level relationships (_rels/.rels)
            # This should ONLY point to aasx-origin per IDTA Part 5
            root_rels = self._create_root_rels()
            zf.writestr("_rels/.rels", root_rels)

            # Write aasx-origin relationships (aasx/_rels/aasx-origin.rels)
            # This points to the actual AAS spec file (data.xml or data.json)
            origin_rels = self._create_origin_rels(env_path, thumbnail_path)
            zf.writestr("aasx/_rels/aasx-origin.rels", origin_rels)

        buffer.seek(0)
        return buffer

    def _create_environment_json(
        self,
        shells: list[AssetAdministrationShell],
        submodels: list[Submodel],
        concept_descriptions: list[ConceptDescription] | None = None,
    ) -> bytes:
        """Create AAS environment JSON.

        Args:
            shells: List of shells to serialize
            submodels: List of submodels to serialize
            concept_descriptions: Optional list of concept descriptions

        Returns:
            UTF-8 encoded JSON bytes
        """
        concept_descriptions = concept_descriptions or []
        environment = {
            "assetAdministrationShells": [
                shell.model_dump(mode="json", by_alias=True, exclude_none=True) for shell in shells
            ],
            "submodels": [
                sm.model_dump(mode="json", by_alias=True, exclude_none=True) for sm in submodels
            ],
            "conceptDescriptions": [
                cd.model_dump(mode="json", by_alias=True, exclude_none=True)
                for cd in concept_descriptions
            ],
        }
        return orjson.dumps(environment, option=orjson.OPT_INDENT_2)

    def _create_content_types(self, parts: list[tuple[str, str]]) -> str:
        """Create [Content_Types].xml."""
        ns = "http://schemas.openxmlformats.org/package/2006/content-types"
        root = ET.Element("Types", xmlns=ns)

        # Default extensions
        ET.SubElement(root, "Default", Extension="json", ContentType="application/json")
        ET.SubElement(root, "Default", Extension="xml", ContentType="application/xml")
        rels_content_type = "application/vnd.openxmlformats-package.relationships+xml"
        ET.SubElement(root, "Default", Extension="rels", ContentType=rels_content_type)

        # Override for specific parts
        for part_path, content_type in parts:
            ET.SubElement(root, "Override", PartName=f"/{part_path}", ContentType=content_type)

        return ET.tostring(root, encoding="unicode", xml_declaration=True)

    def _create_root_rels(self) -> str:
        """Create _rels/.rels file (package-level relationships).

        Per IDTA Part 5, this should ONLY contain relationship to aasx-origin.
        """
        ns = "http://schemas.openxmlformats.org/package/2006/relationships"
        root = ET.Element("Relationships", xmlns=ns)

        # Add relationship to aasx-origin (ONLY this relationship at root level)
        ET.SubElement(
            root,
            "Relationship",
            Type=self.AASX_ORIGIN_REL_TYPE,
            Target="/aasx/aasx-origin",
            Id="rId1",
        )

        return ET.tostring(root, encoding="unicode", xml_declaration=True)

    def _create_origin_rels(self, env_path: str, thumbnail_path: str | None = None) -> str:
        """Create aasx/_rels/aasx-origin.rels file.

        This file contains relationships from aasx-origin to the actual
        AAS spec files (data.xml or data.json) and optionally a thumbnail.

        Args:
            env_path: Path to the environment file (e.g., "aasx/data.xml")
            thumbnail_path: Optional path to thumbnail image
        """
        ns = "http://schemas.openxmlformats.org/package/2006/relationships"
        root = ET.Element("Relationships", xmlns=ns)

        # Add relationship to AAS spec file
        ET.SubElement(
            root,
            "Relationship",
            Type=self.AAS_SPEC_REL_TYPE,
            Target=f"/{env_path}",
            Id="rId1",
        )

        # Add thumbnail relationship if provided
        if thumbnail_path:
            ET.SubElement(
                root,
                "Relationship",
                Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/thumbnail",
                Target=f"/{thumbnail_path}",
                Id="rId2",
            )

        return ET.tostring(root, encoding="unicode", xml_declaration=True)

    def _create_core_properties(self, metadata: PackageMetadata) -> str:
        """Create OPC core properties XML file.

        Args:
            metadata: Package metadata

        Returns:
            XML string for core-properties.xml
        """
        # OPC Core Properties namespace
        cp_ns = "http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
        dc_ns = "http://purl.org/dc/elements/1.1/"
        dcterms_ns = "http://purl.org/dc/terms/"
        xsi_ns = "http://www.w3.org/2001/XMLSchema-instance"

        # Register namespaces
        ET.register_namespace("cp", cp_ns)
        ET.register_namespace("dc", dc_ns)
        ET.register_namespace("dcterms", dcterms_ns)
        ET.register_namespace("xsi", xsi_ns)

        # Create root element
        root = ET.Element(
            f"{{{cp_ns}}}coreProperties",
            attrib={
                f"{{{xsi_ns}}}schemaLocation": f"{cp_ns} {cp_ns}",
            },
        )

        # Add properties
        if metadata.title:
            ET.SubElement(root, f"{{{dc_ns}}}title").text = metadata.title

        if metadata.creator:
            ET.SubElement(root, f"{{{dc_ns}}}creator").text = metadata.creator

        if metadata.description:
            ET.SubElement(root, f"{{{dc_ns}}}description").text = metadata.description

        if metadata.created:
            created_elem = ET.SubElement(
                root, f"{{{dcterms_ns}}}created", attrib={f"{{{xsi_ns}}}type": "dcterms:W3CDTF"}
            )
            created_elem.text = metadata.created.isoformat()

        if metadata.modified:
            modified_elem = ET.SubElement(
                root, f"{{{dcterms_ns}}}modified", attrib={f"{{{xsi_ns}}}type": "dcterms:W3CDTF"}
            )
            modified_elem.text = metadata.modified.isoformat()

        if metadata.version:
            ET.SubElement(root, f"{{{cp_ns}}}version").text = metadata.version

        return ET.tostring(root, encoding="unicode", xml_declaration=True)


async def import_aasx(path: str | Path) -> AasxPackage:
    """Convenience function to import an AASX package.

    Args:
        path: Path to the AASX file

    Returns:
        AasxPackage with shells and submodels
    """
    importer = AasxImporter()
    return await importer.import_package(path)


async def export_aasx(
    shells: list[AssetAdministrationShell],
    submodels: list[Submodel],
    output_path: str | Path,
    concept_descriptions: list[ConceptDescription] | None = None,
    use_json: bool = True,
    thumbnail: bytes | None = None,
    core_properties: PackageMetadata | None = None,
) -> None:
    """Convenience function to export to AASX.

    Args:
        shells: List of shells to export
        submodels: List of submodels to export
        output_path: Path for the output file
        concept_descriptions: Optional list of concept descriptions to export
        use_json: If True, use JSON format; if False, use XML
        thumbnail: Optional thumbnail image bytes (PNG/JPEG)
        core_properties: Optional OPC core properties metadata
    """
    exporter = AasxExporter()
    await exporter.export_package(
        shells,
        submodels,
        output_path,
        concept_descriptions,
        use_json=use_json,
        thumbnail=thumbnail,
        core_properties=core_properties,
    )

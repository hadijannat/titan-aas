"""OPC and AASX Package Validator.

Validates AASX packages for:
- Open Packaging Conventions (OPC) compliance
- Required metadata files
- Content type registration
- Relationship structure
- AASX-specific requirements
"""

from __future__ import annotations

import hashlib
import logging
import zipfile
from dataclasses import dataclass, field
from enum import Enum
from io import BytesIO
from typing import BinaryIO
from xml.etree import ElementTree as ET

logger = logging.getLogger(__name__)


class ValidationLevel(Enum):
    """Validation strictness levels."""

    STRICT = "strict"  # Full OPC + AASX compliance
    STANDARD = "standard"  # Required files + basic structure
    LENIENT = "lenient"  # Minimal validation, accept most packages


@dataclass
class ValidationIssue:
    """A single validation issue."""

    code: str
    message: str
    severity: str  # "error", "warning", "info"
    location: str | None = None


@dataclass
class ValidationResult:
    """Result of package validation."""

    valid: bool
    issues: list[ValidationIssue] = field(default_factory=list)
    content_hash: str | None = None
    file_count: int = 0
    total_size: int = 0

    @property
    def errors(self) -> list[ValidationIssue]:
        """Get only error-level issues."""
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[ValidationIssue]:
        """Get only warning-level issues."""
        return [i for i in self.issues if i.severity == "warning"]

    def add_error(self, code: str, message: str, location: str | None = None) -> None:
        """Add an error-level issue."""
        self.issues.append(ValidationIssue(code, message, "error", location))
        self.valid = False

    def add_warning(self, code: str, message: str, location: str | None = None) -> None:
        """Add a warning-level issue."""
        self.issues.append(ValidationIssue(code, message, "warning", location))

    def add_info(self, code: str, message: str, location: str | None = None) -> None:
        """Add an info-level issue."""
        self.issues.append(ValidationIssue(code, message, "info", location))


class OpcValidator:
    """Validates AASX packages for OPC and AASX compliance."""

    # OPC namespaces
    CONTENT_TYPES_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
    RELATIONSHIPS_NS = "http://schemas.openxmlformats.org/package/2006/relationships"

    # AASX relationship types
    AASX_ORIGIN_REL = "http://admin-shell.io/aasx/relationships/aasx-origin"
    AAS_SPEC_REL = "http://admin-shell.io/aasx/relationships/aas-spec"
    THUMBNAIL_REL = (
        "http://schemas.openxmlformats.org/package/2006/relationships/metadata/thumbnail"
    )
    CORE_PROPERTIES_REL = (
        "http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties"
    )

    # Required OPC files
    REQUIRED_FILES = {"[Content_Types].xml"}

    # Reserved OPC paths that should not be used for content
    RESERVED_PATHS = {"_rels/", "[Content_Types].xml"}

    # Common content type mappings
    CONTENT_TYPE_MAPPINGS = {
        "json": "application/json",
        "xml": "application/xml",
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "pdf": "application/pdf",
    }

    def __init__(self, level: ValidationLevel = ValidationLevel.STANDARD) -> None:
        """Initialize validator with strictness level."""
        self.level = level

    async def validate(self, stream: BinaryIO) -> ValidationResult:
        """Validate an AASX package.

        Args:
            stream: Binary stream containing AASX data

        Returns:
            ValidationResult with issues and metadata
        """
        result = ValidationResult(valid=True)

        # Read content for hashing
        content = stream.read()
        stream.seek(0)
        result.content_hash = hashlib.sha256(content).hexdigest()
        result.total_size = len(content)

        try:
            with zipfile.ZipFile(BytesIO(content), "r") as zf:
                file_list = zf.namelist()
                result.file_count = len(file_list)

                # Check ZIP integrity
                self._validate_zip_integrity(zf, result)

                # Check required OPC files
                self._validate_required_files(file_list, result)

                # Validate Content_Types.xml
                if "[Content_Types].xml" in file_list:
                    content_types_data = zf.read("[Content_Types].xml")
                    self._validate_content_types(content_types_data, file_list, result)

                # Validate relationships
                self._validate_relationships(zf, file_list, result)

                # Validate AASX-specific content
                self._validate_aasx_content(zf, file_list, result)

                # Enhanced validations (Phase 3)
                self._validate_part_uris(file_list, result)
                self._validate_reserved_paths(file_list, result)
                self._check_recommended_features(zf, file_list, result)

        except zipfile.BadZipFile as e:
            result.add_error("ZIP_INVALID", f"Invalid ZIP archive: {e}")
        except Exception as e:
            result.add_error("VALIDATION_ERROR", f"Validation failed: {e}")

        return result

    def _validate_zip_integrity(self, zf: zipfile.ZipFile, result: ValidationResult) -> None:
        """Verify ZIP archive integrity."""
        try:
            bad_file = zf.testzip()
            if bad_file:
                result.add_error("ZIP_CORRUPT", f"Corrupted file in archive: {bad_file}")
        except Exception as e:
            result.add_error("ZIP_TEST_FAILED", f"ZIP integrity test failed: {e}")

    def _validate_required_files(self, file_list: list[str], result: ValidationResult) -> None:
        """Check for required OPC files."""
        for required in self.REQUIRED_FILES:
            if required not in file_list:
                if self.level == ValidationLevel.STRICT:
                    result.add_error(
                        "MISSING_REQUIRED_FILE",
                        f"Missing required OPC file: {required}",
                    )
                else:
                    result.add_warning(
                        "MISSING_REQUIRED_FILE",
                        f"Missing OPC file: {required}",
                    )

    def _validate_content_types(
        self, data: bytes, file_list: list[str], result: ValidationResult
    ) -> None:
        """Validate [Content_Types].xml structure."""
        try:
            root = ET.fromstring(data)  # nosec B314 - validated AASX package

            # Check namespace
            if root.tag != f"{{{self.CONTENT_TYPES_NS}}}Types":
                result.add_warning(
                    "CONTENT_TYPES_NAMESPACE",
                    f"Unexpected root element: {root.tag}",
                    "[Content_Types].xml",
                )

            # Extract registered extensions and overrides
            extensions = set()
            overrides = set()

            for child in root:
                if child.tag == f"{{{self.CONTENT_TYPES_NS}}}Default":
                    ext = child.get("Extension", "").lower()
                    if ext:
                        extensions.add(ext)
                elif child.tag == f"{{{self.CONTENT_TYPES_NS}}}Override":
                    part = child.get("PartName", "")
                    if part:
                        overrides.add(part.lstrip("/"))

            # Check that content types are registered for files
            if self.level == ValidationLevel.STRICT:
                for filename in file_list:
                    if filename.startswith("_rels/") or filename == "[Content_Types].xml":
                        continue

                    ext = filename.split(".")[-1].lower() if "." in filename else ""
                    normalized = filename.lstrip("/")

                    if ext not in extensions and normalized not in overrides:
                        result.add_warning(
                            "UNREGISTERED_CONTENT_TYPE",
                            f"No content type registered for: {filename}",
                            "[Content_Types].xml",
                        )

        except ET.ParseError as e:
            result.add_error(
                "CONTENT_TYPES_PARSE_ERROR",
                f"Failed to parse [Content_Types].xml: {e}",
                "[Content_Types].xml",
            )

    def _validate_relationships(
        self, zf: zipfile.ZipFile, file_list: list[str], result: ValidationResult
    ) -> None:
        """Validate OPC relationships."""
        # Find all relationship files
        rels_files = [f for f in file_list if f.endswith(".rels")]

        # Check root relationships file
        root_rels = "_rels/.rels"
        if root_rels not in file_list:
            if self.level == ValidationLevel.STRICT:
                result.add_error(
                    "MISSING_RELS",
                    "Missing root relationships file: _rels/.rels",
                )
            else:
                result.add_warning(
                    "MISSING_RELS",
                    "Missing root relationships file: _rels/.rels",
                )
            return

        # Validate each relationship file
        for rels_file in rels_files:
            try:
                rels_data = zf.read(rels_file)
                root = ET.fromstring(rels_data)  # nosec B314 - validated AASX package

                # Check namespace
                if root.tag != f"{{{self.RELATIONSHIPS_NS}}}Relationships":
                    result.add_warning(
                        "RELS_NAMESPACE",
                        f"Unexpected root element in relationships: {root.tag}",
                        rels_file,
                    )

                # Validate each relationship
                for rel in root.findall(f"{{{self.RELATIONSHIPS_NS}}}Relationship"):
                    rel_type = rel.get("Type", "")
                    target = rel.get("Target", "")

                    # Check for AASX-origin in root rels (only in _rels/.rels)
                    if rels_file == root_rels and rel_type == self.AASX_ORIGIN_REL:
                        # Verify aasx-origin target exists
                        target_norm = target.lstrip("/")
                        if target_norm and target_norm not in file_list:
                            result.add_error(
                                "MISSING_RELS_TARGET",
                                f"AASX-origin target not found: {target}",
                                rels_file,
                            )

                    # Verify all relationship targets exist
                    if target:
                        # Resolve target path relative to source
                        if rels_file == root_rels:
                            # Root relationships are relative to package root
                            target_path = target.lstrip("/")
                        else:
                            # Part relationships are relative to the part's directory
                            source_dir = "/".join(rels_file.split("/")[:-2])  # Remove /_rels/x.rels
                            if source_dir:
                                target_path = f"{source_dir}/{target}".lstrip("/")
                            else:
                                target_path = target.lstrip("/")

                        # Normalize and check existence
                        if target_path not in file_list:
                            result.add_warning(
                                "MISSING_RELS_TARGET",
                                f"Relationship target not found: {target_path}",
                                rels_file,
                            )

            except ET.ParseError as e:
                result.add_error(
                    "RELS_PARSE_ERROR",
                    f"Failed to parse relationships: {e}",
                    rels_file,
                )

        # Check for AASX-origin in root rels
        try:
            root_rels_data = zf.read(root_rels)
            root_rels_tree = ET.fromstring(root_rels_data)  # nosec B314
            has_origin = any(
                rel.get("Type") == self.AASX_ORIGIN_REL
                for rel in root_rels_tree.findall(f"{{{self.RELATIONSHIPS_NS}}}Relationship")
            )

            if not has_origin and self.level == ValidationLevel.STRICT:
                result.add_warning(
                    "MISSING_AASX_ORIGIN",
                    "No aasx-origin relationship found in root",
                    root_rels,
                )
        except Exception:
            pass  # Already reported in loop above

    def _validate_aasx_content(
        self, zf: zipfile.ZipFile, file_list: list[str], result: ValidationResult
    ) -> None:
        """Validate AASX-specific content."""
        has_aas_content = False
        json_count = 0
        xml_count = 0

        for filename in file_list:
            lower = filename.lower()

            # Check for AAS content
            if lower.endswith(".json"):
                json_count += 1
                try:
                    content = zf.read(filename)
                    # Quick check for AAS-related content
                    if (
                        b"assetAdministrationShells" in content
                        or b"submodels" in content
                        or b'"modelType"' in content
                    ):
                        has_aas_content = True
                except Exception as e:
                    result.add_warning(
                        "JSON_READ_ERROR",
                        f"Failed to read JSON file: {e}",
                        filename,
                    )

            elif lower.endswith(".xml") and not filename.startswith("_"):
                xml_count += 1
                if "aas-environment" in lower or "aas_environment" in lower:
                    has_aas_content = True

        # Verify package has AAS content
        if not has_aas_content:
            if self.level in (ValidationLevel.STRICT, ValidationLevel.STANDARD):
                result.add_warning(
                    "NO_AAS_CONTENT",
                    "No AAS content detected in package",
                )

        # Add info about content
        result.add_info(
            "CONTENT_SUMMARY",
            f"Package contains {json_count} JSON files, {xml_count} XML files",
        )

    def _validate_part_uris(self, file_list: list[str], result: ValidationResult) -> None:
        """Validate Part URIs according to OPC spec.

        Part URIs must:
        - Not contain spaces
        - Use forward slashes (/)
        - Be properly encoded
        - Not start with /
        """
        for filename in file_list:
            # Check for spaces in URI
            if " " in filename:
                result.add_error(
                    "PART_URI_SPACE",
                    f"Part URI contains space: {filename}",
                    filename,
                )

            # Check for backslashes (should be forward slashes)
            if "\\" in filename:
                result.add_error(
                    "PART_URI_BACKSLASH",
                    f"Part URI contains backslash: {filename}",
                    filename,
                )

            # Check for leading slash (relative paths only in OPC)
            if filename.startswith("/"):
                if self.level == ValidationLevel.STRICT:
                    result.add_warning(
                        "PART_URI_LEADING_SLASH",
                        f"Part URI has leading slash: {filename}",
                        filename,
                    )

            # Check for percent encoding issues (unencoded special chars)
            special_chars = ["<", ">", '"', "|", "?", "*"]
            for char in special_chars:
                if char in filename:
                    result.add_error(
                        "PART_URI_INVALID_CHAR",
                        f"Part URI contains invalid character '{char}': {filename}",
                        filename,
                    )

    def _validate_reserved_paths(self, file_list: list[str], result: ValidationResult) -> None:
        """Check for misuse of reserved OPC paths."""
        for filename in file_list:
            # Check if content is placed in _rels directory (reserved for relationships)
            if filename.startswith("_rels/") and not filename.endswith(".rels"):
                result.add_warning(
                    "RESERVED_PATH_MISUSE",
                    f"Non-relationship file in _rels directory: {filename}",
                    filename,
                )

    def _check_recommended_features(
        self, zf: zipfile.ZipFile, file_list: list[str], result: ValidationResult
    ) -> None:
        """Check for optional but recommended OPC features."""
        # Check for thumbnail
        has_thumbnail = False
        for filename in file_list:
            lower = filename.lower()
            if "thumbnail" in lower and (lower.endswith(".png") or lower.endswith(".jpg")):
                has_thumbnail = True
                break

        if not has_thumbnail and self.level == ValidationLevel.STRICT:
            result.add_info(
                "NO_THUMBNAIL",
                "Package does not include a thumbnail image (recommended)",
            )

        # Check for core properties
        has_core_properties = False
        for filename in file_list:
            if "core-properties" in filename.lower() and filename.endswith(".xml"):
                has_core_properties = True
                break

        if not has_core_properties and self.level == ValidationLevel.STRICT:
            result.add_info(
                "NO_CORE_PROPERTIES",
                "Package does not include OPC core properties metadata (recommended)",
            )

        # Check for digital signature
        has_signature = False
        for filename in file_list:
            if filename.startswith("_xmlsignatures/") or filename.endswith(".sig"):
                has_signature = True
                break

        if not has_signature and self.level == ValidationLevel.STRICT:
            result.add_info(
                "NO_DIGITAL_SIGNATURE",
                "Package is not digitally signed (recommended for production)",
            )

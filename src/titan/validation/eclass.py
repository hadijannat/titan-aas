"""ECLASS vocabulary validator.

This module provides validation for ECLASS (eCl@ss) semantic identifiers,
the international product classification standard widely used in Industry 4.0.

ECLASS IRDI Format:
    0173-1#XX-XXXXXX#YYY

    - 0173: ISO registration authority code for ECLASS
    - 1: Version segment identifier
    - XX: Object type indicator (01=class, 02=property, etc.)
    - XXXXXX: Object code (alphanumeric, 6+ characters)
    - YYY: Version number (3 digits)

Examples:
    - 0173-1#01-AEW677#001 (Class: Pump)
    - 0173-1#02-AAO677#001 (Property: Max temperature)
    - 0173-1#07-BAF963#001 (Value: On/Off)

Reference: https://eclass.eu/
"""

from __future__ import annotations

import re
from typing import Final

from titan.validation.vocabulary import BaseVocabularyValidator, ValidationResult

# ECLASS IRDI pattern components
# Full format: 0173-1#XX-XXXXXX#YYY
# - 0173: eCl@ss registration code
# - 1: Version segment
# - XX: Object type (01-08)
# - XXXXXX: Code (alphanumeric, typically 6+ chars)
# - YYY: Version (3 digits)
ECLASS_IRDI_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^0173-1#"
    r"(?P<type>\d{2})-"
    r"(?P<code>[A-Z0-9]{3,})"
    r"#"
    r"(?P<version>\d{3})$",
    re.IGNORECASE,
)

# Alternative ECLASS URL format
# https://eclass.eu/api/irdi/0173-1%2301-AEW677%23001
ECLASS_URL_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^https?://(?:www\.)?eclass\.eu/",
    re.IGNORECASE,
)

# Object type codes and their meanings
ECLASS_OBJECT_TYPES: Final[dict[str, str]] = {
    "01": "Class",
    "02": "Property",
    "03": "Unit",
    "04": "Value (deprecated)",
    "05": "Block",
    "06": "Keyword",
    "07": "Value",
    "08": "Application Class",
}


class EclassValidator(BaseVocabularyValidator):
    """Validator for ECLASS (eCl@ss) semantic identifiers.

    Validates ECLASS IRDIs according to the international product
    classification standard.

    Supports:
    - IRDI format validation (0173-1#XX-XXXXXX#YYY)
    - Object type validation (01=class, 02=property, etc.)
    - Version number validation
    - URL format detection

    Attributes:
        allow_url_format: Accept ECLASS URLs in addition to IRDIs
        strict_type_check: Enforce valid object type codes
    """

    def __init__(
        self,
        allow_url_format: bool = True,
        strict_type_check: bool = False,
    ):
        """Initialize the ECLASS validator.

        Args:
            allow_url_format: Accept ECLASS URLs (default: True)
            strict_type_check: Require known object type codes (default: False)
        """
        self.allow_url_format = allow_url_format
        self.strict_type_check = strict_type_check

    @property
    def name(self) -> str:
        """Name of the vocabulary."""
        return "ECLASS"

    @property
    def pattern(self) -> re.Pattern[str]:
        """Pattern to detect ECLASS identifiers."""
        return ECLASS_IRDI_PATTERN

    def matches(self, semantic_id: str) -> bool:
        """Check if the semantic ID is an ECLASS identifier.

        Args:
            semantic_id: The semantic ID to check

        Returns:
            True if this looks like an ECLASS identifier
        """
        if ECLASS_IRDI_PATTERN.match(semantic_id):
            return True
        if self.allow_url_format and ECLASS_URL_PATTERN.match(semantic_id):
            return True
        return False

    def validate(self, semantic_id: str) -> ValidationResult:
        """Validate an ECLASS semantic identifier.

        Checks:
        1. Format matches ECLASS IRDI pattern
        2. Object type code is valid (if strict_type_check)
        3. Version number is valid (000-999)

        Args:
            semantic_id: The ECLASS IRDI to validate

        Returns:
            ValidationResult with validation status and details
        """
        # Handle URL format
        if ECLASS_URL_PATTERN.match(semantic_id):
            if not self.allow_url_format:
                return ValidationResult(
                    valid=False,
                    semantic_id=semantic_id,
                    vocabulary=self.name,
                    error="ECLASS URL format not allowed",
                )
            # Extract IRDI from URL and validate
            return self._validate_url_format(semantic_id)

        # Validate IRDI format
        match = ECLASS_IRDI_PATTERN.match(semantic_id)
        if not match:
            return ValidationResult(
                valid=False,
                semantic_id=semantic_id,
                vocabulary=self.name,
                error="Invalid ECLASS IRDI format. Expected: 0173-1#XX-XXXXXX#YYY",
            )

        # Extract components
        object_type = match.group("type")
        code = match.group("code")
        version = match.group("version")

        # Validate object type
        if self.strict_type_check and object_type not in ECLASS_OBJECT_TYPES:
            return ValidationResult(
                valid=False,
                semantic_id=semantic_id,
                vocabulary=self.name,
                error=f"Unknown ECLASS object type: {object_type}. "
                f"Valid types: {', '.join(ECLASS_OBJECT_TYPES.keys())}",
            )

        # Build details
        details: dict[str, str | int] = {
            "object_type_code": object_type,
            "object_type_name": ECLASS_OBJECT_TYPES.get(object_type, "Unknown"),
            "code": code,
            "version": int(version),
        }

        return ValidationResult(
            valid=True,
            semantic_id=semantic_id,
            vocabulary=self.name,
            version=version,
            details=details,
        )

    def _validate_url_format(self, semantic_id: str) -> ValidationResult:
        """Validate ECLASS URL format.

        Args:
            semantic_id: The ECLASS URL to validate

        Returns:
            ValidationResult with validation status
        """
        # Try to extract IRDI from URL
        # Common formats:
        # https://eclass.eu/api/irdi/0173-1%2301-AEW677%23001
        # https://eclass.eu/eclass-standard/0173-1-01-AEW677-001

        import urllib.parse

        try:
            # Parse URL-encoded IRDI
            decoded = urllib.parse.unquote(semantic_id)

            # Try to find IRDI pattern in the URL
            match = ECLASS_IRDI_PATTERN.search(decoded)
            if match:
                # Validate the extracted IRDI
                irdi = match.group(0)
                result = self.validate(irdi)
                if result.details:
                    result.details["source_url"] = semantic_id
                return result

        except Exception:
            pass

        # URL format detected but couldn't extract valid IRDI
        return ValidationResult(
            valid=True,  # Accept URL format as valid but unverified
            semantic_id=semantic_id,
            vocabulary=self.name,
            details={"format": "url", "verified": False},
        )

    @staticmethod
    def get_object_type_name(code: str) -> str | None:
        """Get the human-readable name for an object type code.

        Args:
            code: Two-digit object type code

        Returns:
            Object type name or None if unknown
        """
        return ECLASS_OBJECT_TYPES.get(code)

    @staticmethod
    def parse_irdi(irdi: str) -> dict[str, str | int] | None:
        """Parse an ECLASS IRDI into components.

        Args:
            irdi: The ECLASS IRDI string

        Returns:
            Dict with type, code, version or None if invalid
        """
        match = ECLASS_IRDI_PATTERN.match(irdi)
        if not match:
            return None

        return {
            "type": match.group("type"),
            "type_name": ECLASS_OBJECT_TYPES.get(match.group("type"), "Unknown"),
            "code": match.group("code"),
            "version": int(match.group("version")),
        }

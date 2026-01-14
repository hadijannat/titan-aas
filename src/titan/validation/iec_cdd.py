"""IEC Common Data Dictionary (CDD) validator.

This module provides validation for IEC CDD semantic identifiers,
the Common Data Dictionary for electrical and electronic components
defined in IEC 61360.

IEC CDD IRDI Format:
    0112/X///YYY#ZZZZ#AAA

    - 0112: IEC registration authority code
    - X: Database indicator (0=published, 2=private)
    - YYY: Organization code
    - ZZZZ: Object identifier
    - AAA: Version

Alternative format (simplified):
    0112/2///61360_4_27000#ABF999#001

IEC 61360-4 URL format:
    https://cdd.iec.ch/cdd/iec61360/iec61360.nsf/TreeFrameset?...

Reference: https://cdd.iec.ch/
"""

from __future__ import annotations

import re
from typing import Final

from titan.validation.vocabulary import BaseVocabularyValidator, ValidationResult

# IEC CDD IRDI patterns
# Full IRDI format: 0112/X///ORG#CODE#VER
IEC_CDD_IRDI_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^0112/"
    r"(?P<db>[02])///"
    r"(?P<org>[A-Z0-9_-]+)"
    r"#"
    r"(?P<code>[A-Z0-9_-]+)"
    r"#"
    r"(?P<version>\d{3})$",
    re.IGNORECASE,
)

# IEC 61360-4 specific pattern (most common in AAS)
IEC_61360_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^0112/2///61360[_-]4[_-]"
    r"(?P<class>\d+)"
    r"#"
    r"(?P<code>[A-Z0-9]+)"
    r"#"
    r"(?P<version>\d{3})$",
    re.IGNORECASE,
)

# IEC CDD URL pattern
IEC_CDD_URL_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^https?://(?:www\.)?cdd\.iec\.ch/",
    re.IGNORECASE,
)

# Simplified pattern for broader matching
IEC_SIMPLE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^0112/",
    re.IGNORECASE,
)


class IecCddValidator(BaseVocabularyValidator):
    """Validator for IEC CDD (Common Data Dictionary) semantic identifiers.

    Validates IEC CDD IRDIs according to IEC 61360 standard for
    data element types with associated classification schemes.

    Supports:
    - IRDI format validation (0112/X///ORG#CODE#VER)
    - IEC 61360-4 specific format
    - URL format detection
    - Database indicator validation (0=published, 2=private)

    Attributes:
        allow_url_format: Accept IEC CDD URLs in addition to IRDIs
        allow_private_db: Accept private database (2) identifiers
    """

    def __init__(
        self,
        allow_url_format: bool = True,
        allow_private_db: bool = True,
    ):
        """Initialize the IEC CDD validator.

        Args:
            allow_url_format: Accept IEC CDD URLs (default: True)
            allow_private_db: Accept private database codes (default: True)
        """
        self.allow_url_format = allow_url_format
        self.allow_private_db = allow_private_db

    @property
    def name(self) -> str:
        """Name of the vocabulary."""
        return "IEC_CDD"

    @property
    def pattern(self) -> re.Pattern[str]:
        """Pattern to detect IEC CDD identifiers."""
        return IEC_SIMPLE_PATTERN

    def matches(self, semantic_id: str) -> bool:
        """Check if the semantic ID is an IEC CDD identifier.

        Args:
            semantic_id: The semantic ID to check

        Returns:
            True if this looks like an IEC CDD identifier
        """
        if IEC_SIMPLE_PATTERN.match(semantic_id):
            return True
        if self.allow_url_format and IEC_CDD_URL_PATTERN.match(semantic_id):
            return True
        return False

    def validate(self, semantic_id: str) -> ValidationResult:
        """Validate an IEC CDD semantic identifier.

        Checks:
        1. Format matches IEC CDD IRDI pattern
        2. Database indicator is valid (0 or 2)
        3. Version number is valid (000-999)

        Args:
            semantic_id: The IEC CDD IRDI to validate

        Returns:
            ValidationResult with validation status and details
        """
        # Handle URL format
        if IEC_CDD_URL_PATTERN.match(semantic_id):
            if not self.allow_url_format:
                return ValidationResult(
                    valid=False,
                    semantic_id=semantic_id,
                    vocabulary=self.name,
                    error="IEC CDD URL format not allowed",
                )
            return self._validate_url_format(semantic_id)

        # Try IEC 61360-4 specific pattern first (most common in AAS)
        match = IEC_61360_PATTERN.match(semantic_id)
        if match:
            return self._validate_61360_match(semantic_id, match)

        # Try general IEC CDD pattern
        match = IEC_CDD_IRDI_PATTERN.match(semantic_id)
        if match:
            return self._validate_irdi_match(semantic_id, match)

        # Check if it starts with 0112 but doesn't match patterns
        if IEC_SIMPLE_PATTERN.match(semantic_id):
            return ValidationResult(
                valid=False,
                semantic_id=semantic_id,
                vocabulary=self.name,
                error="Invalid IEC CDD IRDI format. Expected: 0112/X///ORG#CODE#VER",
            )

        return ValidationResult(
            valid=False,
            semantic_id=semantic_id,
            vocabulary=self.name,
            error="Not a recognized IEC CDD identifier",
        )

    def _validate_61360_match(
        self, semantic_id: str, match: re.Match[str]
    ) -> ValidationResult:
        """Validate IEC 61360-4 specific format.

        Args:
            semantic_id: Original semantic ID
            match: Regex match object

        Returns:
            ValidationResult with details
        """
        class_num = match.group("class")
        code = match.group("code")
        version = match.group("version")

        details: dict[str, str | int | bool] = {
            "standard": "IEC 61360-4",
            "class": class_num,
            "code": code,
            "version": int(version),
            "database": "private",
        }

        return ValidationResult(
            valid=True,
            semantic_id=semantic_id,
            vocabulary=self.name,
            version=version,
            details=details,
        )

    def _validate_irdi_match(
        self, semantic_id: str, match: re.Match[str]
    ) -> ValidationResult:
        """Validate general IEC CDD IRDI format.

        Args:
            semantic_id: Original semantic ID
            match: Regex match object

        Returns:
            ValidationResult with details
        """
        db_indicator = match.group("db")
        org = match.group("org")
        code = match.group("code")
        version = match.group("version")

        # Check database indicator
        if db_indicator == "2" and not self.allow_private_db:
            return ValidationResult(
                valid=False,
                semantic_id=semantic_id,
                vocabulary=self.name,
                error="Private database (2) identifiers not allowed",
            )

        details: dict[str, str | int] = {
            "database_indicator": db_indicator,
            "database": "published" if db_indicator == "0" else "private",
            "organization": org,
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
        """Validate IEC CDD URL format.

        Args:
            semantic_id: The IEC CDD URL to validate

        Returns:
            ValidationResult with validation status
        """
        # IEC CDD URLs are complex; accept them as valid but unverified
        return ValidationResult(
            valid=True,
            semantic_id=semantic_id,
            vocabulary=self.name,
            details={"format": "url", "verified": False},
        )

    @staticmethod
    def parse_irdi(irdi: str) -> dict[str, str | int] | None:
        """Parse an IEC CDD IRDI into components.

        Args:
            irdi: The IEC CDD IRDI string

        Returns:
            Dict with components or None if invalid
        """
        # Try 61360-4 format first
        match = IEC_61360_PATTERN.match(irdi)
        if match:
            return {
                "standard": "IEC 61360-4",
                "class": match.group("class"),
                "code": match.group("code"),
                "version": int(match.group("version")),
            }

        # Try general format
        match = IEC_CDD_IRDI_PATTERN.match(irdi)
        if match:
            db = match.group("db")
            return {
                "database": "published" if db == "0" else "private",
                "organization": match.group("org"),
                "code": match.group("code"),
                "version": int(match.group("version")),
            }

        return None

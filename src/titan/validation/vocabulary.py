"""Base vocabulary validation framework.

This module provides the core validation framework for semantic identifiers,
including the base validator interface, validation results, and modes.

The framework supports multiple validation modes:
- strict: Raises ValidationError for invalid semanticIds
- warn: Logs warnings but accepts invalid semanticIds
- off: Disables validation entirely

Example:
    from titan.validation import VocabularyValidator, ValidationMode
    from titan.validation.registry import VocabularyRegistry

    registry = VocabularyRegistry()
    validator = VocabularyValidator(registry, mode=ValidationMode.WARN)

    result = validator.validate("0173-1#01-AEW677#001")
    print(f"Valid: {result.valid}, Vocabulary: {result.vocabulary}")
"""

from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from titan.validation.registry import VocabularyRegistry

logger = logging.getLogger(__name__)


class ValidationMode(str, Enum):
    """Validation mode for semantic identifier checking.

    Attributes:
        STRICT: Reject invalid semanticIds (raise ValidationError)
        WARN: Log warnings for invalid semanticIds but accept them
        OFF: Disable validation entirely
    """

    STRICT = "strict"
    WARN = "warn"
    OFF = "off"


@dataclass
class ValidationResult:
    """Result of a semantic ID validation check.

    Attributes:
        valid: Whether the semantic ID is valid
        semantic_id: The semantic ID that was validated
        vocabulary: Name of the matched vocabulary (e.g., "ECLASS", "IEC_CDD")
        version: Version of the vocabulary (if determinable)
        error: Error message if validation failed
        details: Additional validation details
    """

    valid: bool
    semantic_id: str
    vocabulary: str | None = None
    version: str | None = None
    error: str | None = None
    details: dict[str, Any] | None = None


class ValidationError(Exception):
    """Raised when validation fails in strict mode.

    Attributes:
        message: Human-readable error message
        semantic_id: The invalid semantic ID
        vocabulary: Expected vocabulary (if known)
    """

    def __init__(
        self,
        message: str,
        semantic_id: str,
        vocabulary: str | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.semantic_id = semantic_id
        self.vocabulary = vocabulary


class BaseVocabularyValidator(ABC):
    """Abstract base class for vocabulary-specific validators.

    Subclasses implement validation logic for specific vocabulary
    standards (ECLASS, IEC CDD, etc.).

    Each validator should:
    1. Detect if a semantic ID belongs to its vocabulary
    2. Validate the format and structure
    3. Optionally validate against an external API or local cache
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the vocabulary (e.g., 'ECLASS', 'IEC_CDD')."""

    @property
    @abstractmethod
    def pattern(self) -> re.Pattern[str]:
        """Regex pattern to detect this vocabulary's semantic IDs."""

    def matches(self, semantic_id: str) -> bool:
        """Check if the semantic ID belongs to this vocabulary.

        Args:
            semantic_id: The semantic ID to check

        Returns:
            True if the semantic ID matches this vocabulary's pattern
        """
        return self.pattern.match(semantic_id) is not None

    @abstractmethod
    def validate(self, semantic_id: str) -> ValidationResult:
        """Validate the semantic ID against this vocabulary.

        Args:
            semantic_id: The semantic ID to validate

        Returns:
            ValidationResult with validation status and details
        """


class VocabularyValidator:
    """Main validator that dispatches to vocabulary-specific validators.

    This class serves as the primary entry point for semantic ID validation.
    It maintains a registry of vocabulary validators and dispatches
    validation requests to the appropriate validator.

    Attributes:
        registry: Registry of vocabulary-specific validators
        mode: Validation mode (strict, warn, or off)
        cache_size: Maximum number of validation results to cache
    """

    def __init__(
        self,
        registry: VocabularyRegistry,
        mode: ValidationMode = ValidationMode.WARN,
        cache_size: int = 1000,
    ):
        """Initialize the vocabulary validator.

        Args:
            registry: Registry containing vocabulary-specific validators
            mode: Validation mode (default: WARN)
            cache_size: Size of the validation result cache
        """
        self.registry = registry
        self.mode = mode
        self._cache_size = cache_size
        # Create cached validate method
        self._cached_validate = lru_cache(maxsize=cache_size)(self._validate_impl)

    def validate(self, semantic_id: str) -> ValidationResult:
        """Validate a semantic ID.

        Dispatches to the appropriate vocabulary validator based on
        the semantic ID pattern. Returns a cached result if available.

        Args:
            semantic_id: The semantic ID to validate

        Returns:
            ValidationResult with validation status

        Raises:
            ValidationError: If mode is STRICT and validation fails
        """
        if self.mode == ValidationMode.OFF:
            return ValidationResult(
                valid=True,
                semantic_id=semantic_id,
                vocabulary=None,
                details={"mode": "off", "skipped": True},
            )

        result = self._cached_validate(semantic_id)

        if not result.valid:
            if self.mode == ValidationMode.STRICT:
                raise ValidationError(
                    message=result.error or "Validation failed",
                    semantic_id=semantic_id,
                    vocabulary=result.vocabulary,
                )
            elif self.mode == ValidationMode.WARN:
                logger.warning(
                    "Invalid semantic ID: %s - %s",
                    semantic_id,
                    result.error,
                )

        return result

    def _validate_impl(self, semantic_id: str) -> ValidationResult:
        """Internal validation implementation (cached).

        Args:
            semantic_id: The semantic ID to validate

        Returns:
            ValidationResult with validation status
        """
        # Find matching validator
        validator = self.registry.find_validator(semantic_id)

        if validator is None:
            # No matching vocabulary - return unknown result
            return ValidationResult(
                valid=True,  # Unknown vocabularies are accepted
                semantic_id=semantic_id,
                vocabulary=None,
                details={"recognized": False},
            )

        # Delegate to vocabulary-specific validator
        return validator.validate(semantic_id)

    def validate_many(self, semantic_ids: list[str]) -> list[ValidationResult]:
        """Validate multiple semantic IDs.

        Args:
            semantic_ids: List of semantic IDs to validate

        Returns:
            List of ValidationResults in the same order
        """
        return [self.validate(sid) for sid in semantic_ids]

    def is_valid(self, semantic_id: str) -> bool:
        """Quick check if a semantic ID is valid.

        Args:
            semantic_id: The semantic ID to check

        Returns:
            True if valid, False otherwise
        """
        try:
            result = self.validate(semantic_id)
            return result.valid
        except ValidationError:
            return False

    def clear_cache(self) -> None:
        """Clear the validation result cache."""
        self._cached_validate.cache_clear()

    @property
    def cache_info(self) -> dict[str, int]:
        """Get cache statistics.

        Returns:
            Dict with hits, misses, maxsize, currsize
        """
        info = self._cached_validate.cache_info()
        return {
            "hits": info.hits,
            "misses": info.misses,
            "maxsize": info.maxsize or 0,
            "currsize": info.currsize,
        }

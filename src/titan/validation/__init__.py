"""External vocabulary validation for AAS semantic identifiers.

This package provides validation capabilities for semantic identifiers (semanticId)
against external vocabulary standards used in Industry 4.0 environments.

Supported vocabularies:
- ECLASS: International product classification standard (0173-1#XX-XXXXXX#XXX)
- IEC CDD: Common Data Dictionary for electrical/electronic (IEC 61360)

Validation modes:
- strict: Reject invalid semanticIds (raise ValidationError)
- warn: Log warnings for invalid semanticIds but accept them
- off: Disable validation (pass-through)

Example:
    from titan.validation import (
        VocabularyRegistry,
        VocabularyValidator,
        ValidationMode,
    )

    # Create registry and add validators
    registry = VocabularyRegistry()
    registry.register_eclass()
    registry.register_iec_cdd()

    # Create validator
    validator = VocabularyValidator(registry, mode=ValidationMode.WARN)

    # Validate a semantic ID
    result = validator.validate("0173-1#01-AEW677#001")
    if result.valid:
        print(f"Valid ECLASS ID: {result.vocabulary}")
    else:
        print(f"Invalid: {result.error}")
"""

from titan.validation.eclass import EclassValidator
from titan.validation.iec_cdd import IecCddValidator
from titan.validation.registry import VocabularyRegistry
from titan.validation.vocabulary import (
    ValidationError,
    ValidationMode,
    ValidationResult,
    VocabularyValidator,
)

__all__ = [
    # Core
    "VocabularyValidator",
    "VocabularyRegistry",
    "ValidationMode",
    "ValidationResult",
    "ValidationError",
    # Vocabulary-specific validators
    "EclassValidator",
    "IecCddValidator",
]

"""Tests for vocabulary validation framework.

Tests the VocabularyValidator, VocabularyRegistry, and vocabulary-specific
validators (ECLASS, IEC CDD).
"""

import pytest

from titan.validation import (
    EclassValidator,
    IecCddValidator,
    ValidationError,
    ValidationMode,
    ValidationResult,
    VocabularyRegistry,
    VocabularyValidator,
)


class TestValidationResult:
    """Test ValidationResult dataclass."""

    def test_valid_result(self) -> None:
        """Create valid result."""
        result = ValidationResult(
            valid=True,
            semantic_id="0173-1#01-AEW677#001",
            vocabulary="ECLASS",
        )
        assert result.valid is True
        assert result.vocabulary == "ECLASS"
        assert result.error is None

    def test_invalid_result(self) -> None:
        """Create invalid result with error."""
        result = ValidationResult(
            valid=False,
            semantic_id="invalid",
            vocabulary="ECLASS",
            error="Invalid format",
        )
        assert result.valid is False
        assert result.error == "Invalid format"


class TestValidationError:
    """Test ValidationError exception."""

    def test_error_attributes(self) -> None:
        """Error stores attributes."""
        error = ValidationError(
            message="Invalid IRDI format",
            semantic_id="bad-id",
            vocabulary="ECLASS",
        )
        assert error.message == "Invalid IRDI format"
        assert error.semantic_id == "bad-id"
        assert error.vocabulary == "ECLASS"

    def test_error_is_exception(self) -> None:
        """Error is an exception."""
        error = ValidationError("Test", "id")
        assert isinstance(error, Exception)


class TestValidationMode:
    """Test ValidationMode enum."""

    def test_strict_mode(self) -> None:
        """Strict mode value."""
        assert ValidationMode.STRICT.value == "strict"

    def test_warn_mode(self) -> None:
        """Warn mode value."""
        assert ValidationMode.WARN.value == "warn"

    def test_off_mode(self) -> None:
        """Off mode value."""
        assert ValidationMode.OFF.value == "off"


class TestEclassValidator:
    """Test ECLASS validator."""

    def test_valid_class_irdi(self) -> None:
        """Validate valid ECLASS class IRDI."""
        validator = EclassValidator()
        result = validator.validate("0173-1#01-AEW677#001")

        assert result.valid is True
        assert result.vocabulary == "ECLASS"
        assert result.details is not None
        assert result.details["object_type_code"] == "01"
        assert result.details["object_type_name"] == "Class"

    def test_valid_property_irdi(self) -> None:
        """Validate valid ECLASS property IRDI."""
        validator = EclassValidator()
        result = validator.validate("0173-1#02-AAO677#001")

        assert result.valid is True
        assert result.details is not None
        assert result.details["object_type_code"] == "02"
        assert result.details["object_type_name"] == "Property"

    def test_valid_value_irdi(self) -> None:
        """Validate valid ECLASS value IRDI."""
        validator = EclassValidator()
        result = validator.validate("0173-1#07-BAF963#001")

        assert result.valid is True
        assert result.details is not None
        assert result.details["object_type_code"] == "07"
        assert result.details["object_type_name"] == "Value"

    def test_invalid_format(self) -> None:
        """Invalid ECLASS format fails validation."""
        validator = EclassValidator()
        result = validator.validate("invalid-irdi")

        assert result.valid is False
        assert "Invalid ECLASS IRDI format" in (result.error or "")

    def test_matches_eclass_pattern(self) -> None:
        """Matches detects ECLASS patterns."""
        validator = EclassValidator()

        assert validator.matches("0173-1#01-AEW677#001") is True
        assert validator.matches("0173-1#02-AAO677#001") is True
        assert validator.matches("0112/2///61360_4#AAA001#001") is False
        assert validator.matches("invalid") is False

    def test_strict_type_check_unknown_type(self) -> None:
        """Strict mode rejects unknown object types."""
        validator = EclassValidator(strict_type_check=True)

        # Valid type should pass
        result = validator.validate("0173-1#01-AEW677#001")
        assert result.valid is True

        # Unknown type (99) should fail
        result = validator.validate("0173-1#99-AEW677#001")
        assert result.valid is False
        assert "Unknown ECLASS object type" in (result.error or "")

    def test_parse_irdi(self) -> None:
        """Parse IRDI into components."""
        parsed = EclassValidator.parse_irdi("0173-1#01-AEW677#001")

        assert parsed is not None
        assert parsed["type"] == "01"
        assert parsed["type_name"] == "Class"
        assert parsed["code"] == "AEW677"
        assert parsed["version"] == 1

    def test_parse_invalid_irdi(self) -> None:
        """Parse returns None for invalid IRDI."""
        parsed = EclassValidator.parse_irdi("invalid")
        assert parsed is None

    def test_get_object_type_name(self) -> None:
        """Get object type name."""
        assert EclassValidator.get_object_type_name("01") == "Class"
        assert EclassValidator.get_object_type_name("02") == "Property"
        assert EclassValidator.get_object_type_name("99") is None


class TestIecCddValidator:
    """Test IEC CDD validator."""

    def test_valid_61360_irdi(self) -> None:
        """Validate valid IEC 61360-4 IRDI."""
        validator = IecCddValidator()
        result = validator.validate("0112/2///61360_4_27000#ABF999#001")

        assert result.valid is True
        assert result.vocabulary == "IEC_CDD"
        assert result.details is not None
        assert result.details["standard"] == "IEC 61360-4"

    def test_valid_general_irdi(self) -> None:
        """Validate valid general IEC CDD IRDI."""
        validator = IecCddValidator()
        result = validator.validate("0112/0///IEC#TEST123#001")

        assert result.valid is True
        assert result.vocabulary == "IEC_CDD"
        assert result.details is not None
        assert result.details["database"] == "published"

    def test_private_database(self) -> None:
        """Validate private database IRDI."""
        validator = IecCddValidator()
        result = validator.validate("0112/2///ORG#CODE123#001")

        assert result.valid is True
        assert result.details is not None
        assert result.details["database"] == "private"

    def test_reject_private_database(self) -> None:
        """Reject private database when not allowed."""
        validator = IecCddValidator(allow_private_db=False)
        result = validator.validate("0112/2///ORG#CODE123#001")

        assert result.valid is False
        assert "Private database" in (result.error or "")

    def test_invalid_format(self) -> None:
        """Invalid IEC CDD format fails validation."""
        validator = IecCddValidator()
        result = validator.validate("0112/invalid")

        assert result.valid is False
        assert "Invalid IEC CDD IRDI format" in (result.error or "")

    def test_matches_iec_cdd_pattern(self) -> None:
        """Matches detects IEC CDD patterns."""
        validator = IecCddValidator()

        assert validator.matches("0112/2///61360_4_27000#ABF999#001") is True
        assert validator.matches("0112/0///IEC#TEST#001") is True
        assert validator.matches("0173-1#01-AEW677#001") is False
        assert validator.matches("invalid") is False

    def test_parse_irdi_61360(self) -> None:
        """Parse IEC 61360-4 IRDI."""
        parsed = IecCddValidator.parse_irdi("0112/2///61360_4_27000#ABF999#001")

        assert parsed is not None
        assert parsed["standard"] == "IEC 61360-4"
        assert parsed["code"] == "ABF999"
        assert parsed["version"] == 1

    def test_parse_irdi_general(self) -> None:
        """Parse general IEC CDD IRDI."""
        parsed = IecCddValidator.parse_irdi("0112/0///IEC#TEST123#001")

        assert parsed is not None
        assert parsed["database"] == "published"
        assert parsed["organization"] == "IEC"
        assert parsed["code"] == "TEST123"


class TestVocabularyRegistry:
    """Test VocabularyRegistry class."""

    def test_empty_registry(self) -> None:
        """Empty registry has no validators."""
        registry = VocabularyRegistry()
        assert len(registry) == 0
        assert registry.list_vocabularies() == []

    def test_register_eclass(self) -> None:
        """Register ECLASS validator."""
        registry = VocabularyRegistry()
        registry.register_eclass()

        assert len(registry) == 1
        assert "ECLASS" in registry
        assert "ECLASS" in registry.list_vocabularies()

    def test_register_iec_cdd(self) -> None:
        """Register IEC CDD validator."""
        registry = VocabularyRegistry()
        registry.register_iec_cdd()

        assert len(registry) == 1
        assert "IEC_CDD" in registry

    def test_register_defaults(self) -> None:
        """Register default validators."""
        registry = VocabularyRegistry()
        registry.register_defaults()

        assert len(registry) == 2
        assert "ECLASS" in registry
        assert "IEC_CDD" in registry

    def test_find_validator_eclass(self) -> None:
        """Find ECLASS validator for ECLASS IRDI."""
        registry = VocabularyRegistry()
        registry.register_defaults()

        validator = registry.find_validator("0173-1#01-AEW677#001")

        assert validator is not None
        assert validator.name == "ECLASS"

    def test_find_validator_iec_cdd(self) -> None:
        """Find IEC CDD validator for IEC CDD IRDI."""
        registry = VocabularyRegistry()
        registry.register_defaults()

        validator = registry.find_validator("0112/2///61360_4#AAA#001")

        assert validator is not None
        assert validator.name == "IEC_CDD"

    def test_find_validator_unknown(self) -> None:
        """Find returns None for unknown vocabulary."""
        registry = VocabularyRegistry()
        registry.register_defaults()

        validator = registry.find_validator("https://example.com/custom#id")

        assert validator is None

    def test_get_validator(self) -> None:
        """Get validator by name."""
        registry = VocabularyRegistry()
        registry.register_eclass()

        validator = registry.get_validator("ECLASS")
        assert validator is not None
        assert validator.name == "ECLASS"

        unknown = registry.get_validator("UNKNOWN")
        assert unknown is None

    def test_unregister(self) -> None:
        """Unregister validator."""
        registry = VocabularyRegistry()
        registry.register_eclass()
        registry.register_iec_cdd()

        assert len(registry) == 2

        result = registry.unregister("ECLASS")
        assert result is True
        assert len(registry) == 1
        assert "ECLASS" not in registry

        result = registry.unregister("UNKNOWN")
        assert result is False

    def test_clear(self) -> None:
        """Clear all validators."""
        registry = VocabularyRegistry()
        registry.register_defaults()

        assert len(registry) == 2

        registry.clear()
        assert len(registry) == 0


class TestVocabularyValidator:
    """Test VocabularyValidator class."""

    def test_validate_eclass(self) -> None:
        """Validate ECLASS semantic ID."""
        registry = VocabularyRegistry()
        registry.register_defaults()
        validator = VocabularyValidator(registry)

        result = validator.validate("0173-1#01-AEW677#001")

        assert result.valid is True
        assert result.vocabulary == "ECLASS"

    def test_validate_iec_cdd(self) -> None:
        """Validate IEC CDD semantic ID."""
        registry = VocabularyRegistry()
        registry.register_defaults()
        validator = VocabularyValidator(registry)

        result = validator.validate("0112/2///61360_4_27000#ABF999#001")

        assert result.valid is True
        assert result.vocabulary == "IEC_CDD"

    def test_validate_unknown_vocabulary(self) -> None:
        """Unknown vocabulary is accepted."""
        registry = VocabularyRegistry()
        registry.register_defaults()
        validator = VocabularyValidator(registry)

        result = validator.validate("https://example.com/custom#property")

        assert result.valid is True
        assert result.vocabulary is None
        assert result.details is not None
        assert result.details["recognized"] is False

    def test_strict_mode_raises_on_invalid(self) -> None:
        """Strict mode raises ValidationError."""
        registry = VocabularyRegistry()
        registry.register_eclass(strict_type_check=True)
        validator = VocabularyValidator(registry, mode=ValidationMode.STRICT)

        with pytest.raises(ValidationError) as exc_info:
            validator.validate("0173-1#99-INVALID#001")

        assert "Unknown ECLASS object type" in exc_info.value.message

    def test_warn_mode_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """Warn mode logs warning."""
        registry = VocabularyRegistry()
        registry.register_eclass(strict_type_check=True)
        validator = VocabularyValidator(registry, mode=ValidationMode.WARN)

        import logging

        with caplog.at_level(logging.WARNING):
            result = validator.validate("0173-1#99-INVALID#001")

        assert result.valid is False
        assert "Invalid semantic ID" in caplog.text

    def test_off_mode_skips_validation(self) -> None:
        """Off mode skips validation."""
        registry = VocabularyRegistry()
        registry.register_defaults()
        validator = VocabularyValidator(registry, mode=ValidationMode.OFF)

        result = validator.validate("anything-at-all")

        assert result.valid is True
        assert result.details is not None
        assert result.details["skipped"] is True

    def test_is_valid(self) -> None:
        """is_valid returns boolean."""
        registry = VocabularyRegistry()
        registry.register_defaults()
        validator = VocabularyValidator(registry)

        assert validator.is_valid("0173-1#01-AEW677#001") is True
        assert validator.is_valid("anything") is True  # Unknown is accepted

    def test_validate_many(self) -> None:
        """Validate multiple semantic IDs."""
        registry = VocabularyRegistry()
        registry.register_defaults()
        validator = VocabularyValidator(registry)

        results = validator.validate_many([
            "0173-1#01-AEW677#001",
            "0112/2///61360_4_27000#ABF999#001",
            "https://example.com/custom#id",
        ])

        assert len(results) == 3
        assert results[0].vocabulary == "ECLASS"
        assert results[1].vocabulary == "IEC_CDD"
        assert results[2].vocabulary is None

    def test_cache_works(self) -> None:
        """Validation results are cached."""
        registry = VocabularyRegistry()
        registry.register_defaults()
        validator = VocabularyValidator(registry)

        # Validate same ID multiple times
        validator.validate("0173-1#01-AEW677#001")
        validator.validate("0173-1#01-AEW677#001")
        validator.validate("0173-1#01-AEW677#001")

        info = validator.cache_info
        assert info["hits"] >= 2
        assert info["misses"] >= 1

    def test_clear_cache(self) -> None:
        """Clear cache resets statistics."""
        registry = VocabularyRegistry()
        registry.register_defaults()
        validator = VocabularyValidator(registry)

        validator.validate("0173-1#01-AEW677#001")
        validator.validate("0173-1#01-AEW677#001")

        validator.clear_cache()

        info = validator.cache_info
        assert info["currsize"] == 0

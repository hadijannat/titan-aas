"""Vocabulary registry for semantic identifier validation.

This module provides the VocabularyRegistry class that manages a collection
of vocabulary-specific validators and dispatches validation requests.

Example:
    from titan.validation import VocabularyRegistry

    # Create registry with default validators
    registry = VocabularyRegistry()
    registry.register_defaults()

    # Or register specific validators
    registry.register_eclass()
    registry.register_iec_cdd()

    # Find validator for a semantic ID
    validator = registry.find_validator("0173-1#01-AEW677#001")
    print(validator.name)  # "ECLASS"
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from titan.validation.vocabulary import BaseVocabularyValidator

logger = logging.getLogger(__name__)


class VocabularyRegistry:
    """Registry of vocabulary-specific validators.

    Maintains a collection of validators for different vocabulary
    standards (ECLASS, IEC CDD, etc.) and provides methods to
    find the appropriate validator for a given semantic ID.

    Validators are checked in registration order, so register
    more specific validators before more general ones.

    Attributes:
        validators: List of registered vocabulary validators
    """

    def __init__(self) -> None:
        """Initialize an empty registry."""
        self._validators: list[BaseVocabularyValidator] = []

    @property
    def validators(self) -> list[BaseVocabularyValidator]:
        """Get list of registered validators."""
        return list(self._validators)

    def register(self, validator: BaseVocabularyValidator) -> None:
        """Register a vocabulary validator.

        Args:
            validator: The validator to register
        """
        self._validators.append(validator)
        logger.debug("Registered vocabulary validator: %s", validator.name)

    def unregister(self, name: str) -> bool:
        """Unregister a validator by name.

        Args:
            name: Name of the validator to remove

        Returns:
            True if a validator was removed, False if not found
        """
        for i, v in enumerate(self._validators):
            if v.name == name:
                del self._validators[i]
                logger.debug("Unregistered vocabulary validator: %s", name)
                return True
        return False

    def find_validator(self, semantic_id: str) -> BaseVocabularyValidator | None:
        """Find a validator that matches the semantic ID.

        Args:
            semantic_id: The semantic ID to match

        Returns:
            Matching validator or None if no match
        """
        for validator in self._validators:
            if validator.matches(semantic_id):
                return validator
        return None

    def get_validator(self, name: str) -> BaseVocabularyValidator | None:
        """Get a validator by name.

        Args:
            name: Name of the validator

        Returns:
            Validator or None if not found
        """
        for validator in self._validators:
            if validator.name == name:
                return validator
        return None

    def list_vocabularies(self) -> list[str]:
        """Get list of registered vocabulary names.

        Returns:
            List of vocabulary names
        """
        return [v.name for v in self._validators]

    def clear(self) -> None:
        """Remove all registered validators."""
        self._validators.clear()

    # Convenience methods for registering common validators

    def register_eclass(
        self,
        allow_url_format: bool = True,
        strict_type_check: bool = False,
    ) -> None:
        """Register the ECLASS validator.

        Args:
            allow_url_format: Accept ECLASS URLs (default: True)
            strict_type_check: Require known object types (default: False)
        """
        from titan.validation.eclass import EclassValidator

        validator = EclassValidator(
            allow_url_format=allow_url_format,
            strict_type_check=strict_type_check,
        )
        self.register(validator)

    def register_iec_cdd(
        self,
        allow_url_format: bool = True,
        allow_private_db: bool = True,
    ) -> None:
        """Register the IEC CDD validator.

        Args:
            allow_url_format: Accept IEC CDD URLs (default: True)
            allow_private_db: Accept private DB codes (default: True)
        """
        from titan.validation.iec_cdd import IecCddValidator

        validator = IecCddValidator(
            allow_url_format=allow_url_format,
            allow_private_db=allow_private_db,
        )
        self.register(validator)

    def register_defaults(self) -> None:
        """Register all default vocabulary validators.

        Registers ECLASS and IEC CDD validators with default settings.
        """
        self.register_eclass()
        self.register_iec_cdd()

    def __len__(self) -> int:
        """Get number of registered validators."""
        return len(self._validators)

    def __contains__(self, name: str) -> bool:
        """Check if a validator is registered by name."""
        return any(v.name == name for v in self._validators)

    def __iter__(self):
        """Iterate over registered validators."""
        return iter(self._validators)

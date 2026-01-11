"""Semantic validation for AAS packages.

Validates semantic correctness beyond structural compliance:
- ConceptDescription reference integrity
- IEC 61360 DataSpecification content
- Value type consistency
- Semantic ID chain validation
- Required property presence
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from titan.core.model import (
    AssetAdministrationShell,
    ConceptDescription,
    DataTypeDefXsd,
    Reference,
    Submodel,
)
from titan.core.model.identifiers import AasSubmodelElements

logger = logging.getLogger(__name__)


class SemanticSeverity(Enum):
    """Severity levels for semantic issues."""

    ERROR = "error"  # Breaks semantic integrity
    WARNING = "warning"  # Questionable but valid
    INFO = "info"  # Informational


@dataclass
class SemanticIssue:
    """A semantic validation issue."""

    code: str
    message: str
    severity: SemanticSeverity
    entity_id: str | None = None
    property_path: str | None = None


@dataclass
class SemanticValidationResult:
    """Result of semantic validation."""

    valid: bool = True
    issues: list[SemanticIssue] = field(default_factory=list)
    concept_descriptions_validated: int = 0
    references_validated: int = 0
    data_specifications_validated: int = 0

    @property
    def errors(self) -> list[SemanticIssue]:
        """Get only error-level issues."""
        return [i for i in self.issues if i.severity == SemanticSeverity.ERROR]

    @property
    def warnings(self) -> list[SemanticIssue]:
        """Get only warning-level issues."""
        return [i for i in self.issues if i.severity == SemanticSeverity.WARNING]

    def add_error(
        self,
        code: str,
        message: str,
        entity_id: str | None = None,
        property_path: str | None = None,
    ) -> None:
        """Add an error-level issue."""
        self.issues.append(
            SemanticIssue(code, message, SemanticSeverity.ERROR, entity_id, property_path)
        )
        self.valid = False

    def add_warning(
        self,
        code: str,
        message: str,
        entity_id: str | None = None,
        property_path: str | None = None,
    ) -> None:
        """Add a warning-level issue."""
        self.issues.append(
            SemanticIssue(code, message, SemanticSeverity.WARNING, entity_id, property_path)
        )

    def add_info(
        self,
        code: str,
        message: str,
        entity_id: str | None = None,
        property_path: str | None = None,
    ) -> None:
        """Add an info-level issue."""
        self.issues.append(
            SemanticIssue(code, message, SemanticSeverity.INFO, entity_id, property_path)
        )


class SemanticValidator:
    """Validates semantic correctness of AAS packages."""

    def __init__(self) -> None:
        """Initialize semantic validator."""
        self.concept_descriptions: dict[str, ConceptDescription] = {}

    async def validate_package(
        self,
        shells: list[AssetAdministrationShell],
        submodels: list[Submodel],
        concept_descriptions: list[ConceptDescription],
    ) -> SemanticValidationResult:
        """Validate semantic correctness of an entire package.

        Args:
            shells: Asset Administration Shells
            submodels: Submodels
            concept_descriptions: Concept Descriptions

        Returns:
            SemanticValidationResult with issues
        """
        result = SemanticValidationResult()

        # Build concept description index
        self.concept_descriptions = {cd.id: cd for cd in concept_descriptions}

        # Validate concept descriptions themselves
        for cd in concept_descriptions:
            self._validate_concept_description(cd, result)

        # Validate shells
        for shell in shells:
            self._validate_shell(shell, result)

        # Validate submodels
        for submodel in submodels:
            self._validate_submodel(submodel, result)

        result.concept_descriptions_validated = len(concept_descriptions)

        return result

    def _validate_concept_description(
        self, cd: ConceptDescription, result: SemanticValidationResult
    ) -> None:
        """Validate a ConceptDescription."""
        # Check for IEC 61360 data specification
        if not cd.embedded_data_specifications:
            result.add_info(
                "CD_NO_DATA_SPEC",
                "ConceptDescription has no embedded data specifications",
                cd.id,
            )
            return

        for eds in cd.embedded_data_specifications:
            result.data_specifications_validated += 1

            # Validate data specification content
            if not eds.data_specification_content:
                result.add_warning(
                    "CD_EMPTY_DATA_SPEC",
                    "EmbeddedDataSpecification has no content",
                    cd.id,
                )
                continue

            content = eds.data_specification_content

            # Check for required IEC 61360 fields
            if hasattr(content, "preferred_name") and not content.preferred_name:
                result.add_warning(
                    "CD_NO_PREFERRED_NAME",
                    "IEC 61360 DataSpecification missing preferredName",
                    cd.id,
                )

            # Validate value type if present
            if hasattr(content, "data_type") and content.data_type:
                if not self._is_valid_data_type(content.data_type):
                    result.add_error(
                        "CD_INVALID_DATA_TYPE",
                        f"Invalid data type: {content.data_type}",
                        cd.id,
                        "dataSpecificationContent.dataType",
                    )

            # Validate value list if present
            if hasattr(content, "value_list") and content.value_list:
                if hasattr(content, "data_type") and content.data_type:
                    self._validate_value_list(content.value_list, content.data_type, cd.id, result)

    def _validate_shell(
        self, shell: AssetAdministrationShell, result: SemanticValidationResult
    ) -> None:
        """Validate an AssetAdministrationShell."""
        # Validate asset information semantic IDs
        if shell.asset_information and shell.asset_information.specific_asset_ids:
            for specific_id in shell.asset_information.specific_asset_ids:
                if specific_id.semantic_id:
                    self._validate_semantic_id_reference(
                        specific_id.semantic_id,
                        shell.id,
                        "assetInformation.specificAssetIds.semanticId",
                        result,
                    )

        # Validate submodel references
        if shell.submodels:
            for ref in shell.submodels:
                result.references_validated += 1
                self._validate_reference_structure(ref, shell.id, "submodels", result)

    def _validate_submodel(self, submodel: Submodel, result: SemanticValidationResult) -> None:
        """Validate a Submodel and its elements."""
        # Validate submodel semantic ID
        if submodel.semantic_id:
            self._validate_semantic_id_reference(
                submodel.semantic_id,
                submodel.id,
                "semanticId",
                result,
            )

        # Validate submodel elements
        if submodel.submodel_elements:
            for sme in submodel.submodel_elements:
                self._validate_submodel_element(sme, submodel.id, result)

    def _validate_submodel_element(
        self, element: Any, parent_id: str, result: SemanticValidationResult, path: str = ""
    ) -> None:
        """Validate a SubmodelElement recursively."""
        element_path = f"{path}/{element.id_short}" if path else element.id_short

        # Validate semantic ID if present
        if hasattr(element, "semantic_id") and element.semantic_id:
            self._validate_semantic_id_reference(
                element.semantic_id,
                parent_id,
                f"{element_path}.semanticId",
                result,
            )

            # Check if referenced ConceptDescription defines value constraints
            if element.semantic_id.keys:
                cd_id = element.semantic_id.keys[0].value
                if cd_id in self.concept_descriptions:
                    self._validate_element_against_concept(
                        element, self.concept_descriptions[cd_id], parent_id, element_path, result
                    )

        # Validate specific element types
        model_type = getattr(element, "model_type", None)

        if model_type == AasSubmodelElements.PROPERTY:
            self._validate_property(element, parent_id, element_path, result)

        elif model_type == AasSubmodelElements.MULTI_LANGUAGE_PROPERTY:
            self._validate_multi_language_property(element, parent_id, element_path, result)

        elif model_type == AasSubmodelElements.RANGE:
            self._validate_range(element, parent_id, element_path, result)

        elif model_type == AasSubmodelElements.REFERENCE_ELEMENT:
            if element.value:
                self._validate_reference_structure(element.value, parent_id, element_path, result)

        elif model_type == AasSubmodelElements.RELATIONSHIP_ELEMENT:
            if element.first:
                self._validate_reference_structure(
                    element.first, parent_id, f"{element_path}.first", result
                )
            if element.second:
                self._validate_reference_structure(
                    element.second, parent_id, f"{element_path}.second", result
                )

        elif model_type == AasSubmodelElements.SUBMODEL_ELEMENT_COLLECTION:
            # Recursively validate nested elements
            if hasattr(element, "value") and element.value:
                for nested in element.value:
                    self._validate_submodel_element(nested, parent_id, result, element_path)

        elif model_type == AasSubmodelElements.SUBMODEL_ELEMENT_LIST:
            # Validate list elements
            if hasattr(element, "value") and element.value:
                for nested in element.value:
                    self._validate_submodel_element(nested, parent_id, result, element_path)

    def _validate_property(
        self, prop: Any, parent_id: str, path: str, result: SemanticValidationResult
    ) -> None:
        """Validate a Property element."""
        # Check value type is valid
        if hasattr(prop, "value_type") and prop.value_type:
            if not self._is_valid_data_type(prop.value_type):
                result.add_error(
                    "PROPERTY_INVALID_VALUE_TYPE",
                    f"Invalid value type: {prop.value_type}",
                    parent_id,
                    f"{path}.valueType",
                )

        # Validate value matches value type if both present
        if (
            hasattr(prop, "value")
            and prop.value
            and hasattr(prop, "value_type")
            and prop.value_type
        ):
            self._validate_value_for_type(prop.value, prop.value_type, parent_id, path, result)

    def _validate_multi_language_property(
        self, mlp: Any, parent_id: str, path: str, result: SemanticValidationResult
    ) -> None:
        """Validate a MultiLanguageProperty element."""
        if not hasattr(mlp, "value") or not mlp.value:
            return

        # Validate language codes (BCP 47)
        for lang_string in mlp.value:
            if hasattr(lang_string, "language"):
                lang = lang_string.language
                # Basic BCP 47 validation (language-region format)
                if not lang or not isinstance(lang, str):
                    result.add_error(
                        "MLP_INVALID_LANGUAGE",
                        "MultiLanguageProperty has invalid language code",
                        parent_id,
                        f"{path}.value.language",
                    )
                elif len(lang) < 2:
                    result.add_warning(
                        "MLP_SHORT_LANGUAGE_CODE",
                        f"Unusually short language code: {lang}",
                        parent_id,
                        f"{path}.value.language",
                    )

    def _validate_range(
        self, range_elem: Any, parent_id: str, path: str, result: SemanticValidationResult
    ) -> None:
        """Validate a Range element."""
        if not hasattr(range_elem, "value_type"):
            return

        value_type = range_elem.value_type

        # Validate min/max are same type
        has_min = hasattr(range_elem, "min") and range_elem.min is not None
        has_max = hasattr(range_elem, "max") and range_elem.max is not None

        if has_min:
            self._validate_value_for_type(
                range_elem.min, value_type, parent_id, f"{path}.min", result
            )

        if has_max:
            self._validate_value_for_type(
                range_elem.max, value_type, parent_id, f"{path}.max", result
            )

        # Validate min <= max (for numeric types)
        if has_min and has_max:
            try:
                if self._is_numeric_type(value_type):
                    min_val = self._parse_numeric_value(range_elem.min, value_type)
                    max_val = self._parse_numeric_value(range_elem.max, value_type)
                    if min_val is not None and max_val is not None and min_val > max_val:
                        result.add_error(
                            "RANGE_MIN_GT_MAX",
                            f"Range min ({min_val}) > max ({max_val})",
                            parent_id,
                            path,
                        )
            except ValueError:
                pass  # Already caught by value validation

    def _validate_semantic_id_reference(
        self, semantic_id: Reference, entity_id: str, path: str, result: SemanticValidationResult
    ) -> None:
        """Validate a semantic ID reference."""
        result.references_validated += 1

        if not semantic_id.keys:
            result.add_warning(
                "SEMANTIC_ID_NO_KEYS",
                "SemanticId has no keys",
                entity_id,
                path,
            )
            return

        # Check if referenced ConceptDescription exists
        cd_id = semantic_id.keys[0].value
        if cd_id not in self.concept_descriptions:
            result.add_warning(
                "SEMANTIC_ID_NOT_FOUND",
                f"Referenced ConceptDescription not found: {cd_id}",
                entity_id,
                path,
            )

    def _validate_reference_structure(
        self, ref: Reference, entity_id: str, path: str, result: SemanticValidationResult
    ) -> None:
        """Validate Reference structure."""
        result.references_validated += 1

        if not ref.keys:
            result.add_error(
                "REFERENCE_NO_KEYS",
                "Reference has no keys",
                entity_id,
                path,
            )
            return

        # Validate key chain
        for idx, key in enumerate(ref.keys):
            if not key.value:
                result.add_error(
                    "REFERENCE_KEY_NO_VALUE",
                    f"Reference key [{idx}] has no value",
                    entity_id,
                    f"{path}.keys[{idx}]",
                )

    def _validate_element_against_concept(
        self,
        element: Any,
        cd: ConceptDescription,
        parent_id: str,
        path: str,
        result: SemanticValidationResult,
    ) -> None:
        """Validate element values against ConceptDescription constraints."""
        if not cd.embedded_data_specifications:
            return

        for eds in cd.embedded_data_specifications:
            if not eds.data_specification_content:
                continue

            content = eds.data_specification_content

            # Validate data type matches
            if hasattr(content, "data_type") and content.data_type:
                if hasattr(element, "value_type") and element.value_type:
                    # Convert both to comparable form
                    cd_type = self._normalize_data_type(content.data_type)
                    elem_type = self._normalize_data_type(element.value_type)

                    if cd_type != elem_type:
                        result.add_warning(
                            "TYPE_MISMATCH",
                            f"Element type {elem_type} doesn't match CD type {cd_type}",
                            parent_id,
                            path,
                        )

            # Validate value against allowed values
            if hasattr(content, "value_list") and content.value_list:
                if hasattr(element, "value") and element.value:
                    # Handle both list and ValueList object
                    pairs = (
                        content.value_list
                        if isinstance(content.value_list, list)
                        else getattr(content.value_list, "value_reference_pairs", [])
                    )
                    allowed_values = {vle.value for vle in pairs if hasattr(vle, "value")}
                    if allowed_values and element.value not in allowed_values:
                        result.add_error(
                            "VALUE_NOT_IN_ALLOWED_LIST",
                            f"Value '{element.value}' not in allowed list: {allowed_values}",
                            parent_id,
                            path,
                        )

    def _validate_value_list(
        self, value_list: Any, data_type: str, cd_id: str, result: SemanticValidationResult
    ) -> None:
        """Validate value list entries."""
        # value_list can be list of ValueReferencePair or ValueList object
        pairs = (
            value_list
            if isinstance(value_list, list)
            else getattr(value_list, "value_reference_pairs", [])
        )

        for vrp in pairs:
            if hasattr(vrp, "value") and vrp.value:
                self._validate_value_for_type(vrp.value, data_type, cd_id, "valueList", result)

    def _validate_value_for_type(
        self,
        value: str,
        value_type: str | DataTypeDefXsd,
        parent_id: str,
        path: str,
        result: SemanticValidationResult,
    ) -> None:
        """Validate a value matches its declared type."""
        type_str = self._normalize_data_type(value_type)

        try:
            if type_str == "int":
                int(value)
            elif type_str == "integer":
                int(value)
            elif type_str == "long":
                int(value)
            elif type_str == "double":
                float(value)
            elif type_str == "float":
                float(value)
            elif type_str == "boolean":
                if value.lower() not in ("true", "false", "0", "1"):
                    raise ValueError(f"Invalid boolean: {value}")
            # String types always valid
        except (ValueError, AttributeError) as e:
            result.add_error(
                "VALUE_TYPE_MISMATCH",
                f"Value '{value}' is not valid for type {type_str}: {e}",
                parent_id,
                path,
            )

    def _is_valid_data_type(self, data_type: str | DataTypeDefXsd) -> bool:
        """Check if a data type is valid."""
        if isinstance(data_type, DataTypeDefXsd):
            return True

        # Check string representation
        valid_types = {
            "string",
            "int",
            "integer",
            "long",
            "double",
            "float",
            "boolean",
            "date",
            "time",
            "dateTime",
            "anyURI",
        }
        return str(data_type).lower() in valid_types

    def _is_numeric_type(self, value_type: str | DataTypeDefXsd) -> bool:
        """Check if a type is numeric."""
        type_str = self._normalize_data_type(value_type).lower()
        return type_str in ("int", "integer", "long", "double", "float", "decimal")

    def _parse_numeric_value(
        self, value: str, value_type: str | DataTypeDefXsd
    ) -> float | int | None:
        """Parse a numeric value."""
        type_str = self._normalize_data_type(value_type).lower()
        try:
            if type_str in ("int", "integer", "long"):
                return int(value)
            else:
                return float(value)
        except ValueError:
            return None

    def _normalize_data_type(self, data_type: str | DataTypeDefXsd) -> str:
        """Normalize data type to comparable string."""
        if isinstance(data_type, DataTypeDefXsd):
            # Remove XS_ prefix
            return data_type.value.replace("xs:", "").lower()
        return str(data_type).lower()

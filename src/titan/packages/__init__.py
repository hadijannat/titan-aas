"""AASX Package Management for Titan-AAS.

Provides enhanced package lifecycle management including:
- Package versioning
- Dependency tracking with graph analysis
- OPC compliance validation
- Semantic validation (IEC 61360 DataSpecifications)
- Batch import/export operations
- Integrity verification
- Advanced conflict resolution
"""

from titan.packages.dependency_manager import (
    DependencyGraph,
    DependencyManager,
    DependencyType,
    DependencyValidationResult,
    PackageDependency,
)
from titan.packages.differ import PackageComparison, PackageDiffer
from titan.packages.manager import (
    BatchExportResult,
    BatchImportResult,
    ConflictResolution,
    PackageManager,
    PackageVersion,
)
from titan.packages.semantic_validator import (
    SemanticValidationResult,
    SemanticValidator,
)
from titan.packages.validator import OpcValidator, ValidationLevel, ValidationResult

__all__ = [
    "PackageManager",
    "PackageVersion",
    "ConflictResolution",
    "BatchImportResult",
    "BatchExportResult",
    "OpcValidator",
    "ValidationResult",
    "ValidationLevel",
    "SemanticValidator",
    "SemanticValidationResult",
    "DependencyManager",
    "DependencyType",
    "PackageDependency",
    "DependencyGraph",
    "DependencyValidationResult",
    "PackageDiffer",
    "PackageComparison",
]

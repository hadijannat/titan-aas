"""BaSyx compatibility module for Titan-AAS.

Provides import/export functionality:
- AASX package import (ZIP with AAS, submodels, supplementary files)
- AASX package export
- JSON/XML serialization

AASX Structure:
    package.aasx (ZIP file)
    ├── [Content_Types].xml
    ├── _rels/.rels
    └── aasx/
        ├── aas.json or aas.xml
        ├── submodels/
        │   └── *.json or *.xml
        └── supplementary-files/
            └── (attachments, images, etc.)
"""

from titan.compat.aasx import (
    AasxExporter,
    AasxImporter,
    AasxPackage,
)

__all__ = [
    "AasxImporter",
    "AasxExporter",
    "AasxPackage",
]

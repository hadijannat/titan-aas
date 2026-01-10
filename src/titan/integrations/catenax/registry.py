"""Digital Twin Registry client scaffolding for Catena-X."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class DtrClient:
    """Placeholder DTR client."""

    base_url: str | None = None

    async def lookup(self, asset_id: str) -> dict[str, Any]:
        """Return an empty lookup result (placeholder)."""
        return {
            "assetId": asset_id,
            "status": "not_implemented",
        }

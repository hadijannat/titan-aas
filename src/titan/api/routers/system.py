from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["system"])


@router.get("/description")
async def description() -> dict[str, object]:
    return {
        "spec": {
            "idta_release": "25-01",
            "part1_metamodel": "3.1.2",
            "part2_api": "3.1.1",
            "part3a_iec61360": "3.1.1",
            "part4_security": "3.0.1",
        },
        "profiles": [
            "https://admin-shell.io/aas/API/3/1/AASService/SSP-001",
        ],
        "modifiers": ["$value", "$metadata", "$reference", "$path"],
        "formats": ["application/json"],
    }

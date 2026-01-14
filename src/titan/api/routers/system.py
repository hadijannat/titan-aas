from __future__ import annotations

from fastapi import APIRouter, Depends

from titan.config import settings
from titan.security.deps import require_permission_if_public
from titan.security.rbac import Permission

router = APIRouter(
    tags=["system"],
    dependencies=[
        Depends(
            require_permission_if_public(
                Permission.READ_AAS,
                lambda: settings.public_description_endpoints,
            )
        )
    ],
)


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

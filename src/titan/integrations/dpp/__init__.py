"""Digital Product Passport (DPP) integration.

EU-compliant digital product passports for batteries, carbon footprint,
and other regulated products.
"""

from titan.integrations.dpp.passport import (
    DppGenerator,
    DppType,
    PassportData,
    QrCodeGenerator,
)

__all__ = [
    "DppGenerator",
    "DppType",
    "PassportData",
    "QrCodeGenerator",
]

"""Digital Product Passport generator.

Generates EU-compliant Digital Product Passports from AAS data.
Supports Battery Passport (EU Battery Regulation 2023/1542) and
Product Carbon Footprint (PCF).
"""

from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Template directory
TEMPLATE_DIR = Path(__file__).parent / "templates"


class DppType(str, Enum):
    """Digital Product Passport types."""

    BATTERY = "battery"
    CARBON_FOOTPRINT = "carbon_footprint"
    TEXTILE = "textile"
    ELECTRONICS = "electronics"
    GENERIC = "generic"


class ComplianceStatus(str, Enum):
    """Compliance status levels."""

    COMPLIANT = "compliant"
    PARTIAL = "partial"
    NON_COMPLIANT = "non_compliant"
    UNKNOWN = "unknown"


@dataclass
class PassportData:
    """Data container for Digital Product Passport."""

    passport_id: str
    passport_type: DppType
    product_id: str
    manufacturer: str
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    valid_until: str | None = None
    data: dict[str, Any] = field(default_factory=dict)
    compliance_status: ComplianceStatus = ComplianceStatus.UNKNOWN
    verification_url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary format."""
        return {
            "passportId": self.passport_id,
            "passportType": self.passport_type.value,
            "productId": self.product_id,
            "manufacturer": self.manufacturer,
            "createdAt": self.created_at,
            "validUntil": self.valid_until,
            "data": self.data,
            "complianceStatus": self.compliance_status.value,
            "verificationUrl": self.verification_url,
        }

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2)


@dataclass
class BatteryPassportData:
    """Battery-specific passport data per EU Regulation 2023/1542."""

    # Identification
    battery_id: str
    manufacturer_id: str
    manufacturing_date: str
    manufacturing_place: str

    # Technical specifications
    battery_category: str  # EV, LMT, industrial, etc.
    chemistry: str
    nominal_capacity_kwh: float
    nominal_voltage: float
    weight_kg: float

    # Sustainability
    carbon_footprint_kg_co2: float
    recycled_content_percent: float
    cobalt_content_percent: float
    lithium_content_percent: float
    nickel_content_percent: float

    # Performance
    cycle_life: int
    energy_efficiency_percent: float
    state_of_health_percent: float = 100.0

    # Compliance
    ce_marking: bool = False
    battery_due_diligence: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary format."""
        return {
            "identification": {
                "batteryId": self.battery_id,
                "manufacturerId": self.manufacturer_id,
                "manufacturingDate": self.manufacturing_date,
                "manufacturingPlace": self.manufacturing_place,
            },
            "technicalSpecifications": {
                "batteryCategory": self.battery_category,
                "chemistry": self.chemistry,
                "nominalCapacityKwh": self.nominal_capacity_kwh,
                "nominalVoltage": self.nominal_voltage,
                "weightKg": self.weight_kg,
            },
            "sustainability": {
                "carbonFootprintKgCo2": self.carbon_footprint_kg_co2,
                "recycledContentPercent": self.recycled_content_percent,
                "materialComposition": {
                    "cobaltPercent": self.cobalt_content_percent,
                    "lithiumPercent": self.lithium_content_percent,
                    "nickelPercent": self.nickel_content_percent,
                },
            },
            "performance": {
                "cycleLife": self.cycle_life,
                "energyEfficiencyPercent": self.energy_efficiency_percent,
                "stateOfHealthPercent": self.state_of_health_percent,
            },
            "compliance": {
                "ceMarking": self.ce_marking,
                "batteryDueDiligence": self.battery_due_diligence,
            },
        }


@dataclass
class CarbonFootprintData:
    """Product Carbon Footprint (PCF) data."""

    product_id: str
    pcf_id: str
    declared_unit: str  # kg, piece, etc.
    unitary_product_amount: float

    # Carbon values
    pcf_excluding_biogenic_kg_co2e: float
    pcf_including_biogenic_kg_co2e: float | None = None
    fossil_ghg_emissions_kg_co2e: float | None = None
    biogenic_carbon_content_kg_co2e: float | None = None

    # Lifecycle stages
    boundary: str = "Cradle-to-Gate"
    primary_data_share_percent: float | None = None

    # Verification
    verified: bool = False
    verification_standard: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to Catena-X PCF format."""
        result = {
            "productId": self.product_id,
            "pcfId": self.pcf_id,
            "declaredUnit": self.declared_unit,
            "unitaryProductAmount": self.unitary_product_amount,
            "pcfExcludingBiogenic": self.pcf_excluding_biogenic_kg_co2e,
            "boundaryProcessesDescription": self.boundary,
        }

        if self.pcf_including_biogenic_kg_co2e is not None:
            result["pcfIncludingBiogenic"] = self.pcf_including_biogenic_kg_co2e
        if self.fossil_ghg_emissions_kg_co2e is not None:
            result["fossilGhgEmissions"] = self.fossil_ghg_emissions_kg_co2e
        if self.biogenic_carbon_content_kg_co2e is not None:
            result["biogenicCarbonContent"] = self.biogenic_carbon_content_kg_co2e
        if self.primary_data_share_percent is not None:
            result["primaryDataShare"] = self.primary_data_share_percent
        if self.verified:
            result["verification"] = {
                "verified": True,
                "standard": self.verification_standard,
            }

        return result


class QrCodeGenerator:
    """Generates QR codes for Digital Product Passports.

    This is a scaffold that would use qrcode library in production.
    """

    def __init__(self, base_url: str = "https://dpp.example.com") -> None:
        """Initialize QR code generator.

        Args:
            base_url: Base URL for passport verification
        """
        self.base_url = base_url

    def generate_url(self, passport_id: str) -> str:
        """Generate verification URL for passport.

        Args:
            passport_id: The passport identifier

        Returns:
            Verification URL
        """
        encoded_id = base64.urlsafe_b64encode(passport_id.encode()).decode().rstrip("=")
        return f"{self.base_url}/verify/{encoded_id}"

    def generate_qr_data(self, passport: PassportData) -> dict[str, Any]:
        """Generate QR code data structure.

        Args:
            passport: The passport to encode

        Returns:
            QR code data dictionary
        """
        return {
            "url": self.generate_url(passport.passport_id),
            "passport_id": passport.passport_id,
            "passport_type": passport.passport_type.value,
            "product_id": passport.product_id,
            "created_at": passport.created_at,
        }

    def generate_svg(self, passport: PassportData) -> str:
        """Generate QR code as SVG.

        Args:
            passport: The passport to encode

        Returns:
            SVG string (placeholder - would use qrcode library)
        """
        url = self.generate_url(passport.passport_id)
        # Placeholder - would generate actual QR code SVG
        return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <rect width="100" height="100" fill="white"/>
  <text x="50" y="50" text-anchor="middle" font-size="8">QR: {url[:20]}...</text>
</svg>"""


class DppGenerator:
    """Generator for Digital Product Passports.

    Extracts data from AAS submodels and generates EU-compliant
    Digital Product Passports.
    """

    # Semantic IDs for supported submodel types
    SEMANTIC_IDS = {
        DppType.BATTERY: [
            "urn:samm:io.catenax.battery.battery_pass:3.0.1#BatteryPass",
            "https://admin-shell.io/battery/1/0/BatteryPass",
        ],
        DppType.CARBON_FOOTPRINT: [
            "urn:samm:io.catenax.pcf:6.0.0#Pcf",
            "https://admin-shell.io/idta/CarbonFootprint/ProductCarbonFootprint/0/9",
        ],
    }

    def __init__(
        self,
        verification_base_url: str = "https://dpp.example.com",
    ) -> None:
        """Initialize DPP generator.

        Args:
            verification_base_url: Base URL for passport verification
        """
        self.qr_generator = QrCodeGenerator(verification_base_url)
        self._templates: dict[DppType, dict[str, Any]] = {}
        self._load_templates()

    def _load_templates(self) -> None:
        """Load passport templates from JSON files."""
        for dpp_type in DppType:
            template_path = TEMPLATE_DIR / f"{dpp_type.value}.json"
            if template_path.exists():
                try:
                    with open(template_path) as f:
                        self._templates[dpp_type] = json.load(f)
                    logger.debug(f"Loaded template: {dpp_type.value}")
                except Exception as e:
                    logger.warning(f"Failed to load template {dpp_type.value}: {e}")

    def detect_type(self, submodel: Any) -> DppType | None:
        """Detect DPP type from submodel semantic ID.

        Args:
            submodel: The AAS Submodel

        Returns:
            Detected DPP type or None
        """
        semantic_id = None

        # Extract semantic ID from submodel
        if hasattr(submodel, "semantic_id") and submodel.semantic_id:
            if hasattr(submodel.semantic_id, "keys") and submodel.semantic_id.keys:
                semantic_id = submodel.semantic_id.keys[0].value

        if not semantic_id:
            return None

        # Match against known semantic IDs
        for dpp_type, sem_ids in self.SEMANTIC_IDS.items():
            if semantic_id in sem_ids:
                return dpp_type

        return None

    def generate_battery_passport(
        self,
        submodel: Any,
        manufacturer: str,
    ) -> PassportData:
        """Generate Battery Passport from AAS submodel.

        Args:
            submodel: Battery Pass submodel
            manufacturer: Manufacturer name

        Returns:
            Generated passport data
        """
        # Extract data from submodel elements
        data = self._extract_submodel_data(submodel)

        battery_data = BatteryPassportData(
            battery_id=data.get("batteryId", submodel.id),
            manufacturer_id=data.get("manufacturerId", ""),
            manufacturing_date=data.get("manufacturingDate", ""),
            manufacturing_place=data.get("manufacturingPlace", ""),
            battery_category=data.get("batteryCategory", "Unknown"),
            chemistry=data.get("chemistry", "Unknown"),
            nominal_capacity_kwh=float(data.get("nominalCapacity", 0)),
            nominal_voltage=float(data.get("nominalVoltage", 0)),
            weight_kg=float(data.get("batteryWeight", 0)),
            carbon_footprint_kg_co2=float(data.get("carbonFootprint", 0)),
            recycled_content_percent=float(data.get("recycledContent", 0)),
            cobalt_content_percent=float(data.get("cobaltContent", 0)),
            lithium_content_percent=float(data.get("lithiumContent", 0)),
            nickel_content_percent=float(data.get("nickelContent", 0)),
            cycle_life=int(data.get("expectedLifetimeCycles", 0)),
            energy_efficiency_percent=float(data.get("energyEfficiency", 0)),
            state_of_health_percent=float(data.get("stateOfHealth", 100)),
            ce_marking=bool(data.get("ceMarking", False)),
            battery_due_diligence=bool(data.get("dueDiligence", False)),
        )

        # Determine compliance status
        compliance = self._check_battery_compliance(battery_data)

        passport = PassportData(
            passport_id=f"bp-{submodel.id}",
            passport_type=DppType.BATTERY,
            product_id=submodel.id,
            manufacturer=manufacturer,
            data=battery_data.to_dict(),
            compliance_status=compliance,
            verification_url=self.qr_generator.generate_url(f"bp-{submodel.id}"),
        )

        logger.info(f"Generated Battery Passport: {passport.passport_id}")
        return passport

    def generate_carbon_footprint_passport(
        self,
        submodel: Any,
        manufacturer: str,
    ) -> PassportData:
        """Generate Carbon Footprint Passport from AAS submodel.

        Args:
            submodel: PCF submodel
            manufacturer: Manufacturer name

        Returns:
            Generated passport data
        """
        data = self._extract_submodel_data(submodel)

        pcf_data = CarbonFootprintData(
            product_id=submodel.id,
            pcf_id=data.get("pcfId", f"pcf-{submodel.id}"),
            declared_unit=data.get("declaredUnit", "piece"),
            unitary_product_amount=float(data.get("unitaryProductAmount", 1)),
            pcf_excluding_biogenic_kg_co2e=float(data.get("pcfExcludingBiogenic", 0)),
            pcf_including_biogenic_kg_co2e=data.get("pcfIncludingBiogenic"),
            fossil_ghg_emissions_kg_co2e=data.get("fossilGhgEmissions"),
            biogenic_carbon_content_kg_co2e=data.get("biogenicCarbonContent"),
            boundary=data.get("boundary", "Cradle-to-Gate"),
            primary_data_share_percent=data.get("primaryDataShare"),
            verified=bool(data.get("verified", False)),
            verification_standard=data.get("verificationStandard"),
        )

        passport = PassportData(
            passport_id=f"pcf-{submodel.id}",
            passport_type=DppType.CARBON_FOOTPRINT,
            product_id=submodel.id,
            manufacturer=manufacturer,
            data=pcf_data.to_dict(),
            compliance_status=(
                ComplianceStatus.COMPLIANT
                if pcf_data.verified
                else ComplianceStatus.PARTIAL
            ),
            verification_url=self.qr_generator.generate_url(f"pcf-{submodel.id}"),
        )

        logger.info(f"Generated PCF Passport: {passport.passport_id}")
        return passport

    def generate_from_submodel(
        self,
        submodel: Any,
        manufacturer: str,
        dpp_type: DppType | None = None,
    ) -> PassportData | None:
        """Generate passport from submodel with auto-detection.

        Args:
            submodel: The AAS Submodel
            manufacturer: Manufacturer name
            dpp_type: Optional explicit DPP type

        Returns:
            Generated passport or None if type not supported
        """
        if dpp_type is None:
            dpp_type = self.detect_type(submodel)

        if dpp_type is None:
            logger.warning(f"Could not detect DPP type for submodel: {submodel.id}")
            return None

        if dpp_type == DppType.BATTERY:
            return self.generate_battery_passport(submodel, manufacturer)
        elif dpp_type == DppType.CARBON_FOOTPRINT:
            return self.generate_carbon_footprint_passport(submodel, manufacturer)
        else:
            # Generic passport generation
            return self._generate_generic_passport(submodel, manufacturer, dpp_type)

    def _extract_submodel_data(self, submodel: Any) -> dict[str, Any]:
        """Extract data from submodel elements.

        Args:
            submodel: The AAS Submodel

        Returns:
            Flattened dictionary of element values
        """
        data: dict[str, Any] = {}

        def extract_element(element: Any, prefix: str = "") -> None:
            if not hasattr(element, "id_short"):
                return

            key = f"{prefix}{element.id_short}" if prefix else element.id_short

            # Get value based on element type
            if hasattr(element, "value"):
                if isinstance(element.value, list):
                    # SubmodelElementCollection or List
                    for child in element.value:
                        extract_element(child, f"{key}.")
                else:
                    data[key] = element.value

        if hasattr(submodel, "submodel_elements") and submodel.submodel_elements:
            for element in submodel.submodel_elements:
                extract_element(element)

        return data

    def _check_battery_compliance(
        self,
        battery_data: BatteryPassportData,
    ) -> ComplianceStatus:
        """Check battery passport EU compliance.

        Args:
            battery_data: Battery passport data

        Returns:
            Compliance status
        """
        issues = []

        # Check minimum requirements
        if not battery_data.ce_marking:
            issues.append("Missing CE marking")
        if not battery_data.battery_due_diligence:
            issues.append("Missing due diligence")
        if battery_data.carbon_footprint_kg_co2 <= 0:
            issues.append("Missing carbon footprint")
        if battery_data.recycled_content_percent < 0:
            issues.append("Invalid recycled content")

        if len(issues) == 0:
            return ComplianceStatus.COMPLIANT
        elif len(issues) <= 2:
            return ComplianceStatus.PARTIAL
        else:
            return ComplianceStatus.NON_COMPLIANT

    def _generate_generic_passport(
        self,
        submodel: Any,
        manufacturer: str,
        dpp_type: DppType,
    ) -> PassportData:
        """Generate generic passport for unsupported types.

        Args:
            submodel: The AAS Submodel
            manufacturer: Manufacturer name
            dpp_type: The DPP type

        Returns:
            Generic passport data
        """
        data = self._extract_submodel_data(submodel)

        passport = PassportData(
            passport_id=f"{dpp_type.value}-{submodel.id}",
            passport_type=dpp_type,
            product_id=submodel.id,
            manufacturer=manufacturer,
            data=data,
            compliance_status=ComplianceStatus.UNKNOWN,
            verification_url=self.qr_generator.generate_url(f"{dpp_type.value}-{submodel.id}"),
        )

        logger.info(f"Generated {dpp_type.value} Passport: {passport.passport_id}")
        return passport

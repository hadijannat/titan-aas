"""SSP Test Case ID Mapping for IDTA Conformance.

This module maps test case IDs to IDTA-01002 Part 2 v3.1.1 specification requirements.
Each test case ID follows the pattern: SSP-{profile}-{category}-{sequence}

Reference: IDTA-01002-3-1-1 Asset Administration Shell Part 2: API

Profiles:
- AAS-REPO: AAS Repository SSP-001/002
- SM-REPO: Submodel Repository SSP-001/002
- REG: Registry SSP-001/002
- DISC: Discovery SSP-001/002
- CD-REPO: Concept Description Repository SSP-001/002
- DESC: Self-Description endpoints

Categories:
- LIST: List/pagination operations
- GET: Read single resource
- POST: Create operations
- PUT: Update operations
- DELETE: Delete operations
- ERR: Error handling
- HEAD: Metadata operations
"""

from dataclasses import dataclass
from enum import Enum


class Profile(str, Enum):
    """IDTA Service Specification Profiles."""

    AAS_REPO_001 = "AAS-REPO-SSP-001"
    AAS_REPO_002 = "AAS-REPO-SSP-002"
    SM_REPO_001 = "SM-REPO-SSP-001"
    SM_REPO_002 = "SM-REPO-SSP-002"
    REG_AAS_001 = "REG-AAS-SSP-001"
    REG_AAS_002 = "REG-AAS-SSP-002"
    REG_SM_001 = "REG-SM-SSP-001"
    REG_SM_002 = "REG-SM-SSP-002"
    DISC_001 = "DISC-SSP-001"
    DISC_002 = "DISC-SSP-002"
    CD_REPO_001 = "CD-REPO-SSP-001"
    CD_REPO_002 = "CD-REPO-SSP-002"
    DESC = "SELF-DESC"


@dataclass
class SSPTestCase:
    """Represents an SSP test case with IDTA reference."""

    id: str
    profile: Profile
    description: str
    endpoint: str
    method: str
    idta_reference: str
    required: bool = True


# AAS Repository SSP-001/002 Test Cases
AAS_REPOSITORY_TESTS = {
    "SSP-AAS-REPO-LIST-001": SSPTestCase(
        id="SSP-AAS-REPO-LIST-001",
        profile=Profile.AAS_REPO_001,
        description="GET /shells returns paginated response with result and paging_metadata",
        endpoint="/shells",
        method="GET",
        idta_reference="IDTA-01002-3-1-1 Section 5.3.2.1",
    ),
    "SSP-AAS-REPO-LIST-002": SSPTestCase(
        id="SSP-AAS-REPO-LIST-002",
        profile=Profile.AAS_REPO_001,
        description="GET /shells with idShort filter returns matching AAS",
        endpoint="/shells?idShort={idShort}",
        method="GET",
        idta_reference="IDTA-01002-3-1-1 Section 5.3.2.1",
    ),
    "SSP-AAS-REPO-LIST-003": SSPTestCase(
        id="SSP-AAS-REPO-LIST-003",
        profile=Profile.AAS_REPO_001,
        description="GET /shells with assetIds filter returns matching AAS",
        endpoint="/shells?assetIds={base64url}",
        method="GET",
        idta_reference="IDTA-01002-3-1-1 Section 5.3.2.1",
    ),
    "SSP-AAS-REPO-LIST-004": SSPTestCase(
        id="SSP-AAS-REPO-LIST-004",
        profile=Profile.AAS_REPO_001,
        description="GET /shells supports cursor-based pagination",
        endpoint="/shells?cursor={cursor}",
        method="GET",
        idta_reference="IDTA-01002-3-1-1 Section 5.3.2.1",
    ),
    "SSP-AAS-REPO-GET-001": SSPTestCase(
        id="SSP-AAS-REPO-GET-001",
        profile=Profile.AAS_REPO_002,
        description="GET /shells/{aasIdentifier} returns AAS by Base64URL-encoded ID",
        endpoint="/shells/{aasIdentifier}",
        method="GET",
        idta_reference="IDTA-01002-3-1-1 Section 5.3.2.2",
    ),
    "SSP-AAS-REPO-GET-002": SSPTestCase(
        id="SSP-AAS-REPO-GET-002",
        profile=Profile.AAS_REPO_002,
        description="GET /shells/{aasIdentifier} returns ETag header",
        endpoint="/shells/{aasIdentifier}",
        method="GET",
        idta_reference="IDTA-01002-3-1-1 Section 5.3.2.2",
    ),
    "SSP-AAS-REPO-POST-001": SSPTestCase(
        id="SSP-AAS-REPO-POST-001",
        profile=Profile.AAS_REPO_001,
        description="POST /shells creates new AAS and returns 201",
        endpoint="/shells",
        method="POST",
        idta_reference="IDTA-01002-3-1-1 Section 5.3.2.3",
    ),
    "SSP-AAS-REPO-PUT-001": SSPTestCase(
        id="SSP-AAS-REPO-PUT-001",
        profile=Profile.AAS_REPO_001,
        description="PUT /shells/{aasIdentifier} updates existing AAS",
        endpoint="/shells/{aasIdentifier}",
        method="PUT",
        idta_reference="IDTA-01002-3-1-1 Section 5.3.2.4",
    ),
    "SSP-AAS-REPO-PUT-002": SSPTestCase(
        id="SSP-AAS-REPO-PUT-002",
        profile=Profile.AAS_REPO_001,
        description="PUT /shells/{aasIdentifier} with If-Match validates ETag",
        endpoint="/shells/{aasIdentifier}",
        method="PUT",
        idta_reference="IDTA-01002-3-1-1 Section 5.3.2.4",
    ),
    "SSP-AAS-REPO-DELETE-001": SSPTestCase(
        id="SSP-AAS-REPO-DELETE-001",
        profile=Profile.AAS_REPO_001,
        description="DELETE /shells/{aasIdentifier} removes AAS",
        endpoint="/shells/{aasIdentifier}",
        method="DELETE",
        idta_reference="IDTA-01002-3-1-1 Section 5.3.2.5",
    ),
    "SSP-AAS-REPO-ERR-001": SSPTestCase(
        id="SSP-AAS-REPO-ERR-001",
        profile=Profile.AAS_REPO_002,
        description="GET /shells/{aasIdentifier} returns 404 for non-existent AAS",
        endpoint="/shells/{aasIdentifier}",
        method="GET",
        idta_reference="IDTA-01002-3-1-1 Section 5.1.3",
    ),
    "SSP-AAS-REPO-ERR-002": SSPTestCase(
        id="SSP-AAS-REPO-ERR-002",
        profile=Profile.AAS_REPO_002,
        description="Invalid Base64URL ID returns 400 Bad Request",
        endpoint="/shells/{invalid}",
        method="GET",
        idta_reference="IDTA-01002-3-1-1 Section 5.1.3",
    ),
    "SSP-AAS-REPO-ERR-003": SSPTestCase(
        id="SSP-AAS-REPO-ERR-003",
        profile=Profile.AAS_REPO_001,
        description="POST /shells with duplicate ID returns 409 Conflict",
        endpoint="/shells",
        method="POST",
        idta_reference="IDTA-01002-3-1-1 Section 5.1.3",
    ),
    "SSP-AAS-REPO-ERR-004": SSPTestCase(
        id="SSP-AAS-REPO-ERR-004",
        profile=Profile.AAS_REPO_001,
        description="PUT with mismatched ETag returns 412 Precondition Failed",
        endpoint="/shells/{aasIdentifier}",
        method="PUT",
        idta_reference="IDTA-01002-3-1-1 Section 5.1.3",
    ),
}

# Submodel Repository SSP-001/002 Test Cases
SUBMODEL_REPOSITORY_TESTS = {
    "SSP-SM-REPO-LIST-001": SSPTestCase(
        id="SSP-SM-REPO-LIST-001",
        profile=Profile.SM_REPO_001,
        description="GET /submodels returns paginated response",
        endpoint="/submodels",
        method="GET",
        idta_reference="IDTA-01002-3-1-1 Section 5.4.2.1",
    ),
    "SSP-SM-REPO-LIST-002": SSPTestCase(
        id="SSP-SM-REPO-LIST-002",
        profile=Profile.SM_REPO_001,
        description="GET /submodels with semanticId filter returns matching submodels",
        endpoint="/submodels?semanticId={base64url}",
        method="GET",
        idta_reference="IDTA-01002-3-1-1 Section 5.4.2.1",
    ),
    "SSP-SM-REPO-LIST-003": SSPTestCase(
        id="SSP-SM-REPO-LIST-003",
        profile=Profile.SM_REPO_001,
        description="GET /submodels with idShort filter returns matching submodels",
        endpoint="/submodels?idShort={idShort}",
        method="GET",
        idta_reference="IDTA-01002-3-1-1 Section 5.4.2.1",
    ),
    "SSP-SM-REPO-GET-001": SSPTestCase(
        id="SSP-SM-REPO-GET-001",
        profile=Profile.SM_REPO_002,
        description="GET /submodels/{submodelIdentifier} returns submodel by ID",
        endpoint="/submodels/{submodelIdentifier}",
        method="GET",
        idta_reference="IDTA-01002-3-1-1 Section 5.4.2.2",
    ),
    "SSP-SM-REPO-GET-002": SSPTestCase(
        id="SSP-SM-REPO-GET-002",
        profile=Profile.SM_REPO_002,
        description="GET /submodels/{id}/$value returns value-only serialization",
        endpoint="/submodels/{submodelIdentifier}/$value",
        method="GET",
        idta_reference="IDTA-01002-3-1-1 Section 5.4.2.2",
    ),
    "SSP-SM-REPO-GET-003": SSPTestCase(
        id="SSP-SM-REPO-GET-003",
        profile=Profile.SM_REPO_002,
        description="GET /submodels/{id}/$metadata returns metadata-only",
        endpoint="/submodels/{submodelIdentifier}/$metadata",
        method="GET",
        idta_reference="IDTA-01002-3-1-1 Section 5.4.2.2",
    ),
    "SSP-SM-REPO-POST-001": SSPTestCase(
        id="SSP-SM-REPO-POST-001",
        profile=Profile.SM_REPO_001,
        description="POST /submodels creates new submodel",
        endpoint="/submodels",
        method="POST",
        idta_reference="IDTA-01002-3-1-1 Section 5.4.2.3",
    ),
    "SSP-SM-REPO-PUT-001": SSPTestCase(
        id="SSP-SM-REPO-PUT-001",
        profile=Profile.SM_REPO_001,
        description="PUT /submodels/{submodelIdentifier} updates submodel",
        endpoint="/submodels/{submodelIdentifier}",
        method="PUT",
        idta_reference="IDTA-01002-3-1-1 Section 5.4.2.4",
    ),
    "SSP-SM-REPO-DELETE-001": SSPTestCase(
        id="SSP-SM-REPO-DELETE-001",
        profile=Profile.SM_REPO_001,
        description="DELETE /submodels/{submodelIdentifier} removes submodel",
        endpoint="/submodels/{submodelIdentifier}",
        method="DELETE",
        idta_reference="IDTA-01002-3-1-1 Section 5.4.2.5",
    ),
    "SSP-SM-REPO-ERR-001": SSPTestCase(
        id="SSP-SM-REPO-ERR-001",
        profile=Profile.SM_REPO_002,
        description="GET /submodels/{id} returns 404 for non-existent submodel",
        endpoint="/submodels/{submodelIdentifier}",
        method="GET",
        idta_reference="IDTA-01002-3-1-1 Section 5.1.3",
    ),
}

# Registry SSP-001/002 Test Cases
REGISTRY_TESTS = {
    "SSP-REG-AAS-LIST-001": SSPTestCase(
        id="SSP-REG-AAS-LIST-001",
        profile=Profile.REG_AAS_001,
        description="GET /shell-descriptors returns paginated descriptors",
        endpoint="/shell-descriptors",
        method="GET",
        idta_reference="IDTA-01002-3-1-1 Section 5.5.2.1",
    ),
    "SSP-REG-AAS-GET-001": SSPTestCase(
        id="SSP-REG-AAS-GET-001",
        profile=Profile.REG_AAS_002,
        description="GET /shell-descriptors/{aasIdentifier} returns descriptor",
        endpoint="/shell-descriptors/{aasIdentifier}",
        method="GET",
        idta_reference="IDTA-01002-3-1-1 Section 5.5.2.2",
    ),
    "SSP-REG-AAS-POST-001": SSPTestCase(
        id="SSP-REG-AAS-POST-001",
        profile=Profile.REG_AAS_001,
        description="POST /shell-descriptors creates new descriptor",
        endpoint="/shell-descriptors",
        method="POST",
        idta_reference="IDTA-01002-3-1-1 Section 5.5.2.3",
    ),
    "SSP-REG-AAS-PUT-001": SSPTestCase(
        id="SSP-REG-AAS-PUT-001",
        profile=Profile.REG_AAS_001,
        description="PUT /shell-descriptors/{aasIdentifier} updates descriptor",
        endpoint="/shell-descriptors/{aasIdentifier}",
        method="PUT",
        idta_reference="IDTA-01002-3-1-1 Section 5.5.2.4",
    ),
    "SSP-REG-AAS-DELETE-001": SSPTestCase(
        id="SSP-REG-AAS-DELETE-001",
        profile=Profile.REG_AAS_001,
        description="DELETE /shell-descriptors/{aasIdentifier} removes descriptor",
        endpoint="/shell-descriptors/{aasIdentifier}",
        method="DELETE",
        idta_reference="IDTA-01002-3-1-1 Section 5.5.2.5",
    ),
    "SSP-REG-SM-LIST-001": SSPTestCase(
        id="SSP-REG-SM-LIST-001",
        profile=Profile.REG_SM_001,
        description="GET /submodel-descriptors returns paginated descriptors",
        endpoint="/submodel-descriptors",
        method="GET",
        idta_reference="IDTA-01002-3-1-1 Section 5.5.3.1",
    ),
    "SSP-REG-SM-GET-001": SSPTestCase(
        id="SSP-REG-SM-GET-001",
        profile=Profile.REG_SM_002,
        description="GET /submodel-descriptors/{submodelIdentifier} returns descriptor",
        endpoint="/submodel-descriptors/{submodelIdentifier}",
        method="GET",
        idta_reference="IDTA-01002-3-1-1 Section 5.5.3.2",
    ),
    "SSP-REG-SM-POST-001": SSPTestCase(
        id="SSP-REG-SM-POST-001",
        profile=Profile.REG_SM_001,
        description="POST /submodel-descriptors creates new descriptor",
        endpoint="/submodel-descriptors",
        method="POST",
        idta_reference="IDTA-01002-3-1-1 Section 5.5.3.3",
    ),
}

# Discovery SSP-001/002 Test Cases
DISCOVERY_TESTS = {
    "SSP-DISC-LOOKUP-001": SSPTestCase(
        id="SSP-DISC-LOOKUP-001",
        profile=Profile.DISC_002,
        description="GET /lookup/shells returns AAS IDs for asset ID",
        endpoint="/lookup/shells?assetIds={base64url}",
        method="GET",
        idta_reference="IDTA-01002-3-1-1 Section 5.6.2.1",
    ),
    "SSP-DISC-LOOKUP-002": SSPTestCase(
        id="SSP-DISC-LOOKUP-002",
        profile=Profile.DISC_002,
        description="POST /lookup/shells accepts multiple asset IDs",
        endpoint="/lookup/shells",
        method="POST",
        idta_reference="IDTA-01002-3-1-1 Section 5.6.2.2",
    ),
}

# Concept Description Repository SSP-001/002 Test Cases
CONCEPT_DESCRIPTION_TESTS = {
    "SSP-CD-REPO-LIST-001": SSPTestCase(
        id="SSP-CD-REPO-LIST-001",
        profile=Profile.CD_REPO_001,
        description="GET /concept-descriptions returns paginated response",
        endpoint="/concept-descriptions",
        method="GET",
        idta_reference="IDTA-01002-3-1-1 Section 5.7.2.1",
    ),
    "SSP-CD-REPO-LIST-002": SSPTestCase(
        id="SSP-CD-REPO-LIST-002",
        profile=Profile.CD_REPO_002,
        description="GET /concept-descriptions with idShort filter",
        endpoint="/concept-descriptions?idShort={idShort}",
        method="GET",
        idta_reference="IDTA-01002-3-1-1 Section 5.7.2.1",
    ),
    "SSP-CD-REPO-LIST-003": SSPTestCase(
        id="SSP-CD-REPO-LIST-003",
        profile=Profile.CD_REPO_002,
        description="GET /concept-descriptions with isCaseOf filter",
        endpoint="/concept-descriptions?isCaseOf={base64url}",
        method="GET",
        idta_reference="IDTA-01002-3-1-1 Section 5.7.2.1",
    ),
    "SSP-CD-REPO-GET-001": SSPTestCase(
        id="SSP-CD-REPO-GET-001",
        profile=Profile.CD_REPO_002,
        description="GET /concept-descriptions/{cdIdentifier} returns CD",
        endpoint="/concept-descriptions/{cdIdentifier}",
        method="GET",
        idta_reference="IDTA-01002-3-1-1 Section 5.7.2.2",
    ),
    "SSP-CD-REPO-POST-001": SSPTestCase(
        id="SSP-CD-REPO-POST-001",
        profile=Profile.CD_REPO_001,
        description="POST /concept-descriptions creates new CD",
        endpoint="/concept-descriptions",
        method="POST",
        idta_reference="IDTA-01002-3-1-1 Section 5.7.2.3",
    ),
    "SSP-CD-REPO-PUT-001": SSPTestCase(
        id="SSP-CD-REPO-PUT-001",
        profile=Profile.CD_REPO_001,
        description="PUT /concept-descriptions/{cdIdentifier} updates CD",
        endpoint="/concept-descriptions/{cdIdentifier}",
        method="PUT",
        idta_reference="IDTA-01002-3-1-1 Section 5.7.2.4",
    ),
    "SSP-CD-REPO-DELETE-001": SSPTestCase(
        id="SSP-CD-REPO-DELETE-001",
        profile=Profile.CD_REPO_001,
        description="DELETE /concept-descriptions/{cdIdentifier} removes CD",
        endpoint="/concept-descriptions/{cdIdentifier}",
        method="DELETE",
        idta_reference="IDTA-01002-3-1-1 Section 5.7.2.5",
    ),
}

# Self-Description Test Cases
DESCRIPTION_TESTS = {
    "SSP-DESC-001": SSPTestCase(
        id="SSP-DESC-001",
        profile=Profile.DESC,
        description="GET /description returns service description with profiles",
        endpoint="/description",
        method="GET",
        idta_reference="IDTA-01002-3-1-1 Section 5.2.1",
    ),
    "SSP-DESC-002": SSPTestCase(
        id="SSP-DESC-002",
        profile=Profile.DESC,
        description="GET /description includes modifiers ($value, $metadata)",
        endpoint="/description",
        method="GET",
        idta_reference="IDTA-01002-3-1-1 Section 5.2.1",
    ),
    "SSP-DESC-003": SSPTestCase(
        id="SSP-DESC-003",
        profile=Profile.DESC,
        description="GET /description/profiles returns profile URIs",
        endpoint="/description/profiles",
        method="GET",
        idta_reference="IDTA-01002-3-1-1 Section 5.2.2",
    ),
}

# Error Response Test Cases
ERROR_RESPONSE_TESTS = {
    "SSP-ERR-FORMAT-001": SSPTestCase(
        id="SSP-ERR-FORMAT-001",
        profile=Profile.AAS_REPO_002,
        description="Error responses use IDTA message format with 'messages' array",
        endpoint="*",
        method="*",
        idta_reference="IDTA-01002-3-1-1 Section 5.1.3",
    ),
    "SSP-ERR-FORMAT-002": SSPTestCase(
        id="SSP-ERR-FORMAT-002",
        profile=Profile.AAS_REPO_002,
        description="Error message includes code, messageType, text, timestamp",
        endpoint="*",
        method="*",
        idta_reference="IDTA-01002-3-1-1 Section 5.1.3",
    ),
}

# Aggregate all test cases
ALL_SSP_TESTS = {
    **AAS_REPOSITORY_TESTS,
    **SUBMODEL_REPOSITORY_TESTS,
    **REGISTRY_TESTS,
    **DISCOVERY_TESTS,
    **CONCEPT_DESCRIPTION_TESTS,
    **DESCRIPTION_TESTS,
    **ERROR_RESPONSE_TESTS,
}


def get_tests_for_profile(profile: Profile) -> dict[str, SSPTestCase]:
    """Get all test cases for a specific profile."""
    return {k: v for k, v in ALL_SSP_TESTS.items() if v.profile == profile}


def get_required_tests() -> dict[str, SSPTestCase]:
    """Get all required test cases."""
    return {k: v for k, v in ALL_SSP_TESTS.items() if v.required}


# Pytest marker for SSP test case linkage
def ssp(test_case_id: str):
    """Pytest marker to link a test to an SSP test case ID.

    Usage:
        @pytest.mark.ssp("SSP-AAS-REPO-GET-001")
        async def test_get_aas_by_id(api_client):
            ...
    """
    import pytest

    if test_case_id not in ALL_SSP_TESTS:
        raise ValueError(f"Unknown SSP test case ID: {test_case_id}")

    test_case = ALL_SSP_TESTS[test_case_id]
    return pytest.mark.ssp(
        test_case_id,
        profile=test_case.profile.value,
        idta_ref=test_case.idta_reference,
    )

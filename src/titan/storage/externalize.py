"""Externalize large Blob/File content into object storage."""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from typing import Any

from titan.storage.base import BlobMetadata, BlobStorage

BLOB_REF_PREFIX = "/blobs/"


@dataclass
class ExternalizationResult:
    """Result of externalizing blob/file content."""

    new_blobs: list[BlobMetadata] = field(default_factory=list)
    # blob_id -> idShortPath
    referenced: dict[str, str] = field(default_factory=dict)


def _is_blob_ref(value: str) -> str | None:
    """Return blob_id if value is an internal blob ref."""
    if value.startswith(BLOB_REF_PREFIX):
        return value[len(BLOB_REF_PREFIX) :]
    return None


def _extract_data_uri(value: str) -> tuple[bytes, str] | None:
    """Extract bytes and content type from a base64 data URI."""
    if not value.startswith("data:") or ";base64," not in value:
        return None
    header, b64 = value.split(",", 1)
    content_type = header[5:].split(";", 1)[0] or "application/octet-stream"
    return base64.b64decode(b64, validate=True), content_type


def _build_path(parent_path: str | None, id_short: str | None, index: int | None) -> str:
    """Build an idShortPath segment."""
    if index is not None:
        base = parent_path or ""
        return f"{base}[{index}]" if base else f"[{index}]"

    if not id_short:
        return parent_path or ""

    if parent_path:
        return f"{parent_path}.{id_short}"
    return id_short


async def externalize_submodel_doc(
    doc: dict[str, Any],
    submodel_id: str,
    storage: BlobStorage,
) -> ExternalizationResult:
    """Externalize large Blob/File content in a Submodel document.

    Mutates the document in-place and returns metadata for stored blobs.
    """
    result = ExternalizationResult()
    elements = doc.get("submodelElements") or []
    await _externalize_elements(elements, None, False, submodel_id, storage, result)
    return result


async def _externalize_elements(
    elements: list[Any],
    parent_path: str | None,
    parent_is_list: bool,
    submodel_id: str,
    storage: BlobStorage,
    result: ExternalizationResult,
) -> None:
    for idx, element in enumerate(elements):
        if not isinstance(element, dict):
            continue

        element_path = _build_path(
            parent_path,
            element.get("idShort"),
            idx if parent_is_list else None,
        )

        model_type = element.get("modelType")
        if model_type == "Blob":
            await _externalize_blob(element, element_path, submodel_id, storage, result)
        elif model_type == "File":
            await _externalize_file(element, element_path, submodel_id, storage, result)

        # Recurse into nested structures
        if model_type in ("SubmodelElementCollection", "SubmodelElementList"):
            children = element.get("value") or []
            await _externalize_elements(
                children,
                element_path,
                model_type == "SubmodelElementList",
                submodel_id,
                storage,
                result,
            )

        annotations = element.get("annotations")
        if isinstance(annotations, list):
            await _externalize_elements(
                annotations,
                element_path,
                False,
                submodel_id,
                storage,
                result,
            )

        statements = element.get("statements")
        if isinstance(statements, list):
            await _externalize_elements(
                statements,
                element_path,
                False,
                submodel_id,
                storage,
                result,
            )

        # Operation variables contain SubmodelElements in "value"
        for var_key in ("inputVariables", "outputVariables", "inoutputVariables"):
            variables = element.get(var_key)
            if not isinstance(variables, list):
                continue
            for var_index, var in enumerate(variables):
                if not isinstance(var, dict):
                    continue
                var_element = var.get("value")
                if not isinstance(var_element, dict):
                    continue
                var_path = _build_path(element_path, var_key, var_index)
                await _externalize_elements(
                    [var_element],
                    var_path,
                    False,
                    submodel_id,
                    storage,
                    result,
                )


async def _externalize_blob(
    element: dict[str, Any],
    element_path: str,
    submodel_id: str,
    storage: BlobStorage,
    result: ExternalizationResult,
) -> None:
    value = element.get("value")
    if not isinstance(value, str) or not value:
        return

    blob_id = _is_blob_ref(value)
    if blob_id:
        result.referenced[blob_id] = element_path
        return

    content_type = element.get("contentType") or "application/octet-stream"

    try:
        content_bytes = base64.b64decode(value, validate=True)
    except Exception:
        # Not base64 (already externalized or invalid)
        return

    if not storage.should_externalize(content_bytes, content_type):
        return

    metadata = await storage.store(
        submodel_id=submodel_id,
        id_short_path=element_path,
        content=content_bytes,
        content_type=content_type,
    )
    result.new_blobs.append(metadata)
    element["value"] = f"{BLOB_REF_PREFIX}{metadata.id}"


async def _externalize_file(
    element: dict[str, Any],
    element_path: str,
    submodel_id: str,
    storage: BlobStorage,
    result: ExternalizationResult,
) -> None:
    value = element.get("value")
    if not isinstance(value, str) or not value:
        return

    blob_id = _is_blob_ref(value)
    if blob_id:
        result.referenced[blob_id] = element_path
        return

    data_uri = _extract_data_uri(value)
    if data_uri is None:
        return

    content_bytes, inferred_type = data_uri
    content_type = element.get("contentType") or inferred_type

    if not storage.should_externalize(content_bytes, content_type):
        return

    metadata = await storage.store(
        submodel_id=submodel_id,
        id_short_path=element_path,
        content=content_bytes,
        content_type=content_type,
    )
    result.new_blobs.append(metadata)
    element["value"] = f"{BLOB_REF_PREFIX}{metadata.id}"

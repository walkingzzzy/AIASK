"""Helpers for scoped unified vector collection and version names."""

from __future__ import annotations

import re
from typing import Iterable

LEGACY_MARKET_DOC_COLLECTION = "market_doc_chunks"
MARKET_DOC_PROFILE_TYPES = ("news", "notice", "research")
_VECTOR_DIM_VERSION_RE = re.compile(r"__d(\d+)$")


def normalize_profile_type(value: object) -> str | None:
    normalized = str(value or "").strip().lower()
    return normalized or None


def is_profile_scoped_collection(collection_name: object) -> bool:
    normalized = str(collection_name or "").strip()
    return normalized.startswith(f"{LEGACY_MARKET_DOC_COLLECTION}__")


def resolve_vector_collection_name(collection_name: object, profile_type: object = None) -> str:
    normalized_collection = str(collection_name or "").strip()
    normalized_profile_type = normalize_profile_type(profile_type)
    if normalized_collection == LEGACY_MARKET_DOC_COLLECTION and normalized_profile_type:
        return f"{normalized_collection}__{normalized_profile_type}"
    return normalized_collection


def resolve_dimension_scoped_version(version: object, vector_dim: object = None) -> str:
    normalized_version = str(version or "").strip() or "v1"
    try:
        resolved_dim = int(vector_dim or 0)
    except (TypeError, ValueError):
        resolved_dim = 0
    if resolved_dim <= 0:
        return normalized_version
    suffix = f"__d{resolved_dim}"
    if normalized_version.endswith(suffix):
        return normalized_version
    match = _VECTOR_DIM_VERSION_RE.search(normalized_version)
    if match:
        existing_dim = int(match.group(1) or 0)
        if existing_dim == resolved_dim:
            return normalized_version
    return f"{normalized_version}{suffix}"


def vector_collection_candidates(collection_name: object, profile_type: object = None) -> list[str]:
    normalized_collection = str(collection_name or "").strip()
    resolved_collection = resolve_vector_collection_name(normalized_collection, profile_type)
    ordered: list[str] = []
    for item in (resolved_collection, normalized_collection):
        candidate = str(item or "").strip()
        if candidate and candidate not in ordered:
            ordered.append(candidate)
    return ordered


def normalize_market_doc_types(values: object) -> list[str]:
    if isinstance(values, str):
        raw_values: Iterable[object] = [item for item in values.split(",")]
    else:
        raw_values = list(values or [])
    ordered: list[str] = []
    for item in raw_values:
        normalized = normalize_profile_type(item)
        if normalized in MARKET_DOC_PROFILE_TYPES and normalized not in ordered:
            ordered.append(normalized)
    return ordered


def market_doc_collection_name(doc_type: object) -> str:
    return resolve_vector_collection_name(LEGACY_MARKET_DOC_COLLECTION, doc_type)


def market_doc_search_scopes(doc_types: object = None) -> list[tuple[str, str | None]]:
    normalized_doc_types = normalize_market_doc_types(doc_types)
    search_types = normalized_doc_types or list(MARKET_DOC_PROFILE_TYPES)
    ordered: list[tuple[str, str | None]] = []
    for doc_type in search_types:
        scope = (market_doc_collection_name(doc_type), doc_type)
        if scope not in ordered:
            ordered.append(scope)
    legacy_scope = (
        LEGACY_MARKET_DOC_COLLECTION,
        search_types[0] if len(search_types) == 1 else None,
    )
    if legacy_scope not in ordered:
        ordered.append(legacy_scope)
    return ordered

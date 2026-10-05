# Copyright (c) 2026 Valency Systems Inc.
# SPDX-License-Identifier: Apache-2.0
"""Open Canonical Review Schema (OCRS) - schema + mappers for peer reviews."""

from .identifiers import (
    IDENTIFIER_PRIORITY,
    build_resolver_url,
    build_work_identifiers,
    compute_content_hash,
    generate_canonical_work_id,
    normalize_orcid,
    resolve_primary_identifier,
    validate_arxiv,
    validate_doi,
    validate_openalex_author,
    validate_openalex_work,
    validate_orcid,
    validate_pmcid,
)
from .mappers._ai import AiPayload, AiRun
from .registry import (
    map_from,
    map_to,
    map_with_record,
    mapper_version,
    supported_sources,
    supported_targets,
)
from .report import render_mapping_markdown
from .schema import load_schema, validate_canonical
from .util import migrate_work_id_to_identifiers

__all__ = [
    # Schema
    "load_schema",
    "validate_canonical",
    # Registry
    "map_from",
    "map_to",
    "map_with_record",
    "mapper_version",
    "AiPayload",
    "AiRun",
    "render_mapping_markdown",
    "supported_sources",
    "supported_targets",
    # Identifiers
    "IDENTIFIER_PRIORITY",
    "build_resolver_url",
    "build_work_identifiers",
    "compute_content_hash",
    "generate_canonical_work_id",
    "migrate_work_id_to_identifiers",
    "normalize_orcid",
    "resolve_primary_identifier",
    "validate_arxiv",
    "validate_doi",
    "validate_openalex_author",
    "validate_openalex_work",
    "validate_orcid",
    "validate_pmcid",
]

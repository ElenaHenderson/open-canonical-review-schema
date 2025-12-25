"""Utilities for paper and reviewer identifier handling.

This module provides validation, normalization, and resolution utilities for
scholarly identifiers used in the OCRS schema, including DOI, ORCID, arXiv,
PubMed, Semantic Scholar, OpenAlex, and other standard identifiers.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

# =============================================================================
# Validation Patterns (from scholarly infrastructure standards)
# =============================================================================

# ORCID: 16 digits with hyphens, last char is checksum (0-9 or X)
# Uses ISO 7064 MOD 11-2 checksum algorithm
ORCID_PATTERN = re.compile(r"^[0-9]{4}-[0-9]{4}-[0-9]{4}-[0-9]{3}[0-9X]$")

# DOI: 10.prefix/suffix (prefix is 4+ digits registrant code)
DOI_PATTERN = re.compile(r"^10\.\d{4,9}/[^\s]+$")

# arXiv: Modern format YYMM.NNNNN(vN) or legacy arch-ive/YYMMNNN
ARXIV_PATTERN = re.compile(r"^(\d{4}\.\d{4,5}(v\d+)?|[a-z\-]+/\d{7})$")

# PMCID: PMC followed by digits
PMCID_PATTERN = re.compile(r"^PMC\d+$")

# OpenAlex Work ID: W followed by digits
OPENALEX_WORK_PATTERN = re.compile(r"^W\d+$")

# OpenAlex Author ID: A followed by digits
OPENALEX_AUTHOR_PATTERN = re.compile(r"^A\d+$")

# Scopus Author ID: 10-12 digits, no leading zero
SCOPUS_AUTHOR_PATTERN = re.compile(r"^[1-9]\d{9,11}$")

# Google Scholar profile ID: 12 alphanumeric characters (including - and _)
GOOGLE_SCHOLAR_PATTERN = re.compile(r"^[-_0-9A-Za-z]{12}$")

# =============================================================================
# Resolution Priority Order
# =============================================================================

IDENTIFIER_PRIORITY = [
    "doi",  # Crossref, most stable and widely used
    "arxiv_id",  # Preprints, versioned
    "s2cid",  # Semantic Scholar Corpus ID
    "pubmed_id",  # MEDLINE abstracts
    "pmcid",  # PubMed Central full text
    "openalex_id",  # OpenAlex
    "permalink",  # Stable URL
    "internal_id",  # System-specific fallback
]

# =============================================================================
# Resolver URLs
# =============================================================================

RESOLVERS = {
    "doi": "https://doi.org/",
    "arxiv_id": "https://arxiv.org/abs/",
    "pubmed_id": "https://pubmed.ncbi.nlm.nih.gov/",
    "pmcid": "https://pmc.ncbi.nlm.nih.gov/articles/",
    "openalex_id": "https://openalex.org/",
    "s2cid": "https://api.semanticscholar.org/CorpusID:",
    "orcid": "https://orcid.org/",
}


# =============================================================================
# ORCID Validation
# =============================================================================


def validate_orcid_checksum(orcid: str) -> bool:
    """Verify ORCID checksum digit using ISO 7064 MOD 11-2 algorithm.

    The ORCID checksum uses a modified MOD 11-2 algorithm where:
    - Each digit is processed left to right
    - Running total = (total + digit) * 2
    - Final check = (12 - (total % 11)) % 11
    - Check digit is 'X' if result is 10, else the digit

    Args:
        orcid: ORCID in standard format (0000-0000-0000-000X)

    Returns:
        True if checksum is valid
    """
    digits = orcid.replace("-", "")
    if len(digits) != 16:
        return False

    total = 0
    for d in digits[:-1]:
        if not d.isdigit():
            return False
        total = (total + int(d)) * 2

    remainder = total % 11
    result = (12 - remainder) % 11
    expected = "X" if result == 10 else str(result)
    return digits[-1].upper() == expected


def validate_orcid(orcid: str) -> bool:
    """Validate ORCID format AND checksum.

    Args:
        orcid: ORCID identifier to validate

    Returns:
        True if format is correct and checksum is valid
    """
    if not ORCID_PATTERN.match(orcid):
        return False
    return validate_orcid_checksum(orcid)


def normalize_orcid(orcid: str) -> str | None:
    """Normalize ORCID from various formats to standard format.

    Handles:
    - https://orcid.org/0000-0001-2345-6789
    - http://orcid.org/0000-0001-2345-6789
    - 0000000123456789 (no hyphens)
    - 0000-0001-2345-6789 (standard format)

    Args:
        orcid: ORCID in any common format

    Returns:
        Normalized ORCID in standard format (0000-0000-0000-000X) or None if invalid
    """
    # Remove URL prefix if present
    orcid = orcid.strip()
    orcid = orcid.replace("https://orcid.org/", "")
    orcid = orcid.replace("http://orcid.org/", "")

    # Remove hyphens for processing
    clean = orcid.replace("-", "")

    if len(clean) != 16:
        return None

    # Check all characters are valid (digits or X at end)
    if not clean[:-1].isdigit():
        return None
    if clean[-1] not in "0123456789Xx":
        return None

    # Reconstruct with hyphens
    formatted = f"{clean[0:4]}-{clean[4:8]}-{clean[8:12]}-{clean[12:16]}".upper()

    # Fix case: only last character can be X, and it should be uppercase
    formatted = formatted[:-1] + formatted[-1].upper()

    if validate_orcid(formatted):
        return formatted
    return None


# =============================================================================
# Other Identifier Validation
# =============================================================================


def validate_doi(doi: str) -> bool:
    """Validate DOI format.

    Args:
        doi: DOI string (e.g., "10.1234/example.2024")

    Returns:
        True if format is valid
    """
    return bool(DOI_PATTERN.match(doi))


def validate_arxiv(arxiv_id: str) -> bool:
    """Validate arXiv identifier format.

    Supports:
    - Modern format: 2401.12345 or 2401.12345v2
    - Legacy format: hep-th/9901001

    Args:
        arxiv_id: arXiv identifier

    Returns:
        True if format is valid
    """
    return bool(ARXIV_PATTERN.match(arxiv_id))


def validate_pmcid(pmcid: str) -> bool:
    """Validate PubMed Central ID format.

    Args:
        pmcid: PMCID (e.g., "PMC5555555")

    Returns:
        True if format is valid
    """
    return bool(PMCID_PATTERN.match(pmcid))


def validate_openalex_work(openalex_id: str) -> bool:
    """Validate OpenAlex Work ID format.

    Args:
        openalex_id: OpenAlex Work ID (e.g., "W2741809807")

    Returns:
        True if format is valid
    """
    return bool(OPENALEX_WORK_PATTERN.match(openalex_id))


def validate_openalex_author(openalex_id: str) -> bool:
    """Validate OpenAlex Author ID format.

    Args:
        openalex_id: OpenAlex Author ID (e.g., "A5023888391")

    Returns:
        True if format is valid
    """
    return bool(OPENALEX_AUTHOR_PATTERN.match(openalex_id))


def validate_scopus_author(scopus_id: str) -> bool:
    """Validate Scopus Author ID format.

    Args:
        scopus_id: Scopus Author ID (10-12 digits, no leading zero)

    Returns:
        True if format is valid
    """
    return bool(SCOPUS_AUTHOR_PATTERN.match(scopus_id))


def validate_google_scholar(gs_id: str) -> bool:
    """Validate Google Scholar profile ID format.

    Args:
        gs_id: Google Scholar ID (12 alphanumeric characters)

    Returns:
        True if format is valid
    """
    return bool(GOOGLE_SCHOLAR_PATTERN.match(gs_id))


# =============================================================================
# Identifier Resolution
# =============================================================================


def resolve_primary_identifier(
    identifiers: dict[str, Any],
) -> tuple[str, str | None]:
    """Resolve the primary identifier from a workIdentifiers object.

    Uses the priority order defined in IDENTIFIER_PRIORITY to determine
    which identifier takes precedence.

    Args:
        identifiers: Dictionary matching the workIdentifiers schema

    Returns:
        Tuple of (identifier_type, value) following priority order.
        Returns ("unknown", None) if no valid identifier found.
    """
    for id_type in IDENTIFIER_PRIORITY:
        if id_type not in identifiers:
            continue
        id_data = identifiers[id_type]

        if id_type == "internal_id":
            # internal_id is an object with field_name and value
            if isinstance(id_data, dict) and id_data.get("value"):
                return (id_type, str(id_data["value"]))
        elif id_type == "permalink":
            # permalink is a direct string (URI)
            if isinstance(id_data, str) and id_data:
                return (id_type, id_data)
        else:
            # Other IDs use identifierWithLink structure {value, hyperlink?}
            if isinstance(id_data, dict) and id_data.get("value"):
                return (id_type, str(id_data["value"]))

    return ("unknown", None)


def generate_canonical_work_id(identifiers: dict[str, Any]) -> str:
    """Generate a canonical work ID string from identifiers.

    Creates a prefixed identifier string for consistent referencing.

    Args:
        identifiers: Dictionary matching the workIdentifiers schema

    Returns:
        Canonical ID in format "{type}:{value}" (e.g., "doi:10.1234/example")
    """
    id_type, value = resolve_primary_identifier(identifiers)
    if value:
        return f"{id_type}:{value}"
    return "unknown:unidentified"


def build_resolver_url(id_type: str, value: str) -> str | None:
    """Build a resolver URL for a known identifier type.

    Args:
        id_type: Identifier type (e.g., "doi", "orcid", "arxiv_id")
        value: Identifier value

    Returns:
        Resolver URL or None if no resolver is known for this type
    """
    resolver_base = RESOLVERS.get(id_type)
    if resolver_base:
        return f"{resolver_base}{value}"
    return None


# =============================================================================
# Identifier Construction Helpers
# =============================================================================


def build_work_identifiers(
    *,
    doi: str | None = None,
    arxiv_id: str | None = None,
    s2cid: str | None = None,
    pubmed_id: str | None = None,
    pmcid: str | None = None,
    openalex_id: str | None = None,
    permalink: str | None = None,
    internal_field_name: str | None = None,
    internal_value: str | None = None,
) -> dict[str, Any]:
    """Build a workIdentifiers object from available identifiers.

    Constructs a dictionary suitable for the target.identifiers field,
    automatically adding resolver hyperlinks for known identifier types.

    Args:
        doi: Digital Object Identifier
        arxiv_id: arXiv identifier
        s2cid: Semantic Scholar Corpus ID
        pubmed_id: PubMed ID
        pmcid: PubMed Central ID
        openalex_id: OpenAlex Work ID
        permalink: Stable URL
        internal_field_name: Name of internal ID field
        internal_value: Value of internal ID

    Returns:
        Dictionary matching workIdentifiers schema

    Raises:
        ValueError: If no identifier is provided
    """
    identifiers: dict[str, Any] = {}

    if doi:
        identifiers["doi"] = {
            "value": doi,
            "hyperlink": build_resolver_url("doi", doi),
        }
    if arxiv_id:
        identifiers["arxiv_id"] = {
            "value": arxiv_id,
            "hyperlink": build_resolver_url("arxiv_id", arxiv_id),
        }
    if s2cid:
        identifiers["s2cid"] = {
            "value": s2cid,
            "hyperlink": build_resolver_url("s2cid", s2cid),
        }
    if pubmed_id:
        identifiers["pubmed_id"] = {
            "value": pubmed_id,
            "hyperlink": build_resolver_url("pubmed_id", pubmed_id),
        }
    if pmcid:
        identifiers["pmcid"] = {
            "value": pmcid,
            "hyperlink": build_resolver_url("pmcid", pmcid),
        }
    if openalex_id:
        identifiers["openalex_id"] = {
            "value": openalex_id,
            "hyperlink": build_resolver_url("openalex_id", openalex_id),
        }
    if permalink:
        identifiers["permalink"] = permalink
    if internal_field_name and internal_value:
        identifiers["internal_id"] = {
            "field_name": internal_field_name,
            "value": internal_value,
        }

    if not identifiers:
        raise ValueError("At least one identifier must be provided")

    return identifiers


# =============================================================================
# Content Hashing
# =============================================================================


def compute_content_hash(content: bytes, algorithm: str = "sha256") -> str:
    """Compute content hash for document identification.

    Generates a cryptographic hash of document content for integrity
    verification and content-addressed identification.

    Args:
        content: Document content as bytes
        algorithm: Hash algorithm ("sha256" or "sha512")

    Returns:
        Hexadecimal hash string

    Raises:
        ValueError: If unsupported algorithm specified
    """
    if algorithm == "sha256":
        return hashlib.sha256(content).hexdigest()
    elif algorithm == "sha512":
        return hashlib.sha512(content).hexdigest()
    else:
        raise ValueError(f"Unsupported hash algorithm: {algorithm}")


def build_content_hash(content: bytes, algorithm: str = "sha256") -> dict[str, str]:
    """Build a content_hash object for the schema.

    Args:
        content: Document content as bytes
        algorithm: Hash algorithm ("sha256" or "sha512")

    Returns:
        Dictionary with algorithm and value keys
    """
    return {
        "algorithm": algorithm,
        "value": compute_content_hash(content, algorithm),
    }

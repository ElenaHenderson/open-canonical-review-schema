# Open Canonical Review Schema (OCRS)

[![CI](https://github.com/valency-oss/open-canonical-review-schema/actions/workflows/ci.yml/badge.svg)](https://github.com/valency-oss/open-canonical-review-schema/actions/workflows/ci.yml)

A standardized JSON schema and Python mapping utilities for peer review data. OCRS enables interoperability between different peer review systems by providing a canonical representation that preserves rich metadata including reviewer information, decision recommendations, structured findings, metrics, and AI provenance tracking.

## Why OCRS?

Peer review data is fragmented across platforms (OpenReview, CMT, journal systems) with incompatible formats. OCRS solves this by:

- **Unifying formats**: Convert between OpenReview, CMT, journal narratives, and more
- **Preserving provenance**: Track where data came from and how it was transformed
- **Supporting AI reviews**: First-class support for AI/hybrid referee metadata with execution traces, model specifications, and cost tracking
- **Enabling analysis**: Structured schema enables cross-platform review analytics
- **Ensuring validation**: JSON Schema validation catches malformed data early

## Supported Systems

OCRS provides bidirectional mappers for converting between the canonical schema and various peer review platforms:

| System | Source (`from`) | Target (`to`) | Notes |
|--------|:---------------:|:-------------:|-------|
| **OpenReview** | Full | Full | Conference reviews with structured findings and metrics |
| **CMT** | Full | Full | Microsoft Conference Management Toolkit exports |
| **HotCRP** | Full | Basic | Conference reviews; `to_hotcrp` is a minimal stub |
| **Editorial Manager** | Full | Basic | Journal manuscript system; `to_editorialmanager` is a minimal stub |
| **ScholarOne** | Full | Basic | Clarivate journal system; `to_scholarone` is a minimal stub |
| **Journal Narrative** | Full | Full | Minimal free-text reviews with DOI/journal metadata |
| **PAT** | Full | – | AI reviewer (Paper Assistant Tool): `review.json` |
| **OpenAIReview** | Full | – | AI reviewer ([ChicagoHAI/OpenAIReview](https://github.com/ChicagoHAI/OpenAIReview)): `paper.json` |

**Legend:**
- **Full**: Complete mapping with all relevant fields preserved
- **Basic**: Lossy stub that produces valid output but may not preserve all fields

## Quickstart
```bash
uv sync
uv run pytest -q
```

## Development

### Setup
```bash
uv sync
```

### Install git hooks (prek)
Prek is a pre-commit-compatible runner that reads `.pre-commit-config.yaml`.
```bash
uv run prek install
```

### Run hooks on all files
```bash
uv run prek run --all-files
```

### Lint and format
```bash
uv run ruff check .
uv run ruff format .
```

### Tests
```bash
uv run pytest -q
```

## API
```python
from ocrs import map_from, map_to, validate_canonical

canonical = map_from("openreview", openreview_note, keep_raw=True)
validate_canonical(canonical)

note_like = map_to("openreview", canonical)
```

## AI reviewers

The PAT and OpenAIReview mappers copy the reviewer's own output into OCRS; they never rewrite or invent text. Whatever has no OCRS field is kept, unchanged, in `extensions.<reviewer>`.

`map_with_record` also returns a record of how each field was mapped and where the result falls short of OCRS:

- **unmapped**: reviewer fields with no OCRS field;
- **unfilled**: OCRS fields the review leaves empty;
- **coerced**: reviewer values OCRS does not allow (for example an unknown severity), and what the mapper did instead;
- **unanchored**: quotes the reviewer took from the paper that cannot be found in it.

Quotes are matched against the paper, given as plain-text blocks (body, abstract, references). The record says where each quote was found, with the block's ID when it has one.

```python
from ocrs import map_with_record, render_mapping_markdown

result = map_with_record(
    "pat",
    {
        "output": pat_review_json,
        "run": {
            "review_id": "…",
            "source_system": "valency",
            "work_id": "…",
            "work_version": "…",
            "reviewer_commit": "…",
            "model_id": "…",
            "started_at": "…",
            "ended_at": "…",
            "cost_usd": 3.04,
        },
        "blocks": [{"id": "p1", "kind": "body", "text": "…"}, {"kind": "abstract", "text": "…"}],
    },
)
result.review  # the OCRS review
result.record.gaps  # unmapped, unfilled, coerced, unanchored
render_mapping_markdown(result)  # the same record, for people
```

## Example

A minimal canonical review in JSON:

```json
{
  "review_id": "rev_2025_001",
  "version": "1.0.0",
  "created_at": "2025-01-15T14:30:00Z",
  "provenance": {
    "source_system": "openreview",
    "source_review_id": "or_review_abc123"
  },
  "referee": {
    "referee_type": "human",
    "identity_mode": "double_blind",
    "human_referee": {
      "expertise": {
        "self_reported_level": "expert",
        "domain_tags": ["machine-learning", "nlp"]
      }
    }
  },
  "target": {
    "work_id": "paper_xyz789",
    "work_type": "preprint",
    "venue": "NeurIPS 2025"
  },
  "opinion": {
    "summary": "Solid contribution with novel approach to attention mechanisms.",
    "stance": "positive"
  },
  "decision": {
    "recommendation": "weak_accept",
    "confidence": 0.8
  },
  "findings": {
    "strengths": [
      {"text": "Novel architecture with strong theoretical grounding", "severity": "major"},
      {"text": "Comprehensive experiments across multiple benchmarks"}
    ],
    "weaknesses": [
      {
        "title": "No ablation for the gating module",
        "text": "Missing ablation study for key component",
        "severity": "minor",
        "evidence_links": [
          {
            "type": "paper_section",
            "ref": "Section 4.2",
            "quote": "The gating module is essential to our results."
          }
        ]
      }
    ]
  }
}
```

Converting from OpenReview format:

```python
from ocrs import map_from, validate_canonical

openreview_note = {
    "id": "or_review_1",
    "forum": "paper_123",
    "content": {
        "rating": "6: Weak Accept",
        "summary": "Interesting paper with novel contributions.",
        "review": "The main idea is promising...",
        "strengths": ["Good motivation", "Solid results"],
        "weaknesses": ["Proof incomplete"],
    },
}

canonical = map_from("openreview", openreview_note, keep_raw=True)
validate_canonical(canonical)
```

## Schema Overview

The canonical review schema captures:

| Section | Description |
|---------|-------------|
| `provenance` | Source system, original IDs, import timestamps, raw payload |
| `referee` | Human, AI, or hybrid reviewer with identity mode and expertise |
| `target` | Work being reviewed (article, preprint, dataset, etc.) |
| `opinion` | Summary text and overall stance |
| `decision` | Recommendation (accept/reject/revise) with confidence |
| `metrics` | Structured assessments (soundness, clarity, novelty, etc.) |
| `findings` | Strengths, weaknesses, questions, required changes |
| `ethics_and_risk` | Ethical concerns and required mitigations |
| `written_report` | Optional uploaded report document (PDF, Word, Markdown, TXT) |

For AI referees, the schema supports detailed provenance including model specifications, execution traces, token usage, costs, and safety metadata.

### Written Report Upload

Reviewers can optionally attach a written report document alongside their structured review. This supports traditional narrative-style reviews while maintaining the structured data benefits of OCRS.

Supported formats:
- **PDF** (`pdf`) - Portable Document Format
- **Word** (`docx`) - Microsoft Word documents
- **Markdown** (`markdown`) - Markdown text files
- **Plain Text** (`txt`) - Plain text files

Example:
```json
{
  "written_report": {
    "filename": "detailed_review.pdf",
    "content_type": "pdf",
    "url": "https://example.com/reviews/rev_001.pdf",
    "size_bytes": 245678,
    "uploaded_at": "2025-01-15T14:30:00Z",
    "content_hash": {
      "algorithm": "sha256",
      "value": "a1b2c3d4e5f6..."
    },
    "description": "Detailed technical review with annotated figures"
  }
}
```

## Entity Identifiers

OCRS provides comprehensive support for industry-standard scholarly identifiers, enabling integration with bibliographic databases and academic infrastructure.

### Work Identifiers

The `target.identifiers` field supports structured metadata for papers and other scholarly works:

| Identifier | Pattern | Resolver URL | Description |
|------------|---------|--------------|-------------|
| DOI | `10.xxxx/suffix` | `https://doi.org/{value}` | Digital Object Identifier (Crossref, DataCite) |
| arXiv ID | `YYMM.NNNNN(vN)` | `https://arxiv.org/abs/{value}` | arXiv preprint (modern/legacy formats) |
| S2CID | numeric | `https://api.semanticscholar.org/CorpusID:{value}` | Semantic Scholar Corpus ID |
| PubMed ID | numeric | `https://pubmed.ncbi.nlm.nih.gov/{value}` | PubMed/MEDLINE abstract ID |
| PMCID | `PMCnnnnnnn` | `https://pmc.ncbi.nlm.nih.gov/articles/{value}` | PubMed Central full-text ID |
| OpenAlex ID | `Wnnnnnnn` | `https://openalex.org/{value}` | OpenAlex Work ID |
| Permalink | URI | — | Stable URL for the work |
| Internal ID | `{field_name, value}` | — | System-specific ID (HotCRP pid, ScholarOne documentId, etc.) |

**Resolution Priority**: When multiple identifiers are present, OCRS resolves in this order: DOI → arXiv → S2CID → PubMed → PMCID → OpenAlex → permalink → internal_id.

### Reviewer Identifiers

The `referee.human_referee` object supports author/reviewer identification:

| Identifier | Pattern | Resolver URL | Description |
|------------|---------|--------------|-------------|
| ORCID | `0000-0000-0000-000X` | `https://orcid.org/{value}` | Open Researcher and Contributor ID (with checksum validation) |
| OpenAlex Author ID | `Annnnnnn` | `https://openalex.org/{value}` | OpenAlex Author ID |
| Scopus Author ID | 10-12 digits | — | Elsevier Scopus author identifier |
| Google Scholar ID | 12 alphanumeric | — | Google Scholar profile ID |
| Third-party ID | `{key, value}` | — | Other identifiers (Publons, ResearcherID, etc.) |

### OpenAlex Integration

[OpenAlex](https://openalex.org/) is an open catalog of the world's scholarly works. OCRS provides native support for OpenAlex entity IDs:

```python
from ocrs import build_work_identifiers, validate_openalex_work, validate_openalex_author

# Build identifiers with OpenAlex Work ID
identifiers = build_work_identifiers(
    doi="10.1234/example.2024",
    openalex_id="W2741809807",  # Automatically generates resolver URL
)
# Result: {"doi": {...}, "openalex_id": {"value": "W2741809807", "hyperlink": "https://openalex.org/W2741809807"}}

# Validate OpenAlex IDs
assert validate_openalex_work("W2741809807")  # Work IDs start with 'W'
assert validate_openalex_author("A5023888391")  # Author IDs start with 'A'
```

The schema also supports OpenAlex Author IDs for reviewer identification:
```json
{
  "referee": {
    "referee_type": "human",
    "identity_mode": "disclosed",
    "human_referee": {
      "orcid": "0000-0001-5000-0007",
      "openalex_id": "A5023888391",
      "name": "Dr. Jane Smith"
    }
  }
}
```

### ORCID Validation

ORCID identifiers are validated using the ISO 7064 MOD 11-2 checksum algorithm:

```python
from ocrs import validate_orcid, normalize_orcid

# Validate format and checksum
assert validate_orcid("0000-0001-5000-0007")  # Valid
assert not validate_orcid("0000-0001-5000-0008")  # Invalid checksum

# Normalize from various formats
normalize_orcid("https://orcid.org/0000-0001-5000-0007")  # → "0000-0001-5000-0007"
normalize_orcid("0000000150000007")  # → "0000-0001-5000-0007"
```

### Identifier Utilities

The `ocrs.identifiers` module provides utilities for working with scholarly identifiers:

```python
from ocrs import (
    build_work_identifiers,  # Construct workIdentifiers with hyperlinks
    build_resolver_url,  # Generate resolver URL for any identifier type
    resolve_primary_identifier,  # Get highest-priority identifier
    generate_canonical_work_id,  # Create "type:value" canonical ID
    validate_doi,  # Validate DOI format
    validate_arxiv,  # Validate arXiv ID format
    validate_pmcid,  # Validate PMCID format
    compute_content_hash,  # SHA-256/512 for content verification
)

# Build identifiers with automatic hyperlinks
ids = build_work_identifiers(
    doi="10.1234/example",
    arxiv_id="2401.12345",
    internal_field_name="hotcrp_pid",
    internal_value="42",
)

# Resolve to primary identifier
id_type, value = resolve_primary_identifier(ids)  # → ("doi", "10.1234/example")

# Generate canonical work ID
canonical_id = generate_canonical_work_id(ids)  # → "doi:10.1234/example"

# Build resolver URL
url = build_resolver_url("arxiv_id", "2401.12345")  # → "https://arxiv.org/abs/2401.12345"
```

## Related Review Platforms

OCRS currently supports these peer review systems (see [Supported Systems](#supported-systems) for implementation details):

- [OpenReview](https://openreview.net/) - Open peer review platform for scientific publishing
- [Microsoft CMT](https://cmt3.research.microsoft.com/) - Conference management toolkit
- [HotCRP](https://hotcrp.com/) - Conference review software
- [Editorial Manager](https://www.ariessys.com/software/editorial-manager/) - Journal manuscript management (Aries Systems)
- [ScholarOne](https://clarivate.com/products/scientific-and-academic-research/research-publishing-solutions/scholarone/) - Manuscript submission and peer review (Clarivate)

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

Apache License 2.0 - see [LICENSE](LICENSE) for details.

## Acknowledgments

The initial version of OCRS was created by [Valency Systems Inc.](https://valency.io)

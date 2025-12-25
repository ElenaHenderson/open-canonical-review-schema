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

## Supported source formats

- **OpenReview** - Note-like dicts from the OpenReview API
- **CMT** - Export dicts from Microsoft CMT (field names vary by conference)
- **Journal narrative** - Free-text reviews with minimal metadata (DOI, journal name)

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
      {"text": "Missing ablation study for key component", "severity": "minor"}
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
    }
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

For AI referees, the schema supports detailed provenance including model specifications, execution traces, token usage, costs, and safety metadata.

## Related Review Platforms

OCRS is designed to interoperate with these peer review systems:

- [OpenReview](https://openreview.net/) - Open peer review platform for scientific publishing
- [Microsoft CMT](https://cmt3.research.microsoft.com/) - Conference management toolkit
- [HotCRP](https://hotcrp.com/) - Conference review software
- [Editorial Manager](https://www.ariessys.com/software/editorial-manager/) - Journal manuscript management
- [ScholarOne](https://clarivate.com/products/scientific-and-academic-research/research-publishing-solutions/scholarone/) - Manuscript submission and peer review

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

MIT License - see [LICENSE](LICENSE) for details.

## Acknowledgments

The initial version of OCRS was created by [Valency Systems Inc.](https://valency.io)

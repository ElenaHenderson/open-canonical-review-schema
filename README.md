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

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

MIT License - see [LICENSE](LICENSE) for details.

## Acknowledgments

The initial version of OCRS was created by [Valency Systems Inc.](https://valency.io)

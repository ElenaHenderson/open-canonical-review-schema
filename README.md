# Open Canonical Review Schema (OCRS)

Open Canonical Review Schema - JSON schema + mapping utilities for peer reviews.

## Supported source formats
- OpenReview (Note-like dicts)
- CMT export (dicts; field names vary)
- Journal narrative (free text + minimal metadata)

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

## Contributing

We welcome contributions! Please open issues or pull requests.

## License

MIT License - see [LICENSE](LICENSE) for details.

## Acknowledgments

The initial version of OCRS was created by [Valency Systems Inc.](https://valency.io)

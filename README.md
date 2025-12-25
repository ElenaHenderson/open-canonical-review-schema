# canonreview

Canonical peer review JSON schema + mapping utilities.

## Supported source formats
- OpenReview (Note-like dicts)
- CMT export (dicts; field names vary)
- Journal narrative (free text + minimal metadata)

## Quickstart
```bash
pip install -e .[dev]
pytest -q
```

## API
```python
from canonreview import map_from, map_to, validate_canonical

canonical = map_from("openreview", openreview_note, keep_raw=True)
validate_canonical(canonical)

note_like = map_to("openreview", canonical)
```

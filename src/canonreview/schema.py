from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, Optional

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

SCHEMA_PATH = Path(__file__).resolve().parent.parent.parent / "schemas" / "canonical-review.schema.json"

_validator: Optional[Draft202012Validator] = None
_schema: Optional[Dict[str, Any]] = None

def load_schema(path: Optional[str | Path] = None) -> Dict[str, Any]:
    global _schema, _validator
    p = Path(path) if path else SCHEMA_PATH
    _schema = json.loads(p.read_text())
    _validator = Draft202012Validator(_schema)
    return _schema

def validate_canonical(obj: Dict[str, Any], *, schema_path: Optional[str | Path] = None) -> None:
    """Validate a canonical review object; raises ValidationError on failure."""
    global _validator
    if _validator is None or schema_path is not None:
        load_schema(schema_path)
    assert _validator is not None
    _validator.validate(obj)

# Copyright (c) 2026 Valency Systems Inc.
# SPDX-License-Identifier: MIT
"""JSON schema loading and validation for canonical reviews."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent.parent / "schemas" / "canonical-review.schema.json"
)

_validator: Draft202012Validator | None = None
_schema: dict[str, Any] | None = None


def load_schema(path: str | Path | None = None) -> dict[str, Any]:
    global _schema, _validator
    p = Path(path) if path else SCHEMA_PATH
    _schema = json.loads(p.read_text())
    _validator = Draft202012Validator(_schema)
    return _schema


def validate_canonical(obj: dict[str, Any], *, schema_path: str | Path | None = None) -> None:
    """Validate a canonical review object; raises ValidationError on failure."""
    global _validator
    if _validator is None or schema_path is not None:
        load_schema(schema_path)
    assert _validator is not None
    _validator.validate(obj)

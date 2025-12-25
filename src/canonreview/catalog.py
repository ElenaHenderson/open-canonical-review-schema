from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

CATALOG_PATH = Path(__file__).resolve().parent.parent.parent / "schemas" / "metric-catalog.core.v1.json"

def load_catalog(path: Optional[str | Path] = None) -> Dict[str, Any]:
    p = Path(path) if path else CATALOG_PATH
    return json.loads(p.read_text())

def metric_index(catalog: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {m["key"]: m for m in catalog.get("metrics", [])}

def alias_map(catalog: Dict[str, Any]) -> Dict[str, str]:
    amap: Dict[str, str] = {}
    for m in catalog.get("metrics", []):
        key = m["key"]
        for a in m.get("aliases", []):
            amap[a.casefold()] = key
    return amap

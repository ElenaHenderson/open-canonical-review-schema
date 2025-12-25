# Copyright (c) 2026 Valency Systems Inc.
# SPDX-License-Identifier: MIT
"""Pytest configuration for OCRS tests."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

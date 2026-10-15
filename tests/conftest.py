"""Shared fixtures for the ViCare Plus tests."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from typing import Any

import pytest

ROOT = Path(__file__).parent.parent
LOGIC_PATH = ROOT / "custom_components" / "vicare" / "plus" / "logic.py"


def _load_logic() -> Any:
    """Load logic.py on its own, without the Home Assistant package around it."""
    spec = importlib.util.spec_from_file_location("vicare_plus_logic", LOGIC_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def logic() -> Any:
    """Return the logic module."""
    return _load_logic()


@pytest.fixture(scope="session")
def features() -> dict[str, dict[str, Any]]:
    """Return the features of a Vitodens 200-W (VScotHO1 72) as feature map."""
    data = json.loads((ROOT / "tests" / "fixtures" / "features.json").read_text())
    return {item["feature"]: item for item in data["data"]}

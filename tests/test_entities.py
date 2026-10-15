"""Smoke tests of the ViCare Plus entities (needs Home Assistant installed)."""

from __future__ import annotations

from pathlib import Path
import sys
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

pytest.importorskip("homeassistant")
pytest.importorskip("PyViCare")

sys.path.insert(0, str(Path(__file__).parent.parent))

from custom_components.vicare.plus.entity import (  # noqa: E402
    ApiCallsSensor,
    BurnerCyclingBinarySensor,
    HeatingCurveSensor,
    PlusBinarySensor,
    PlusNumber,
    PlusSelect,
    RuntimeTodaySensor,
    ScheduleSensor,
    build_entities,
)
from custom_components.vicare.plus.runtime import PlusRuntime  # noqa: E402
from custom_components.vicare.types import ViCareDevice  # noqa: E402

PLATFORMS = ("sensor", "binary_sensor", "number", "select", "text", "switch", "button")


class FakeService:
    """PyViCare service returning the fixture."""

    def __init__(self, features: dict[str, Any]) -> None:
        self.payload = {"data": list(features.values())}

    def fetch_all_features(self, accessor: Any) -> dict[str, Any]:
        return self.payload

    def _extract_entities(self, data: Any, accessor: Any) -> list[Any]:
        return data["data"]


@pytest.fixture
def runtime(features: dict[str, Any]) -> PlusRuntime:
    """Return a runtime with one fake Vitodens."""
    api = SimpleNamespace(
        service=FakeService(features),
        accessor=SimpleNamespace(device_id="0"),
        roles=["type:boiler"],
    )
    config = MagicMock()
    config.getConfig.return_value = SimpleNamespace(serial="1234567890123456")
    config.getId.return_value = "0"
    config.getModel.return_value = "VScotHO1_72"
    device = ViCareDevice(config=config, api=api, serial=None, coordinator=MagicMock())
    hass = SimpleNamespace(config=SimpleNamespace(language="de"))
    entry = SimpleNamespace(options={}, entry_id="test")
    rt = PlusRuntime(hass, entry)  # type: ignore[arg-type]
    rt.build_devices([device])
    rt.update_trackers(rt.devices[0])
    return rt


def _all(runtime: PlusRuntime) -> dict[str, list[Any]]:
    return {platform: build_entities(runtime, platform) for platform in PLATFORMS}


def test_unique_ids_are_unique_and_prefixed(runtime: PlusRuntime) -> None:
    """Every entity has its own unique id in the plus namespace."""
    ids = [e.unique_id for items in _all(runtime).values() for e in items]
    assert len(ids) == len(set(ids))
    assert all(uid.startswith("1234567890123456_0-plus-") for uid in ids)


def test_every_platform_builds(runtime: PlusRuntime) -> None:
    """All platforms get entities on this device."""
    entities = _all(runtime)
    for platform in PLATFORMS:
        assert entities[platform], platform


def test_pump_sensors(runtime: PlusRuntime) -> None:
    """Pump states are exposed as running binary sensors with readable names."""
    pumps = {
        e._spec.feature: e
        for e in build_entities(runtime, "binary_sensor")
        if isinstance(e, PlusBinarySensor) and "pump" in e._spec.feature
    }
    assert len(pumps) == 6
    assert pumps["heating.dhw.pumps.circulation"].is_on is True
    assert pumps["heating.dhw.pumps.primary"].is_on is False
    assert "Zirkulation" in pumps["heating.dhw.pumps.circulation"].name
    runtimes = [
        e
        for e in build_entities(runtime, "sensor")
        if isinstance(e, RuntimeTodaySensor)
    ]
    assert len(runtimes) >= 6


def test_schedule_sensor(runtime: PlusRuntime) -> None:
    """The circulation program shows its mode and the full week."""
    schedule = next(
        e
        for e in build_entities(runtime, "sensor")
        if isinstance(e, ScheduleSensor)
        and e.spec.feature == "heating.dhw.pumps.circulation.schedule"
    )
    assert schedule.native_value in ("on", "off")
    attrs = schedule.extra_state_attributes
    assert attrs is not None
    assert len(attrs["schedule"]["mon"]) == 3
    assert "next_change" in attrs


def test_operating_mode_select(runtime: PlusRuntime) -> None:
    """The circuit mode select maps snake case options to the API values."""
    select = next(
        e
        for e in build_entities(runtime, "select")
        if isinstance(e, PlusSelect)
        and e._spec.feature == "heating.circuits.1.operating.modes.active"
    )
    assert "dhw_and_heating" in select.options
    assert select._to_api["dhw_and_heating"] == "dhwAndHeating"
    assert select.current_option in select.options


def test_numbers_have_ranges(runtime: PlusRuntime) -> None:
    """Writable temperatures get min, max and step from the API."""
    numbers = [
        e for e in build_entities(runtime, "number") if isinstance(e, PlusNumber)
    ]
    assert numbers
    for number in numbers:
        assert number.native_min_value < number.native_max_value


def test_derived_entities(runtime: PlusRuntime) -> None:
    """Heating curve, cycling detection and API counter are created."""
    sensors = build_entities(runtime, "sensor")
    curves = [e for e in sensors if isinstance(e, HeatingCurveSensor)]
    assert curves
    assert any(e.native_value is not None for e in curves)
    assert any(isinstance(e, ApiCallsSensor) for e in sensors)
    assert any(
        isinstance(e, BurnerCyclingBinarySensor)
        for e in build_entities(runtime, "binary_sensor")
    )

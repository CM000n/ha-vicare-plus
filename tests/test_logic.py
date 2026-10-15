"""Tests of the pure ViCare Plus logic against a real feature dump."""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest

CIRCULATION = "heating.dhw.pumps.circulation.schedule"


def _keys(items: list[Any]) -> set[str]:
    return {item.key for item in items}


def test_get_features_is_memoized(logic: Any, features: dict[str, Any]) -> None:
    """The snapshot is only rebuilt when PyViCare fetched new data."""
    payload = {"data": list(features.values())}
    calls = []

    class Service:
        def fetch_all_features(self, accessor: Any) -> dict[str, Any]:
            return payload

        def _extract_entities(self, data: Any, accessor: Any) -> list[Any]:
            calls.append(1)
            return data["data"]

    api = SimpleNamespace(service=Service(), accessor=SimpleNamespace(device_id="0"))
    first = logic.get_features(api)
    assert logic.get_features(api) is first
    assert len(calls) == 1
    assert "heating.boiler.sensors.temperature.main" in first


def test_discovery_exposes_pumps(logic: Any, features: dict[str, Any]) -> None:
    """All pumps, including the ones the core skips, become entities."""
    disc = logic.discover(features)
    keys = _keys(disc.properties)
    assert "heating.dhw.pumps.circulation:status" in keys
    assert "heating.dhw.pumps.primary:status" in keys
    assert "heating.circuits.2.circulation.pump:status" in keys
    assert "heating.circuits.1.circulation.pump:status" in keys


def test_discovery_schedules(logic: Any, features: dict[str, Any]) -> None:
    """Every writable time program is found with its constraints."""
    disc = logic.discover(features)
    schedules = {spec.feature: spec for spec in disc.schedules}
    assert CIRCULATION in schedules
    assert "heating.dhw.schedule" in schedules
    assert "heating.circuits.1.heating.schedule" in schedules
    circulation = schedules[CIRCULATION]
    assert circulation.modes == ("on",)
    assert circulation.default_mode == "off"
    assert circulation.max_entries == 4
    assert circulation.resolution == 10


def test_discovery_operating_mode_select(logic: Any, features: dict[str, Any]) -> None:
    """The operating mode of each circuit becomes a select with all API options."""
    disc = logic.discover(features)
    selects = {c.feature: c for c in disc.commands if c.platform == "select"}
    mode = selects["heating.circuits.1.operating.modes.active"]
    assert mode.command == "setMode"
    assert "dhwAndHeating" in mode.options
    assert "standby" in mode.options


def test_discovery_holiday_is_not_an_entity(
    logic: Any, features: dict[str, Any]
) -> None:
    """Commands needing several free parameters are services, not entities."""
    disc = logic.discover(features)
    holiday = [
        c for c in disc.commands if c.feature == "heating.operating.programs.holiday"
    ]
    assert all(c.platform != "number" for c in holiday)


def test_discovery_keys_are_unique(logic: Any, features: dict[str, Any]) -> None:
    """Unique ids must not collide."""
    disc = logic.discover(features)
    for items in (disc.properties, disc.commands):
        keys = [item.key for item in items]
        assert len(keys) == len(set(keys))


def test_labels(logic: Any) -> None:
    """Feature names translate to readable labels."""
    assert logic.camel_to_snake("dhwAndHeating") == "dhw_and_heating"
    label_de = logic.feature_label("heating.dhw.pumps.circulation", "de")
    label_en = logic.feature_label("heating.dhw.pumps.circulation", "en")
    assert "Zirkulation" in label_de
    assert "irculation" in label_en


def test_clean_string(logic: Any) -> None:
    """NUL padding is removed."""
    assert logic.clean_string("abc\x00\x00 ") == "abc"
    assert logic.clean_string(5) == 5


@pytest.fixture
def circulation(logic: Any, features: dict[str, Any]) -> Any:
    """Return the schedule spec of the circulation pump."""
    return logic.schedule_spec(features[CIRCULATION])


def test_mode_at_and_next_change(logic: Any) -> None:
    """The current and next mode are derived from the entries."""
    entries = {"mon": [{"start": "06:00", "end": "08:00", "mode": "on"}]}
    monday = datetime(2026, 10, 12, 7, 0)
    assert logic.mode_at(entries, "off", monday) == "on"
    assert logic.mode_at(entries, "off", monday.replace(hour=9)) == "off"
    when, mode = logic.next_change(entries, "off", monday)
    assert (when, mode) == (monday.replace(hour=8), "off")
    when, mode = logic.next_change(entries, "off", monday.replace(hour=9))
    assert (when, mode) == (datetime(2026, 10, 19, 6, 0), "on")


def test_next_change_none_for_constant(logic: Any) -> None:
    """A schedule without changes has no next change."""
    assert logic.next_change({}, "off", datetime(2026, 10, 12, 7, 0)) is None


def test_validate_schedule(logic: Any, circulation: Any) -> None:
    """Valid schedules are normalized, invalid ones raise."""
    result = logic.validate_schedule(
        {
            "mon": [
                {"start": "17:00", "end": "24:00"},
                {"start": "06:00", "end": "08:00"},
            ]
        },
        circulation,
    )
    assert result["mon"][0] == {
        "start": "06:00",
        "end": "08:00",
        "mode": "on",
        "position": 0,
    }
    assert result["mon"][1]["end"] == "24:00"
    assert result["tue"] == []
    with pytest.raises(logic.ScheduleError):
        logic.validate_schedule(
            {"mon": [{"start": "06:05", "end": "08:00"}]}, circulation
        )
    with pytest.raises(logic.ScheduleError):
        logic.validate_schedule(
            {"mon": [{"start": "08:00", "end": "06:00"}]}, circulation
        )
    with pytest.raises(logic.ScheduleError):
        logic.validate_schedule(
            {"mon": [{"start": "06:00", "end": "08:00", "mode": "eco"}]}, circulation
        )
    with pytest.raises(logic.ScheduleError):
        logic.validate_schedule(
            {
                "mon": [
                    {"start": f"{h:02d}:00", "end": f"{h:02d}:30"}
                    for h in range(0, 10, 2)
                ]
            },
            circulation,
        )


def test_boost_schedule_merges(logic: Any, circulation: Any) -> None:
    """A boost extends an existing slot instead of using a new one."""
    entries = {"mon": [{"start": "06:00", "end": "08:00", "mode": "on", "position": 0}]}
    now = datetime(2026, 10, 12, 7, 43)
    new, end = logic.boost_schedule(entries, circulation, now, timedelta(minutes=30))
    assert new["mon"] == [
        {"start": "06:00", "end": "08:20", "mode": "on", "position": 0}
    ]
    assert end == datetime(2026, 10, 12, 8, 20)
    assert entries["mon"][0]["end"] == "08:00"


def test_boost_schedule_caps_at_midnight(logic: Any, circulation: Any) -> None:
    """A boost never spills into the next day."""
    now = datetime(2026, 10, 12, 23, 50)
    new, end = logic.boost_schedule({}, circulation, now, timedelta(hours=2))
    assert new["mon"][0]["end"] == "24:00"
    assert end == datetime(2026, 10, 13, 0, 0)


def test_boost_schedule_full(logic: Any, circulation: Any) -> None:
    """A boost fails when no slot is left."""
    entries = {
        "mon": [
            {"start": f"{h:02d}:00", "end": f"{h:02d}:30", "mode": "on"}
            for h in range(0, 8, 2)
        ]
    }
    with pytest.raises(logic.ScheduleError):
        logic.boost_schedule(
            entries, circulation, datetime(2026, 10, 12, 12, 0), timedelta(minutes=30)
        )


def test_permanent_schedule(logic: Any, circulation: Any) -> None:
    """A permanent schedule covers every day completely."""
    result = logic.permanent_schedule(circulation)
    assert set(result) == set(logic.WEEKDAYS)
    assert result["sun"] == [
        {"start": "00:00", "end": "24:00", "mode": "on", "position": 0}
    ]


def test_heating_curve(logic: Any) -> None:
    """The Viessmann heating curve formula yields known values."""
    assert logic.heating_curve_supply(-10, 20, 0, 1.4) == pytest.approx(63.2, abs=0.1)
    assert logic.heating_curve_supply(20, 20, 0, 1.4) == 20
    assert logic.heating_curve_supply(20, 20, 5, 1.4) == 25
    assert logic.heating_curve_supply(-10, 20, 0, 0.6) < logic.heating_curve_supply(
        -10, 20, 0, 1.4
    )


def test_circuit_room_setpoint(logic: Any, features: dict[str, Any]) -> None:
    """The setpoint of the active program is used."""
    temperature, program = logic.circuit_room_setpoint(features, "1")
    assert isinstance(temperature, float)
    assert (temperature, program) == (19.0, "normal")


def test_groups(logic: Any) -> None:
    """Features are clustered thematically."""
    assert logic.group_of("heating.circuits.1.circulation.pump") == "circuit_1"
    assert logic.group_of("heating.circuits.2.heating.curve") == "circuit_2"
    assert logic.group_of("heating.dhw.pumps.circulation.schedule") == "circulation"
    assert logic.group_of("heating.dhw.pumps.primary") == "dhw"
    assert logic.group_of("heating.solar.power.production") == "solar"
    assert logic.group_of("heating.burners.0.modulation") == "generator"
    assert logic.group_of("heating.boiler.sensors.temperature.main") == "generator"
    assert logic.group_of("heating.sensors.temperature.outside") == "system"
    assert logic.group_of("api_calls_24h") == "system"
    assert logic.group_label("circuit_1", "de") == "Heizkreis 1"
    assert logic.group_label("generator", "en", heatpump=True) == "Heat pump"


def test_strip_group_prefix(logic: Any) -> None:
    """The group name is not repeated in entity names."""
    strip = logic.strip_group_prefix
    assert strip("Heizkreis 1 Betriebsart", "circuit_1", "de") == "Betriebsart"
    assert strip("Heizkreis 1", "circuit_1", "de") == "Aktiv"
    assert strip("Zirkulationspumpe Boost", "circulation", "de") == "Pumpe Boost"
    assert strip("Solarertrag heute", "solar", "de") == "Ertrag heute"
    assert strip("Kesseltemperatur", "generator", "de") == "Temperatur"
    assert strip("Brenner 0 Modulation", "generator", "de") == "Brenner Modulation"
    assert strip("Speicherladepumpe", "dhw", "de") == "Speicherladepumpe"
    assert strip("Außentemperatur", "system", "de") == "Außentemperatur"
    assert strip("DHW circulation pump", "circulation", "en") == "Pump"


def test_icons(logic: Any) -> None:
    """Icons follow the theme, with an off variant for pumps and burners."""
    assert logic.icon_for("heating.circuits.1.circulation.pump:status") == (
        "mdi:pump",
        "mdi:pump-off",
    )
    assert logic.icon_for("heating.dhw.pumps.circulation:status")[0] == "mdi:water-sync"
    assert logic.icon_for("heating.burners.0:active") == ("mdi:fire", "mdi:fire-off")
    assert logic.icon_for(f"{CIRCULATION}:resetSchedule")[0] == "mdi:calendar-refresh"
    assert (
        logic.icon_for("heating.dhw.sensors.temperature.outlet:status")[0]
        == "mdi:thermometer-alert"
    )
    assert logic.icon_for("unknown.feature:value") == (None, None)


def test_helper_roundtrip(logic: Any, circulation: Any) -> None:
    """Device programs convert to helper weeks and back."""
    entries = {
        "mon": [
            {"start": "05:00", "end": "09:00", "mode": "on", "position": 0},
            {"start": "08:00", "end": "10:00", "mode": "on", "position": 1},
            {"start": "18:00", "end": "24:00", "mode": "on", "position": 2},
        ]
    }
    week = logic.entries_to_helper(entries, circulation)
    assert week["monday"] == [
        {"from": "05:00:00", "to": "10:00:00"},
        {"from": "18:00:00", "to": "24:00:00"},
    ]
    assert week["sunday"] == []
    back = logic.helper_to_entries(week, circulation)
    assert [(e["start"], e["end"]) for e in back["mon"]] == [
        ("05:00", "10:00"),
        ("18:00", "24:00"),
    ]
    assert logic.entries_to_helper(back, circulation) == week


def test_helper_rounding_and_limits(logic: Any, circulation: Any) -> None:
    """Helper times are aligned to the device resolution and validated."""
    item = {"tuesday": [{"from": "06:05:00", "to": "06:41:00"}]}
    entries = logic.helper_to_entries(item, circulation)
    assert (entries["tue"][0]["start"], entries["tue"][0]["end"]) == ("06:00", "06:50")
    assert logic.normalize_helper(item, circulation)["tuesday"] == [
        {"from": "06:00:00", "to": "06:50:00"}
    ]
    too_many = {
        "monday": [
            {"from": f"{h:02d}:00:00", "to": f"{h:02d}:30:00"} for h in range(0, 10, 2)
        ]
    }
    with pytest.raises(logic.ScheduleError):
        logic.helper_to_entries(too_many, circulation)


def test_helper_keeps_modes(logic: Any) -> None:
    """Programs with several modes store the mode in the range data."""
    spec = logic.ScheduleSpec(
        feature="heating.circuits.1.heating.schedule",
        modes=("normal", "comfort"),
        default_mode="reduced",
        max_entries=4,
        resolution=10,
        overlap_allowed=True,
    )
    entries = {
        "wed": [
            {"start": "06:00", "end": "22:00", "mode": "normal"},
            {"start": "07:00", "end": "08:00", "mode": "comfort"},
        ]
    }
    week = logic.entries_to_helper(entries, spec)
    assert week["wednesday"] == [
        {"from": "06:00:00", "to": "07:00:00", "data": {"mode": "normal"}},
        {"from": "07:00:00", "to": "08:00:00", "data": {"mode": "comfort"}},
        {"from": "08:00:00", "to": "22:00:00", "data": {"mode": "normal"}},
    ]
    back = logic.helper_to_entries(week, spec)
    assert [e["mode"] for e in back["wed"]] == ["normal", "comfort", "normal"]


@pytest.mark.parametrize(
    ("key", "kind", "comp_id", "group"),
    [
        ("heating", "HeatingCircuit", 1, "circuit_1"),
        ("heating curve slope", "HeatingCircuit", 2, "circuit_2"),
        ("supply_temperature", "HeatingCircuit", 1, "circuit_1"),
        ("frost_protection_active", "HeatingCircuit", 2, "circuit_2"),
        ("burner_active", "GazBurner", 0, "generator"),
        ("burner_modulation", "GazBurner", 0, "generator"),
        ("compressor_starts", "Compressor", 0, "generator"),
        ("1", None, None, "dhw"),
        ("dhw_temperature", None, None, "dhw"),
        ("dhw_operating_mode", None, None, "dhw"),
        ("activate_onetimecharge", None, None, "dhw"),
        ("charging_active", None, None, "dhw"),
        ("hotwater_max_temperature", None, None, "dhw"),
        ("dhw_storage_temperature", None, None, "dhw"),
        ("dhw_pump_active", None, None, "dhw"),
        ("dhw_circulationpump_active", None, None, "circulation"),
        ("domestic_hot_water_circulation_pump", None, None, "circulation"),
        ("solar_pump_active", None, None, "solar"),
        ("solar storage temperature", None, None, "solar"),
        ("collector temperature", None, None, "solar"),
        ("solar power production today", None, None, "solar"),
        ("boiler_temperature", None, None, "generator"),
        ("gas_consumption_heating_today", None, None, "generator"),
        ("buffer_top_temperature", None, None, "buffer"),
        ("ventilation", None, None, "ventilation"),
        ("outside_temperature", None, None, "system"),
        ("device_error", None, None, "system"),
    ],
)
def test_core_group(
    logic: Any, key: str, kind: str | None, comp_id: Any, group: str
) -> None:
    """Core entities are mapped to the same clusters as plus entities."""
    assert logic.core_group(key, kind, comp_id) == group


def test_is_duplicate(logic: Any) -> None:
    """An alias only counts as duplicate while its original exists."""
    key = "heating.dhw.sensors.temperature.dhwCylinder:value"
    original = {"heating.dhw.sensors.temperature.hotWaterStorage": {"isEnabled": True}}
    assert logic.is_duplicate(key, original)
    assert not logic.is_duplicate(key, {})
    assert logic.is_duplicate(key.replace(":value", ":status"), original)
    assert logic.is_duplicate("heating.sensors.temperature.outside:value", {})
    assert not logic.is_duplicate("heating.boiler.temperature:value", {})

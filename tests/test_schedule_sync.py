"""Tests of the schedule helper sync (needs Home Assistant installed)."""

from __future__ import annotations

import asyncio
import copy
from pathlib import Path
import sys
from types import SimpleNamespace
from typing import Any

import pytest

pytest.importorskip("homeassistant")

sys.path.insert(0, str(Path(__file__).parent.parent))

from custom_components.vicare.plus import schedule_sync  # noqa: E402
from custom_components.vicare.plus.logic import schedule_spec  # noqa: E402

FEATURE = "heating.dhw.pumps.circulation.schedule"
KEY = f"dev|{FEATURE}"


class FakeStore:
    """In-memory replacement of the storage helper."""

    def __init__(self, *args: Any) -> None:
        self.data: dict[str, Any] | None = None

    async def async_load(self) -> dict[str, Any] | None:
        return self.data

    async def async_save(self, data: dict[str, Any]) -> None:
        self.data = copy.deepcopy(data)

    def async_delay_save(self, func: Any, delay: float) -> None:
        self.data = copy.deepcopy(func())


class FakeCollection:
    """Minimal schedule storage collection."""

    def __init__(self) -> None:
        self.data: dict[str, dict[str, Any]] = {}
        self.listeners: list[Any] = []
        self.updates = 0

    def async_add_listener(self, listener: Any) -> Any:
        self.listeners.append(listener)
        return lambda: self.listeners.remove(listener)

    async def _notify(self, change: str, item: dict[str, Any]) -> None:
        for listener in self.listeners:
            await listener(change, item["id"], item)

    async def async_create_item(self, data: dict[str, Any]) -> dict[str, Any]:
        item = {"id": "circ", **data}
        self.data["circ"] = item
        await self._notify("added", item)
        return item

    async def async_update_item(self, item_id: str, data: dict[str, Any]) -> None:
        self.updates += 1
        item = {"id": item_id, **data}
        self.data[item_id] = item
        await self._notify("updated", item)


class FakeOverrides:
    """Override manager without active overrides."""

    def __init__(self) -> None:
        self.active: dict[str, Any] | None = None
        self.updated: dict[str, Any] | None = None

    def get(self, ctx: Any, feature: str) -> dict[str, Any] | None:
        return self.active

    async def async_update_original(
        self, ctx: Any, feature: str, entries: dict[str, Any]
    ) -> None:
        self.updated = entries

    def async_add_listener(self, listener: Any) -> Any:
        return lambda: None


@pytest.fixture
def setup(features: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> Any:
    """Return a sync with a fake device, collection and hass."""
    collection = FakeCollection()
    writes: list[dict[str, Any]] = []
    monkeypatch.setattr(schedule_sync, "Store", FakeStore)
    monkeypatch.setattr(
        schedule_sync, "find_schedule_collection", lambda hass: collection
    )
    monkeypatch.setattr(
        schedule_sync,
        "write_schedule",
        lambda ctx, feature, entries: writes.append(entries),
    )
    notifications: list[str] = []
    monkeypatch.setattr(
        schedule_sync.persistent_notification,
        "async_create",
        lambda hass, message, **kwargs: notifications.append(message),
    )
    spec = schedule_spec(features[FEATURE])

    class Coordinator:
        listeners: list[Any] = []

        def async_add_listener(self, listener: Any) -> Any:
            self.listeners.append(listener)
            return lambda: None

        async def async_request_refresh(self) -> None:
            return None

    ctx = SimpleNamespace(
        identifier="dev",
        features=copy.deepcopy(features),
        heatpump=False,
        discovery=SimpleNamespace(schedules=[spec]),
        device=SimpleNamespace(coordinator=Coordinator()),
    )
    tasks: list[Any] = []

    async def executor(func: Any, *args: Any) -> Any:
        return func(*args)

    hass = SimpleNamespace(
        async_create_task=lambda coro: tasks.append(asyncio.ensure_future(coro)),
        async_add_executor_job=executor,
    )
    runtime = SimpleNamespace(
        hass=hass,
        entry=SimpleNamespace(entry_id="test"),
        language="de",
        devices=[ctx],
        overrides=FakeOverrides(),
    )
    sync = schedule_sync.ScheduleSync(hass, runtime)  # type: ignore[arg-type]

    async def settle() -> None:
        while tasks:
            await tasks.pop(0)

    return SimpleNamespace(
        sync=sync,
        collection=collection,
        writes=writes,
        notifications=notifications,
        ctx=ctx,
        settle=settle,
        runtime=runtime,
    )


async def test_creates_helper_from_device(setup: Any) -> None:
    """A helper with the device program is created on start."""
    assert await setup.sync.async_start()
    item = setup.collection.data["circ"]
    assert item["name"] == "ViCare Zirkulation Zeitprogramm"
    assert item["icon"] == "mdi:water-sync"
    assert item["monday"][0] == {"from": "05:00:00", "to": "09:00:00"}
    await setup.settle()
    assert setup.writes == []


async def test_helper_edit_is_written(setup: Any) -> None:
    """Editing the helper writes the rounded program to the device."""
    await setup.sync.async_start()
    item = copy.deepcopy(setup.collection.data["circ"])
    item["monday"] = [{"from": "06:05:00", "to": "07:00:00"}]
    await setup.collection.async_update_item("circ", item)
    await setup.settle()
    assert len(setup.writes) == 1
    assert setup.writes[0]["mon"][0]["start"] == "06:00"
    # The helper shows what the device stores.
    assert setup.collection.data["circ"]["monday"] == [
        {"from": "06:00:00", "to": "07:00:00"}
    ]


async def test_invalid_edit_is_reverted(setup: Any) -> None:
    """Too many ranges are rejected, notified and reverted."""
    await setup.sync.async_start()
    original = copy.deepcopy(setup.collection.data["circ"]["monday"])
    item = copy.deepcopy(setup.collection.data["circ"])
    item["monday"] = [
        {"from": f"{h:02d}:00:00", "to": f"{h:02d}:30:00"} for h in range(0, 10, 2)
    ]
    await setup.collection.async_update_item("circ", item)
    await setup.settle()
    assert setup.writes == []
    assert setup.notifications
    assert setup.collection.data["circ"]["monday"] == original


async def test_device_change_updates_helper(setup: Any) -> None:
    """A changed device program is mirrored without writing back."""
    await setup.sync.async_start()
    entries = setup.ctx.features[FEATURE]["properties"]["entries"]["value"]
    entries["mon"] = [{"start": "07:00", "end": "08:00", "mode": "on", "position": 0}]
    setup.sync._async_device_changed()
    await setup.settle()
    assert setup.collection.data["circ"]["monday"] == [
        {"from": "07:00:00", "to": "08:00:00"}
    ]
    assert setup.writes == []


async def test_edit_during_override_updates_original(setup: Any) -> None:
    """While a boost is active the edit replaces the program restored later."""
    await setup.sync.async_start()
    setup.runtime.overrides.active = {"original": {}, "kind": "boost"}
    item = copy.deepcopy(setup.collection.data["circ"])
    item["friday"] = [{"from": "10:00:00", "to": "11:00:00"}]
    await setup.collection.async_update_item("circ", item)
    await setup.settle()
    assert setup.writes == []
    assert setup.runtime.overrides.updated["fri"][0]["start"] == "10:00"

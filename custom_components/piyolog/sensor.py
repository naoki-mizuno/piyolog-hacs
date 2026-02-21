"""Sensors for PiyoLog integration: last event per type (by event time) with params."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN, EVENT_TYPE_NAMES
from .coordinator import PiyoLogCoordinator

from .client import EventType

_LOGGER = logging.getLogger(__name__)


def _event_type_name_to_friendly(name: str) -> str:
    """Convert event_type name to a friendly label for sensor name."""
    labels = {
        "milk": "Milk",
        "breastfeeding": "Breastfeeding",
        "expressed_milk": "Expressed Milk",
        "sleep": "Sleep",
        "wake_up": "Wake Up",
        "pee": "Pee",
        "poo": "Poo",
        "body_temperature": "Body Temperature",
        "baby_food": "Baby Food",
        "height": "Height",
        "weight": "Weight",
        "bath": "Bath",
        "walk": "Walk",
        "meal": "Meal",
        "snack": "Snack",
        "medicine": "Medicine",
        "vaccine": "Vaccine",
        "pumping": "Pumping",
        "head_circumference": "Head Circumference",
        "chest_circumference": "Chest Circumference",
        "memo": "Memo",
        "other": "Other",
    }
    return labels.get(name, name.replace("_", " ").title())


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up PiyoLog last-event sensors from a config entry."""
    data = hass.data[DOMAIN].get(entry.entry_id)
    if not data:
        return
    coordinator: PiyoLogCoordinator = data["coordinator"]

    # One sensor per (baby_id, event_type). Use babies from coordinator cache.
    # If cache is empty (no successful sync yet), we create no sensors.
    baby_ids = list(coordinator._babies_cache.keys())
    if not baby_ids:
        _LOGGER.debug("No babies in cache yet; no last-event sensors created")
        return

    entities: list[SensorEntity] = []
    entry_id = entry.entry_id
    for baby_id in baby_ids:
        baby_name = coordinator._babies_cache.get(baby_id, "")
        for event_type, type_name in EVENT_TYPE_NAMES.items():
            entities.append(
                PiyoLogLastEventSensor(
                    coordinator=coordinator,
                    entry_id=entry_id,
                    baby_id=baby_id,
                    baby_name=baby_name,
                    event_type=event_type,
                    event_type_name=type_name,
                )
            )
        # One breastfeeding-today sensor per baby
        entities.append(
            PiyoLogBreastfeedingTodaySensor(
                coordinator=coordinator,
                entry_id=entry_id,
                baby_id=baby_id,
                baby_name=baby_name,
            )
        )

    async_add_entities(entities)
    _LOGGER.info(
        "Added %d PiyoLog sensors (%d babies × %d event types + %d breastfeeding-today)",
        len(entities),
        len(baby_ids),
        len(EVENT_TYPE_NAMES),
        len(baby_ids),
    )


class PiyoLogLastEventSensor(CoordinatorEntity[PiyoLogCoordinator], SensorEntity):
    """Sensor that holds the latest event (by event time) for a given baby and event type."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_native_value = None

    def __init__(
        self,
        coordinator: PiyoLogCoordinator,
        entry_id: str,
        baby_id: str,
        baby_name: str,
        event_type: int,
        event_type_name: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._baby_id = baby_id
        self._baby_name = baby_name or baby_id
        self._event_type = event_type
        self._event_type_name = event_type_name

        friendly = _event_type_name_to_friendly(event_type_name)
        name = f"PiyoLog Most Recent {friendly}"
        if baby_name:
            name = f"{name} ({baby_name})"
        self._attr_name = name
        self._attr_unique_id = f"{entry_id}_{baby_id}_{event_type_name}"
        self._attr_icon = _icon_for_event_type(event_type)

    @property
    def native_value(self) -> Optional[datetime]:
        """Return the datetime of the most recent event (by event time). TIMESTAMP device_class requires a datetime object."""
        event = self._get_latest_event()
        if not event:
            return None
        return self.coordinator._parse_datetime_jst(event.get("datetime"))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the last event's params (amount, memo, type-specific fields)."""
        event = self._get_latest_event()
        if not event:
            return {}
        return self.coordinator.build_event_attributes(event)

    def _get_latest_event(self) -> Optional[dict]:
        """Get the latest event for this baby and event type from coordinator data."""
        key = (str(self._baby_id), int(self._event_type))
        return self.coordinator._last_events.get(key)


class PiyoLogBreastfeedingTodaySensor(
    CoordinatorEntity[PiyoLogCoordinator], SensorEntity
):
    """Sensor showing cumulative breastfeeding minutes today (HA system timezone)."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_state_class = SensorStateClass.TOTAL
    _attr_icon = "mdi:mother-nurse"

    def __init__(
        self,
        coordinator: PiyoLogCoordinator,
        entry_id: str,
        baby_id: str,
        baby_name: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._baby_id = baby_id

        name = f"PiyoLog Breastfeeding Today"
        if baby_name:
            name = f"{name} ({baby_name})"
        self._attr_name = name
        self._attr_unique_id = f"{entry_id}_{baby_id}_breastfeeding_today"

    @property
    def native_value(self) -> int:
        """Total breastfeeding minutes today (left + right)."""
        left, right, _ = self._today_totals()
        return left + right

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Left minutes, right minutes, and session count for today."""
        left, right, count = self._today_totals()
        return {
            "left_minutes": left,
            "right_minutes": right,
            "total_minutes": left + right,
            "session_count": count,
        }

    def _today_totals(self) -> tuple[int, int, int]:
        """Return (left_minutes, right_minutes, session_count) for today in HA timezone."""
        today = dt_util.now().date()
        left_sec = 0
        right_sec = 0
        count = 0
        for e in self.coordinator._breastfeeding_events.values():
            if str(e.get("baby_id")) != str(self._baby_id):
                continue
            dt = self.coordinator._parse_datetime_jst(e.get("datetime"))
            if dt is None:
                continue
            # Convert to HA's configured timezone for "today" comparison
            event_date = dt.astimezone(dt_util.DEFAULT_TIME_ZONE).date()
            if event_date != today:
                continue
            left_sec += e.get("left_time", 0)
            right_sec += e.get("right_time", 0)
            count += 1
        return left_sec // 60, right_sec // 60, count


def _icon_for_event_type(event_type: int) -> str:
    """Return a suitable icon for the event type."""
    icons = {
        EventType.MILK: "mdi:cup",
        EventType.MOTHERS_MILK: "mdi:mother-nurse",
        EventType.MILKING: "mdi:bottle-tonic-plus",
        EventType.SLEEP_BEGIN: "mdi:sleep",
        EventType.SLEEP_END: "mdi:bed-clock",
        EventType.PEE: "mdi:water",
        EventType.POO: "mdi:emoticon-poop",
        EventType.BODY_TEMPERATURE: "mdi:thermometer",
        EventType.BODY_WEIGHT: "mdi:scale-bathroom",
        EventType.BODY_HEIGHT: "mdi:human-male-height",
        EventType.BATH: "mdi:bathtub",
        EventType.WALKING: "mdi:walk",
        EventType.MEAL: "mdi:food-apple",
        EventType.MEAL2: "mdi:silverware-fork-knife",
        EventType.SNACK: "mdi:food",
        EventType.MEDICINE: "mdi:medical-bag",
        EventType.VACCINE: "mdi:needle",
        EventType.PUMPING: "mdi:bottle-tonic-plus",
        EventType.HEAD: "mdi:head",
        EventType.CHEST: "mdi:human-handsdown",
        EventType.MEMO: "mdi:note-text",
    }
    return icons.get(event_type, "mdi:calendar-clock")

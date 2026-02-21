"""DataUpdateCoordinator for PiyoLog integration."""

from datetime import datetime, timedelta
import logging
from typing import Any, Dict, List, Optional, Set
from zoneinfo import ZoneInfo

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import (
    PiyoLogClient,
    EventType,
    PoopAmount,
    PoopHardness,
    PoopColor,
    BreastfeedingOrder,
)
from .const import DOMAIN, EVENT_TYPE_NAMES, PIYOLOG_TIMEZONE

_JST = ZoneInfo(PIYOLOG_TIMEZONE)

_LOGGER = logging.getLogger(__name__)

# Reverse mappings: numeric enum value -> human-readable string
POOP_AMOUNT_REVERSE = {
    PoopAmount.SMALL: "small",
    PoopAmount.LARGE: "large",
    PoopAmount.NORMAL: "normal",
    PoopAmount.MINIMUM: "bit",
}

POOP_HARDNESS_REVERSE = {
    PoopHardness.DIARRHEA: "diarrhea",
    PoopHardness.SOFT: "soft",
    PoopHardness.HARD: "hard",
    PoopHardness.NORMAL: "normal",
}

POOP_COLOR_REVERSE = {
    PoopColor.WHITE: "white",
    PoopColor.YELLOW: "yellow",
    PoopColor.ORANGE: "orange",
    PoopColor.BROWN: "brown",
    PoopColor.GREEN: "green",
    PoopColor.RED: "red",
    PoopColor.BLACK: "black",
}

BREASTFEEDING_ORDER_REVERSE = {
    BreastfeedingOrder.UNSPECIFIED: "unspecified",
    BreastfeedingOrder.LEFT_TO_RIGHT: "left_first",
    BreastfeedingOrder.RIGHT_TO_LEFT: "right_first",
}


class PiyoLogCoordinator(DataUpdateCoordinator):
    """Class to manage fetching PiyoLog data from API."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: PiyoLogClient,
        update_interval: timedelta,
    ) -> None:
        """Initialize coordinator.

        Args:
            hass: Home Assistant instance
            client: PiyoLogClient instance
            update_interval: How often to sync with PiyoLog API
        """
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=update_interval,
        )
        self.client = client
        self._seen_event_ids: Set[str] = set()
        self._babies_cache: Dict[str, str] = {}  # baby_id -> baby_name mapping
        self._is_first_sync = (
            True  # Track first sync to avoid firing all historical events
        )
        # Accumulated latest event per (baby_id, event_type) across all syncs.
        # Kept in memory so delta syncs (which return 0 total events when nothing is new)
        # don't wipe out the data.
        self._last_events: Dict[tuple, Dict[str, Any]] = {}
        # SLEEP_BEGIN events keyed by event_id (needed to find the correct preceding
        # sleep for asleep_minutes even after subsequent sleep sessions).
        # Dict allows deletions and edits to be reflected without a full restart.
        self._sleep_begin_events: Dict[str, Dict[str, Any]] = {}
        # MOTHERS_MILK events keyed by event_id (for today's cumulative sensor).
        # Using a dict allows deletions and edits to be reflected without a full restart.
        self._breastfeeding_events: Dict[str, Dict[str, Any]] = {}

    async def _async_update_data(self) -> Dict[str, Any]:
        """Fetch data from PiyoLog API.

        This is called by the coordinator on the configured update interval.
        Returns latest events and fires Home Assistant events for new ones.
        """
        try:
            # Fetch latest data from PiyoLog API
            response = await self.hass.async_add_executor_job(
                self.client.sync,
                self.client._main_version,
                self.client._minor_version,
            )

            status = response.get("status")
            if status != 200:
                if status == 407:
                    _LOGGER.warning(
                        "PiyoLog API returned 407. Your session may have expired or "
                        "credentials are invalid. Re-add the integration or check "
                        "your PiyoLog account linking."
                    )
                raise UpdateFailed(f"PiyoLog API error: {status}")

            data = response.get("data", {})

            # Update baby cache if babies data is present
            if "baby" in data:
                babies = data["baby"]
                if babies:  # Only update if we got actual baby data
                    self._update_baby_cache(babies)

            # Process baby events (ignore soft-deleted)
            raw_events = data.get("baby_event", [])
            baby_events = [e for e in raw_events if not e.get("deleted")]
            new_events = self._process_events(baby_events)

            # Fire Home Assistant events for new baby events
            # Skip firing events on first sync to avoid flooding with historical data
            if self._is_first_sync:
                _LOGGER.info(
                    "First sync: Loaded %d historical events (not fired). "
                    "Only NEW events will fire from now on.",
                    len(baby_events),
                )
                self._is_first_sync = False
            elif new_events:
                _LOGGER.info("Firing %d new event(s)", len(new_events))
                for event in new_events:
                    self._fire_ha_event(event)

            _LOGGER.debug(
                "Sync: %d total, %d new, %d tracked",
                len(baby_events),
                len(new_events),
                len(self._seen_event_ids),
            )

            # Merge this sync's events into the persistent last_events accumulator.
            # Delta syncs may return 0 events when nothing is new -- that's fine,
            # _last_events already holds the data from the first full sync.
            self._update_last_events(baby_events)
            # Update sleep/breastfeeding dicts with raw events (including deleted) so
            # that deletions and edits are immediately reflected in sensors.
            self._update_sleep_begin_events(raw_events)
            self._update_breastfeeding_events(raw_events)

            return {
                "baby_events": baby_events,
                "new_events": new_events,
                "last_events": self._last_events,
                "last_sync": response.get("main_version"),
                "sync_count": len(baby_events),
            }

        except Exception as err:
            _LOGGER.error("Error syncing with PiyoLog API: %s", err, exc_info=True)
            raise UpdateFailed(f"Failed to sync with PiyoLog: {err}") from err

    def _update_baby_cache(self, babies: list) -> None:
        """Update the baby ID to name mapping cache.

        Args:
            babies: List of baby dicts from API
        """
        if not babies:
            _LOGGER.warning("No baby data to cache")
            return

        # Update cache
        for baby in babies:
            baby_id = baby.get("baby_id")
            nickname = baby.get("nickname", "")
            if baby_id:
                self._babies_cache[baby_id] = nickname
                _LOGGER.debug("Cached baby: %s -> %s", baby_id, nickname)
            else:
                _LOGGER.warning("Baby record missing baby_id: %s", baby)

        _LOGGER.info(
            "Baby cache now has %d %s: %s",
            len(self._babies_cache),
            "baby" if len(self._babies_cache) == 1 else "babies",
            ",".join(self._babies_cache.values()),
        )

    def _process_events(self, events: list) -> list:
        """Process events and identify new ones.

        Args:
            events: List of baby event dicts from API

        Returns:
            List of new events (not seen before)
        """
        new_events = []

        for event in events:
            event_id = event.get("event_id")

            # Skip if we've seen this event before
            if event_id in self._seen_event_ids:
                continue

            # Mark as seen
            self._seen_event_ids.add(event_id)
            new_events.append(event)

        # Limit the seen_event_ids set size to prevent memory issues
        # Keep only the most recent 10,000 event IDs
        if len(self._seen_event_ids) > 10000:
            _LOGGER.debug(
                "Trimming seen_event_ids cache from %d to 5000 entries",
                len(self._seen_event_ids),
            )
            # Convert to list, keep last 5000, convert back to set
            recent_ids = list(self._seen_event_ids)[-5000:]
            self._seen_event_ids = set(recent_ids)

        return new_events

    def _update_last_events(self, events: list) -> None:
        """Merge events into self._last_events, keeping the latest per (baby_id, event_type).

        Called after every sync (including delta syncs that return 0 events).
        self._last_events accumulates across syncs so data isn't lost when
        subsequent delta syncs return an empty baby_event list.

        Args:
            events: List of non-deleted baby event dicts from this sync.
        """
        for event in events:
            baby_id = event.get("baby_id")
            event_type = event.get("type")
            if baby_id is None or event_type is None:
                continue
            dt_iso = self._format_datetime_iso(event.get("datetime"))
            if not dt_iso:
                continue
            key = (str(baby_id), int(event_type))
            existing = self._last_events.get(key)
            if existing is None or dt_iso > self._format_datetime_iso(
                existing.get("datetime")
            ):
                self._last_events[key] = event

            # SLEEP_BEGIN and MOTHERS_MILK events are now managed by
            # _update_sleep_begin_events / _update_breastfeeding_events.

    def _update_sleep_begin_events(self, raw_events: list) -> None:
        """Update the sleep-begin dict from raw events (including deleted ones)."""
        for event in raw_events:
            if int(event.get("type", -1)) != EventType.SLEEP_BEGIN:
                continue
            event_id = event.get("event_id")
            if not event_id:
                continue
            if event.get("deleted"):
                self._sleep_begin_events.pop(event_id, None)
            else:
                self._sleep_begin_events[event_id] = event

    def _update_breastfeeding_events(self, raw_events: list) -> None:
        """Update the breastfeeding dict from raw events (including deleted ones).

        Using raw (unfiltered) events means deletions and time edits made in the
        Piyolog app are reflected immediately after the next sync.
        """
        for event in raw_events:
            if int(event.get("type", -1)) != EventType.MOTHERS_MILK:
                continue
            event_id = event.get("event_id")
            if not event_id:
                continue
            if event.get("deleted"):
                self._breastfeeding_events.pop(event_id, None)
                _LOGGER.debug("Breastfeeding event removed (deleted): %s", event_id)
            else:
                self._breastfeeding_events[event_id] = event

    def _parse_datetime_jst(self, datetime_str: Optional[str]) -> Optional[datetime]:
        """Parse PiyoLog "YYYYMMDD HH:mm" or ISO string to JST-aware datetime.

        PiyoLog assumes JST. Comparisons and duration math (e.g. asleep_minutes)
        use these so all values are in the same timezone.
        """
        if not datetime_str:
            return None
        s = str(datetime_str).strip()
        if not s:
            return None
        try:
            if " " in s and len(s) >= 14 and s[8:9] == " ":
                # PiyoLog format: "20260209 14:30" (14 chars)
                date_part, time_part = s.split(None, 1)
                year = int(date_part[0:4])
                month = int(date_part[4:6])
                day = int(date_part[6:8])
                hour, minute = int(time_part[0:2]), int(time_part[3:5])
                sec = int(time_part[6:8]) if len(time_part) >= 8 else 0
                return datetime(year, month, day, hour, minute, sec, tzinfo=_JST)
            # ISO-like: parse and convert to JST
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=_JST)
            else:
                dt = dt.astimezone(_JST)
            return dt
        except (ValueError, TypeError, IndexError):
            return None

    def build_event_attributes(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Build HA-style attribute dict for a baby event (for sensors / events).

        For SLEEP_END events, asleep_minutes is computed from self._sleep_begin_events.

        Args:
            event: Baby event dict from PiyoLog API.

        Returns:
            Dict of attributes (event_id, baby_id, baby_name, event_type,
            datetime, memo, and type-specific fields like amount, poo_amount).
        """
        event_type = event.get("type")
        event_type_name = EVENT_TYPE_NAMES.get(event_type, "unknown")

        baby_id = event.get("baby_id")
        baby_name = self._babies_cache.get(baby_id, "")

        attrs: Dict[str, Any] = {
            "event_id": event.get("event_id"),
            "baby_id": baby_id,
            "baby_name": baby_name,
            "event_type": event_type_name,
            "datetime": self._format_datetime_iso(event.get("datetime")),
            "memo": event.get("memo", ""),
        }

        amount = event.get("amount", 0)
        value = event.get("value", 0)
        left_time = event.get("left_time", 0)
        right_time = event.get("right_time", 0)

        if event_type == EventType.SLEEP_END:
            wake_dt = self._parse_datetime_jst(event.get("datetime"))
            if wake_dt:
                last_sleep_dt: Optional[datetime] = None
                for e in self._sleep_begin_events.values():
                    if str(e.get("baby_id")) != str(baby_id):
                        continue
                    dt = self._parse_datetime_jst(e.get("datetime"))
                    if (
                        dt
                        and dt < wake_dt
                        and (last_sleep_dt is None or dt > last_sleep_dt)
                    ):
                        last_sleep_dt = dt
                if last_sleep_dt is not None:
                    attrs["asleep_minutes"] = int(
                        (wake_dt - last_sleep_dt).total_seconds() / 60
                    )

        if event_type == EventType.MILK and amount > 0:
            attrs["amount"] = amount
        elif event_type == EventType.MOTHERS_MILK:
            if amount > 0:
                attrs["amount"] = amount
            if left_time > 0:
                attrs["breastfeeding_left_minutes"] = left_time // 60
            if right_time > 0:
                attrs["breastfeeding_right_minutes"] = right_time // 60
            if value > 0:
                attrs["breastfeeding_order"] = BREASTFEEDING_ORDER_REVERSE.get(
                    value, "unspecified"
                )
        elif event_type == EventType.POO:
            if amount > 0:
                attrs["poo_amount"] = POOP_AMOUNT_REVERSE.get(amount, "normal")
            if value > 0:
                attrs["poo_hardness"] = POOP_HARDNESS_REVERSE.get(value, "normal")
            if left_time > 0:
                attrs["poo_color"] = POOP_COLOR_REVERSE.get(left_time, "brown")
        elif event_type == EventType.BODY_TEMPERATURE and value > 0:
            attrs["temperature"] = value
        elif event_type == EventType.BODY_WEIGHT and value > 0:
            attrs["weight"] = value
        elif event_type == EventType.BODY_HEIGHT and value > 0:
            attrs["height"] = value
        elif event_type == EventType.HEAD and value > 0:
            attrs["head_circumference"] = value
        elif event_type == EventType.CHEST and value > 0:
            attrs["chest_circumference"] = value
        elif event_type in [EventType.MILKING, EventType.PUMPING] and amount > 0:
            attrs["amount"] = amount

        return attrs

    def _fire_ha_event(self, event: Dict[str, Any]) -> None:
        """Fire a Home Assistant event for a PiyoLog baby event.

        Args:
            event: Baby event dict from PiyoLog API
        """
        ha_event_data = self.build_event_attributes(event)
        event_type_name = ha_event_data["event_type"]
        event_name = f"piyolog_event_{event_type_name}"
        self.hass.bus.fire(event_name, ha_event_data)

        _LOGGER.debug(
            "Fired HA event: %s for baby %s (%s) at %s",
            event_name,
            ha_event_data["baby_name"],
            ha_event_data["baby_id"],
            ha_event_data["datetime"],
        )

    def _format_datetime_iso(self, datetime_str: Optional[str]) -> Optional[str]:
        """Convert PiyoLog datetime to ISO 8601 with JST timezone.

        PiyoLog assumes JST. Output includes +09:00 so HA and templates
        interpret the time correctly.

        Args:
            datetime_str: PiyoLog "YYYYMMDD HH:mm" or ISO string

        Returns:
            ISO 8601 string like "2026-02-09T14:30:00+09:00" or None
        """
        dt = self._parse_datetime_jst(datetime_str)
        return dt.isoformat() if dt else None

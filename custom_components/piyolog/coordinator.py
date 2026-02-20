"""DataUpdateCoordinator for PiyoLog integration."""

from datetime import timedelta
import logging
from typing import Any, Dict, Set, Optional

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
from .const import DOMAIN, EVENT_TYPE_NAMES

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

            # Process baby events
            baby_events = data.get("baby_event", [])
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

            # Latest event per (baby_id, event_type) by event time (not retrieval time)
            last_events = self._compute_latest_events_by_time(baby_events)

            return {
                "baby_events": baby_events,
                "new_events": new_events,
                "last_events": last_events,
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

    def _compute_latest_events_by_time(
        self, events: list
    ) -> Dict[tuple, Dict[str, Any]]:
        """Compute the latest event per (baby_id, event_type) by event datetime.

        Args:
            events: List of baby event dicts from API.

        Returns:
            Dict mapping (baby_id, event_type) -> event dict for the most recent
            event of that type for that baby (by the event's own datetime).
        """
        last_events: Dict[tuple, Dict[str, Any]] = {}
        for event in events:
            baby_id = event.get("baby_id")
            event_type = event.get("type")
            if baby_id is None or event_type is None:
                continue
            dt_iso = self._format_datetime_iso(event.get("datetime"))
            if not dt_iso:
                continue
            key = (baby_id, event_type)
            existing = last_events.get(key)
            if existing is None or dt_iso > self._format_datetime_iso(
                existing.get("datetime")
            ):
                last_events[key] = event
        return last_events

    def build_event_attributes(
        self, event: Dict[str, Any], all_events: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """Build HA-style attribute dict for a baby event (for sensors / events).

        Args:
            event: Baby event dict from PiyoLog API.
            all_events: Optional list of all baby events (used to compute sleep_minutes
                for wake_up from the preceding sleep event).

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

        if event_type == EventType.SLEEP_END and all_events:
            wake_dt = self._parse_datetime_jst(event.get("datetime"))
            if wake_dt:
                last_sleep_dt: Optional[datetime] = None
                for e in all_events:
                    if e.get("baby_id") != baby_id or e.get("type") != EventType.SLEEP_BEGIN:
                        continue
                    dt = self._parse_datetime_jst(e.get("datetime"))
                    if dt and dt < wake_dt and (last_sleep_dt is None or dt > last_sleep_dt):
                        last_sleep_dt = dt
                if last_sleep_dt is not None:
                    attrs["sleep_minutes"] = int((wake_dt - last_sleep_dt).total_seconds() / 60)

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

    def _fire_ha_event(
        self, event: Dict[str, Any], all_events: Optional[List[Dict[str, Any]]] = None
    ) -> None:
        """Fire a Home Assistant event for a PiyoLog baby event.

        Args:
            event: Baby event dict from PiyoLog API
            all_events: Optional list of all baby events (for sleep_minutes on wake_up)
        """
        ha_event_data = self.build_event_attributes(event, all_events)
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
        """Convert PiyoLog datetime format to ISO 8601 format.

        Args:
            datetime_str: DateTime string in PiyoLog format "20260209 14:30"

        Returns:
            ISO 8601 format string like "2026-02-09T14:30:00" or None
        """
        if not datetime_str:
            return None

        try:
            # PiyoLog format: "20260209 14:30"
            parts = datetime_str.split()
            if len(parts) != 2:
                return None

            date_part = parts[0]  # "20260209"
            time_part = parts[1]  # "14:30"

            # Convert to ISO 8601: "2026-02-09T14:30:00"
            year = date_part[0:4]
            month = date_part[4:6]
            day = date_part[6:8]

            return f"{year}-{month}-{day}T{time_part}:00"

        except Exception as err:
            _LOGGER.debug(
                "Failed to convert datetime to ISO: %s - %s", datetime_str, err
            )
            return None

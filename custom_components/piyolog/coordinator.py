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

            if response.get("status") != 200:
                raise UpdateFailed(f"PiyoLog API error: {response.get('status')}")

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

            return {
                "baby_events": baby_events,
                "new_events": new_events,
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

    def _fire_ha_event(self, event: Dict[str, Any]) -> None:
        """Fire a Home Assistant event for a PiyoLog baby event.

        Args:
            event: Baby event dict from PiyoLog API
        """
        event_type = event.get("type")
        event_type_name = EVENT_TYPE_NAMES.get(event_type, "unknown")

        # Get baby name from cache
        baby_id = event.get("baby_id")
        if baby_id in self._babies_cache:
            baby_name = self._babies_cache[baby_id]
        else:
            baby_name = ""
            if self._babies_cache:
                _LOGGER.warning(
                    "Baby ID '%s' not found in cache. Cache has %d babies: %s",
                    baby_id,
                    len(self._babies_cache),
                    list(self._babies_cache.keys()),
                )

        # Build base event data (always included)
        ha_event_data = {
            "event_id": event.get("event_id"),
            "baby_id": baby_id,
            "baby_name": baby_name,
            "event_type": event_type_name,
            "datetime": self._format_datetime_iso(event.get("datetime")),  # ISO 8601
            "memo": event.get("memo", ""),
        }

        # Add event-specific fields based on type
        amount = event.get("amount", 0)
        value = event.get("value", 0)
        left_time = event.get("left_time", 0)
        right_time = event.get("right_time", 0)

        # Milk/formula events
        if event_type == EventType.MILK and amount > 0:
            ha_event_data["amount"] = amount

        # Breastfeeding events
        elif event_type == EventType.MOTHERS_MILK:
            if amount > 0:  # Amount in ml
                ha_event_data["amount"] = amount
            if left_time > 0:
                ha_event_data["breastfeeding_left_minutes"] = left_time // 60
            if right_time > 0:
                ha_event_data["breastfeeding_right_minutes"] = right_time // 60
            if value > 0:  # Breastfeeding order
                ha_event_data["breastfeeding_order"] = BREASTFEEDING_ORDER_REVERSE.get(
                    value, "unspecified"
                )

        # Poo events
        elif event_type == EventType.POO:
            if amount > 0:  # PoopAmount
                ha_event_data["poo_amount"] = POOP_AMOUNT_REVERSE.get(amount, "normal")
            if value > 0:  # PoopHardness
                ha_event_data["poo_hardness"] = POOP_HARDNESS_REVERSE.get(
                    value, "normal"
                )
            if left_time > 0:  # PoopColor
                ha_event_data["poo_color"] = POOP_COLOR_REVERSE.get(left_time, "brown")

        # Temperature events
        elif event_type == EventType.BODY_TEMPERATURE and value > 0:
            ha_event_data["temperature"] = value

        # Weight events
        elif event_type == EventType.BODY_WEIGHT and value > 0:
            ha_event_data["weight"] = value

        # Height events
        elif event_type == EventType.BODY_HEIGHT and value > 0:
            ha_event_data["height"] = value

        # Head circumference
        elif event_type == EventType.HEAD and value > 0:
            ha_event_data["head_circumference"] = value

        # Chest circumference
        elif event_type == EventType.CHEST and value > 0:
            ha_event_data["chest_circumference"] = value

        # Expressed breast milk / pumping
        elif event_type in [EventType.MILKING, EventType.PUMPING] and amount > 0:
            ha_event_data["amount"] = amount

        # Fire the event
        event_name = f"piyolog_event_{event_type_name}"
        self.hass.bus.fire(event_name, ha_event_data)

        _LOGGER.debug(
            "Fired HA event: %s for baby %s (%s) at %s",
            event_name,
            baby_name,
            baby_id,
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

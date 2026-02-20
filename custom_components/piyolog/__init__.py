"""The PiyoLog Baby Tracker integration."""

import asyncio
from datetime import timedelta
import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.event import async_track_time_interval

from .client import PiyoLogClient, BreastfeedingOrder
from .coordinator import PiyoLogCoordinator, UpdateFailed
from .const import (
    DOMAIN,
    CONF_USER_ID,
    CONF_CLIENT_ID,
    CONF_CLIENT_TOKEN,
    CONF_DEFAULT_BABY_ID,
    CONF_SYNC_INTERVAL,
    DEFAULT_SYNC_INTERVAL,
    DEFAULT_MILK_AMOUNT,
    SERVICE_ADD_PEE,
    SERVICE_ADD_POO,
    SERVICE_ADD_SLEEP,
    SERVICE_ADD_WAKE_UP,
    SERVICE_ADD_PEE_AND_POO,
    SERVICE_ADD_MILK,
    SERVICE_ADD_BREASTFEEDING,
    SERVICE_ADD_BATH,
    SERVICE_ADD_WALK,
    SERVICE_FORCE_SYNC,
    ATTR_BABY_ID,
    ATTR_BABY_INDEX,
    ATTR_DATETIME,
    ATTR_MEMO,
    ATTR_AMOUNT,
    ATTR_POO_AMOUNT,
    ATTR_POO_HARDNESS,
    ATTR_POO_COLOR,
    ATTR_BREASTFEEDING_LEFT_MINUTES,
    ATTR_BREASTFEEDING_RIGHT_MINUTES,
    ATTR_BREASTFEEDING_ORDER,
    POOP_AMOUNT_MAP,
    POOP_HARDNESS_MAP,
    POOP_COLOR_MAP,
    BREASTFEEDING_ORDER_MAP,
)

_LOGGER = logging.getLogger(__name__)

# Service schemas
SERVICE_BASE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_BABY_ID): cv.string,
        vol.Optional(ATTR_BABY_INDEX): cv.positive_int,
        vol.Optional(ATTR_DATETIME): cv.string,
        vol.Optional(ATTR_MEMO, default=""): cv.string,
    }
)

SERVICE_MILK_SCHEMA = SERVICE_BASE_SCHEMA.extend(
    {
        vol.Optional(ATTR_AMOUNT, default=DEFAULT_MILK_AMOUNT): vol.All(
            vol.Coerce(float), vol.Range(min=0)
        ),
    }
)

SERVICE_BREASTFEEDING_SCHEMA = SERVICE_BASE_SCHEMA.extend(
    {
        vol.Optional(ATTR_BREASTFEEDING_LEFT_MINUTES, default=0): vol.All(
            cv.positive_int, vol.Range(min=0)
        ),
        vol.Optional(ATTR_BREASTFEEDING_RIGHT_MINUTES, default=0): vol.All(
            cv.positive_int, vol.Range(min=0)
        ),
        vol.Optional(ATTR_BREASTFEEDING_ORDER, default="unspecified"): vol.In(
            ["unspecified", "left_first", "right_first"]
        ),
        vol.Optional(ATTR_AMOUNT, default=0): vol.All(
            vol.Coerce(float), vol.Range(min=0)
        ),
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up PiyoLog from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # Initialize client
    client = PiyoLogClient(
        user_id=entry.data[CONF_USER_ID],
        client_id=entry.data[CONF_CLIENT_ID],
        client_token=entry.data[CONF_CLIENT_TOKEN],
    )

    # Set default baby if configured
    if CONF_DEFAULT_BABY_ID in entry.data and entry.data[CONF_DEFAULT_BABY_ID]:
        client._default_baby_id = entry.data[CONF_DEFAULT_BABY_ID]

    # Get sync interval from options (or use default)
    sync_interval_seconds = entry.options.get(CONF_SYNC_INTERVAL, DEFAULT_SYNC_INTERVAL)
    update_interval = timedelta(seconds=sync_interval_seconds)

    # Create coordinator for syncing
    coordinator = PiyoLogCoordinator(hass, client, update_interval)

    # Perform initial refresh to populate data (non-blocking for setup)
    try:
        await coordinator.async_config_entry_first_refresh()
    except UpdateFailed as err:
        # Allow setup to complete so services (e.g. add_sleep) are available
        # even when sync fails (e.g. 407 session/credentials issue)
        _LOGGER.warning(
            "Initial PiyoLog sync failed: %s. Integration loaded; "
            "services are available. Sync will retry on the configured interval.",
            err,
        )

    # Store client and coordinator
    hass.data[DOMAIN][entry.entry_id] = {
        "client": client,
        "coordinator": coordinator,
    }

    # Register services
    await _async_register_services(hass, client)

    # Set up options update listener
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    # Schedule periodic refreshes using track_time_interval
    async def _periodic_refresh(_now=None):
        """Trigger periodic refreshes."""
        _LOGGER.debug("Periodic sync trigger")
        try:
            await coordinator.async_request_refresh()
        except Exception as e:
            _LOGGER.error("Periodic sync failed: %s", e)

    # Register the periodic refresh and store the unsubscribe callable
    refresh_interval = timedelta(seconds=sync_interval_seconds)
    unsubscribe = async_track_time_interval(hass, _periodic_refresh, refresh_interval)

    # Register for cleanup on unload
    entry.async_on_unload(unsubscribe)

    _LOGGER.info(
        "PiyoLog integration setup complete (sync interval: %ds)", sync_interval_seconds
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Remove entry data (refresh task is cancelled via entry.async_on_unload)
    entry_data = hass.data[DOMAIN].pop(entry.entry_id)
    _LOGGER.debug("Unloading PiyoLog entry")

    # Unregister services if this was the last entry
    if not hass.data[DOMAIN]:
        for service in [
            SERVICE_ADD_PEE,
            SERVICE_ADD_POO,
            SERVICE_ADD_SLEEP,
            SERVICE_ADD_WAKE_UP,
            SERVICE_ADD_PEE_AND_POO,
            SERVICE_ADD_MILK,
            SERVICE_ADD_BREASTFEEDING,
            SERVICE_ADD_BATH,
            SERVICE_ADD_WALK,
            SERVICE_FORCE_SYNC,
        ]:
            hass.services.async_remove(DOMAIN, service)

    return True


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    _LOGGER.info("Reloading PiyoLog integration")
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)


async def _async_register_services(hass: HomeAssistant, client: PiyoLogClient):
    """Register PiyoLog services."""

    async def add_pee_service(call: ServiceCall):
        """Handle add_pee service call."""
        baby_id = call.data.get(ATTR_BABY_ID)
        baby_index = call.data.get(ATTR_BABY_INDEX)
        datetime_str = call.data.get(ATTR_DATETIME)
        memo = call.data.get(ATTR_MEMO, "")

        try:
            await hass.async_add_executor_job(
                client.add_pee, datetime_str, baby_id, baby_index, memo
            )
            _LOGGER.info("Successfully added pee event")
        except Exception as err:
            _LOGGER.error("Failed to add pee event: %s", err)
            raise

    async def add_poo_service(call: ServiceCall):
        """Handle add_poo service call."""
        baby_id = call.data.get(ATTR_BABY_ID)
        baby_index = call.data.get(ATTR_BABY_INDEX)
        datetime_str = call.data.get(ATTR_DATETIME)
        memo = call.data.get(ATTR_MEMO, "")

        # Get poo detail parameters and convert strings to enums
        poo_amount_str = call.data.get(ATTR_POO_AMOUNT)
        hardness_str = call.data.get(ATTR_POO_HARDNESS)
        color_str = call.data.get(ATTR_POO_COLOR)

        # Map string values to enum values
        poo_amount = POOP_AMOUNT_MAP.get(poo_amount_str, 0) if poo_amount_str else None
        poo_hardness = POOP_HARDNESS_MAP.get(hardness_str, 0) if hardness_str else None
        poo_color = POOP_COLOR_MAP.get(color_str, 0) if color_str else None

        try:
            await hass.async_add_executor_job(
                client.add_poop,
                poo_amount,
                poo_hardness,
                poo_color,
                datetime_str,
                baby_id,
                baby_index,
                memo,
            )
            _LOGGER.info(
                "Successfully added poo event (amount=%s, hardness=%s, color=%s)",
                poo_amount,
                poo_hardness,
                poo_color,
            )
        except Exception as err:
            _LOGGER.error("Failed to add poo event: %s", err)
            raise

    async def add_sleep_service(call: ServiceCall):
        """Handle add_sleep service call."""
        baby_id = call.data.get(ATTR_BABY_ID)
        baby_index = call.data.get(ATTR_BABY_INDEX)
        datetime_str = call.data.get(ATTR_DATETIME)
        memo = call.data.get(ATTR_MEMO, "")

        try:
            await hass.async_add_executor_job(
                client.add_sleep_begin, datetime_str, baby_id, baby_index, memo
            )
            _LOGGER.info("Successfully added sleep event")
        except Exception as err:
            _LOGGER.error("Failed to add sleep event: %s", err)
            raise

    async def add_wake_up_service(call: ServiceCall):
        """Handle add_wake_up service call."""
        baby_id = call.data.get(ATTR_BABY_ID)
        baby_index = call.data.get(ATTR_BABY_INDEX)
        datetime_str = call.data.get(ATTR_DATETIME)
        memo = call.data.get(ATTR_MEMO, "")

        try:
            await hass.async_add_executor_job(
                client.add_sleep_end, datetime_str, baby_id, baby_index, memo
            )
            _LOGGER.info("Successfully added wake up event")
        except Exception as err:
            _LOGGER.error("Failed to add wake up event: %s", err)
            raise

    async def add_bath_service(call: ServiceCall):
        """Handle add_bath service call."""
        baby_id = call.data.get(ATTR_BABY_ID)
        baby_index = call.data.get(ATTR_BABY_INDEX)
        datetime_str = call.data.get(ATTR_DATETIME)
        memo = call.data.get(ATTR_MEMO, "")

        try:
            await hass.async_add_executor_job(
                client.add_bath, datetime_str, baby_id, baby_index, memo
            )
            _LOGGER.info("Successfully added bath event")
        except Exception as err:
            _LOGGER.error("Failed to add bath event: %s", err)
            raise

    async def add_walk_service(call: ServiceCall):
        """Handle add_walk service call."""
        baby_id = call.data.get(ATTR_BABY_ID)
        baby_index = call.data.get(ATTR_BABY_INDEX)
        datetime_str = call.data.get(ATTR_DATETIME)
        memo = call.data.get(ATTR_MEMO, "")

        try:
            await hass.async_add_executor_job(
                client.add_walking, datetime_str, baby_id, baby_index, memo
            )
            _LOGGER.info("Successfully added walk event")
        except Exception as err:
            _LOGGER.error("Failed to add walk event: %s", err)
            raise

    async def add_pee_and_poo_service(call: ServiceCall):
        """Handle add_pee_and_poo service call."""
        baby_id = call.data.get(ATTR_BABY_ID)
        baby_index = call.data.get(ATTR_BABY_INDEX)
        datetime_str = call.data.get(ATTR_DATETIME)
        memo = call.data.get(ATTR_MEMO, "")

        # Get poo detail parameters and convert strings to enums
        poo_amount_str = call.data.get(ATTR_POO_AMOUNT)
        poo_hardness_str = call.data.get(ATTR_POO_HARDNESS)
        poo_color_str = call.data.get(ATTR_POO_COLOR)

        # Map string values to enum values
        poo_amount = POOP_AMOUNT_MAP.get(poo_amount_str, 0) if poo_amount_str else None
        hardness = (
            POOP_HARDNESS_MAP.get(poo_hardness_str, 0) if poo_hardness_str else None
        )
        color = POOP_COLOR_MAP.get(poo_color_str, 0) if poo_color_str else None

        try:
            # Register both PEE and POO events with same timestamp
            await hass.async_add_executor_job(
                client.add_pee, datetime_str, baby_id, baby_index, memo
            )
            await hass.async_add_executor_job(
                client.add_poop,
                poo_amount,
                hardness,
                color,
                datetime_str,
                baby_id,
                baby_index,
                memo,
            )
            _LOGGER.info(
                "Successfully added pee and poo events (poo: amount=%s, hardness=%s, color=%s)",
                poo_amount,
                hardness,
                color,
            )
        except Exception as err:
            _LOGGER.error("Failed to add pee and poo events: %s", err)
            raise

    async def add_milk_service(call: ServiceCall):
        """Handle add_milk service call."""
        baby_id = call.data.get(ATTR_BABY_ID)
        baby_index = call.data.get(ATTR_BABY_INDEX)
        datetime_str = call.data.get(ATTR_DATETIME)
        memo = call.data.get(ATTR_MEMO, "")
        amount = call.data.get(ATTR_AMOUNT, DEFAULT_MILK_AMOUNT)

        try:
            await hass.async_add_executor_job(
                client.add_milk, amount, datetime_str, baby_id, baby_index, memo
            )
            _LOGGER.info("Successfully added milk event: %sml", amount)
        except Exception as err:
            _LOGGER.error("Failed to add milk event: %s", err)
            raise

    async def add_breastfeeding_service(call: ServiceCall):
        """Handle add_breastfeeding service call."""
        baby_id = call.data.get(ATTR_BABY_ID)
        baby_index = call.data.get(ATTR_BABY_INDEX)
        datetime_str = call.data.get(ATTR_DATETIME)
        memo = call.data.get(ATTR_MEMO, "")
        left_minutes = call.data.get(ATTR_BREASTFEEDING_LEFT_MINUTES, 0)
        right_minutes = call.data.get(ATTR_BREASTFEEDING_RIGHT_MINUTES, 0)
        order_str = call.data.get(ATTR_BREASTFEEDING_ORDER, "unspecified")
        amount = call.data.get(ATTR_AMOUNT, 0)

        # Map string value to enum value
        order = BREASTFEEDING_ORDER_MAP.get(order_str, BreastfeedingOrder.UNSPECIFIED)

        try:
            await hass.async_add_executor_job(
                client.add_breastfeeding,
                left_minutes,
                right_minutes,
                order,
                amount,
                datetime_str,
                baby_id,
                baby_index,
                memo,
            )
            log_msg = f"Successfully added breastfeeding event: L={left_minutes}min R={right_minutes}min"
            if amount > 0:
                log_msg += f" Amount={amount}ml"
            _LOGGER.info(log_msg)
        except Exception as err:
            _LOGGER.error("Failed to add breastfeeding event: %s", err)
            raise

    # Register services
    hass.services.async_register(
        DOMAIN, SERVICE_ADD_PEE, add_pee_service, schema=SERVICE_BASE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_ADD_POO, add_poo_service, schema=SERVICE_BASE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_ADD_SLEEP, add_sleep_service, schema=SERVICE_BASE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_ADD_WAKE_UP, add_wake_up_service, schema=SERVICE_BASE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_ADD_PEE_AND_POO,
        add_pee_and_poo_service,
        schema=SERVICE_BASE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_ADD_MILK, add_milk_service, schema=SERVICE_MILK_SCHEMA
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_ADD_BREASTFEEDING,
        add_breastfeeding_service,
        schema=SERVICE_BREASTFEEDING_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_ADD_BATH, add_bath_service, schema=SERVICE_BASE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_ADD_WALK, add_walk_service, schema=SERVICE_BASE_SCHEMA
    )

    # Diagnostic service to manually trigger sync
    async def force_sync_service(call: ServiceCall):
        """Handle force_sync service call."""
        _LOGGER.info("Manual sync triggered via service call")
        entry_id = list(hass.data[DOMAIN].keys())[0]  # Get first entry
        coordinator = hass.data[DOMAIN][entry_id]["coordinator"]
        await coordinator.async_request_refresh()
        _LOGGER.info("Manual sync completed")

    hass.services.async_register(DOMAIN, SERVICE_FORCE_SYNC, force_sync_service)

    _LOGGER.info("PiyoLog services registered successfully")

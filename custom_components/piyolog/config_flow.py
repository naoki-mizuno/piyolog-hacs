"""Config flow for PiyoLog integration."""

import logging
from typing import Any, Dict, Optional

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.translation import async_get_translations

from .const import (
    DOMAIN,
    CONF_USER_ID,
    CONF_CLIENT_ID,
    CONF_CLIENT_TOKEN,
    CONF_DEFAULT_BABY_ID,
    CONF_SYNC_INTERVAL,
    DEFAULT_SYNC_INTERVAL,
    MIN_SYNC_INTERVAL,
    MAX_SYNC_INTERVAL,
)
from .client import PiyoLogClient

_LOGGER = logging.getLogger(__name__)


def _auth_method_schema(translations: dict) -> vol.Schema:
    """Build user step schema with translated auth_method option labels."""
    create_new = "Create new account and link to existing"
    use_existing = "Use existing credentials"
    if translations:
        # HA flattens with prefix component.{domain}.config.
        prefix = f"component.{DOMAIN}.config."
        create_new = translations.get(
            f"{prefix}step.user.options.auth_method.create_new", create_new
        )
        use_existing = translations.get(
            f"{prefix}step.user.options.auth_method.use_existing", use_existing
        )
    return vol.Schema(
        {
            vol.Required("auth_method", default="create_new"): vol.In(
                {"create_new": create_new, "use_existing": use_existing}
            ),
        }
    )


STEP_CREATE_DATA_SCHEMA = vol.Schema(
    {
        vol.Required("device_name", default="Home Assistant"): str,
    }
)

STEP_LINK_DATA_SCHEMA = vol.Schema(
    {
        vol.Required("other_user_id"): str,
        vol.Required("share_code"): str,
    }
)

STEP_EXISTING_DATA_SCHEMA = vol.Schema(
    {
        vol.Required("user_id"): str,
        vol.Required("client_id"): cv.positive_int,
        vol.Required("client_token"): str,
    }
)


class PiyoLogConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for PiyoLog."""

    VERSION = 1

    def __init__(self):
        """Initialize the config flow."""
        self._client = None
        self._device_name = None
        self._auth_method = None

    async def async_step_user(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle the initial step - choose authentication method."""
        if user_input is not None:
            self._auth_method = user_input["auth_method"]

            if self._auth_method == "create_new":
                return await self.async_step_create()
            else:
                return await self.async_step_existing()

        try:
            translations = await async_get_translations(
                self.hass,
                self.hass.config.language,
                "config",
                integrations=[DOMAIN],
            )
        except Exception:  # noqa: BLE001
            translations = {}
        return self.async_show_form(
            step_id="user",
            data_schema=_auth_method_schema(translations),
        )

    async def async_step_create(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle creating a new user."""
        errors = {}

        if user_input is not None:
            device_name = user_input["device_name"]

            try:
                # Create new user (run in executor to avoid blocking)
                client = await self.hass.async_add_executor_job(
                    self._create_user, device_name
                )

                self._client = client
                self._device_name = device_name

                # Move to link account step
                return await self.async_step_link()

            except Exception as err:
                _LOGGER.error("Failed to create user: %s", err)
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="create",
            data_schema=STEP_CREATE_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_existing(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle using existing credentials."""
        errors = {}

        if user_input is not None:
            user_id = user_input["user_id"]
            client_id = user_input["client_id"]
            client_token = user_input["client_token"]

            try:
                # Create client with existing credentials
                client = PiyoLogClient(
                    user_id=user_id,
                    client_id=client_id,
                    client_token=client_token,
                )

                # Test credentials by syncing
                await self.hass.async_add_executor_job(client.sync, 1, 1)

                self._client = client
                self._device_name = f"Existing ({user_id[:8]}...)"

                # Get baby list
                babies = await self.hass.async_add_executor_job(self._client.get_babies)

                if babies:
                    # Let user select default baby
                    return await self.async_step_select_baby()
                else:
                    # No babies yet, just finish
                    return self._create_entry()

            except Exception as err:
                _LOGGER.error(
                    "Failed to authenticate with existing credentials: %s", err
                )
                errors["base"] = "invalid_auth"

        return self.async_show_form(
            step_id="existing",
            data_schema=STEP_EXISTING_DATA_SCHEMA,
            errors=errors,
        )

    def _create_user(self, device_name: str) -> PiyoLogClient:
        """Create a new PiyoLog user (runs in executor)."""
        client = PiyoLogClient()
        client.create_new_user(device_name)
        return client

    async def async_step_link(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle linking to an existing account."""
        errors = {}

        if user_input is not None:
            other_user_id = user_input["other_user_id"]
            share_code = user_input["share_code"]

            try:
                # Link account
                await self.hass.async_add_executor_job(
                    self._link_account, other_user_id, share_code
                )

                # Get baby list
                babies = await self.hass.async_add_executor_job(self._client.get_babies)

                if babies:
                    # Let user select default baby
                    return await self.async_step_select_baby()
                else:
                    # No babies yet, just finish
                    return self._create_entry()

            except Exception as err:
                _LOGGER.error("Failed to link account: %s", err)
                errors["base"] = "invalid_auth"

        return self.async_show_form(
            step_id="link",
            data_schema=STEP_LINK_DATA_SCHEMA,
            errors=errors,
            description_placeholders={
                "info": (
                    "Enter the User ID and Share Code from your PiyoLog app. "
                    "To get these: Open PiyoLog app → Settings → Share → Issue Code"
                ),
            },
        )

    def _link_account(self, other_user_id: str, share_code: str):
        """Link to existing account (runs in executor)."""
        self._client.link_account(other_user_id, share_code, self._device_name)

    async def async_step_select_baby(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle baby selection."""
        babies = self._client.get_babies()

        if user_input is not None:
            # Store selected baby
            selected_index = int(user_input["baby_index"])
            self._client.set_default_baby(baby_index=selected_index)

            return self._create_entry()

        # Build baby selection schema
        baby_options = {
            str(i): f"{b.get('nickname', 'Unnamed')} (ID: {b['baby_id']})"
            for i, b in enumerate(babies)
        }

        return self.async_show_form(
            step_id="select_baby",
            data_schema=vol.Schema(
                {
                    vol.Required("baby_index", default="0"): vol.In(baby_options),
                }
            ),
            description_placeholders={
                "info": "Select the default baby for this integration",
            },
        )

    def _create_entry(self) -> FlowResult:
        """Create the config entry."""
        return self.async_create_entry(
            title=f"PiyoLog ({self._device_name})",
            data={
                CONF_USER_ID: self._client.user_id,
                CONF_CLIENT_ID: self._client.client_id,
                CONF_CLIENT_TOKEN: self._client.client_token,
                CONF_DEFAULT_BABY_ID: self._client._default_baby_id,
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get the options flow for this handler."""
        return PiyoLogOptionsFlowHandler()


class PiyoLogOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for PiyoLog."""

    async def async_step_init(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_SYNC_INTERVAL,
                        default=self.config_entry.options.get(
                            CONF_SYNC_INTERVAL, DEFAULT_SYNC_INTERVAL
                        ),
                    ): vol.All(
                        cv.positive_int,
                        vol.Range(min=MIN_SYNC_INTERVAL, max=MAX_SYNC_INTERVAL),
                    ),
                }
            ),
        )

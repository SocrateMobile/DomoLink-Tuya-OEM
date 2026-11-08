"""Config Flow for DomoLink Tuya OEM Multi-Brand Integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_BRAND,
    CONF_CLIENT_ID,
    CONF_ENDPOINT,
    CONF_SCHEMA,
    CONF_SECRET,
    DEFAULT_ENDPOINT,
    DOMAIN,
    ENDPOINTS,
    OEM_PROFILES,
)
from .tuya_api import TuyaOEMAuthError, TuyaOEMClient, TuyaOEMError

_LOGGER = logging.getLogger(__name__)


class TuyaOEMConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for DomoLink Tuya OEM."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            brand = user_input[CONF_BRAND]
            profile = OEM_PROFILES.get(brand, {})
            client_id = user_input[CONF_CLIENT_ID].strip()
            secret = user_input[CONF_SECRET].strip()
            endpoint = user_input.get(CONF_ENDPOINT, DEFAULT_ENDPOINT)
            schema = profile.get("schema", "thanksapp")

            session = async_get_clientsession(self.hass)
            client = TuyaOEMClient(
                endpoint=endpoint,
                client_id=client_id,
                secret=secret,
                schema=schema,
                session=session,
            )

            try:
                # Test credentials by requesting a token directly from Tuya Cloud
                await client.get_access_token()
            except TuyaOEMAuthError as err:
                _LOGGER.warning("Authentication failed: %s", err)
                errors["base"] = "invalid_auth"
            except TuyaOEMError as err:
                _LOGGER.error("Cannot connect to Tuya Cloud: %s", err)
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error in Tuya OEM config flow")
                errors["base"] = "unknown"
            else:
                unique_id = f"{brand}_{client_id}"
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()

                title = f"{profile['name']} ({client_id[:6]}...)"
                config_data = {
                    CONF_BRAND: brand,
                    CONF_CLIENT_ID: client_id,
                    CONF_SECRET: secret,
                    CONF_ENDPOINT: endpoint,
                    CONF_SCHEMA: schema,
                }
                return self.async_create_entry(title=title, data=config_data)

        brand_options = {key: profile["name"] for key, profile in OEM_PROFILES.items()}

        schema = vol.Schema(
            {
                vol.Required(CONF_BRAND, default="thanks"): vol.In(brand_options),
                vol.Required(CONF_CLIENT_ID): str,
                vol.Required(CONF_SECRET): str,
                vol.Optional(CONF_ENDPOINT, default=DEFAULT_ENDPOINT): vol.In(ENDPOINTS.values()),
            }
        )

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

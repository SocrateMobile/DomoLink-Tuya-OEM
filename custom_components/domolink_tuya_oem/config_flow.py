"""Config Flow for DomoLink Tuya OEM Multi-Brand Integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_BRAND,
    CONF_CLIENT_ID,
    CONF_COUNTRY_CODE,
    CONF_ENDPOINT,
    CONF_PASSWORD,
    CONF_SCHEMA,
    CONF_SECRET,
    CONF_USERNAME,
    DEFAULT_COUNTRY_CODE,
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

    def __init__(self) -> None:
        """Initialize flow."""
        self._brand_data: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            brand = user_input[CONF_BRAND]
            profile = OEM_PROFILES.get(brand, {})

            if brand == "custom":
                self._brand_data = user_input
                return await self.async_step_custom_oem()

            # Prepare client to validate credentials
            session = async_get_clientsession(self.hass)
            client = TuyaOEMClient(
                endpoint=user_input.get(CONF_ENDPOINT, DEFAULT_ENDPOINT),
                client_id=profile["client_id"],
                secret=profile["secret"],
                schema=profile["schema"],
                username=user_input[CONF_USERNAME],
                password=user_input[CONF_PASSWORD],
                country_code=user_input.get(CONF_COUNTRY_CODE, DEFAULT_COUNTRY_CODE),
                session=session,
            )

            try:
                await client.login()
            except TuyaOEMAuthError:
                errors["base"] = "invalid_auth"
            except TuyaOEMError:
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception during Tuya OEM login")
                errors["base"] = "unknown"
            else:
                unique_id = f"{brand}_{user_input[CONF_USERNAME].lower()}"
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()

                title = f"{profile['name']} ({user_input[CONF_USERNAME]})"
                config_data = {
                    **user_input,
                    CONF_SCHEMA: profile["schema"],
                    CONF_CLIENT_ID: profile["client_id"],
                    CONF_SECRET: profile["secret"],
                }
                return self.async_create_entry(title=title, data=config_data)

        # Brand choices for select dropdown
        brand_options = {key: profile["name"] for key, profile in OEM_PROFILES.items()}

        schema = vol.Schema(
            {
                vol.Required(CONF_BRAND, default="thanks"): vol.In(brand_options),
                vol.Required(CONF_USERNAME): str,
                vol.Required(CONF_PASSWORD): str,
                vol.Optional(CONF_COUNTRY_CODE, default=DEFAULT_COUNTRY_CODE): str,
                vol.Optional(CONF_ENDPOINT, default=DEFAULT_ENDPOINT): vol.In(ENDPOINTS.values()),
            }
        )

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_custom_oem(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle custom OEM keys entry."""
        errors: dict[str, str] = {}

        if user_input is not None:
            combined_data = {**self._brand_data, **user_input}
            session = async_get_clientsession(self.hass)
            client = TuyaOEMClient(
                endpoint=combined_data.get(CONF_ENDPOINT, DEFAULT_ENDPOINT),
                client_id=user_input[CONF_CLIENT_ID],
                secret=user_input[CONF_SECRET],
                schema=user_input[CONF_SCHEMA],
                username=combined_data[CONF_USERNAME],
                password=combined_data[CONF_PASSWORD],
                country_code=combined_data.get(CONF_COUNTRY_CODE, DEFAULT_COUNTRY_CODE),
                session=session,
            )

            try:
                await client.login()
            except TuyaOEMAuthError:
                errors["base"] = "invalid_auth"
            except TuyaOEMError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception during Custom OEM login")
                errors["base"] = "unknown"
            else:
                unique_id = f"custom_{user_input[CONF_SCHEMA]}_{combined_data[CONF_USERNAME].lower()}"
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()

                title = f"OEM {user_input[CONF_SCHEMA]} ({combined_data[CONF_USERNAME]})"
                return self.async_create_entry(title=title, data=combined_data)

        schema = vol.Schema(
            {
                vol.Required(CONF_SCHEMA): str,
                vol.Required(CONF_CLIENT_ID): str,
                vol.Required(CONF_SECRET): str,
            }
        )

        return self.async_show_form(step_id="custom_oem", data_schema=schema, errors=errors)

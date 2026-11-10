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
    CONF_COUNTRY_CODE,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_ENDPOINT,
    CONF_IP_ADDRESS,
    CONF_LOCAL_KEY,
    CONF_MODE,
    CONF_PASSWORD,
    CONF_PROTOCOL_VERSION,
    CONF_SCHEMA,
    CONF_SECRET,
    CONF_USERNAME,
    DEFAULT_COUNTRY_CODE,
    DEFAULT_ENDPOINT,
    DOMAIN,
    ENDPOINTS,
    MODE_CLOUD,
    MODE_LOCAL,
    MODE_MOBILE,
    OEM_PROFILES,
)
from .tuya_api import (
    TuyaOEMAuthError,
    TuyaOEMBrandRestrictedError,
    TuyaOEMClient,
    TuyaOEMError,
    TuyaOEMMobileClient,
)
from .tuya_local import TuyaLocalDevice, async_discover_devices

_LOGGER = logging.getLogger(__name__)


class TuyaOEMConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for DomoLink Tuya OEM."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize flow."""
        self._discovered_devices: dict[str, dict[str, Any]] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the initial mode selection step."""
        if user_input is not None:
            if user_input[CONF_MODE] == MODE_MOBILE:
                return await self.async_step_mobile()
            if user_input[CONF_MODE] == MODE_LOCAL:
                return await self.async_step_local_discovery()
            return await self.async_step_cloud()

        schema = vol.Schema(
            {
                vol.Required(CONF_MODE, default=MODE_MOBILE): vol.In(
                    {
                        MODE_MOBILE: "Connexion Mobile Smartphone (Recommandé - Email + Mot de passe direct, sans compte dev)",
                        MODE_LOCAL: "Contrôle Local LAN (100% hors-ligne, découverte réseau & local_key)",
                        MODE_CLOUD: "Mode Cloud Tuya Developer (iot.tuya.com)",
                    }
                ),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    async def async_step_mobile(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle Mobile smartphone login."""
        errors: dict[str, str] = {}

        if user_input is not None:
            brand = user_input[CONF_BRAND]
            profile = OEM_PROFILES.get(brand, {})
            username = user_input[CONF_USERNAME].strip()
            password = user_input[CONF_PASSWORD]
            country_code = user_input.get(CONF_COUNTRY_CODE, DEFAULT_COUNTRY_CODE).strip()

            session = async_get_clientsession(self.hass)
            client = TuyaOEMMobileClient(
                brand_key=brand,
                username=username,
                password=password,
                country_code=country_code,
                session=session,
            )

            try:
                login_res = await client.login()
                # Test device discovery and local keys extraction
                devices = await client.get_devices()
                _LOGGER.info("Mobile login OK: %d appareil(s) découverts pour %s", len(devices), username)
            except TuyaOEMBrandRestrictedError as err:
                _LOGGER.warning("OEM brand restricted mobile access: %s", err)
                errors["base"] = "brand_restricted"
            except TuyaOEMAuthError:
                errors["base"] = "invalid_auth"
            except TuyaOEMError:
                errors["base"] = "cannot_connect"
            except Exception as err:
                _LOGGER.exception("Unexpected exception during mobile login: %s", err)
                errors["base"] = "unknown"
            else:
                unique_id = f"mobile_{brand}_{username.lower()}"
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()

                title = f"{profile.get('name', brand.upper())} Mobile ({username})"
                config_data = {
                    CONF_MODE: MODE_MOBILE,
                    CONF_BRAND: brand,
                    CONF_USERNAME: username,
                    CONF_PASSWORD: password,
                    CONF_COUNTRY_CODE: country_code,
                    "uid": login_res.get("uid"),
                }
                return self.async_create_entry(title=title, data=config_data)

        brand_options = {key: profile["name"] for key, profile in OEM_PROFILES.items()}

        schema = vol.Schema(
            {
                vol.Required(CONF_BRAND, default="smartlife"): vol.In(brand_options),
                vol.Required(CONF_USERNAME): str,
                vol.Required(CONF_PASSWORD): str,
                vol.Optional(CONF_COUNTRY_CODE, default=DEFAULT_COUNTRY_CODE): str,
            }
        )

        return self.async_show_form(step_id="mobile", data_schema=schema, errors=errors)

    async def async_step_local_discovery(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Scan local network and configure a discovered Tuya device."""
        errors: dict[str, str] = {}

        if not self._discovered_devices:
            self._discovered_devices = await async_discover_devices(timeout=3.0)

        if user_input is not None:
            dev_id = user_input[CONF_DEVICE_ID]
            dev_info = self._discovered_devices.get(dev_id, {})
            ip = dev_info.get("ip", user_input.get(CONF_IP_ADDRESS, ""))
            version = dev_info.get("version", "3.3")
            local_key = user_input[CONF_LOCAL_KEY].strip()
            brand = user_input.get(CONF_BRAND, "thanks")
            dev_name = user_input.get(CONF_DEVICE_NAME, f"Appareil {ip}")

            # Verify local connectivity
            test_dev = TuyaLocalDevice(device_id=dev_id, ip=ip, local_key=local_key, version=version)
            try:
                await test_dev.async_poll_status()
            except Exception as err:
                _LOGGER.warning("Could not poll device locally: %s", err)

            unique_id = f"local_{dev_id}"
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            profile = OEM_PROFILES.get(brand, {})
            brand_name = profile.get("name", brand.upper())
            title = f"{dev_name} ({brand_name})"

            config_data = {
                CONF_MODE: MODE_LOCAL,
                CONF_BRAND: brand,
                CONF_DEVICE_ID: dev_id,
                CONF_IP_ADDRESS: ip,
                CONF_LOCAL_KEY: local_key,
                CONF_PROTOCOL_VERSION: version,
                CONF_DEVICE_NAME: dev_name,
            }
            return self.async_create_entry(title=title, data=config_data)

        # Build dropdown options of discovered devices
        dev_options = {
            dev_id: f"{info['ip']} - ID: {dev_id} (Tuya v{info.get('version', '3.3')})"
            for dev_id, info in self._discovered_devices.items()
        }

        # If none found, allow manual entry
        if not dev_options:
            dev_options["manual"] = "Saisie manuelle (aucun appareil détecté automatiquement)"

        brand_options = {key: profile["name"] for key, profile in OEM_PROFILES.items()}

        schema_fields: dict[Any, Any] = {
            vol.Required(CONF_DEVICE_ID): vol.In(dev_options),
            vol.Required(CONF_LOCAL_KEY): str,
            vol.Required(CONF_DEVICE_NAME, default="Mon Appareil GiFi"): str,
            vol.Required(CONF_BRAND, default="thanks"): vol.In(brand_options),
        }

        return self.async_show_form(
            step_id="local_discovery",
            data_schema=vol.Schema(schema_fields),
            errors=errors,
            description_placeholders={"count": str(len(self._discovered_devices))},
        )

    async def async_step_cloud(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle Cloud Tuya developer credentials."""
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
                await client.get_access_token()
            except TuyaOEMAuthError:
                errors["base"] = "invalid_auth"
            except TuyaOEMError:
                errors["base"] = "cannot_connect"
            except Exception:
                errors["base"] = "unknown"
            else:
                unique_id = f"cloud_{brand}_{client_id}"
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()

                title = f"{profile['name']} Cloud ({client_id[:6]}...)"
                config_data = {
                    CONF_MODE: MODE_CLOUD,
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

        return self.async_show_form(step_id="cloud", data_schema=schema, errors=errors)

"""The DomoLink Tuya OEM Multi-Brand Integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
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
    DOMAIN,
    MODE_LOCAL,
    MODE_MOBILE,
    OEM_PROFILES,
    PLATFORMS,
)
from .coordinator import TuyaOEMDataCoordinator
from .tuya_api import (
    TuyaOEMAuthError,
    TuyaOEMClient,
    TuyaOEMError,
    TuyaOEMMobileClient,
)
from .tuya_local import TuyaLocalDevice

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up DomoLink Tuya OEM from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    data = entry.data
    mode = data.get(CONF_MODE, MODE_LOCAL)
    brand_key = data.get(CONF_BRAND, "thanks")
    profile = OEM_PROFILES.get(brand_key, {})
    brand_name = profile.get("name", brand_key.upper())

    # --- 1. MOBILE SMARTPHONE EMULATION SETUP ---
    if mode == MODE_MOBILE:
        username = data[CONF_USERNAME]
        password = data[CONF_PASSWORD]
        country_code = data.get(CONF_COUNTRY_CODE, DEFAULT_COUNTRY_CODE)

        session = async_get_clientsession(hass)
        mobile_client = TuyaOEMMobileClient(
            brand_key=brand_key,
            username=username,
            password=password,
            country_code=country_code,
            session=session,
        )

        coordinator = TuyaOEMDataCoordinator(
            hass,
            brand_name=brand_name,
            mobile_client=mobile_client,
        )

        try:
            await coordinator.async_config_entry_first_refresh()
        except TuyaOEMAuthError as err:
            _LOGGER.error("Erreur d'authentification mobile pour %s (%s): %s", brand_name, username, err)
            return False
        except TuyaOEMError as err:
            _LOGGER.warning("Impossible de joindre la passerelle mobile Tuya pour %s (%s): %s", brand_name, username, err)
            raise ConfigEntryNotReady from err

        hass.data[DOMAIN][entry.entry_id] = {
            "coordinator": coordinator,
            "mobile_client": mobile_client,
            "brand_name": brand_name,
            "mode": MODE_MOBILE,
        }

        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        return True

    # --- 2. LOCAL LAN SETUP ---
    if mode == MODE_LOCAL:
        dev_id = data[CONF_DEVICE_ID]
        ip = data[CONF_IP_ADDRESS]
        local_key = data[CONF_LOCAL_KEY]
        version = data.get(CONF_PROTOCOL_VERSION, "3.3")
        dev_name = data.get(CONF_DEVICE_NAME, f"{brand_name} ({ip})")

        local_device = TuyaLocalDevice(
            device_id=dev_id,
            ip=ip,
            local_key=local_key,
            version=version,
        )

        coordinator = TuyaOEMDataCoordinator(
            hass,
            brand_name=brand_name,
            local_device=local_device,
            device_meta={"name": dev_name, "product_name": f"{brand_name} Local"},
        )

        await coordinator.async_config_entry_first_refresh()

        hass.data[DOMAIN][entry.entry_id] = {
            "coordinator": coordinator,
            "brand_name": brand_name,
            "mode": MODE_LOCAL,
        }

        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        return True

    # --- 2. CLOUD SETUP ---
    client_id = data[CONF_CLIENT_ID]
    secret = data[CONF_SECRET]
    endpoint = data.get(CONF_ENDPOINT, "https://openapi.tuyaeu.com")
    schema = data.get(CONF_SCHEMA, profile.get("schema", "thanksapp"))

    session = async_get_clientsession(hass)
    client = TuyaOEMClient(
        endpoint=endpoint,
        client_id=client_id,
        secret=secret,
        schema=schema,
        session=session,
    )

    coordinator = TuyaOEMDataCoordinator(
        hass,
        brand_name=brand_name,
        client=client,
    )

    try:
        await coordinator.async_config_entry_first_refresh()
    except TuyaOEMAuthError as err:
        _LOGGER.error("Erreur d'authentification pour %s (%s): %s", brand_name, client_id, err)
        return False
    except TuyaOEMError as err:
        _LOGGER.warning("Impossible de joindre le Cloud Tuya pour %s (%s): %s", brand_name, client_id, err)
        raise ConfigEntryNotReady from err

    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "client": client,
        "brand_name": brand_name,
        "mode": "cloud",
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        entry_data = hass.data[DOMAIN].pop(entry.entry_id, None)
        if entry_data:
            if "client" in entry_data and entry_data["client"]:
                await entry_data["client"].close()
            if "mobile_client" in entry_data and entry_data["mobile_client"]:
                await entry_data["mobile_client"].close()

    return unload_ok

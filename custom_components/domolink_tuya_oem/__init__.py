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
    CONF_ENDPOINT,
    CONF_SCHEMA,
    CONF_SECRET,
    DOMAIN,
    OEM_PROFILES,
    PLATFORMS,
)
from .coordinator import TuyaOEMDataCoordinator
from .tuya_api import TuyaOEMAuthError, TuyaOEMClient, TuyaOEMError

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up DomoLink Tuya OEM from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    data = entry.data
    brand_key = data.get(CONF_BRAND, "thanks")
    profile = OEM_PROFILES.get(brand_key, {})

    brand_name = profile.get("name", brand_key.upper())
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

    coordinator = TuyaOEMDataCoordinator(hass, client, brand_name)

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
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        entry_data = hass.data[DOMAIN].pop(entry.entry_id, None)
        if entry_data and "client" in entry_data:
            await entry_data["client"].close()

    return unload_ok

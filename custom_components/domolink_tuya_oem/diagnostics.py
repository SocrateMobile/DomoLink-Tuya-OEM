"""Diagnostics support for DomoLink Tuya OEM."""
from __future__ import annotations

from typing import Any

try:
    from homeassistant.components.diagnostics import async_redact_data
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
except ImportError:
    def async_redact_data(data: dict[str, Any], to_redact: set[str]) -> dict[str, Any]:
        """Fallback redactor when running outside HA."""
        return {k: ("***REDACTED***" if k in to_redact else v) for k, v in data.items()}
    ConfigEntry = Any  # type: ignore[misc,assignment]
    HomeAssistant = Any  # type: ignore[misc,assignment]

try:
    from .const import CONF_PASSWORD, CONF_SECRET, DOMAIN
    from .coordinator import TuyaOEMDataCoordinator
except (ImportError, ValueError):
    from const import CONF_PASSWORD, CONF_SECRET, DOMAIN
    TuyaOEMDataCoordinator = Any  # type: ignore[misc,assignment]

TO_REDACT = {
    CONF_PASSWORD,
    CONF_SECRET,
    "local_key",
    "access_token",
    "refresh_token",
    "sid",
    "uid",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    entry_data = hass.data[DOMAIN].get(entry.entry_id, {})
    coordinator: TuyaOEMDataCoordinator | None = entry_data.get("coordinator")

    devices_data: dict[str, Any] = {}
    lan_info_data: dict[str, Any] = {}
    if coordinator:
        devices_data = {
            dev_id: {
                "name": dev.get("name"),
                "product_name": dev.get("product_name"),
                "category": dev.get("category"),
                "online": dev.get("online"),
                "lan_active": dev.get("lan_active"),
                "ip": dev.get("ip"),
                "device_type": dev.get("device_type"),
                "dps_keys": list(dev.get("dps_status", {}).keys()),
                "raw_dps": dev.get("dps_status", {}),
            }
            for dev_id, dev in coordinator.data.items()
        }
        if hasattr(coordinator, "lan_resolver"):
            lan_info_data = {
                dev_id: coordinator.lan_resolver.get_device_lan_info(dev_id)
                for dev_id in coordinator.data
            }

    diag = {
        "entry": {
            "entry_id": entry.entry_id,
            "version": entry.version,
            "domain": entry.domain,
            "title": entry.title,
            "data": dict(entry.data),
        },
        "brand_name": entry_data.get("brand_name"),
        "mode": entry_data.get("mode"),
        "devices_count": len(devices_data),
        "devices": devices_data,
        "lan_status": lan_info_data,
    }

    return async_redact_data(diag, TO_REDACT)

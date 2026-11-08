"""DataUpdateCoordinator for DomoLink Tuya OEM."""
from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DEFAULT_SCAN_INTERVAL, DOMAIN
from .tuya_api import TuyaOEMClient, TuyaOEMError

_LOGGER = logging.getLogger(__name__)


class TuyaOEMDataCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Coordinator to manage Tuya OEM device data updates."""

    def __init__(self, hass: HomeAssistant, client: TuyaOEMClient, brand_name: str) -> None:
        """Initialize coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{brand_name}",
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.client = client
        self.brand_name = brand_name
        self.devices: dict[str, dict[str, Any]] = {}

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        """Fetch latest device states from Tuya OEM cloud."""
        try:
            device_list = await self.client.get_devices()
            devices_map: dict[str, dict[str, Any]] = {}

            for dev in device_list:
                dev_id = dev.get("id") or dev.get("devId") or dev.get("device_id")
                if not dev_id:
                    continue

                # Fetch updated status if available
                status_list = await self.client.get_device_status(dev_id)
                # Convert list of {"code": "...", "value": ...} to a dict for easy entity lookups
                status_dict: dict[str, Any] = {}
                for item in status_list:
                    if isinstance(item, dict) and "code" in item:
                        status_dict[item["code"]] = item.get("value")

                dev["dps_status"] = status_dict
                devices_map[dev_id] = dev

            self.devices = devices_map
            return devices_map
        except TuyaOEMError as err:
            raise UpdateFailed(f"Erreur de communication avec le Cloud Tuya {self.brand_name}: {err}") from err

    async def async_send_command(self, device_id: str, commands: list[dict[str, Any]]) -> bool:
        """Send command and update local cached state optimistically."""
        success = await self.client.send_command(device_id, commands)
        if success and device_id in self.data:
            # Optimistic update
            dps = self.data[device_id].setdefault("dps_status", {})
            for cmd in commands:
                dps[cmd["code"]] = cmd["value"]
            self.async_set_updated_data(self.data)
        return success

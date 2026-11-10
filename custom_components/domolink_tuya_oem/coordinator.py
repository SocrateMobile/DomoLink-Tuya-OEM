"""DataUpdateCoordinator for DomoLink Tuya OEM."""
from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DEFAULT_SCAN_INTERVAL, DOMAIN
from .tuya_api import TuyaOEMClient, TuyaOEMError, TuyaOEMMobileClient
from .tuya_local import TuyaLocalDevice

_LOGGER = logging.getLogger(__name__)


class TuyaOEMDataCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Coordinator to manage Tuya OEM device data updates (Local, Mobile or Cloud)."""

    def __init__(
        self,
        hass: HomeAssistant,
        brand_name: str,
        client: TuyaOEMClient | None = None,
        mobile_client: TuyaOEMMobileClient | None = None,
        local_device: TuyaLocalDevice | None = None,
        device_meta: dict[str, Any] | None = None,
    ) -> None:
        """Initialize coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{brand_name}",
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.brand_name = brand_name
        self.client = client
        self.mobile_client = mobile_client
        self.local_device = local_device
        self.device_meta = device_meta or {}
        self.devices: dict[str, dict[str, Any]] = {}
        self.local_devices: dict[str, TuyaLocalDevice] = {}

        if local_device:
            self.local_devices[local_device.device_id] = local_device

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        """Fetch latest device states (Local LAN, Mobile Cloud or Developer Cloud)."""
        # --- 1. SINGLE LOCAL LAN MODE ---
        if self.local_device and not self.mobile_client and not self.client:
            try:
                dps = await self.local_device.async_poll_status()
                dev_id = self.local_device.device_id
                dev_data = {
                    "id": dev_id,
                    "name": self.device_meta.get("name", f"Appareil {dev_id[:6]}"),
                    "category": self.device_meta.get("category", ""),
                    "product_name": self.device_meta.get("product_name", f"{self.brand_name} (Local)"),
                    "dps_status": dps,
                }
                self.devices = {dev_id: dev_data}
                return self.devices
            except Exception as err:
                raise UpdateFailed(f"Erreur de communication locale LAN avec {self.local_device.ip}: {err}") from err

        # --- 2. MOBILE EMULATION MODE (Smart Life, Thank's, Lidl...) ---
        if self.mobile_client:
            try:
                device_list = await self.mobile_client.get_devices()
                devices_map: dict[str, dict[str, Any]] = {}

                for dev in device_list:
                    dev_id = dev.get("id") or dev.get("devId") or dev.get("device_id")
                    if not dev_id:
                        continue

                    # Register or update local device if local_key and IP are available
                    local_key = dev.get("local_key")
                    ip = dev.get("ip")
                    if local_key and ip and dev_id not in self.local_devices:
                        self.local_devices[dev_id] = TuyaLocalDevice(
                            device_id=dev_id,
                            ip=ip,
                            local_key=local_key,
                        )

                    # Poll status: prioritize fast local LAN poll, fallback to mobile cloud
                    status_dict: dict[str, Any] = {}
                    polled_locally = False

                    if dev_id in self.local_devices:
                        try:
                            status_dict = await self.local_devices[dev_id].async_poll_status()
                            polled_locally = True
                        except Exception as local_err:
                            _LOGGER.debug("Local poll for %s failed (%s), fallback to mobile cloud", dev_id, local_err)

                    if not polled_locally:
                        try:
                            status_dict = await self.mobile_client.get_device_status(dev_id)
                        except Exception as cloud_err:
                            _LOGGER.debug("Mobile cloud status for %s failed: %s", dev_id, cloud_err)

                    if not status_dict and dev.get("dps"):
                        status_dict = dev["dps"]

                    dev["dps_status"] = status_dict
                    devices_map[dev_id] = dev

                self.devices = devices_map
                return devices_map
            except Exception as err:
                raise UpdateFailed(f"Erreur de communication mobile {self.brand_name}: {err}") from err

        # --- 3. DEVELOPER CLOUD MODE ---
        if self.client:
            try:
                device_list = await self.client.get_devices()
                devices_map: dict[str, dict[str, Any]] = {}

                for dev in device_list:
                    dev_id = dev.get("id") or dev.get("devId") or dev.get("device_id")
                    if not dev_id:
                        continue

                    status_list = await self.client.get_device_status(dev_id)
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

        return {}

    async def async_send_command(self, device_id: str, commands: list[dict[str, Any]]) -> bool:
        """Send command (prioritizing ultra-fast Local LAN, fallback to Cloud)."""
        # 1. Try local LAN execution if device is registered locally
        if device_id in self.local_devices:
            try:
                success = await self.local_devices[device_id].async_send_command(commands)
                if success:
                    if device_id in self.data:
                        dps = self.data[device_id].setdefault("dps_status", {})
                        for cmd in commands:
                            dps[str(cmd["code"])] = cmd["value"]
                        self.async_set_updated_data(self.data)
                    return True
            except Exception as err:
                _LOGGER.debug("Local command to %s failed (%s), trying cloud fallback", device_id, err)

        # 2. Try mobile client fallback
        if self.mobile_client:
            success = await self.mobile_client.send_command(device_id, commands)
            if success and device_id in self.data:
                dps = self.data[device_id].setdefault("dps_status", {})
                for cmd in commands:
                    dps[str(cmd["code"])] = cmd["value"]
                self.async_set_updated_data(self.data)
            return success

        # 3. Try developer cloud client fallback
        if self.client:
            success = await self.client.send_command(device_id, commands)
            if success and device_id in self.data:
                dps = self.data[device_id].setdefault("dps_status", {})
                for cmd in commands:
                    dps[cmd["code"]] = cmd["value"]
                self.async_set_updated_data(self.data)
            return success

        return False

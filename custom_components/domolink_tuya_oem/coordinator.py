"""DataUpdateCoordinator for DomoLink Tuya OEM."""
from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DEFAULT_SCAN_INTERVAL, DOMAIN
from .dp_registry import parse_device_capabilities
from .tuya_api import TuyaOEMClient, TuyaOEMError, TuyaOEMMobileClient
from .tuya_local import TuyaLocalDevice

_LOGGER = logging.getLogger(__name__)
STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}_overrides"


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
        self._store = Store[dict[str, Any]](hass, STORAGE_VERSION, STORAGE_KEY)
        self.overrides: dict[str, Any] = {}
        self._overrides_loaded = False

        if local_device:
            self.local_devices[local_device.device_id] = local_device

    async def _async_ensure_overrides(self) -> None:
        """Load persistent user overrides from disk."""
        if not self._overrides_loaded:
            loaded = await self._store.async_load()
            if isinstance(loaded, dict):
                self.overrides = loaded
            self._overrides_loaded = True

    async def async_save_device_override(self, device_id: str, new_overrides: dict[str, Any]) -> None:
        """Save user customization (renaming, forced type, manual IP) to persistent store."""
        await self._async_ensure_overrides()
        current = self.overrides.setdefault(device_id, {})
        current.update(new_overrides)
        await self._store.async_save(self.overrides)
        # Apply immediately
        if device_id in self.data:
            caps = parse_device_capabilities(self.data[device_id], self.overrides)
            self.data[device_id]["caps"] = caps
            self.data[device_id]["name"] = caps["name"]
            self.data[device_id]["device_type"] = caps["device_type"]
            self.async_set_updated_data(self.data)

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        """Fetch latest device states (Local LAN, Mobile Cloud or Developer Cloud)."""
        await self._async_ensure_overrides()

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
                    "online": True,
                    "lan_active": True,
                    "ip": self.local_device.ip,
                    "local_key": self.local_device.local_key.decode("utf-8") if isinstance(self.local_device.local_key, bytes) else str(self.local_device.local_key),
                }
                dev_data["caps"] = parse_device_capabilities(dev_data, self.overrides)
                dev_data["device_type"] = dev_data["caps"]["device_type"]
                dev_data["icon_url"] = dev_data["caps"]["icon_url"]
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

                    # Check for override IP
                    dev_overrides = self.overrides.get(dev_id, {})
                    if dev_overrides.get("ip"):
                        dev["ip"] = dev_overrides["ip"]

                    # Register or update local device if local_key and IP are available
                    local_key = dev.get("local_key")
                    ip = dev.get("ip")
                    if local_key and ip and dev_id not in self.local_devices:
                        try:
                            self.local_devices[dev_id] = TuyaLocalDevice(
                                device_id=dev_id,
                                ip=ip,
                                local_key=local_key,
                            )
                        except Exception as e:
                            _LOGGER.debug("Could not init local client for %s: %s", dev_id, e)

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
                    dev["lan_active"] = polled_locally

                    # Resolve online state
                    if polled_locally:
                        dev["online"] = True
                    else:
                        dev["online"] = bool(dev.get("online", True))

                    # Capability and classification enrichment
                    caps = parse_device_capabilities(dev, self.overrides)
                    dev["caps"] = caps
                    dev["device_type"] = caps["device_type"]
                    dev["icon_url"] = caps["icon_url"]
                    dev["name"] = caps["name"]

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
                    dev["lan_active"] = False
                    dev["online"] = bool(dev.get("online", True))

                    caps = parse_device_capabilities(dev, self.overrides)
                    dev["caps"] = caps
                    dev["device_type"] = caps["device_type"]
                    dev["icon_url"] = caps["icon_url"]
                    dev["name"] = caps["name"]

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
                    dps[str(cmd["code"])] = cmd["value"]
                self.async_set_updated_data(self.data)
            return success

        return False

    async def async_get_camera_stream(self, device_id: str) -> str | None:
        """Get live RTSP/HLS URL for a camera."""
        if self.mobile_client:
            url = await self.mobile_client.get_camera_stream_url(device_id)
            if url:
                return url
        if self.client:
            url = await self.client.get_camera_stream_url(device_id)
            if url:
                return url
        # Fallback local RTSP if IP and local key are present
        dev = self.data.get(device_id, {})
        ip = dev.get("ip")
        key = dev.get("local_key")
        if ip and key:
            return f"rtsp://admin:{key}@{ip}:554/live/ch0"
        return None

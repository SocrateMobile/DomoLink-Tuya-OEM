"""Camera platform for DomoLink Tuya OEM."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import TuyaOEMDataCoordinator
from .dp_registry import classify_device

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Tuya OEM cameras."""
    coordinator: TuyaOEMDataCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    brand_name: str = hass.data[DOMAIN][entry.entry_id]["brand_name"]

    entities: list[TuyaOEMCamera] = []
    for dev_id, dev_data in coordinator.data.items():
        if classify_device(dev_data) == "camera":
            entities.append(TuyaOEMCamera(coordinator, dev_id, brand_name))

    async_add_entities(entities)


class TuyaOEMCamera(CoordinatorEntity[TuyaOEMDataCoordinator], Camera):
    """Representation of a Tuya OEM Camera."""

    _attr_supported_features = CameraEntityFeature.STREAM

    def __init__(
        self,
        coordinator: TuyaOEMDataCoordinator,
        device_id: str,
        brand_name: str,
    ) -> None:
        """Initialize camera."""
        super().__init__(coordinator)
        Camera.__init__(self)
        self.device_id = device_id
        self.brand_name = brand_name
        self._cached_stream_url: str | None = None

        dev = coordinator.data.get(device_id, {})
        base_name = dev.get("name") or dev.get("custom_name") or f"Caméra {device_id[:6]}"

        self._attr_name = base_name
        self._attr_unique_id = f"{device_id}_camera"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=base_name,
            manufacturer=f"Tuya ({brand_name})",
            model=dev.get("product_name") or dev.get("model") or "Tuya OEM IPC",
        )

    @property
    def available(self) -> bool:
        """Return True if camera is online."""
        dev = self.coordinator.data.get(self.device_id, {})
        return bool(dev.get("online", True))

    @property
    def is_on(self) -> bool:
        """Return True if camera is not in private mode."""
        dev = self.coordinator.data.get(self.device_id, {})
        dps = dev.get("dps_status", {})
        private_val = dps.get("105", dps.get("basic_private", False))
        return not bool(private_val)

    @property
    def entity_picture(self) -> str | None:
        """Return product photo from Tuya."""
        dev = self.coordinator.data.get(self.device_id, {})
        return dev.get("icon_url") or None

    async def stream_source(self) -> str | None:
        """Return RTSP or HLS stream URL."""
        url = await self.coordinator.async_get_camera_stream(self.device_id)
        if url:
            self._cached_stream_url = url
            return url
        return self._cached_stream_url

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Return snapshot image bytes."""
        dev = self.coordinator.data.get(self.device_id, {})
        # Check if motion alert snapshot DP is available
        dps = dev.get("dps_status", {})
        pic_url = dps.get("115") or dps.get("movement_detect_pic")
        if pic_url and isinstance(pic_url, str) and pic_url.startswith("http"):
            try:
                session = async_get_clientsession(self.hass)
                async with session.get(pic_url, timeout=5) as resp:
                    if resp.status == 200:
                        return await resp.read()
            except Exception as e:
                _LOGGER.debug("Failed to fetch camera motion picture for %s: %s", self.device_id, e)

        # Fallback to product icon if present
        icon_url = dev.get("icon_url")
        if icon_url and icon_url.startswith("http"):
            try:
                session = async_get_clientsession(self.hass)
                async with session.get(icon_url, timeout=5) as resp:
                    if resp.status == 200:
                        return await resp.read()
            except Exception:
                pass

        return None

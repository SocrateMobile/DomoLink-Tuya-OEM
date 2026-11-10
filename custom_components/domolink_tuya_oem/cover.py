"""Cover platform for DomoLink Tuya OEM."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.cover import (
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import TuyaOEMDataCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Tuya OEM covers."""
    coordinator: TuyaOEMDataCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    brand_name: str = hass.data[DOMAIN][entry.entry_id]["brand_name"]

    entities: list[TuyaOEMCover] = []
    for dev_id, dev_data in coordinator.data.items():
        category = dev_data.get("category", "").lower()
        dps = dev_data.get("dps_status", {})
        if category in ("cl", "clkg") or "control" in dps or "percent_control" in dps:
            entities.append(TuyaOEMCover(coordinator, dev_id, brand_name))

    async_add_entities(entities)


class TuyaOEMCover(CoordinatorEntity[TuyaOEMDataCoordinator], CoverEntity):
    """Representation of a Tuya OEM Cover."""

    def __init__(
        self,
        coordinator: TuyaOEMDataCoordinator,
        device_id: str,
        brand_name: str,
    ) -> None:
        """Initialize cover."""
        super().__init__(coordinator)
        self.device_id = device_id
        self.brand_name = brand_name

        dev = coordinator.data.get(device_id, {})
        base_name = dev.get("name") or dev.get("custom_name") or f"Volet {device_id}"

        self._attr_name = base_name
        self._attr_unique_id = f"{device_id}_cover"
        self._attr_device_class = CoverDeviceClass.SHUTTER

        features = CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.STOP
        dps = dev.get("dps_status", {})
        if "percent_control" in dps:
            features |= CoverEntityFeature.SET_POSITION

        self._attr_supported_features = features
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=base_name,
            manufacturer=f"Tuya ({brand_name})",
            model=dev.get("product_name") or dev.get("model") or "Tuya OEM Shutter",
        )

    @property
    def available(self) -> bool:
        """Return True if device is online."""
        dev = self.coordinator.data.get(self.device_id, {})
        return bool(dev.get("online", True))

    @property
    def entity_picture(self) -> str | None:
        """Return product photo from Tuya."""
        dev = self.coordinator.data.get(self.device_id, {})
        return dev.get("icon_url") or None

    @property
    def current_cover_position(self) -> int | None:
        """Return position between 0 and 100."""
        dps = self.coordinator.data.get(self.device_id, {}).get("dps_status", {})
        val = dps.get("percent_control", dps.get("percent_state"))
        if val is None:
            return None
        return int(val)

    @property
    def is_closed(self) -> bool | None:
        """Return if closed."""
        pos = self.current_cover_position
        if pos is not None:
            return pos <= 2
        return None

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open cover."""
        await self.coordinator.async_send_command(
            self.device_id, [{"code": "control", "value": "open"}]
        )

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close cover."""
        await self.coordinator.async_send_command(
            self.device_id, [{"code": "control", "value": "close"}]
        )

    async def async_stop_cover(self, **kwargs: Any) -> None:
        """Stop cover."""
        await self.coordinator.async_send_command(
            self.device_id, [{"code": "control", "value": "stop"}]
        )

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        """Set cover position."""
        position = kwargs.get("position", 50)
        await self.coordinator.async_send_command(
            self.device_id, [{"code": "percent_control", "value": position}]
        )

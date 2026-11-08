"""Switch platform for DomoLink Tuya OEM."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import TuyaOEMDataCoordinator

_LOGGER = logging.getLogger(__name__)

SWITCH_DP_CODES = [
    "switch",
    "switch_1",
    "switch_2",
    "switch_3",
    "switch_4",
    "switch_5",
    "switch_6",
    "switch_usb1",
    "switch_usb2",
    "power",
]


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Tuya OEM switches."""
    coordinator: TuyaOEMDataCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    brand_name: str = hass.data[DOMAIN][entry.entry_id]["brand_name"]

    entities: list[TuyaOEMSwitch] = []
    for dev_id, dev_data in coordinator.data.items():
        # Check category or DPs
        category = dev_data.get("category", "").lower()
        dps = dev_data.get("dps_status", {})

        # If it's a lighting device, let light.py handle it
        if category in ("dj", "dd", "dc", "xdd", "fwd", "jsq"):
            continue

        for code in SWITCH_DP_CODES:
            if code in dps:
                entities.append(TuyaOEMSwitch(coordinator, dev_id, code, brand_name))

    async_add_entities(entities)


class TuyaOEMSwitch(CoordinatorEntity[TuyaOEMDataCoordinator], SwitchEntity):
    """Representation of a Tuya OEM Switch."""

    def __init__(
        self,
        coordinator: TuyaOEMDataCoordinator,
        device_id: str,
        dp_code: str,
        brand_name: str,
    ) -> None:
        """Initialize switch."""
        super().__init__(coordinator)
        self.device_id = device_id
        self.dp_code = dp_code
        self.brand_name = brand_name

        dev = coordinator.data.get(device_id, {})
        base_name = dev.get("name") or dev.get("custom_name") or f"Device {device_id}"

        # If multi-switch, add suffix
        if self.dp_code in ("switch", "power"):
            self._attr_name = base_name
            self._attr_unique_id = f"{device_id}_{dp_code}"
        else:
            suffix = dp_code.replace("switch_", "Prise ").replace("switch_usb", "USB ")
            self._attr_name = f"{base_name} {suffix}"
            self._attr_unique_id = f"{device_id}_{dp_code}"

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=base_name,
            manufacturer=f"Tuya ({brand_name})",
            model=dev.get("product_name") or dev.get("model") or "Tuya OEM Switch",
        )

    @property
    def is_on(self) -> bool:
        """Return true if switch is on."""
        dev = self.coordinator.data.get(self.device_id, {})
        dps = dev.get("dps_status", {})
        return bool(dps.get(self.dp_code, False))

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on switch."""
        await self.coordinator.async_send_command(
            self.device_id, [{"code": self.dp_code, "value": True}]
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off switch."""
        await self.coordinator.async_send_command(
            self.device_id, [{"code": self.dp_code, "value": False}]
        )

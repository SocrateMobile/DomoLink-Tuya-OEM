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
from .light import is_light_device

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
    "1",
    "2",
    "3",
    "4",
    "20",
]


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Tuya OEM switches."""
    coordinator: TuyaOEMDataCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    brand_name: str = hass.data[DOMAIN][entry.entry_id]["brand_name"]

    entities: list[TuyaOEMSwitch] = []
    for dev_id, dev_data in coordinator.data.items():
        # If it's identified as a light device, let light.py handle it
        if is_light_device(dev_data):
            continue

        dps = dev_data.get("dps_status", {})
        device_entities: list[TuyaOEMSwitch] = []

        for code in SWITCH_DP_CODES:
            if code in dps:
                device_entities.append(TuyaOEMSwitch(coordinator, dev_id, code, brand_name))

        # Fallback: if device is not a light and had no standard switch DPs, create a primary switch
        # so the device always appears in HA and can be controlled.
        if not device_entities:
            fallback_code = "1" if "1" in dps else ("20" if "20" in dps else "switch")
            device_entities.append(TuyaOEMSwitch(coordinator, dev_id, fallback_code, brand_name))

        entities.extend(device_entities)

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
        self.dp_code = str(dp_code)
        self.brand_name = brand_name

        dev = coordinator.data.get(device_id, {})
        base_name = dev.get("name") or dev.get("custom_name") or f"Device {device_id[:6]}"

        # If multi-switch, add suffix
        if self.dp_code in ("switch", "power", "1", "20"):
            self._attr_name = base_name
            self._attr_unique_id = f"{device_id}_{dp_code}"
        else:
            suffix = self.dp_code.replace("switch_", "Prise ").replace("switch_usb", "USB ")
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
        dev = self.coordinator.data.get(self.device_id, {})
        dps = dev.setdefault("dps_status", {})
        await self.coordinator.async_send_command(
            self.device_id,
            [{"code": self.dp_code, "value": True}],
        )
        dps[self.dp_code] = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off switch."""
        dev = self.coordinator.data.get(self.device_id, {})
        dps = dev.setdefault("dps_status", {})
        await self.coordinator.async_send_command(
            self.device_id,
            [{"code": self.dp_code, "value": False}],
        )
        dps[self.dp_code] = False
        self.async_write_ha_state()

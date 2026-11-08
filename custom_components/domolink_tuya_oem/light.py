"""Light platform for DomoLink Tuya OEM."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ColorMode,
    LightEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import TuyaOEMDataCoordinator

_LOGGER = logging.getLogger(__name__)

LIGHT_CATEGORIES = ("dj", "dd", "dc", "xdd", "fwd", "jsq")


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Tuya OEM lights."""
    coordinator: TuyaOEMDataCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    brand_name: str = hass.data[DOMAIN][entry.entry_id]["brand_name"]

    entities: list[TuyaOEMLight] = []
    for dev_id, dev_data in coordinator.data.items():
        category = dev_data.get("category", "").lower()
        dps = dev_data.get("dps_status", {})

        is_light = category in LIGHT_CATEGORIES or "switch_led" in dps or "bright_value" in dps
        if is_light:
            entities.append(TuyaOEMLight(coordinator, dev_id, brand_name))

    async_add_entities(entities)


class TuyaOEMLight(CoordinatorEntity[TuyaOEMDataCoordinator], LightEntity):
    """Representation of a Tuya OEM Light."""

    def __init__(
        self,
        coordinator: TuyaOEMDataCoordinator,
        device_id: str,
        brand_name: str,
    ) -> None:
        """Initialize light."""
        super().__init__(coordinator)
        self.device_id = device_id
        self.brand_name = brand_name

        dev = coordinator.data.get(device_id, {})
        base_name = dev.get("name") or dev.get("custom_name") or f"Ampoule {device_id}"

        self._attr_name = base_name
        self._attr_unique_id = f"{device_id}_light"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=base_name,
            manufacturer=f"Tuya ({brand_name})",
            model=dev.get("product_name") or dev.get("model") or "Tuya OEM Light",
        )

        # Detect color modes
        dps = dev.get("dps_status", {})
        modes: set[ColorMode] = {ColorMode.ONOFF}
        if "bright_value" in dps or "bright_value_v2" in dps:
            modes.add(ColorMode.BRIGHTNESS)
        if "temp_value" in dps or "temp_value_v2" in dps:
            modes.add(ColorMode.COLOR_TEMP)

        self._attr_supported_color_modes = modes
        if ColorMode.COLOR_TEMP in modes:
            self._attr_color_mode = ColorMode.COLOR_TEMP
            self._attr_min_color_temp_kelvin = 2700
            self._attr_max_color_temp_kelvin = 6500
        elif ColorMode.BRIGHTNESS in modes:
            self._attr_color_mode = ColorMode.BRIGHTNESS
        else:
            self._attr_color_mode = ColorMode.ONOFF

    @property
    def is_on(self) -> bool:
        """Return true if light is on."""
        dps = self.coordinator.data.get(self.device_id, {}).get("dps_status", {})
        return bool(dps.get("switch_led", dps.get("switch_1", dps.get("switch", False))))

    @property
    def brightness(self) -> int | None:
        """Return brightness between 0..255."""
        dps = self.coordinator.data.get(self.device_id, {}).get("dps_status", {})
        val = dps.get("bright_value_v2", dps.get("bright_value"))
        if val is None:
            return None
        # Tuya is typically 10..1000
        return max(1, min(255, int(val * 255 / 1000)))

    @property
    def color_temp_kelvin(self) -> int | None:
        """Return color temperature in Kelvin."""
        dps = self.coordinator.data.get(self.device_id, {}).get("dps_status", {})
        val = dps.get("temp_value_v2", dps.get("temp_value"))
        if val is None:
            return None
        # Scale 0..1000 to 2700..6500K
        return int(2700 + (val / 1000.0) * (6500 - 2700))

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the light with optional brightness and color temperature."""
        commands: list[dict[str, Any]] = []

        dps = self.coordinator.data.get(self.device_id, {}).get("dps_status", {})
        switch_code = "switch_led" if "switch_led" in dps else ("switch_1" if "switch_1" in dps else "switch")
        commands.append({"code": switch_code, "value": True})

        if ATTR_BRIGHTNESS in kwargs:
            b_val = kwargs[ATTR_BRIGHTNESS]
            tuya_bright = max(10, min(1000, int(b_val * 1000 / 255)))
            b_code = "bright_value_v2" if "bright_value_v2" in dps else "bright_value"
            commands.append({"code": b_code, "value": tuya_bright})

        if ATTR_COLOR_TEMP_KELVIN in kwargs:
            kelvin = kwargs[ATTR_COLOR_TEMP_KELVIN]
            tuya_temp = int(((kelvin - 2700) / (6500 - 2700)) * 1000)
            tuya_temp = max(0, min(1000, tuya_temp))
            t_code = "temp_value_v2" if "temp_value_v2" in dps else "temp_value"
            commands.append({"code": t_code, "value": tuya_temp})

        await self.coordinator.async_send_command(self.device_id, commands)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the light."""
        dps = self.coordinator.data.get(self.device_id, {}).get("dps_status", {})
        switch_code = "switch_led" if "switch_led" in dps else ("switch_1" if "switch_1" in dps else "switch")
        await self.coordinator.async_send_command(
            self.device_id, [{"code": switch_code, "value": False}]
        )

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
LIGHT_KEYWORDS = ("ampoule", "bulb", "light", "lampe", "spot", "ruban", "strip", "e27", "gu10", "e14", "plafonnier", "luminaire")


def is_light_device(dev_data: dict[str, Any]) -> bool:
    """Determine whether a Tuya device is a light."""
    cat = dev_data.get("category", "").lower()
    if cat in LIGHT_CATEGORIES:
        return True

    name = (dev_data.get("name") or "").lower()
    prod_name = (dev_data.get("product_name") or "").lower()
    if any(k in name for k in LIGHT_KEYWORDS) or any(k in prod_name for k in LIGHT_KEYWORDS):
        return True

    dps = dev_data.get("dps_status", {})
    # Cloud DP names
    if any(k in dps for k in ("switch_led", "bright_value", "bright_value_v2", "temp_value", "temp_value_v2", "colour_data")):
        return True

    # Tuya Mobile numeric DPs (Protocol v2: 20=switch, 21=mode, 22=bright, 23=temp, 24=colour)
    if "20" in dps and any(k in dps for k in ("21", "22", "23", "24", "25")):
        return True

    # Tuya Mobile numeric DPs (Protocol v1: 1=switch, 2=mode, 3=bright, 4=temp, 5=colour)
    if "1" in dps and any(k in dps for k in ("2", "3", "4", "5")):
        return True

    # Standalone lighting DPs
    if "22" in dps or "23" in dps or "3" in dps or "4" in dps:
        return True

    return False


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Tuya OEM lights."""
    coordinator: TuyaOEMDataCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    brand_name: str = hass.data[DOMAIN][entry.entry_id]["brand_name"]

    entities: list[TuyaOEMLight] = []
    for dev_id, dev_data in coordinator.data.items():
        if is_light_device(dev_data):
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
        if any(k in dps for k in ("bright_value", "bright_value_v2", "22", "3")):
            modes.add(ColorMode.BRIGHTNESS)
        if any(k in dps for k in ("temp_value", "temp_value_v2", "23", "4")):
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

    def _get_switch_dp(self, dps: dict[str, Any]) -> str:
        """Find the active power DP code."""
        for code in ("20", "switch_led", "1", "switch_1", "switch"):
            if code in dps:
                return code
        return "20" if "22" in dps else "1"

    def _get_brightness_dp(self, dps: dict[str, Any]) -> str:
        """Find the active brightness DP code."""
        for code in ("22", "bright_value_v2", "bright_value", "3"):
            if code in dps:
                return code
        return "22"

    def _get_temp_dp(self, dps: dict[str, Any]) -> str:
        """Find the active color temperature DP code."""
        for code in ("23", "temp_value_v2", "temp_value", "4"):
            if code in dps:
                return code
        return "23"

    @property
    def is_on(self) -> bool:
        """Return true if light is on."""
        dps = self.coordinator.data.get(self.device_id, {}).get("dps_status", {})
        code = self._get_switch_dp(dps)
        return bool(dps.get(code, False))

    @property
    def brightness(self) -> int | None:
        """Return brightness between 0..255."""
        dps = self.coordinator.data.get(self.device_id, {}).get("dps_status", {})
        code = self._get_brightness_dp(dps)
        val = dps.get(code)
        if val is None:
            return None
        # Scale: Tuya is 10..1000 or 1..255
        try:
            int_val = int(val)
            if int_val > 255:
                return max(1, min(255, int(int_val * 255 / 1000)))
            return max(1, min(255, int_val))
        except (ValueError, TypeError):
            return None

    @property
    def color_temp_kelvin(self) -> int | None:
        """Return color temperature in Kelvin."""
        dps = self.coordinator.data.get(self.device_id, {}).get("dps_status", {})
        code = self._get_temp_dp(dps)
        val = dps.get(code)
        if val is None:
            return None
        try:
            int_val = int(val)
            # Scale 0..1000 to 2700..6500K
            return int(2700 + (int_val / 1000.0) * (6500 - 2700))
        except (ValueError, TypeError):
            return None

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the light with optional brightness and color temperature."""
        commands: list[dict[str, Any]] = []
        dps = self.coordinator.data.get(self.device_id, {}).get("dps_status", {})

        switch_code = self._get_switch_dp(dps)
        commands.append({"code": switch_code, "value": True})

        if ATTR_BRIGHTNESS in kwargs:
            b_val = kwargs[ATTR_BRIGHTNESS]
            b_code = self._get_brightness_dp(dps)
            tuya_bright = max(10, min(1000, int(b_val * 1000 / 255)))
            commands.append({"code": b_code, "value": tuya_bright})

        if ATTR_COLOR_TEMP_KELVIN in kwargs:
            kelvin = kwargs[ATTR_COLOR_TEMP_KELVIN]
            t_code = self._get_temp_dp(dps)
            tuya_temp = int(((kelvin - 2700) / (6500 - 2700)) * 1000)
            tuya_temp = max(0, min(1000, tuya_temp))
            commands.append({"code": t_code, "value": tuya_temp})

        await self.coordinator.async_send_command(self.device_id, commands)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the light."""
        dps = self.coordinator.data.get(self.device_id, {}).get("dps_status", {})
        switch_code = self._get_switch_dp(dps)
        await self.coordinator.async_send_command(
            self.device_id, [{"code": switch_code, "value": False}]
        )

"""Light platform for DomoLink Tuya OEM."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_HS_COLOR,
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
from .dp_registry import classify_device, hs_to_tuya_hsv, tuya_hsv_to_hs

_LOGGER = logging.getLogger(__name__)


def is_light_device(dev_data: dict[str, Any]) -> bool:
    """Determine whether a Tuya device is a light."""
    return classify_device(dev_data) == "light"


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
    """Representation of a Tuya OEM Light with Dimmer, Color Temp and RGB."""

    _attr_min_color_temp_kelvin = 2700
    _attr_max_color_temp_kelvin = 6500

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
        if any(k in dps for k in ("colour_data", "colour_data_v2", "24", "5")):
            modes.add(ColorMode.HS)

        self._attr_supported_color_modes = modes

    @property
    def available(self) -> bool:
        """Return True if device is available / online."""
        dev = self.coordinator.data.get(self.device_id, {})
        return bool(dev.get("online", True))

    @property
    def entity_picture(self) -> str | None:
        """Return official product picture from Tuya."""
        dev = self.coordinator.data.get(self.device_id, {})
        return dev.get("icon_url") or None

    def _get_switch_dp(self, dps: dict[str, Any]) -> str:
        """Find active power switch DP."""
        for code in ("20", "switch_led", "1", "switch_1", "switch"):
            if code in dps and isinstance(dps[code], bool):
                return code
        return "20" if "22" in dps else "1"

    def _get_brightness_dp(self, dps: dict[str, Any]) -> str:
        """Find active brightness DP."""
        for code in ("22", "bright_value_v2", "bright_value", "3"):
            if code in dps:
                return code
        return "22"

    def _get_temp_dp(self, dps: dict[str, Any]) -> str:
        """Find active color temp DP."""
        for code in ("23", "temp_value_v2", "temp_value", "4"):
            if code in dps:
                return code
        return "23"

    def _get_color_dp(self, dps: dict[str, Any]) -> str:
        """Find active HSV color DP."""
        for code in ("24", "colour_data_v2", "colour_data", "5"):
            if code in dps:
                return code
        return "24"

    def _get_mode_dp(self, dps: dict[str, Any]) -> str | None:
        """Find work mode DP."""
        for code in ("21", "work_mode", "2"):
            if code in dps:
                return code
        return None

    @property
    def color_mode(self) -> ColorMode:
        """Return active color mode."""
        dps = self.coordinator.data.get(self.device_id, {}).get("dps_status", {})
        mode_code = self._get_mode_dp(dps)
        if mode_code and dps.get(mode_code) == "colour" and ColorMode.HS in self._attr_supported_color_modes:
            return ColorMode.HS
        if ColorMode.COLOR_TEMP in self._attr_supported_color_modes:
            return ColorMode.COLOR_TEMP
        if ColorMode.BRIGHTNESS in self._attr_supported_color_modes:
            return ColorMode.BRIGHTNESS
        return ColorMode.ONOFF

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
            return int(2700 + (int_val / 1000.0) * (6500 - 2700))
        except (ValueError, TypeError):
            return None

    @property
    def hs_color(self) -> tuple[float, float] | None:
        """Return (Hue, Saturation) color tuple."""
        dps = self.coordinator.data.get(self.device_id, {}).get("dps_status", {})
        code = self._get_color_dp(dps)
        val = dps.get(code)
        if val and isinstance(val, str):
            return tuya_hsv_to_hs(val)
        return None

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the light with optional brightness, color temp or HS color."""
        commands: list[dict[str, Any]] = []
        dps = self.coordinator.data.get(self.device_id, {}).get("dps_status", {})

        switch_code = self._get_switch_dp(dps)
        commands.append({"code": switch_code, "value": True})

        mode_dp = self._get_mode_dp(dps)

        if ATTR_HS_COLOR in kwargs:
            hs = kwargs[ATTR_HS_COLOR]
            c_code = self._get_color_dp(dps)
            b_val = kwargs.get(ATTR_BRIGHTNESS, self.brightness or 255)
            # Encode Tuya HSV
            version = 1 if c_code in ("colour_data", "5") else 2
            hsv_str = hs_to_tuya_hsv(hs, brightness=b_val, version=version)
            commands.append({"code": c_code, "value": hsv_str})
            if mode_dp:
                commands.append({"code": mode_dp, "value": "colour"})

        elif ATTR_COLOR_TEMP_KELVIN in kwargs:
            kelvin = kwargs[ATTR_COLOR_TEMP_KELVIN]
            t_code = self._get_temp_dp(dps)
            tuya_temp = int(((kelvin - 2700) / (6500 - 2700)) * 1000)
            tuya_temp = max(0, min(1000, tuya_temp))
            commands.append({"code": t_code, "value": tuya_temp})
            if mode_dp:
                commands.append({"code": mode_dp, "value": "white"})

        if ATTR_BRIGHTNESS in kwargs and ATTR_HS_COLOR not in kwargs:
            b_val = kwargs[ATTR_BRIGHTNESS]
            b_code = self._get_brightness_dp(dps)
            tuya_bright = max(10, min(1000, int(b_val * 1000 / 255)))
            commands.append({"code": b_code, "value": tuya_bright})

        await self.coordinator.async_send_command(self.device_id, commands)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the light."""
        dps = self.coordinator.data.get(self.device_id, {}).get("dps_status", {})
        switch_code = self._get_switch_dp(dps)
        await self.coordinator.async_send_command(
            self.device_id, [{"code": switch_code, "value": False}]
        )

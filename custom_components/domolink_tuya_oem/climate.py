"""Climate platform for DomoLink Tuya OEM."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
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
    """Set up Tuya OEM thermostats."""
    coordinator: TuyaOEMDataCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    brand_name: str = hass.data[DOMAIN][entry.entry_id]["brand_name"]

    entities: list[TuyaOEMClimate] = []
    for dev_id, dev_data in coordinator.data.items():
        category = dev_data.get("category", "").lower()
        dps = dev_data.get("dps_status", {})
        if category in ("wk", "wkf", "qn") or "temp_set" in dps:
            entities.append(TuyaOEMClimate(coordinator, dev_id, brand_name))

    async_add_entities(entities)


class TuyaOEMClimate(CoordinatorEntity[TuyaOEMDataCoordinator], ClimateEntity):
    """Representation of a Tuya OEM Thermostat."""

    def __init__(
        self,
        coordinator: TuyaOEMDataCoordinator,
        device_id: str,
        brand_name: str,
    ) -> None:
        """Initialize climate entity."""
        super().__init__(coordinator)
        self.device_id = device_id
        self.brand_name = brand_name

        dev = coordinator.data.get(device_id, {})
        base_name = dev.get("name") or dev.get("custom_name") or f"Thermostat {device_id}"

        self._attr_name = base_name
        self._attr_unique_id = f"{device_id}_climate"
        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        self._attr_supported_features = (
            ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.TURN_ON
            | ClimateEntityFeature.TURN_OFF
        )
        self._attr_hvac_modes = [HVACMode.HEAT, HVACMode.OFF]

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=base_name,
            manufacturer=f"Tuya ({brand_name})",
            model=dev.get("product_name") or dev.get("model") or "Tuya OEM Thermostat",
        )

    @property
    def current_temperature(self) -> float | None:
        """Return current temperature."""
        dps = self.coordinator.data.get(self.device_id, {}).get("dps_status", {})
        val = dps.get("temp_current")
        if val is not None:
            # Tuya temperature can be tenths of degree
            return val / 10.0 if val > 100 else float(val)
        return None

    @property
    def target_temperature(self) -> float | None:
        """Return target temperature."""
        dps = self.coordinator.data.get(self.device_id, {}).get("dps_status", {})
        val = dps.get("temp_set")
        if val is not None:
            return val / 10.0 if val > 100 else float(val)
        return None

    @property
    def hvac_mode(self) -> HVACMode:
        """Return hvac mode."""
        dps = self.coordinator.data.get(self.device_id, {}).get("dps_status", {})
        is_on = dps.get("switch", True)
        return HVACMode.HEAT if is_on else HVACMode.OFF

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set target temperature."""
        if ATTR_TEMPERATURE in kwargs:
            target = kwargs[ATTR_TEMPERATURE]
            dps = self.coordinator.data.get(self.device_id, {}).get("dps_status", {})
            current_raw = dps.get("temp_set", 20)
            raw_target = int(target * 10) if current_raw > 100 else int(target)
            await self.coordinator.async_send_command(
                self.device_id, [{"code": "temp_set", "value": raw_target}]
            )

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set HVAC mode."""
        value = hvac_mode == HVACMode.HEAT
        await self.coordinator.async_send_command(
            self.device_id, [{"code": "switch", "value": value}]
        )

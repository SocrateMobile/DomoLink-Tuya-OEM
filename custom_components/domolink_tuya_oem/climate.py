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

    _enable_turn_on_off_backwards_compatibility = False

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
        self._update_state_from_coordinator()

    def _update_state_from_coordinator(self) -> None:
        """Update internal attributes from coordinator data."""
        dev = self.coordinator.data.get(self.device_id, {})
        dps = dev.get("dps_status", {})
        val_cur = dps.get("temp_current")
        if val_cur is not None:
            self._attr_current_temperature = val_cur / 10.0 if val_cur > 100 else float(val_cur)
        else:
            self._attr_current_temperature = None

        val_tgt = dps.get("temp_set")
        if val_tgt is not None:
            self._attr_target_temperature = val_tgt / 10.0 if val_tgt > 100 else float(val_tgt)
        else:
            self._attr_target_temperature = None

        is_on = dps.get("switch", True)
        self._attr_hvac_mode = HVACMode.HEAT if is_on else HVACMode.OFF

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._update_state_from_coordinator()
        self.async_write_ha_state()

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

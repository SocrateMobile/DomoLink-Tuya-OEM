"""Dynamic Number platform for DomoLink Tuya OEM based on official product schema."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import TuyaOEMDataCoordinator
from .dp_schema import DPSpec

_LOGGER = logging.getLogger(__name__)

# Exclude DPs already managed by specialized platforms (light brightness, climate temperature, etc.)
EXCLUDED_NUMBER_DPS = {
    "bright_value",
    "bright_value_v2",
    "temp_value",
    "temp_value_v2",
    "temp_current",
    "target_temperature",
    "cur_power",
    "cur_current",
    "cur_voltage",
    "add_ele",
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Tuya OEM dynamic number entities."""
    coordinator: TuyaOEMDataCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    brand_name: str = hass.data[DOMAIN][entry.entry_id]["brand_name"]

    entities: list[TuyaOEMNumber] = []
    for dev_id, dev_data in coordinator.data.items():
        caps = dev_data.get("caps") or {}
        schema_specs: dict[str, DPSpec] = caps.get("schema_specs") or {}
        dev_type = caps.get("device_type", "")

        for code, spec in schema_specs.items():
            if spec.dp_type != "value" or not spec.writable:
                continue
            if code in EXCLUDED_NUMBER_DPS or spec.code in EXCLUDED_NUMBER_DPS:
                continue
            # For lights, skip 22/23
            if dev_type == "light" and code in ("22", "23"):
                continue

            entities.append(TuyaOEMNumber(coordinator, dev_id, spec, brand_name))

    async_add_entities(entities)


class TuyaOEMNumber(CoordinatorEntity[TuyaOEMDataCoordinator], NumberEntity):
    """Representation of a Tuya numeric DataPoint controllable entity."""

    def __init__(
        self,
        coordinator: TuyaOEMDataCoordinator,
        device_id: str,
        spec: DPSpec,
        brand_name: str,
    ) -> None:
        """Initialize number entity."""
        super().__init__(coordinator)
        self.device_id = device_id
        self.spec = spec
        self.brand_name = brand_name
        self.dp_code = spec.dp_id

        dev = coordinator.data.get(device_id, {})
        base_name = dev.get("name") or dev.get("custom_name") or f"Appareil {device_id[:6]}"

        self._attr_name = f"{base_name} {spec.name}"
        self._attr_unique_id = f"{device_id}_{spec.dp_id}_number"

        # Apply min / max / step / unit from schema
        min_f = spec.min if spec.min is not None else 0.0
        max_f = spec.max if spec.max is not None else 100.0
        step_f = spec.step if spec.step is not None and spec.step > 0 else 1.0

        if spec.scale > 0:
            scale_factor = 10**spec.scale
            self._attr_native_min_value = round(min_f / scale_factor, spec.scale)
            self._attr_native_max_value = round(max_f / scale_factor, spec.scale)
            self._attr_native_step = round(step_f / scale_factor, spec.scale)
        else:
            self._attr_native_min_value = float(min_f)
            self._attr_native_max_value = float(max_f)
            self._attr_native_step = float(step_f)

        self._attr_native_unit_of_measurement = spec.unit
        self._attr_mode = NumberMode.SLIDER if (self._attr_native_max_value - self._attr_native_min_value) <= 100 else NumberMode.BOX

        # If it is a countdown or setting, put in config category
        if "countdown" in spec.code or "delay" in spec.code or "time" in spec.code:
            self._attr_entity_category = EntityCategory.CONFIG
            self._attr_icon = "mdi:timer-outline"

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=base_name,
            manufacturer=f"Tuya ({brand_name})",
            model=dev.get("product_name") or dev.get("model") or "Tuya OEM",
        )

    @property
    def available(self) -> bool:
        """Return True if device is online."""
        dev = self.coordinator.data.get(self.device_id, {})
        return bool(dev.get("online", True))

    @property
    def native_value(self) -> float | None:
        """Return current scaled numeric value."""
        dev = self.coordinator.data.get(self.device_id, {})
        dps = dev.get("dps_status") or dev.get("dps") or {}
        raw_val = dps.get(self.dp_code)
        if raw_val is None:
            raw_val = dps.get(self.spec.code)

        if raw_val is None:
            return None

        try:
            val_f = float(raw_val)
            if self.spec.scale > 0:
                return round(val_f / (10**self.spec.scale), self.spec.scale)
            return val_f
        except (ValueError, TypeError):
            return None

    async def async_set_native_value(self, value: float) -> None:
        """Set new value respecting Tuya scale and constraints."""
        raw_to_send = self.spec.coerce_to_raw(value)
        await self.coordinator.async_send_command(
            self.device_id,
            [{"code": self.dp_code, "value": raw_to_send}],
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return device state attributes including control path and LAN metrics."""
        dev = self.coordinator.data.get(self.device_id, {})
        is_lan = self.device_id in self.coordinator.local_devices and self.coordinator.local_devices[self.device_id].is_connected
        lan_info = self.coordinator.lan_resolver.get_device_lan_status(self.device_id) if getattr(self.coordinator, "lan_resolver", None) else {}
        attrs: dict[str, Any] = {
            "control_path": "local" if is_lan else "cloud",
            "lan_ip": lan_info.get("ip") or dev.get("ip"),
            "protocol_version": lan_info.get("version") or dev.get("protocol_version"),
        }
        if dev.get("room_name"):
            attrs["room"] = dev.get("room_name")
        return attrs

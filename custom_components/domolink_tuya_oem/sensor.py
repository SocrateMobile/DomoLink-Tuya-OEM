"""Sensor platform for DomoLink Tuya OEM."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import TuyaOEMDataCoordinator

_LOGGER = logging.getLogger(__name__)

SENSOR_TYPES = {
    "cur_power": {
        "name": "Puissance",
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfPower.WATT,
        "scale": 0.1,
    },
    "cur_current": {
        "name": "Courant",
        "device_class": SensorDeviceClass.CURRENT,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfElectricCurrent.MILLIAMPERE,
        "scale": 1.0,
    },
    "cur_voltage": {
        "name": "Tension",
        "device_class": SensorDeviceClass.VOLTAGE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfElectricPotential.VOLT,
        "scale": 0.1,
    },
    "add_ele": {
        "name": "Énergie consommée",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "scale": 0.01,
    },
    "battery_percentage": {
        "name": "Batterie",
        "device_class": SensorDeviceClass.BATTERY,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": PERCENTAGE,
        "scale": 1.0,
    },
    "va_temperature": {
        "name": "Température",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfTemperature.CELSIUS,
        "scale": 0.1,
    },
    "va_humidity": {
        "name": "Humidité",
        "device_class": SensorDeviceClass.HUMIDITY,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": PERCENTAGE,
        "scale": 1.0,
    },
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Tuya OEM sensors."""
    coordinator: TuyaOEMDataCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    brand_name: str = hass.data[DOMAIN][entry.entry_id]["brand_name"]

    entities: list[TuyaOEMSensor] = []
    for dev_id, dev_data in coordinator.data.items():
        dps = dev_data.get("dps_status", {})
        for code, conf in SENSOR_TYPES.items():
            if code in dps:
                entities.append(TuyaOEMSensor(coordinator, dev_id, code, conf, brand_name))

    async_add_entities(entities)


class TuyaOEMSensor(CoordinatorEntity[TuyaOEMDataCoordinator], SensorEntity):
    """Representation of a Tuya OEM Sensor."""

    def __init__(
        self,
        coordinator: TuyaOEMDataCoordinator,
        device_id: str,
        dp_code: str,
        conf: dict[str, Any],
        brand_name: str,
    ) -> None:
        """Initialize sensor."""
        super().__init__(coordinator)
        self.device_id = device_id
        self.dp_code = dp_code
        self.scale = conf["scale"]
        self.brand_name = brand_name

        dev = coordinator.data.get(device_id, {})
        base_name = dev.get("name") or dev.get("custom_name") or f"Device {device_id}"

        self._attr_name = f"{base_name} {conf['name']}"
        self._attr_unique_id = f"{device_id}_{dp_code}"
        self._attr_device_class = conf.get("device_class")
        self._attr_state_class = conf.get("state_class")
        self._attr_native_unit_of_measurement = conf.get("unit")

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=base_name,
            manufacturer=f"Tuya ({brand_name})",
            model=dev.get("product_name") or dev.get("model") or "Tuya OEM Sensor",
        )

    @property
    def native_value(self) -> float | int | None:
        """Return raw scaled sensor value."""
        dps = self.coordinator.data.get(self.device_id, {}).get("dps_status", {})
        raw = dps.get(self.dp_code)
        if raw is None:
            return None
        try:
            return round(float(raw) * self.scale, 2)
        except (ValueError, TypeError):
            return None

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
    LIGHT_LUX,
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
from .dp_registry import classify_device

_LOGGER = logging.getLogger(__name__)

SENSOR_TYPES = {
    "cur_power": {
        "name": "Puissance",
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfPower.WATT,
        "scale": 0.1,
    },
    "18": {
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
    "19": {
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
    "20": {
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
    "17": {
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
    "battery": {
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
    "temp_current": {
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
    "humidity_value": {
        "name": "Humidité",
        "device_class": SensorDeviceClass.HUMIDITY,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": PERCENTAGE,
        "scale": 1.0,
    },
    "bright_value": {
        "name": "Luminosité ambiante",
        "device_class": SensorDeviceClass.ILLUMINANCE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": LIGHT_LUX,
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
        dev_type = classify_device(dev_data)
        dps = dev_data.get("dps_status", {})

        for code, conf in SENSOR_TYPES.items():
            if code in dps:
                val = dps[code]
                # Special disambiguation: if code is "20", it is voltage ONLY on switches/plugs with int value
                if code == "20" and (dev_type == "light" or isinstance(val, bool)):
                    continue
                # If code is "bright_value" on a light, it's a dimmer attribute, not an illuminance sensor!
                if code == "bright_value" and dev_type == "light":
                    continue

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
        base_name = dev.get("name") or dev.get("custom_name") or f"Appareil {device_id[:6]}"

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
    def available(self) -> bool:
        """Return True if device is available / online."""
        dev = self.coordinator.data.get(self.device_id, {})
        return bool(dev.get("online", True))

    @property
    def entity_picture(self) -> str | None:
        """Return product photo from Tuya."""
        dev = self.coordinator.data.get(self.device_id, {})
        return dev.get("icon_url") or None

    @property
    def native_value(self) -> float | int | None:
        """Return raw scaled sensor value."""
        dps = self.coordinator.data.get(self.device_id, {}).get("dps_status", {})
        raw = dps.get(self.dp_code)
        if raw is None:
            return None
        try:
            val = float(raw)
            # Automatic scale adjustment for temperature if not scaled
            if self._attr_device_class == SensorDeviceClass.TEMPERATURE:
                if val > 100:
                    val = val / 10.0
                return round(val, 1)

            return round(val * self.scale, 2)
        except (ValueError, TypeError):
            return None

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

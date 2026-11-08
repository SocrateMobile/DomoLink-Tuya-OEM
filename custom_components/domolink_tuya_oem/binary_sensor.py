"""Binary Sensor platform for DomoLink Tuya OEM."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import TuyaOEMDataCoordinator

_LOGGER = logging.getLogger(__name__)

BINARY_SENSOR_TYPES = {
    "doorcontact_state": {
        "name": "Ouverture",
        "device_class": BinarySensorDeviceClass.DOOR,
    },
    "pir": {
        "name": "Mouvement",
        "device_class": BinarySensorDeviceClass.MOTION,
    },
    "presence_state": {
        "name": "Présence",
        "device_class": BinarySensorDeviceClass.PRESENCE,
    },
    "watersensor_state": {
        "name": "Fuite d'eau",
        "device_class": BinarySensorDeviceClass.MOISTURE,
    },
    "smoke_sensor_state": {
        "name": "Fumée",
        "device_class": BinarySensorDeviceClass.SMOKE,
    },
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Tuya OEM binary sensors."""
    coordinator: TuyaOEMDataCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    brand_name: str = hass.data[DOMAIN][entry.entry_id]["brand_name"]

    entities: list[TuyaOEMBinarySensor] = []
    for dev_id, dev_data in coordinator.data.items():
        dps = dev_data.get("dps_status", {})
        for code, conf in BINARY_SENSOR_TYPES.items():
            if code in dps:
                entities.append(TuyaOEMBinarySensor(coordinator, dev_id, code, conf, brand_name))

    async_add_entities(entities)


class TuyaOEMBinarySensor(CoordinatorEntity[TuyaOEMDataCoordinator], BinarySensorEntity):
    """Representation of a Tuya OEM Binary Sensor."""

    def __init__(
        self,
        coordinator: TuyaOEMDataCoordinator,
        device_id: str,
        dp_code: str,
        conf: dict[str, Any],
        brand_name: str,
    ) -> None:
        """Initialize binary sensor."""
        super().__init__(coordinator)
        self.device_id = device_id
        self.dp_code = dp_code
        self.brand_name = brand_name

        dev = coordinator.data.get(device_id, {})
        base_name = dev.get("name") or dev.get("custom_name") or f"Capteur {device_id}"

        self._attr_name = f"{base_name} {conf['name']}"
        self._attr_unique_id = f"{device_id}_{dp_code}"
        self._attr_device_class = conf.get("device_class")

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=base_name,
            manufacturer=f"Tuya ({brand_name})",
            model=dev.get("product_name") or dev.get("model") or "Tuya OEM Detector",
        )

    @property
    def is_on(self) -> bool:
        """Return true if binary sensor is triggered."""
        dps = self.coordinator.data.get(self.device_id, {}).get("dps_status", {})
        val = dps.get(self.dp_code)
        if isinstance(val, bool):
            return val
        if isinstance(val, str):
            return val.lower() in ("alarm", "true", "1", "pir", "open")
        return bool(val)

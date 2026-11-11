"""Dynamic Select platform for DomoLink Tuya OEM based on official product schema."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import TuyaOEMDataCoordinator
from .dp_schema import DPSpec

_LOGGER = logging.getLogger(__name__)

EXCLUDED_SELECT_DPS = {
    "colour_data",
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Tuya OEM dynamic select entities."""
    coordinator: TuyaOEMDataCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    brand_name: str = hass.data[DOMAIN][entry.entry_id]["brand_name"]

    entities: list[TuyaOEMSelect] = []
    for dev_id, dev_data in coordinator.data.items():
        caps = dev_data.get("caps") or {}
        schema_specs: dict[str, DPSpec] = caps.get("schema_specs") or {}

        for code, spec in schema_specs.items():
            if spec.dp_type != "enum" or not spec.writable or not spec.range_options:
                continue
            if code in EXCLUDED_SELECT_DPS or spec.code in EXCLUDED_SELECT_DPS:
                continue

            entities.append(TuyaOEMSelect(coordinator, dev_id, spec, brand_name))

    async_add_entities(entities)


class TuyaOEMSelect(CoordinatorEntity[TuyaOEMDataCoordinator], SelectEntity):
    """Representation of a Tuya enum DataPoint controllable select entity."""

    def __init__(
        self,
        coordinator: TuyaOEMDataCoordinator,
        device_id: str,
        spec: DPSpec,
        brand_name: str,
    ) -> None:
        """Initialize select entity."""
        super().__init__(coordinator)
        self.device_id = device_id
        self.spec = spec
        self.brand_name = brand_name
        self.dp_code = spec.dp_id

        dev = coordinator.data.get(device_id, {})
        base_name = dev.get("name") or dev.get("custom_name") or f"Appareil {device_id[:6]}"

        self._attr_name = f"{base_name} {spec.name}"
        self._attr_unique_id = f"{device_id}_{spec.dp_id}_select"
        self._attr_options = list(spec.range_options)

        # Entity category
        if any(w in spec.code for w in ("mode", "behavior", "status", "tone", "sensitivity")):
            self._attr_entity_category = EntityCategory.CONFIG

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
    def current_option(self) -> str | None:
        """Return current option value."""
        dev = self.coordinator.data.get(self.device_id, {})
        dps = dev.get("dps_status") or dev.get("dps") or {}
        raw_val = dps.get(self.dp_code)
        if raw_val is None:
            raw_val = dps.get(self.spec.code)

        if raw_val is None:
            return None

        val_str = str(raw_val)
        if val_str in self.options:
            return val_str
        # Check case-insensitive match
        for opt in self.options:
            if opt.lower() == val_str.lower():
                return opt
        return val_str

    async def async_select_option(self, option: str) -> None:
        """Send chosen option to Tuya device."""
        await self.coordinator.async_send_command(
            self.device_id,
            [{"code": self.dp_code, "value": option}],
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

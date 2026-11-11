"""Switch platform for DomoLink Tuya OEM."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import TuyaOEMDataCoordinator
from .dp_registry import classify_device

_LOGGER = logging.getLogger(__name__)

SWITCH_DP_CODES = [
    "switch",
    "switch_1",
    "switch_2",
    "switch_3",
    "switch_4",
    "switch_5",
    "switch_6",
    "switch_usb1",
    "switch_usb2",
    "power",
    "1",
    "2",
    "3",
    "4",
    "5",
    "6",
]

# Camera toggle switches
CAMERA_SWITCH_DPS = {
    "105": {"name": "Mode privé", "icon": "mdi:eye-off"},
    "basic_private": {"name": "Mode privé", "icon": "mdi:eye-off"},
    "134": {"name": "Détection mouvement", "icon": "mdi:motion-sensor"},
    "motion_switch": {"name": "Détection mouvement", "icon": "mdi:motion-sensor"},
    "159": {"name": "Sirène", "icon": "mdi:alarm-bell"},
    "siren_switch": {"name": "Sirène", "icon": "mdi:alarm-bell"},
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Tuya OEM switches."""
    coordinator: TuyaOEMDataCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    brand_name: str = hass.data[DOMAIN][entry.entry_id]["brand_name"]

    entities: list[TuyaOEMSwitch] = []
    for dev_id, dev_data in coordinator.data.items():
        dev_type = classify_device(dev_data)
        dps = dev_data.get("dps_status", {})
        dp_names = dev_data.get("dp_names") or {}

        # 1. Lights are managed by light.py
        if dev_type == "light":
            continue

        # 2. Camera special toggle switches
        if dev_type == "camera":
            for cam_dp, conf in CAMERA_SWITCH_DPS.items():
                if cam_dp in dps:
                    entities.append(
                        TuyaOEMSwitch(
                            coordinator,
                            dev_id,
                            cam_dp,
                            brand_name,
                            custom_name=conf["name"],
                            custom_icon=conf["icon"],
                        )
                    )
            continue

        # 3. Standard switches & sockets
        device_entities: list[TuyaOEMSwitch] = []
        for code in SWITCH_DP_CODES:
            if code in dps:
                # If code is '20' on switch, it's voltage not a switch!
                val = dps.get(code)
                if isinstance(val, bool):
                    c_name = dp_names.get(code)
                    device_entities.append(
                        TuyaOEMSwitch(coordinator, dev_id, code, brand_name, custom_name=c_name)
                    )

        # Fallback: if device is not a light, not a camera, and had no standard switch DPs, create a primary switch
        if not device_entities and dev_type == "switch":
            fallback_code = "1" if "1" in dps else "switch"
            device_entities.append(
                TuyaOEMSwitch(coordinator, dev_id, fallback_code, brand_name)
            )

        entities.extend(device_entities)

    async_add_entities(entities)


class TuyaOEMSwitch(CoordinatorEntity[TuyaOEMDataCoordinator], SwitchEntity):
    """Representation of a Tuya OEM Switch."""

    def __init__(
        self,
        coordinator: TuyaOEMDataCoordinator,
        device_id: str,
        dp_code: str,
        brand_name: str,
        custom_name: str | None = None,
        custom_icon: str | None = None,
    ) -> None:
        """Initialize switch."""
        super().__init__(coordinator)
        self.device_id = device_id
        self.dp_code = str(dp_code)
        self.brand_name = brand_name
        self._custom_icon = custom_icon

        dev = coordinator.data.get(device_id, {})
        base_name = dev.get("name") or dev.get("custom_name") or f"Appareil {device_id[:6]}"

        if custom_name:
            self._attr_name = f"{base_name} {custom_name}"
        elif self.dp_code in ("switch", "power", "1"):
            self._attr_name = base_name
        else:
            suffix = self.dp_code.replace("switch_", "Prise ").replace("switch_usb", "USB ")
            if suffix.isdigit():
                suffix = f"Canal {suffix}"
            self._attr_name = f"{base_name} {suffix}"

        self._attr_unique_id = f"{device_id}_{dp_code}"
        self._attr_device_class = SwitchDeviceClass.OUTLET if "switch" in self.dp_code or self.dp_code.isdigit() else SwitchDeviceClass.SWITCH
        if self._custom_icon:
            self._attr_icon = self._custom_icon

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=base_name,
            manufacturer=f"Tuya ({brand_name})",
            model=dev.get("product_name") or dev.get("model") or "Tuya OEM Switch",
        )

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

    @property
    def is_on(self) -> bool:
        """Return true if switch is on."""
        dev = self.coordinator.data.get(self.device_id, {})
        dps = dev.get("dps_status", {})
        return bool(dps.get(self.dp_code, False))

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

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on switch."""
        dev = self.coordinator.data.get(self.device_id, {})
        dps = dev.setdefault("dps_status", {})
        await self.coordinator.async_send_command(
            self.device_id,
            [{"code": self.dp_code, "value": True}],
        )
        dps[self.dp_code] = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off switch."""
        dev = self.coordinator.data.get(self.device_id, {})
        dps = dev.setdefault("dps_status", {})
        await self.coordinator.async_send_command(
            self.device_id,
            [{"code": self.dp_code, "value": False}],
        )
        dps[self.dp_code] = False
        self.async_write_ha_state()

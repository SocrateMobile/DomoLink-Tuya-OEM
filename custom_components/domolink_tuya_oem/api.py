"""WebSocket and HTTP API for DomoLink Tuya OEM."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv

from .const import CONF_BRAND, CONF_MODE, DOMAIN, MODE_MOBILE, OEM_PROFILES
from .coordinator import TuyaOEMDataCoordinator
from .dp_registry import hs_to_tuya_hsv
from .tuya_local import async_discover_devices

_LOGGER = logging.getLogger(__name__)


def register_websocket_handlers(hass: HomeAssistant) -> None:
    """Register WebSocket API commands for DomoLink Tuya OEM."""
    websocket_api.async_register_command(hass, ws_get_dashboard)
    websocket_api.async_register_command(hass, ws_send_dp_command)
    websocket_api.async_register_command(hass, ws_update_device_meta)
    websocket_api.async_register_command(hass, ws_add_account)
    websocket_api.async_register_command(hass, ws_remove_account)
    websocket_api.async_register_command(hass, ws_scan_lan)
    websocket_api.async_register_command(hass, ws_refresh_all)


@websocket_api.websocket_command({vol.Required("type"): "domolink_tuya_oem/get_dashboard"})
@websocket_api.async_response
async def ws_get_dashboard(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Return dashboard summary, accounts, devices and their parsed capabilities."""
    domain_data = hass.data.get(DOMAIN, {})
    accounts: list[dict[str, Any]] = []
    devices: list[dict[str, Any]] = []

    total_devices = 0
    online_count = 0
    offline_count = 0
    lan_count = 0

    for entry_id, data in domain_data.items():
        if not isinstance(data, dict) or "coordinator" not in data:
            continue
        coordinator: TuyaOEMDataCoordinator = data["coordinator"]
        brand_name: str = data.get("brand_name", "Tuya OEM")
        mode: str = data.get("mode", "mobile")

        entry = hass.config_entries.async_get_entry(entry_id)
        accounts.append({
            "entry_id": entry_id,
            "title": entry.title if entry else brand_name,
            "brand_name": brand_name,
            "mode": mode,
            "device_count": len(coordinator.data),
        })

        for dev_id, dev in coordinator.data.items():
            total_devices += 1
            is_online = bool(dev.get("online", True))
            is_lan = bool(dev.get("lan_active", False))

            if is_online:
                online_count += 1
            else:
                offline_count += 1
            if is_lan:
                lan_count += 1

            caps = dev.get("caps") or {}
            # Format parsed DPs for JSON
            parsed_dps_json = {}
            for dp_id, pd in caps.get("parsed_dps", {}).items():
                if hasattr(pd, "value"):
                    parsed_dps_json[dp_id] = {
                        "dp_id": pd.dp_id,
                        "code": pd.code,
                        "name": pd.name,
                        "type": pd.dp_type,
                        "value": pd.value,
                        "unit": pd.unit,
                        "scale": pd.scale,
                        "writable": getattr(pd, "writable", True),
                        "min_val": getattr(pd, "min_val", None),
                        "max_val": getattr(pd, "max_val", None),
                        "step": getattr(pd, "step", None),
                        "options": getattr(pd, "options", None),
                    }
                elif isinstance(pd, dict):
                    parsed_dps_json[dp_id] = pd

            is_cam = (caps.get("device_type") == "camera" or dev.get("device_type") == "camera" or dev.get("category") == "sp")
            linked_cam = coordinator.find_linked_camera_entity(dev_id, caps.get("name") or dev.get("name") or "") if is_cam else None
            lan_info = coordinator.lan_resolver.get_device_lan_info(dev_id) if hasattr(coordinator, "lan_resolver") else {}

            devices.append({
                "id": dev_id,
                "name": caps.get("name") or dev.get("name") or f"Appareil {dev_id[:6]}",
                "product_name": dev.get("product_name") or "Tuya OEM",
                "brand_name": brand_name,
                "category": dev.get("category", ""),
                "device_type": caps.get("device_type") or dev.get("device_type") or "switch",
                "icon_url": dev.get("icon_url") or "",
                "online": is_online,
                "lan_active": is_lan,
                "lan_method": lan_info.get("method", "udp" if is_lan else "none"),
                "ip": dev.get("ip") or "",
                "wan_ip": dev.get("wan_ip") or "",
                "rtsp_url": coordinator.overrides.get(dev_id, {}).get("rtsp_url") or dev.get("rtsp_url") or "",
                "camera_entity_id": f"camera.{dev_id}_camera" if is_cam else "",
                "linked_camera_entity_id": linked_cam or "",
                "local_key": dev.get("local_key") or "",
                "entry_id": entry_id,
                "light_caps": caps.get("light_caps") or {},
                "camera_caps": caps.get("camera_caps") or {},
                "parsed_dps": parsed_dps_json,
                "raw_dps": dev.get("dps_status") or dev.get("dps") or {},
            })

    connection.send_result(
        msg["id"],
        {
            "summary": {
                "total_devices": total_devices,
                "online_count": online_count,
                "offline_count": offline_count,
                "lan_count": lan_count,
                "account_count": len(accounts),
            },
            "accounts": accounts,
            "devices": devices,
            "profiles": [
                {"key": k, "name": v["name"], "icon": v.get("icon", "mdi:home")}
                for k, v in OEM_PROFILES.items()
            ],
        },
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "domolink_tuya_oem/send_dp_command",
        vol.Required("device_id"): cv.string,
        vol.Optional("commands"): vol.All(cv.ensure_list, [dict]),
        vol.Optional("code"): cv.string,
        vol.Optional("value"): vol.Any(bool, int, float, str),
        vol.Optional("action"): cv.string,
        vol.Optional("params"): dict,
    }
)
@websocket_api.async_response
async def ws_send_dp_command(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Send command or action to a Tuya device."""
    device_id = msg["device_id"]
    domain_data = hass.data.get(DOMAIN, {})

    target_coordinator: TuyaOEMDataCoordinator | None = None
    for entry_id, data in domain_data.items():
        if isinstance(data, dict) and "coordinator" in data:
            coord: TuyaOEMDataCoordinator = data["coordinator"]
            if device_id in coord.data:
                target_coordinator = coord
                break

    if not target_coordinator:
        connection.send_error(msg["id"], "device_not_found", f"Device {device_id} non trouvé")
        return

    dev_data = target_coordinator.data.get(device_id, {})
    dps = dev_data.get("dps_status", {})
    caps = dev_data.get("caps", {})

    commands: list[dict[str, Any]] = []

    # 1. Direct DP commands list
    if "commands" in msg and msg["commands"]:
        commands = msg["commands"]

    # 2. Single DP code + value
    elif "code" in msg and "value" in msg:
        commands = [{"code": msg["code"], "value": msg["value"]}]

    # 3. High level action
    elif "action" in msg:
        action = msg["action"]
        params = msg.get("params") or {}

        if action == "turn_on":
            sw_code = caps.get("light_caps", {}).get("switch_dp") or ("20" if "20" in dps else "1")
            commands.append({"code": sw_code, "value": True})

        elif action == "turn_off":
            sw_code = caps.get("light_caps", {}).get("switch_dp") or ("20" if "20" in dps else "1")
            commands.append({"code": sw_code, "value": False})

        elif action == "set_brightness":
            val = int(params.get("brightness", 100))  # 1..100%
            b_code = caps.get("light_caps", {}).get("bright_dp") or "22"
            tuya_val = max(10, min(1000, int(val * 10)))
            commands.append({"code": b_code, "value": tuya_val})

        elif action == "set_color_temp":
            kelvin = int(params.get("kelvin", 4000))
            t_code = caps.get("light_caps", {}).get("temp_dp") or "23"
            tuya_temp = int(((kelvin - 2700) / (6500 - 2700)) * 1000)
            commands.append({"code": t_code, "value": max(0, min(1000, tuya_temp))})

        elif action == "set_color":
            # hex color #RRGGBB
            hex_color = params.get("hex", "#ffffff").lstrip("#")
            if len(hex_color) == 6:
                r = int(hex_color[0:2], 16)
                g = int(hex_color[2:4], 16)
                b = int(hex_color[4:6], 16)
                # RGB to HSV
                import colorsys
                h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
                c_code = caps.get("light_caps", {}).get("color_dp") or "24"
                version = 1 if c_code in ("colour_data", "5") else 2
                hsv_str = hs_to_tuya_hsv((h * 360.0, s * 100.0), brightness=int(v * 255), version=version)
                commands.append({"code": c_code, "value": hsv_str})
                m_code = caps.get("light_caps", {}).get("mode_dp")
                if m_code:
                    commands.append({"code": m_code, "value": "colour"})

    if commands:
        success = await target_coordinator.async_send_command(device_id, commands)
        connection.send_result(msg["id"], {"success": success, "commands": commands})
    else:
        connection.send_error(msg["id"], "invalid_command", "Aucune commande à exécuter")


@websocket_api.websocket_command(
    {
        vol.Required("type"): "domolink_tuya_oem/update_device_meta",
        vol.Required("device_id"): cv.string,
        vol.Optional("custom_name"): cv.string,
        vol.Optional("forced_type"): cv.string,
        vol.Optional("ip"): cv.string,
        vol.Optional("rtsp_url"): cv.string,
        vol.Optional("linked_camera_entity"): cv.string,
    }
)
@websocket_api.async_response
async def ws_update_device_meta(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Save user overrides (renaming, forced type, manual IP, RTSP URL) to disk."""
    device_id = msg["device_id"]
    domain_data = hass.data.get(DOMAIN, {})

    target_coordinator: TuyaOEMDataCoordinator | None = None
    for entry_id, data in domain_data.items():
        if isinstance(data, dict) and "coordinator" in data:
            coord: TuyaOEMDataCoordinator = data["coordinator"]
            if device_id in coord.data:
                target_coordinator = coord
                break

    if not target_coordinator:
        connection.send_error(msg["id"], "device_not_found", f"Device {device_id} non trouvé")
        return

    overrides = {}
    if "custom_name" in msg:
        overrides["custom_name"] = msg["custom_name"].strip()
    if "forced_type" in msg:
        overrides["forced_type"] = msg["forced_type"].strip()
    if "ip" in msg:
        overrides["ip"] = msg["ip"].strip()
    if "rtsp_url" in msg:
        overrides["rtsp_url"] = msg["rtsp_url"].strip()
    if "linked_camera_entity" in msg:
        overrides["linked_camera_entity"] = msg["linked_camera_entity"].strip()

    await target_coordinator.async_save_device_override(device_id, overrides)
    connection.send_result(msg["id"], {"success": True, "overrides": overrides})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "domolink_tuya_oem/add_account",
        vol.Required("brand"): cv.string,
        vol.Required("username"): cv.string,
        vol.Required("password"): cv.string,
        vol.Optional("country_code", default="33"): cv.string,
    }
)
@websocket_api.async_response
async def ws_add_account(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Add a new mobile OEM account directly from panel."""
    brand = msg["brand"]
    username = msg["username"].strip()
    password = msg["password"]
    country_code = msg.get("country_code", "33").strip()

    try:
        res = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": "user"},
            data={CONF_MODE: MODE_MOBILE},
        )
        if res.get("type") == "form" and res.get("step_id") == "mobile":
            flow_id = res["flow_id"]
            final_res = await hass.config_entries.flow.async_configure(
                flow_id,
                user_input={
                    CONF_BRAND: brand,
                    "username": username,
                    "password": password,
                    "country_code": country_code,
                },
            )
            if final_res.get("type") == "create_entry":
                connection.send_result(msg["id"], {"success": True, "title": final_res.get("title")})
                return
            elif final_res.get("type") == "abort":
                connection.send_error(msg["id"], "aborted", final_res.get("reason", "Compte déjà configuré"))
                return
            else:
                errors = final_res.get("errors", {})
                connection.send_error(msg["id"], "auth_failed", f"Erreur de connexion : {errors}")
                return
        connection.send_error(msg["id"], "flow_error", "Impossible d'initier le flow d'ajout")
    except Exception as e:
        _LOGGER.exception("Error adding account via WS: %s", e)
        connection.send_error(msg["id"], "exception", str(e))


@websocket_api.websocket_command(
    {
        vol.Required("type"): "domolink_tuya_oem/remove_account",
        vol.Required("entry_id"): cv.string,
    }
)
@websocket_api.async_response
async def ws_remove_account(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Remove a hub/account entry."""
    entry_id = msg["entry_id"]
    entry = hass.config_entries.async_get_entry(entry_id)
    if not entry or entry.domain != DOMAIN:
        connection.send_error(msg["id"], "entry_not_found", "Entrée non trouvée")
        return

    success = await hass.config_entries.async_remove(entry_id)
    connection.send_result(msg["id"], {"success": success})


@websocket_api.websocket_command({vol.Required("type"): "domolink_tuya_oem/scan_lan"})
@websocket_api.async_response
async def ws_scan_lan(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Scan local network for UDP Tuya broadcasts and match with known devices."""
    discovered = await async_discover_devices(timeout=3.0)
    domain_data = hass.data.get(DOMAIN, {})

    updated_count = 0
    for dev_id, info in discovered.items():
        ip = info.get("ip")
        ver = info.get("version", "3.3")
        if not ip:
            continue
        for entry_id, data in domain_data.items():
            if isinstance(data, dict) and "coordinator" in data:
                coord: TuyaOEMDataCoordinator = data["coordinator"]
                if dev_id in coord.devices or dev_id in coord.data:
                    coord._handle_local_device_discovered(dev_id, ip, ver)
                    updated_count += 1

    connection.send_result(
        msg["id"],
        {
            "found_count": len(discovered),
            "updated_count": updated_count,
            "discovered": discovered,
        },
    )


@websocket_api.websocket_command({vol.Required("type"): "domolink_tuya_oem/refresh_all"})
@websocket_api.async_response
async def ws_refresh_all(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Force refresh of all coordinators."""
    domain_data = hass.data.get(DOMAIN, {})
    refreshed = 0
    for entry_id, data in domain_data.items():
        if isinstance(data, dict) and "coordinator" in data:
            coord: TuyaOEMDataCoordinator = data["coordinator"]
            await coord.async_refresh()
            refreshed += 1
    connection.send_result(msg["id"], {"success": True, "refreshed_count": refreshed})

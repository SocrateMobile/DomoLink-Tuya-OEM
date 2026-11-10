"""DataPoint Registry and Device Classifier for DomoLink Tuya OEM."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

_LOGGER = logging.getLogger(__name__)

# Tuya Cloud image CDN base
TUYA_IMAGE_CDN = "https://images.tuyaeu.com/"

# Categories mapping to major device types
LIGHT_CATEGORIES = {"dj", "dd", "dc", "xdd", "fwd", "jsq", "tgq", "tyndj", "fsd", "gyd", "mxd"}
SWITCH_CATEGORIES = {"kg", "cz", "pc", "tdq", "dlq", "zn", "zncz", "wkcz"}
CAMERA_CATEGORIES = {"sp", "znmj", "lyj", "mk", "sjsb", "camerad"}
CLIMATE_CATEGORIES = {"wk", "wkf", "qn", "kt", "rs", "ktkzq"}
COVER_CATEGORIES = {"cl", "clkg", "ckmkzq", "jdcljqr", "mc"}
SENSOR_CATEGORIES = {"wsdcg", "ldcg", "pm25", "co2bj", "hjjcy", "ywbj", "rqbj"}
SECURITY_CATEGORIES = {"pir", "mcs", "sj", "sos", "zd", "sg"}

# Keywords for semantic classification
LIGHT_KEYWORDS = ("ampoule", "bulb", "light", "lampe", "spot", "ruban", "strip", "e27", "gu10", "e14", "plafonnier", "luminaire", "led")
CAMERA_KEYWORDS = ("camera", "caméra", "cctv", "cam", "ipc", "webcam")
CLIMATE_KEYWORDS = ("thermostat", "radiateur", "heater", "climatiseur", "clim", "vanne", "trv")
COVER_KEYWORDS = ("volet", "shutter", "blind", "curtain", "store", "garage")
SECURITY_KEYWORDS = ("mouvement", "motion", "pir", "detecteur", "détecteur", "porte", "door", "fenetre", "fenêtre", "contact", "fumee", "fumée", "smoke", "fuite", "leak", "flood")
SWITCH_KEYWORDS = ("prise", "socket", "plug", "switch", "interrupteur", "multiprise", "relais", "relay")


def resolve_device_icon(icon_url: str | None, category: str = "") -> str:
    """Normalize and return a full URL for the product image."""
    if not icon_url:
        return ""
    icon_clean = icon_url.strip()
    if icon_clean.startswith("http://"):
        return "https://" + icon_clean[7:]
    if icon_clean.startswith("https://"):
        return icon_clean
    return f"{TUYA_IMAGE_CDN.rstrip('/')}/{icon_clean.lstrip('/')}"


def tuya_hsv_to_hs(hsv_hex: str) -> tuple[float, float]:
    """Convert Tuya hex string into Home Assistant (Hue 0..360, Saturation 0..100)."""
    if not hsv_hex or not isinstance(hsv_hex, str):
        return (0.0, 0.0)
    try:
        clean = hsv_hex.strip()
        # Format v2: 12 chars (HHHH SSSS VVVV) where H=0..360, S=0..1000, V=0..1000
        if len(clean) == 12:
            h = int(clean[0:4], 16)
            s = int(clean[4:8], 16) / 10.0
            return (float(max(0, min(360, h))), float(max(0.0, min(100.0, s))))
        # Format v1: 14 chars (RRGGBB HHHH SS VV) where H=0..360, S=0..255, V=0..255
        if len(clean) == 14:
            h = int(clean[6:10], 16)
            s = (int(clean[10:12], 16) / 255.0) * 100.0
            return (float(max(0, min(360, h))), float(max(0.0, min(100.0, s))))
        # Fallback 8 chars (HHHHSSVV)
        if len(clean) == 8:
            h = int(clean[0:4], 16)
            s = (int(clean[4:6], 16) / 255.0) * 100.0
            return (float(max(0, min(360, h))), float(max(0.0, min(100.0, s))))
    except Exception as err:
        _LOGGER.debug("Error decoding Tuya HSV string %s: %s", hsv_hex, err)
    return (0.0, 0.0)


def hs_to_tuya_hsv(hs_color: tuple[float, float], brightness: int = 255, version: int = 2) -> str:
    """Convert Home Assistant (Hue 0..360, Saturation 0..100) to Tuya hex HSV string."""
    h = max(0, min(360, int(hs_color[0])))
    s = max(0.0, min(100.0, hs_color[1]))
    v_norm = max(0.0, min(1.0, brightness / 255.0))

    if version == 2:
        # 12 chars: HHHH (0..360), SSSS (0..1000), VVVV (0..1000)
        s_val = int(s * 10)
        v_val = int(v_norm * 1000)
        return f"{h:04x}{s_val:04x}{v_val:04x}"
    else:
        # 14 chars format: 000000 + HHHH (0..360) + SS (0..255) + VV (0..255)
        s_val = int((s / 100.0) * 255)
        v_val = int(v_norm * 255)
        return f"000000{h:04x}{s_val:02x}{v_val:02x}"


@dataclass
class ParsedDP:
    """Detailed metadata for a parsed Tuya DataPoint."""
    dp_id: str
    code: str
    name: str
    dp_type: str
    value: Any
    raw_value: Any
    writable: bool = True
    unit: str | None = None
    min_val: float | None = None
    max_val: float | None = None
    scale: float = 1.0
    options: list[str] | None = None


def classify_device(dev_data: dict[str, Any], user_override: str | None = None) -> str:
    """Classify device into one of: 'light', 'switch', 'camera', 'sensor', 'security', 'climate', 'cover'."""
    if user_override and user_override in ("light", "switch", "camera", "sensor", "security", "climate", "cover"):
        return user_override

    cat = (dev_data.get("category") or "").lower()
    name = (dev_data.get("name") or "").lower()
    prod_name = (dev_data.get("product_name") or "").lower()
    dps = dev_data.get("dps_status") or dev_data.get("dps") or {}

    # 1. Category-based checks
    if cat in LIGHT_CATEGORIES:
        return "light"
    if cat in CAMERA_CATEGORIES:
        return "camera"
    if cat in CLIMATE_CATEGORIES:
        return "climate"
    if cat in COVER_CATEGORIES:
        return "cover"
    if cat in SECURITY_CATEGORIES:
        return "security"
    if cat in SENSOR_CATEGORIES:
        return "sensor"
    if cat in SWITCH_CATEGORIES:
        return "switch"

    # 2. Camera DPs & Keywords
    if any(k in name for k in CAMERA_KEYWORDS) or any(k in prod_name for k in CAMERA_KEYWORDS):
        return "camera"
    if any(k in dps for k in ("basic_private", "motion_switch", "movement_detect_pic", "ptz_control", "105", "115", "134", "159")):
        return "camera"

    # 3. Light DPs & Keywords (Careful: check type of DP 20!)
    if any(k in name for k in LIGHT_KEYWORDS) or any(k in prod_name for k in LIGHT_KEYWORDS):
        return "light"
    if any(k in dps for k in ("switch_led", "bright_value", "bright_value_v2", "temp_value", "colour_data", "colour_data_v2")):
        return "light"
    # Check numeric lighting DPs
    # Notice: In plugs, "20" is an int (voltage ~2300). In lights, "20" is a bool!
    dp20 = dps.get("20")
    if isinstance(dp20, bool) and any(k in dps for k in ("21", "22", "23", "24", "25")):
        return "light"
    if "1" in dps and isinstance(dps.get("1"), bool) and any(k in dps for k in ("2", "3", "4", "5")) and not any(k in dps for k in ("cur_power", "cur_voltage", "18", "19")):
        return "light"
    if any(k in dps for k in ("22", "23", "24")):
        return "light"

    # 4. Climate DPs & Keywords
    if any(k in name for k in CLIMATE_KEYWORDS) or any(k in prod_name for k in CLIMATE_KEYWORDS):
        return "climate"
    if "temp_set" in dps or "target_temperature" in dps:
        return "climate"

    # 5. Cover DPs & Keywords
    if any(k in name for k in COVER_KEYWORDS) or any(k in prod_name for k in COVER_KEYWORDS):
        return "cover"
    if "percent_control" in dps or ("control" in dps and str(dps.get("control")).lower() in ("open", "close", "stop")):
        return "cover"

    # 6. Security (motion / door / smoke / leak)
    if any(k in name for k in SECURITY_KEYWORDS) or any(k in prod_name for k in SECURITY_KEYWORDS):
        return "security"
    if any(k in dps for k in ("pir", "doorcontact_state", "presence_state", "watersensor_state", "smoke_sensor_state")):
        return "security"

    # 7. Environment Sensors
    if any(k in dps for k in ("va_temperature", "va_humidity", "humidity_value")):
        return "sensor"

    # 8. Default fallback: switch
    return "switch"


def parse_device_capabilities(dev_data: dict[str, Any], user_overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """Extract full capabilities, DPs and metadata of a Tuya device."""
    dev_id = dev_data.get("id") or dev_data.get("devId") or dev_data.get("device_id") or ""
    dps = dev_data.get("dps_status") or dev_data.get("dps") or {}
    overrides = (user_overrides or {}).get(dev_id, {})
    forced_type = overrides.get("forced_type")

    dev_type = classify_device(dev_data, user_override=forced_type)
    icon_raw = dev_data.get("icon_url") or dev_data.get("icon") or dev_data.get("iconUrl")
    icon_url = resolve_device_icon(icon_raw, dev_data.get("category", ""))

    # Online status resolution: local active or cloud online
    is_online = dev_data.get("online")
    if is_online is None:
        is_online = dev_data.get("isOnline")
    if is_online is None:
        is_online = dev_data.get("cloudOnline", True)
    is_online = bool(is_online)

    parsed_dps: dict[str, ParsedDP] = {}
    for code, val in dps.items():
        code_str = str(code)
        parsed_dps[code_str] = _parse_single_dp(code_str, val, dev_type)

    # Lighting capabilities
    light_caps: dict[str, Any] = {}
    if dev_type == "light":
        light_caps = _detect_light_caps(dps)

    # Camera capabilities
    camera_caps: dict[str, Any] = {}
    if dev_type == "camera":
        camera_caps = _detect_camera_caps(dps)

    return {
        "device_id": dev_id,
        "name": overrides.get("custom_name") or dev_data.get("name") or dev_data.get("custom_name") or f"Appareil {dev_id[:6]}",
        "product_name": dev_data.get("product_name") or dev_data.get("model") or "Tuya OEM",
        "category": dev_data.get("category", ""),
        "device_type": dev_type,
        "icon_url": icon_url,
        "online": is_online,
        "ip": overrides.get("ip") or dev_data.get("ip") or "",
        "local_key": dev_data.get("local_key") or "",
        "parsed_dps": parsed_dps,
        "raw_dps": dps,
        "light_caps": light_caps,
        "camera_caps": camera_caps,
    }


def _parse_single_dp(code: str, val: Any, dev_type: str) -> ParsedDP:
    """Map a single DP into human-readable metadata."""
    # Common codes
    dp_type = "string"
    unit = None
    scale = 1.0
    name = f"DP {code}"

    if isinstance(val, bool):
        dp_type = "bool"
    elif isinstance(val, (int, float)):
        dp_type = "int" if isinstance(val, int) else "float"

    # Mapping by known code/id
    if code in ("20", "switch_led", "1", "switch", "switch_1"):
        if dev_type == "light" or isinstance(val, bool):
            name = "Interrupteur"
            dp_type = "bool"
        elif code == "20" and isinstance(val, (int, float)):
            name = "Tension"
            dp_type = "float"
            unit = "V"
            scale = 0.1
    elif code in ("22", "bright_value", "bright_value_v2", "3"):
        name = "Luminosité"
        dp_type = "int"
        unit = "%"
    elif code in ("23", "temp_value", "temp_value_v2", "4"):
        name = "Température de blanc"
        dp_type = "int"
        unit = "K"
    elif code in ("24", "colour_data", "colour_data_v2", "5"):
        name = "Couleur RVB/HSV"
        dp_type = "hsv"
    elif code in ("21", "work_mode", "2"):
        name = "Mode d'éclairage"
        dp_type = "enum"
        options = ["white", "colour", "scene", "music"]
    elif code in ("cur_power", "18"):
        name = "Puissance"
        dp_type = "float"
        unit = "W"
        scale = 0.1
    elif code in ("cur_current", "19"):
        name = "Courant"
        dp_type = "float"
        unit = "mA"
    elif code in ("cur_voltage", "20") and dev_type == "switch":
        name = "Tension"
        dp_type = "float"
        unit = "V"
        scale = 0.1
    elif code in ("add_ele", "17"):
        name = "Énergie consommée"
        dp_type = "float"
        unit = "kWh"
        scale = 0.01
    elif code in ("va_temperature", "temp_current"):
        name = "Température"
        dp_type = "float"
        unit = "°C"
        scale = 0.1 if isinstance(val, (int, float)) and val > 100 else 1.0
    elif code in ("va_humidity", "humidity_value"):
        name = "Humidité"
        dp_type = "int"
        unit = "%"
    elif code in ("battery_percentage", "battery"):
        name = "Batterie"
        dp_type = "int"
        unit = "%"
    elif code in ("basic_private", "105"):
        name = "Mode privé (veille)"
        dp_type = "bool"
    elif code in ("motion_switch", "134"):
        name = "Détection de mouvement"
        dp_type = "bool"
    elif code in ("siren_switch", "159"):
        name = "Sirène alarme"
        dp_type = "bool"
    elif code in ("nightvision_mode", "108"):
        name = "Vision nocturne"
        dp_type = "enum"

    return ParsedDP(
        dp_id=code,
        code=code,
        name=name,
        dp_type=dp_type,
        value=val,
        raw_value=val,
        writable=True,
        unit=unit,
        scale=scale,
    )


def _detect_light_caps(dps: dict[str, Any]) -> dict[str, Any]:
    """Detect specific DPs used by a lighting device."""
    switch_dp = "20" if "20" in dps and isinstance(dps["20"], bool) else ("switch_led" if "switch_led" in dps else "1")
    bright_dp = None
    for b in ("22", "bright_value_v2", "bright_value", "3"):
        if b in dps:
            bright_dp = b
            break

    temp_dp = None
    for t in ("23", "temp_value_v2", "temp_value", "4"):
        if t in dps:
            temp_dp = t
            break

    color_dp = None
    for c in ("24", "colour_data_v2", "colour_data", "5"):
        if c in dps:
            color_dp = c
            break

    mode_dp = None
    for m in ("21", "work_mode", "2"):
        if m in dps:
            mode_dp = m
            break

    return {
        "switch_dp": switch_dp,
        "bright_dp": bright_dp,
        "temp_dp": temp_dp,
        "color_dp": color_dp,
        "mode_dp": mode_dp,
        "supports_brightness": bright_dp is not None,
        "supports_color_temp": temp_dp is not None,
        "supports_color": color_dp is not None,
    }


def _detect_camera_caps(dps: dict[str, Any]) -> dict[str, Any]:
    """Detect specific DPs used by a camera device."""
    private_dp = "105" if "105" in dps else ("basic_private" if "basic_private" in dps else None)
    motion_dp = "134" if "134" in dps else ("motion_switch" if "motion_switch" in dps else None)
    siren_dp = "159" if "159" in dps else ("siren_switch" if "siren_switch" in dps else None)
    nightvision_dp = "108" if "108" in dps else ("nightvision_mode" if "nightvision_mode" in dps else None)
    motion_pic_dp = "115" if "115" in dps else ("movement_detect_pic" if "movement_detect_pic" in dps else None)

    return {
        "private_dp": private_dp,
        "motion_dp": motion_dp,
        "siren_dp": siren_dp,
        "nightvision_dp": nightvision_dp,
        "motion_pic_dp": motion_pic_dp,
    }

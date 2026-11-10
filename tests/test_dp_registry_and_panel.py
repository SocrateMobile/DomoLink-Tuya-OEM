"""Unit tests for DomoLink Tuya OEM DP Registry, Manifest and Capabilities."""
import asyncio
import importlib.util
import json
import os
import subprocess
import sys
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMPONENT_DIR = os.path.join(REPO_ROOT, "custom_components", "domolink_tuya_oem")

# Load dp_registry directly without executing __init__.py
spec = importlib.util.spec_from_file_location(
    "dp_registry",
    os.path.join(COMPONENT_DIR, "dp_registry.py"),
)
dp_registry = importlib.util.module_from_spec(spec)
sys.modules["dp_registry"] = dp_registry
spec.loader.exec_module(dp_registry)

# Load tuya_api for is_private_lan_ip
api_spec = importlib.util.spec_from_file_location(
    "tuya_api",
    os.path.join(COMPONENT_DIR, "tuya_api.py"),
)
tuya_api = importlib.util.module_from_spec(api_spec)
sys.modules["tuya_api"] = tuya_api
api_spec.loader.exec_module(tuya_api)

classify_device = dp_registry.classify_device
resolve_device_icon = dp_registry.resolve_device_icon
tuya_hsv_to_hs = dp_registry.tuya_hsv_to_hs
hs_to_tuya_hsv = dp_registry.hs_to_tuya_hsv
parse_device_capabilities = dp_registry.parse_device_capabilities
is_private_lan_ip = tuya_api.is_private_lan_ip


def test_manifest_structure_and_version():
    """Verify manifest.json has valid domain, codeowners, and version 2.0.2."""
    manifest_path = os.path.join(COMPONENT_DIR, "manifest.json")
    assert os.path.isfile(manifest_path)
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    assert manifest["domain"] == "domolink_tuya_oem"
    assert manifest["name"] == "DomoLink Tuya OEM Multi-Brand"
    assert manifest["version"] == "2.0.2"
    assert "@SocrateMobile" in manifest["codeowners"]
    assert "tuya-mobile>=1.2.0" in manifest["requirements"]


def test_translations_parity():
    """Verify fr.json and en.json exist and match keys."""
    fr_path = os.path.join(COMPONENT_DIR, "translations", "fr.json")
    en_path = os.path.join(COMPONENT_DIR, "translations", "en.json")
    assert os.path.isfile(fr_path)
    assert os.path.isfile(en_path)
    with open(fr_path, "r", encoding="utf-8") as f:
        fr = json.load(f)
    with open(en_path, "r", encoding="utf-8") as f:
        en = json.load(f)
    assert "config" in fr and "config" in en


def test_resolve_device_icon():
    """Test icon url normalization with CDN and protocols."""
    assert resolve_device_icon(None) == ""
    assert resolve_device_icon("") == ""
    assert resolve_device_icon("http://example.com/pic.png") == "https://example.com/pic.png"
    assert resolve_device_icon("https://cdn.tuya.com/pic.png") == "https://cdn.tuya.com/pic.png"
    assert resolve_device_icon("smart/icon/ay15.png") == "https://images.tuyaeu.com/smart/icon/ay15.png"


def test_classify_device():
    """Test device classification for all types."""
    # 1. Bulb by category
    assert classify_device({"category": "dj", "name": "Device 1"}) == "light"
    # 2. Bulb by DPs (numeric)
    assert classify_device({"name": "Ampoule Salon", "dps_status": {"20": True, "22": 500, "23": 400}}) == "light"
    # 3. Plug with DP 20 as voltage (not light!)
    plug_dev = {
        "name": "Prise Cuisine",
        "category": "cz",
        "dps_status": {"1": True, "18": 1500, "19": 6500, "20": 2305},
    }
    assert classify_device(plug_dev) == "switch"
    # 4. Camera by category and DPs
    cam_dev = {
        "name": "Camera Entree",
        "category": "sp",
        "dps_status": {"105": False, "134": True},
    }
    assert classify_device(cam_dev) == "camera"
    # 5. Security PIR detector
    pir_dev = {
        "name": "Detecteur Couloir",
        "category": "pir",
        "dps_status": {"pir": "pir"},
    }
    assert classify_device(pir_dev) == "security"
    # 6. Climate thermostat
    wk_dev = {
        "name": "Thermostat Salon",
        "category": "wk",
        "dps_status": {"temp_set": 200, "temp_current": 195},
    }
    assert classify_device(wk_dev) == "climate"
    # 7. Shutter / Cover
    cl_dev = {
        "name": "Volet Chambre",
        "category": "cl",
        "dps_status": {"percent_control": 50},
    }
    assert classify_device(cl_dev) == "cover"


def test_dp20_disambiguation_plug_vs_bulb():
    """Verify that DP 20 integer does not trigger light classification."""
    plug = {
        "name": "Prise Connectée",
        "dps_status": {"1": True, "20": 2315},  # 231.5 V
    }
    assert classify_device(plug) == "switch"

    bulb = {
        "name": "Ampoule RGB",
        "dps_status": {"20": True, "21": "white", "22": 1000},
    }
    assert classify_device(bulb) == "light"


def test_hsv_color_encoding_decoding():
    """Test bi-directional Tuya HSV color conversions."""
    # Format v2 (12 chars): H=180, S=100%, V=100%
    encoded_v2 = hs_to_tuya_hsv((180.0, 100.0), brightness=255, version=2)
    assert len(encoded_v2) == 12
    decoded_h, decoded_s = tuya_hsv_to_hs(encoded_v2)
    assert round(decoded_h) == 180
    assert round(decoded_s) == 100

    # Format v1 (14 chars)
    encoded_v1 = hs_to_tuya_hsv((240.0, 80.0), brightness=255, version=1)
    assert len(encoded_v1) == 14
    dec_h1, dec_s1 = tuya_hsv_to_hs(encoded_v1)
    assert round(dec_h1) == 240
    assert abs(dec_s1 - 80.0) < 1.0


def test_parse_device_capabilities_with_overrides():
    """Test capabilities parsing and user override handling."""
    raw_dev = {
        "id": "bf1234567890abcdef",
        "name": "Smart Device",
        "category": "dj",
        "icon_url": "smart/icon/bulb.png",
        "online": True,
        "dps_status": {
            "20": True,
            "21": "colour",
            "22": 800,
            "23": 500,
            "24": "007803e803e8",
        },
    }
    caps = parse_device_capabilities(raw_dev)
    assert caps["device_type"] == "light"
    assert caps["online"] is True
    assert caps["light_caps"]["supports_brightness"] is True
    assert caps["light_caps"]["supports_color"] is True
    assert caps["light_caps"]["supports_color_temp"] is True
    assert "https://images.tuyaeu.com" in caps["icon_url"]

    # Test with user override renaming and forced type
    overrides = {
        "bf1234567890abcdef": {
            "custom_name": "Lustre Salon",
            "forced_type": "light",
            "ip": "192.168.1.55",
        }
    }
    caps_over = parse_device_capabilities(raw_dev, user_overrides=overrides)
    assert caps_over["name"] == "Lustre Salon"
    assert caps_over["ip"] == "192.168.1.55"


def test_frontend_panel_file_exists():
    """Verify frontend panel script is present and non-empty."""
    panel_js = os.path.join(COMPONENT_DIR, "frontend", "domolink-tuya-panel.js")
    assert os.path.isfile(panel_js)
    assert os.path.getsize(panel_js) > 1000


def test_frontend_js_syntax():
    """Verify that domolink-tuya-panel.js has valid JavaScript syntax with node --check."""
    panel_js = os.path.join(COMPONENT_DIR, "frontend", "domolink-tuya-panel.js")
    result = subprocess.run(["node", "--check", panel_js], capture_output=True, text=True)
    assert result.returncode == 0, f"JS Syntax Error:\n{result.stderr}"


def test_is_private_lan_ip_filtering():
    """Verify strict detection of private LAN IPs vs public WAN IPs."""
    # Private RFC1918 IPs -> True
    assert is_private_lan_ip("192.168.1.50") is True
    assert is_private_lan_ip("192.168.0.1") is True
    assert is_private_lan_ip("10.0.0.12") is True
    assert is_private_lan_ip("172.16.0.5") is True

    # Public WAN IPs (Orange box, etc.) -> False
    assert is_private_lan_ip("80.215.210.27") is False
    assert is_private_lan_ip("80.215.138.41") is False
    assert is_private_lan_ip("8.8.8.8") is False

    # Special / Invalid -> False
    assert is_private_lan_ip("127.0.0.1") is False  # Loopback rejected
    assert is_private_lan_ip("0.0.0.0") is False
    assert is_private_lan_ip("") is False
    assert is_private_lan_ip(None) is False
    assert is_private_lan_ip("invalid_ip") is False


def test_send_command_device_offline_handling():
    """Verify send_command catches DEVICE_OFFLINE gracefully without uncaught exceptions."""
    class DummyClient:
        async def publish_dps(self, dev_id, dps):
            raise Exception("Tuya DP publish failed: DEVICE_OFFLINE Device offline")

    async def _test():
        client = tuya_api.TuyaOEMMobileClient(brand_key="smartlife", username="u", password="p")
        client._client = DummyClient()
        success = await client.send_command("offline_dev", [{"code": "1", "value": True}])
        assert success is False

    asyncio.run(_test())


def test_camera_entity_accent_matching():
    """Verify accent stripping and token matching for French camera names."""
    import re
    import unicodedata

    def _clean(s: str) -> str:
        s = unicodedata.normalize("NFD", s)
        s = "".join(c for c in s if unicodedata.category(c) != "Mn")
        return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")

    def match(dev_name, ha_entities):
        norm_name = _clean(dev_name)
        norm_tokens = set(norm_name.split("_")) - {"camera", "cam", "oem", "tuya"}
        for ent_id in ha_entities:
            ent_part = _clean(ent_id.replace("camera.", ""))
            ent_tokens = set(ent_part.split("_")) - {"camera", "cam", "tuya"}
            if norm_tokens and (norm_tokens.issubset(ent_tokens) or ent_tokens.issubset(norm_tokens) or len(norm_tokens & ent_tokens) >= 2):
                return ent_id
        return None

    ha_cams = [
        "camera.camera_exterieur_piscine",
        "camera.solar_wall_light_camera",
        "camera.entree_rochegude",
        "camera.camera_rochegude_chambre",
        "camera.camera_rochegude_salon",
        "camera.lampe_d_exterieur_intelligente_avec_camera",
        "camera.camera_rochegude_cuisine",
    ]

    assert match("Caméra extérieur Piscine", ha_cams) == "camera.camera_exterieur_piscine"
    assert match("Solar Wall Light Camera", ha_cams) == "camera.solar_wall_light_camera"
    assert match("Caméra Entrée Rochegude", ha_cams) == "camera.entree_rochegude"
    assert match("Caméra Rochegude Chambre", ha_cams) == "camera.camera_rochegude_chambre"
    assert match("Caméra Rochegude Salon", ha_cams) == "camera.camera_rochegude_salon"
    assert match("Lampe d'extérieur intelligente avec caméra", ha_cams) == "camera.lampe_d_exterieur_intelligente_avec_camera"
    assert match("Caméra Rochegude cuisine", ha_cams) == "camera.camera_rochegude_cuisine"

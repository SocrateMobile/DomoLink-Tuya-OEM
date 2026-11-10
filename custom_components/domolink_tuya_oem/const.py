"""Constants for the DomoLink Tuya OEM Multi-Brand integration."""
from __future__ import annotations

DOMAIN = "domolink_tuya_oem"

CONF_MODE = "mode"
MODE_MOBILE = "mobile"
MODE_LOCAL = "local"
MODE_CLOUD = "cloud"

CONF_BRAND = "brand"
CONF_SCHEMA = "schema"
CONF_CLIENT_ID = "client_id"
CONF_SECRET = "secret"
CONF_ENDPOINT = "endpoint"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_COUNTRY_CODE = "country_code"
DEFAULT_COUNTRY_CODE = "33"

# Local parameters
CONF_LOCAL_KEY = "local_key"
CONF_DEVICE_ID = "device_id"
CONF_IP_ADDRESS = "ip_address"
CONF_PROTOCOL_VERSION = "protocol_version"
CONF_DEVICE_NAME = "device_name"

DEFAULT_SCAN_INTERVAL = 30  # seconds

ENDPOINTS = {
    "Europe (openapi.tuyaeu.com)": "https://openapi.tuyaeu.com",
    "Amérique de l'Ouest (openapi.tuyaus.com)": "https://openapi.tuyaus.com",
    "Chine (openapi.tuyacn.com)": "https://openapi.tuyacn.com",
    "Inde (openapi.tuyain.com)": "https://openapi.tuyain.com",
}

DEFAULT_ENDPOINT = "https://openapi.tuyaeu.com"

# Verified profiles extracted directly from official APKs
OEM_PROFILES = {
    "smartlife": {
        "name": "Smart Life (Officiel)",
        "package": "com.tuya.smartlife",
        "schema": "smartlife",
        "client_id": "ekmnwp9f5pnh3trdtpgy",
        "secret": "r3me7ghmxjevrvnpemwmhw3fxtacphyg",
        "cert_sha256": "0FC361999CC0C35BA8ACA57DAA5593A20CF55727702EA85AD7B3228949F888FE",
        "app_key": "jfg5rs5kkmrj5mxahugvucrsvw43t48x",
        "app_version": "7.10.0",
        "endpoint": "https://openapi.tuyaeu.com",
        "mobile_endpoint": "https://a1.tuyaeu.com/api.json",
        "icon": "mdi:home-variant",
    },
    "tuya": {
        "name": "Tuya Smart (Officiel)",
        "package": "com.tuya.smart",
        "schema": "tuyaSmart",
        "client_id": "3cxxt3au9x33ytvq3h9j",
        "secret": "5gdtanjtf38vyxkqh87cjwfcqjhvjjqa",
        "cert_sha256": "93219FC273E2200F4ADEE5F7191DC656BA2A2D7B2FF5D24CD55C4B6155001E40",
        "app_key": "f3hd7pet4p83kemjdf5wqsa5tavrv579",
        "app_version": "7.8.6",
        "endpoint": "https://openapi.tuyaeu.com",
        "mobile_endpoint": "https://a1.tuyaeu.com/api.json",
        "icon": "mdi:alpha-t-box-outline",
    },
    "thanks": {
        "name": "Thank's (GiFi)",
        "package": "com.thanksapp.iot",
        "schema": "thanksapp",
        "client_id": "vaxqcygqh45jhwrgqpg5",
        "secret": "37y7m7vtsmn43ph3x7ycw4nxjxcr584g",
        "cert_sha256": "DE0F6F2789A5B0FAAD5698C8847F3B692308AA0169E8D18F80A1E738FC195330",
        "endpoint": "https://openapi.tuyaeu.com",
        "mobile_endpoint": "https://a1.tuyaeu.com/api.json",
        "icon": "mdi:tag-outline",
    },
    "lidlhome": {
        "name": "Lidl Home (Silvercrest)",
        "package": "com.lidlhome.smart",
        "schema": "lidlhomesmart",
        "client_id": "svxtw3yqrwjffa5feuay",
        "secret": "fsdcqh5x3cg7myd4he4kssuedmskx33y",
        "cert_sha256": "7542F822ABBA5F2587A26700DF2DC22A838765D3F576421553554BE3E1638535",
        "endpoint": "https://openapi.tuyaeu.com",
        "mobile_endpoint": "https://a1.tuyaeu.com/api.json",
        "icon": "mdi:cart-outline",
    },
    "lsc": {
        "name": "Action LSC Smart Connect",
        "package": "com.lscsmartconnection.smart",
        "schema": "lscsmartconnectionsmart",
        "client_id": "dyxemkghc8tf87e734k5",
        "secret": "g38mujuhpsm5dfmvhpf9tqkw4afxtpah",
        "endpoint": "https://openapi.tuyaeu.com",
        "mobile_endpoint": "https://a1.tuyaeu.com/api.json",
        "icon": "mdi:lightning-bolt",
    },
    "nedis": {
        "name": "Nedis SmartLife",
        "package": "com.nedis.smartlife",
        "schema": "nedissmartlife",
        "client_id": "t7qgunvv93xqepedahy7",
        "secret": "f4n4jv3rtnmay4rq4prv7yjgueh8s5du",
        "endpoint": "https://openapi.tuyaeu.com",
        "mobile_endpoint": "https://a1.tuyaeu.com/api.json",
        "icon": "mdi:home-automation",
    },
    "calex": {
        "name": "Calex Smart",
        "package": "com.calexsmart.smart",
        "schema": "calexsmartsmart",
        "client_id": "pjgwupckwfm7vqync49e",
        "secret": "4wssns9rujvw4hverrkwam5xqf7gf77e",
        "endpoint": "https://openapi.tuyaeu.com",
        "mobile_endpoint": "https://a1.tuyaeu.com/api.json",
        "icon": "mdi:lightbulb-outline",
    },
    "konyks": {
        "name": "Konyks",
        "package": "com.konyks",
        "schema": "konyks",
        "client_id": "yattjtvf9anwcqse7ks9",
        "secret": "pjwwv8qrsmaccukh87uy4qq3jvnfsw8g",
        "endpoint": "https://openapi.tuyaeu.com",
        "mobile_endpoint": "https://a1.tuyaeu.com/api.json",
        "icon": "mdi:home-circle-outline",
    },
    "custom": {
        "name": "Autre marque OEM (Personnalisé)",
        "package": "",
        "schema": "",
        "client_id": "",
        "secret": "",
        "endpoint": "https://openapi.tuyaeu.com",
        "mobile_endpoint": "https://a1.tuyaeu.com/api.json",
        "icon": "mdi:cog-outline",
    },
}

PLATFORMS = [
    "switch",
    "light",
    "cover",
    "climate",
    "sensor",
    "binary_sensor",
]

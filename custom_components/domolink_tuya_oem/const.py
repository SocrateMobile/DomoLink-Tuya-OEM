"""Constants for the DomoLink Tuya OEM Multi-Brand integration."""
from __future__ import annotations

DOMAIN = "domolink_tuya_oem"

CONF_BRAND = "brand"
CONF_SCHEMA = "schema"
CONF_CLIENT_ID = "client_id"
CONF_SECRET = "secret"
CONF_ENDPOINT = "endpoint"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_COUNTRY_CODE = "country_code"

DEFAULT_COUNTRY_CODE = "33"
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
    "thanks": {
        "name": "Thank's (GiFi)",
        "package": "com.thanksapp.iot",
        "schema": "thanksapp",
        "client_id": "rhue3uvjcger7gsjtshf",
        "secret": "mvr4sg7a7hhmwdgepdpfk8t7hndyucye",
        "endpoint": "https://openapi.tuyaeu.com",
        "icon": "mdi:tag-outline",
    },
    "lidlhome": {
        "name": "Lidl Home (Silvercrest)",
        "package": "com.lidlhome.smart",
        "schema": "lidlhomesmart",
        "client_id": "svxtw3yqrwjffa5feuay",
        "secret": "fsdcqh5x3cg7myd4he4kssuedmskx33y",
        "endpoint": "https://openapi.tuyaeu.com",
        "icon": "mdi:cart-outline",
    },
    "lsc": {
        "name": "Action LSC Smart Connect",
        "package": "com.lscsmartconnection.smart",
        "schema": "lscsmartconnectionsmart",
        "client_id": "dyxemkghc8tf87e734k5",
        "secret": "g38mujuhpsm5dfmvhpf9tqkw4afxtpah",
        "endpoint": "https://openapi.tuyaeu.com",
        "icon": "mdi:lightning-bolt",
    },
    "nedis": {
        "name": "Nedis SmartLife",
        "package": "com.nedis.smartlife",
        "schema": "nedissmartlife",
        "client_id": "t7qgunvv93xqepedahy7",
        "secret": "f4n4jv3rtnmay4rq4prv7yjgueh8s5du",
        "endpoint": "https://openapi.tuyaeu.com",
        "icon": "mdi:home-automation",
    },
    "calex": {
        "name": "Calex Smart",
        "package": "com.calexsmart.smart",
        "schema": "calexsmartsmart",
        "client_id": "pjgwupckwfm7vqync49e",
        "secret": "4wssns9rujvw4hverrkwam5xqf7gf77e",
        "endpoint": "https://openapi.tuyaeu.com",
        "icon": "mdi:lightbulb-outline",
    },
    "konyks": {
        "name": "Konyks",
        "package": "com.konyks",
        "schema": "konyks",
        "client_id": "yattjtvf9anwcqse7ks9",
        "secret": "pjwwv8qrsmaccukh87uy4qq3jvnfsw8g",
        "endpoint": "https://openapi.tuyaeu.com",
        "icon": "mdi:home-circle-outline",
    },
    "smartlife": {
        "name": "Smart Life (Officiel)",
        "package": "com.tuya.smartlife",
        "schema": "smartlife",
        "client_id": "7jmvqw774xmdem47xecv",
        "secret": "t78ygekcue9xgcmnffxntn8uc333sfk4",
        "endpoint": "https://openapi.tuyaeu.com",
        "icon": "mdi:home-variant",
    },
    "tuya": {
        "name": "Tuya Smart (Officiel)",
        "package": "com.tuya.smart",
        "schema": "tuyaSmart",
        "client_id": "dhjsvxcyvxkgw4a8p3ey",
        "secret": "dux4xnus7cd7tmfa9fjcjqt4978xwn8g",
        "endpoint": "https://openapi.tuyaeu.com",
        "icon": "mdi:alpha-t-box-outline",
    },
    "custom": {
        "name": "Autre marque OEM (Personnalisé)",
        "package": "",
        "schema": "",
        "client_id": "",
        "secret": "",
        "endpoint": "https://openapi.tuyaeu.com",
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

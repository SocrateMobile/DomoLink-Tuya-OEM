"""Tuya Cloud OpenAPI Client for DomoLink Tuya OEM."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import ipaddress
import json
import logging
import time
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)


def is_private_lan_ip(ip_str: str | None) -> bool:
    """Return True only if ip_str is a valid private IPv4 LAN address (10.x, 172.16-31.x, 192.168.x)."""
    if not ip_str or not isinstance(ip_str, str):
        return False
    try:
        ip_obj = ipaddress.ip_address(ip_str.strip())
        return (
            ip_obj.version == 4
            and ip_obj.is_private
            and not ip_obj.is_loopback
            and not ip_obj.is_unspecified
            and not ip_obj.is_link_local
        )
    except ValueError:
        return False


class TuyaOEMError(Exception):
    """Base exception for Tuya OEM client."""


class TuyaOEMAuthError(TuyaOEMError):
    """Authentication failed."""


class TuyaOEMBrandRestrictedError(TuyaOEMError):
    """OEM mobile gateway authentication is restricted by Tuya for this specific brand."""


class TuyaOEMClient:
    """Async API Client for Tuya Cloud OpenAPI."""

    def __init__(
        self,
        endpoint: str,
        client_id: str,
        secret: str,
        schema: str = "thanksapp",
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        """Initialize the client."""
        self.endpoint = endpoint.rstrip("/")
        self.client_id = client_id.strip()
        self.secret = secret.strip()
        self.schema = schema.strip()
        self._session = session
        self._own_session = False

        self.access_token: str | None = None
        self.refresh_token: str | None = None
        self.uid: str | None = None
        self.token_expire_time: float = 0

    async def _get_session(self) -> aiohttp.ClientSession:
        """Return aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
            self._own_session = True
        return self._session

    async def close(self) -> None:
        """Close session if owned."""
        if self._own_session and self._session and not self._session.closed:
            await self._session.close()

    def _calc_sign(
        self,
        method: str,
        path: str,
        body_str: str = "",
        token: str | None = None,
    ) -> tuple[str, str]:
        """Compute Tuya OpenAPI v2 signature."""
        t = str(int(time.time() * 1000))
        content_hash = hashlib.sha256(body_str.encode("utf-8")).hexdigest().lower()
        str_to_sign = f"{method.upper()}\n{content_hash}\n\n{path}"

        token_part = token if token else ""
        sign_payload = f"{self.client_id}{token_part}{t}{str_to_sign}"

        sign = (
            hmac.new(
                self.secret.encode("utf-8"),
                msg=sign_payload.encode("utf-8"),
                digestmod=hashlib.sha256,
            )
            .hexdigest()
            .upper()
        )
        return sign, t

    async def get_access_token(self) -> dict[str, Any]:
        """Fetch developer access token from Tuya Cloud."""
        session = await self._get_session()
        path = "/v1.0/token?grant_type=1"
        url = f"{self.endpoint}{path}"

        sign, t = self._calc_sign("GET", path, body_str="", token=None)
        headers = {
            "client_id": self.client_id,
            "sign": sign,
            "t": t,
            "sign_method": "HMAC-SHA256",
            "Content-Type": "application/json",
        }

        try:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                data = await resp.json(content_type=None)
                if not data.get("success", False):
                    code = data.get("code")
                    msg = data.get("msg", "Unknown error")
                    _LOGGER.error("Erreur obtention Token Tuya (Code %s): %s", code, msg)
                    if code == 1004:
                        raise TuyaOEMAuthError(
                            "Signature invalide (Code 1004). Vérifiez attentivement votre Access ID et Access Secret."
                        )
                    raise TuyaOEMAuthError(f"Erreur d'authentification Tuya (Code {code}): {msg}")

                res = data.get("result", {})
                self.access_token = res.get("access_token")
                self.refresh_token = res.get("refresh_token")
                self.uid = res.get("uid")
                expire_in = res.get("expire_time", 7200)
                self.token_expire_time = time.time() + expire_in - 300
                _LOGGER.info("Token Tuya obtenu avec succès (UID: %s)", self.uid)
                return res
        except (TuyaOEMError, TuyaOEMAuthError):
            raise
        except asyncio.TimeoutError as err:
            raise TuyaOEMError("Délai d'attente dépassé (timeout) vers Tuya Cloud.") from err
        except aiohttp.ClientError as err:
            raise TuyaOEMError(f"Erreur réseau lors de la connexion à Tuya Cloud: {err}") from err

    async def request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
    ) -> Any:
        """Send authenticated request to Tuya OpenAPI."""
        if not self.access_token or time.time() > self.token_expire_time:
            await self.get_access_token()

        session = await self._get_session()

        query_str = ""
        if params:
            sorted_params = sorted(params.items())
            query_str = "?" + "&".join(f"{k}={v}" for k, v in sorted_params)

        full_path = f"{path}{query_str}"
        url = f"{self.endpoint}{full_path}"

        body_str = json.dumps(data) if data is not None else ""
        sign, t = self._calc_sign(method, full_path, body_str=body_str, token=self.access_token)

        req_headers = {
            "client_id": self.client_id,
            "access_token": self.access_token,
            "sign": sign,
            "t": t,
            "sign_method": "HMAC-SHA256",
            "Content-Type": "application/json",
        }

        try:
            async with session.request(
                method,
                url,
                headers=req_headers,
                data=body_str if body_str else None,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                resp_json = await resp.json(content_type=None)
                if not resp_json.get("success", False):
                    code = resp_json.get("code")
                    msg = resp_json.get("msg", "Unknown error")
                    _LOGGER.warning("Tuya Cloud API error %s: %s (path: %s)", code, msg, path)
                    if code in (1010, 1011, 1012):
                        self.access_token = None
                    raise TuyaOEMError(f"Erreur Tuya {code}: {msg}")
                return resp_json.get("result", {})
        except asyncio.TimeoutError as err:
            raise TuyaOEMError("Délai d'attente dépassé (timeout)") from err
        except aiohttp.ClientError as err:
            raise TuyaOEMError(f"Erreur réseau: {err}") from err

    async def get_devices(self) -> list[dict[str, Any]]:
        """Fetch all devices linked to this project or user account."""
        devices: list[dict[str, Any]] = []

        # 1. First endpoint: Query devices directly linked to cloud project
        try:
            res = await self.request("GET", "/v1.0/devices", params={"page_no": 1, "page_size": 100})
            if isinstance(res, dict) and "devices" in res:
                devices.extend(res["devices"])
            elif isinstance(res, list):
                devices.extend(res)
        except Exception as err:
            _LOGGER.debug("Could not fetch /v1.0/devices: %s", err)

        # 2. Second endpoint: Query via /v1.0/iot-03/devices
        if not devices:
            try:
                res = await self.request("GET", "/v1.0/iot-03/devices", params={"page_no": 1, "page_size": 100})
                if isinstance(res, dict) and "list" in res:
                    devices.extend(res["list"])
            except Exception as err:
                _LOGGER.debug("Could not fetch /v1.0/iot-03/devices: %s", err)

        # 3. Third endpoint: Query via linked user UID
        if not devices and self.uid:
            try:
                res = await self.request("GET", f"/v1.0/users/{self.uid}/devices")
                if isinstance(res, list):
                    devices.extend(res)
                elif isinstance(res, dict) and "devices" in res:
                    devices.extend(res["devices"])
            except Exception as err:
                _LOGGER.debug("Could not fetch /v1.0/users/{uid}/devices: %s", err)

        _LOGGER.info("Total appareils Tuya découverts : %d", len(devices))
        return devices

    async def get_device_status(self, device_id: str) -> list[dict[str, Any]]:
        """Fetch real-time data points (DPs) status of a device."""
        try:
            res = await self.request("GET", f"/v1.0/devices/{device_id}/status")
            if isinstance(res, list):
                return res
            return []
        except Exception as err:
            _LOGGER.debug("Could not fetch /v1.0/devices/{id}/status: %s", err)
            try:
                res = await self.request("GET", f"/v1.0/iot-03/devices/{device_id}/status")
                if isinstance(res, list):
                    return res
            except Exception:
                pass
            return []

    async def send_command(self, device_id: str, commands: list[dict[str, Any]]) -> bool:
        """Send command execution to a device."""
        try:
            res = await self.request(
                "POST",
                f"/v1.0/devices/{device_id}/commands",
                data={"commands": commands},
            )
            return bool(res)
        except Exception as err:
            _LOGGER.debug("Could not send /v1.0/devices/{id}/commands: %s", err)
            try:
                res = await self.request(
                    "POST",
                    f"/v1.0/iot-03/devices/{device_id}/commands",
                    data={"commands": commands},
                )
                return bool(res)
            except Exception as e:
                _LOGGER.error("Failed to send command to device %s: %s", device_id, e)
                return False

    async def get_camera_stream_url(self, device_id: str) -> str | None:
        """Fetch live stream URL via Cloud OpenAPI."""
        try:
            res = await self.request("POST", f"/v1.0/devices/{device_id}/stream/actions/allocate")
            if isinstance(res, dict):
                return res.get("url") or res.get("rtsp") or res.get("hls")
        except Exception as e:
            _LOGGER.debug("Cloud stream allocation error for %s: %s", device_id, e)
        return None


class TuyaOEMMobileClient:
    """Async client imitating smartphone app connection via Tuya Mobile Gateway."""

    def __init__(
        self,
        brand_key: str,
        username: str,
        password: str,
        country_code: str = "33",
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        """Initialize mobile client."""
        self.brand_key = brand_key
        self.username = username.strip()
        self.password = password
        self.country_code = country_code.strip()
        self._session = session
        self._own_session = False
        self._client: Any = None
        self.session_data: Any = None
        self.devices: list[dict[str, Any]] = []

    async def _get_session(self) -> aiohttp.ClientSession:
        """Return aiohttp session with proper SSL CA certificates."""
        if self._session is None or self._session.closed:
            import certifi
            import ssl

            ssl_context = ssl.create_default_context(cafile=certifi.where())
            connector = aiohttp.TCPConnector(ssl=ssl_context)
            self._session = aiohttp.ClientSession(connector=connector)
            self._own_session = True
        return self._session

    async def close(self) -> None:
        """Close owned session."""
        if self._own_session and self._session and not self._session.closed:
            await self._session.close()

    async def login(self) -> dict[str, Any]:
        """Authenticate user with email and password imitating mobile app."""
        from tuya_mobile import TuyaMobileApp, TuyaMobileAppProfile, TuyaPasswordClient
        from tuya_mobile.errors import TuyaMobileError, TuyaMobileInvalidAuth

        from .const import OEM_PROFILES

        session = await self._get_session()
        profile_data = OEM_PROFILES.get(self.brand_key, OEM_PROFILES["smartlife"])

        if self.brand_key == "tuya":
            client = TuyaPasswordClient.for_application(
                TuyaMobileApp.TUYA_SMART,
                session,
                username=self.username,
                endpoint="https://a1.tuyaeu.com/api.json",
            )
        elif self.brand_key == "smartlife":
            client = TuyaPasswordClient.for_application(
                TuyaMobileApp.SMART_LIFE,
                session,
                username=self.username,
                endpoint="https://a1.tuyaeu.com/api.json",
            )
        else:
            # Custom OEM Profile (Thank's, Lidl, LSC, etc.)
            custom_prof = TuyaMobileAppProfile(
                name=profile_data["name"],
                app_id=profile_data["client_id"],
                app_secret=profile_data["secret"],
                cert_sha256_hex=profile_data.get(
                    "cert_sha256",
                    "0FC361999CC0C35BA8ACA57DAA5593A20CF55727702EA85AD7B3228949F888FE",
                ),
                app_key=profile_data.get("app_key", profile_data["client_id"]),
                package=profile_data["package"],
                app_version=profile_data.get("app_version", "3.1.1"),
                ttid=profile_data.get("ttid", f"sdk_international@{profile_data['client_id']}"),
                sdk_version="5.24.0",
                device_core_version="5.17.0",
                os_system="14",
                platform="Android",
                channel="sdk",
                endpoints=profile_data.get(
                    "endpoints",
                    (
                        "https://a1.tuyaeu.com/api.json",
                        "https://a1.tuyaus.com/api.json",
                        "https://a1-sg.iotbing.com/api.json",
                        "https://a1.tuyacn.com/api.json",
                        "https://a1.tuyain.com/api.json",
                    ),
                ),
            )
            client = TuyaPasswordClient(
                custom_prof,
                session,
                username=self.username,
                endpoint=profile_data.get("mobile_endpoint", "https://a1.tuyaeu.com/api.json"),
            )

        self._client = client
        try:
            mobile_session = await client.login_with_password(self.password, self.country_code)
            self.session_data = mobile_session
            _LOGGER.info(
                "Connexion Mobile Tuya réussie pour %s (UID: %s, Endpoint: %s)",
                self.username,
                mobile_session.uid,
                mobile_session.endpoint,
            )
            return {
                "uid": mobile_session.uid,
                "sid": mobile_session.sid,
                "endpoint": mobile_session.endpoint,
            }
        except TuyaMobileInvalidAuth as err:
            _LOGGER.error("Identifiants mobiles invalides pour %s: %s", self.username, err)
            raise TuyaOEMAuthError(f"Identifiants mobiles incorrects: {err}") from err
        except TuyaMobileError as err:
            err_msg = str(err)
            cause_str = str(getattr(err, "__cause__", ""))
            combined = f"{err_msg} {cause_str}"
            if (
                "ILLEGAL_CLIENT_ID" in combined
                or "TuyaMobileProfileExpired" in str(type(err))
                or "Invalid client" in combined
            ):
                _LOGGER.warning("Accès API mobile verrouillé pour %s (%s): %s", self.brand_key, profile_data.get("name"), err)
                raise TuyaOEMBrandRestrictedError(
                    f"L'accès mobile direct pour {profile_data.get('name', self.brand_key)} est verrouillé par Tuya. "
                    "Conseil : Vos appareils Lidl Silvercrest sont 100% compatibles Tuya et peuvent être appairés directement dans Smart Life ou Tuya Smart pour être synchronisés automatiquement."
                ) from err
            _LOGGER.error("Erreur passerelle mobile Tuya: %s", err)
            raise TuyaOEMError(f"Erreur passerelle mobile: {err}") from err
        except Exception as err:
            _LOGGER.exception("Exception inattendue lors de la connexion mobile Tuya: %s", err)
            raise TuyaOEMError(f"Erreur de connexion mobile: {err}") from err

    async def get_devices(self) -> list[dict[str, Any]]:
        """Fetch all user devices and their local keys via Mobile session."""
        from tuya_mobile.password_client import _walk

        for attempt in range(2):
            if not self._client or not self.session_data:
                await self.login()

            discovered: dict[str, dict[str, Any]] = {}

            # 1. Query homes and group device lists
            try:
                home_apis = ["m.life.home.space.list", "tuya.m.home.space.list", "m.life.home.list"]
                homes_raw = None
                for api in home_apis:
                    try:
                        homes_raw = await self._client._call(api, {})
                        if homes_raw:
                            break
                    except Exception as e:
                        _LOGGER.debug("API %s: %s", api, e)

                gids: set[Any] = set()
                if homes_raw:
                    for obj in _walk(homes_raw):
                        gid = obj.get("gid") or obj.get("groupId") or obj.get("homeId") or obj.get("id")
                        if gid and str(gid).isdigit():
                            gids.add(gid)

                device_apis = [
                    ("m.life.my.group.device.list", "2.2"),
                    ("m.life.my.group.device.list", "2.0"),
                    ("thing.m.my.group.device.list", "1.0"),
                    ("tuya.m.my.group.device.list", "1.0"),
                ]

                target_gids = list(gids) if gids else [0]
                for gid in target_gids:
                    for api, ver in device_apis:
                        try:
                            payload = {"gid": gid, "homeId": gid} if gid else {}
                            resp = await self._client._call(api, payload, version=ver)
                            if resp:
                                for obj in _walk(resp):
                                    dev_id = obj.get("devId") or obj.get("deviceId") or obj.get("id")
                                    if dev_id and isinstance(dev_id, str) and len(dev_id) >= 10:
                                        if dev_id not in discovered:
                                            p_bean = obj.get("productBean") or {}
                                            cat = obj.get("category") or p_bean.get("category") or ""
                                            p_name = obj.get("productName") or p_bean.get("name") or f"{self.brand_key.upper()} Device"
                                            dps = obj.get("dps") or {}
                                            icon_url = obj.get("iconUrl") or obj.get("icon") or p_bean.get("iconUrl") or p_bean.get("icon") or ""
                                            dp_names = obj.get("dpName") or obj.get("dpsName") or {}
                                            schema_info = obj.get("schemaInfo") or p_bean.get("schemaInfo") or obj.get("schema")
                                            
                                            # Strict separation between private LAN IP and public WAN IP
                                            raw_lan = obj.get("lanIp") or obj.get("localIp")
                                            raw_wan = obj.get("ip")
                                            clean_lan = None
                                            clean_wan = None

                                            if is_private_lan_ip(raw_lan):
                                                clean_lan = raw_lan
                                            elif is_private_lan_ip(raw_wan):
                                                clean_lan = raw_wan

                                            if raw_wan and not is_private_lan_ip(raw_wan):
                                                clean_wan = raw_wan

                                            discovered[dev_id] = {
                                                "id": dev_id,
                                                "devId": dev_id,
                                                "name": obj.get("name") or obj.get("customName") or obj.get("devName") or f"Appareil {dev_id[:6]}",
                                                "local_key": obj.get("localKey") or obj.get("local_key") or obj.get("secKey"),
                                                "protocol_version": str(obj.get("pv") or obj.get("protocolVersion") or obj.get("version") or "3.3"),
                                                "ip": clean_lan,
                                                "wan_ip": clean_wan,
                                                "mac": obj.get("mac") or obj.get("macAddress"),
                                                "uuid": obj.get("uuid"),
                                                "category": cat,
                                                "product_name": p_name,
                                                "product_id": obj.get("productId") or p_bean.get("id"),
                                                "icon_url": icon_url,
                                                "dp_names": dp_names,
                                                "schema_info": schema_info,
                                                "online": obj.get("isOnline") if "isOnline" in obj else obj.get("cloudOnline", True),
                                                "dps": dps,
                                            }
                        except Exception as dev_err:
                            _LOGGER.debug("API %s (ver %s, gid %s) error: %s", api, ver, gid, dev_err)
            except Exception as e:
                _LOGGER.debug("Direct mobile device traversal failed (tentative %d): %s", attempt + 1, e)

            # 2. Enrich missing local keys or fallback to get_local_keys
            missing_local_keys = not discovered or any(not d.get("local_key") for d in discovered.values())
            if missing_local_keys:
                try:
                    records = await self._client.get_local_keys([])
                    for r in records:
                        dev_id = r.get("device_id")
                        if not dev_id:
                            continue
                        raw_ip = r.get("ip")
                        clean_lan = raw_ip if is_private_lan_ip(raw_ip) else None
                        clean_wan = raw_ip if (raw_ip and not clean_lan) else None

                        if dev_id in discovered:
                            if not discovered[dev_id].get("local_key") and r.get("local_key"):
                                discovered[dev_id]["local_key"] = r["local_key"]
                            if not discovered[dev_id].get("ip") and clean_lan:
                                discovered[dev_id]["ip"] = clean_lan
                        else:
                            discovered[dev_id] = {
                                "id": dev_id,
                                "devId": dev_id,
                                "name": r.get("name", f"Appareil {dev_id[:6]}"),
                                "local_key": r.get("local_key"),
                                "protocol_version": str(r.get("protocol_version") or "3.3"),
                                "ip": clean_lan,
                                "wan_ip": clean_wan,
                                "uuid": r.get("uuid"),
                                "online": r.get("is_online", True),
                                "product_name": f"{self.brand_key.upper()} Device",
                                "category": "",
                                "dps": {},
                            }
                except Exception as e:
                    _LOGGER.debug("get_local_keys enrichment: %s", e)

            if discovered:
                self.devices = list(discovered.values())
                _LOGGER.info(
                    "Découverte mobile %s : %d appareil(s) trouvé(s)",
                    self.brand_key,
                    len(self.devices),
                )
                return self.devices

            # If discovered is empty on first attempt, reset session and force re-login on second attempt
            if attempt == 0:
                _LOGGER.info("Session mobile potentiellement expirée pour %s, ré-authentification en cours...", self.brand_key)
                self.session_data = None
                self._client = None

        if self.devices:
            _LOGGER.warning(
                "Mise à jour mobile temporairement indisponible pour %s, conservation des %d appareils actifs",
                self.brand_key,
                len(self.devices),
            )
            return self.devices

        return []

    async def get_device_status(self, device_id: str) -> dict[str, Any]:
        """Fetch status of device via mobile API."""
        if not self._client:
            await self.login()
        try:
            res = await self._client.get_device_status(device_id)
            dps: dict[str, Any] = {}
            if isinstance(res, dict):
                raw_dps = res.get("dps") or res.get("result", {}).get("dps") or {}
                if isinstance(raw_dps, dict):
                    return raw_dps
            return dps
        except Exception as err:
            _LOGGER.debug("Could not fetch mobile status for %s: %s", device_id, err)
            return {}

    async def send_command(self, device_id: str, commands: list[dict[str, Any]]) -> bool:
        """Send command via mobile API."""
        if not self._client:
            await self.login()
        try:
            dps_payload = {str(c["code"]): c["value"] for c in commands}
            await self._client.publish_dps(device_id, dps_payload)
            return True
        except Exception as err:
            err_msg = str(err)
            if "DEVICE_OFFLINE" in err_msg or "offline" in err_msg.lower():
                _LOGGER.warning("Appareil %s hors ligne (DEVICE_OFFLINE), commande non transmise", device_id)
            else:
                _LOGGER.error("Erreur lors de l'envoi de la commande mobile pour %s: %s", device_id, err)
            return False

    async def get_camera_stream_url(self, device_id: str) -> str | None:
        """Retrieve live RTSP or HLS stream URL for a camera device."""
        if not self._client:
            await self.login()
        for api in (
            "m.ipc.v4.rtc.config.get",
            "thing.m.rtc.config.get",
            "m.ipc.media.stream.allocate",
            "tuya.m.ipc.stream.url.get",
            "m.ipc.stream.get",
            "thing.m.ipc.stream.get",
        ):
            try:
                res = await self._client._call(api, {"devId": device_id, "deviceId": device_id})
                if isinstance(res, dict):
                    url = (
                        res.get("url")
                        or res.get("rtsp")
                        or res.get("hls")
                        or res.get("live_url")
                        or res.get("streamUrl")
                        or res.get("result", {}).get("url")
                    )
                    if url and isinstance(url, str):
                        return url
            except Exception as e:
                _LOGGER.debug("API %s for camera %s returned: %s", api, device_id, e)
        return None

    async def get_camera_snapshot_url(self, device_id: str) -> str | None:
        """Retrieve latest snapshot URL for a camera."""
        if not self._client:
            await self.login()
        for api in ("m.ipc.camera.cover.get", "thing.m.security.camera.cover.get"):
            try:
                res = await self._client._call(api, {"devId": device_id, "deviceId": device_id})
                if isinstance(res, dict):
                    cover = res.get("cover") or res.get("imageUrl") or res.get("coverUrl") or res.get("result", {}).get("cover")
                    if cover and isinstance(cover, str):
                        return cover
            except Exception as e:
                _LOGGER.debug("Snapshot API %s for camera %s returned: %s", api, device_id, e)
        return None

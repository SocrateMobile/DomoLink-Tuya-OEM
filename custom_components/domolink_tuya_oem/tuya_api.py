"""Tuya Cloud OpenAPI Client for DomoLink Tuya OEM."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import time
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)


class TuyaOEMError(Exception):
    """Base exception for Tuya OEM client."""


class TuyaOEMAuthError(TuyaOEMError):
    """Authentication failed."""


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

"""Tuya OEM Cloud OpenAPI Client."""
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
    """Async API Client for Tuya OEM Cloud services."""

    def __init__(
        self,
        endpoint: str,
        client_id: str,
        secret: str,
        schema: str,
        username: str,
        password: str,
        country_code: str = "33",
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        """Initialize the client."""
        self.endpoint = endpoint.rstrip("/")
        self.client_id = client_id
        self.secret = secret
        self.schema = schema
        self.username = username
        self.password = password
        self.country_code = country_code
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
        headers: dict[str, str],
        body: str = "",
        token: str | None = None,
        timestamp: str | None = None,
    ) -> tuple[str, str]:
        """Compute Tuya OpenAPI v2 signature."""
        t = timestamp or str(int(time.time() * 1000))
        content_hash = hashlib.sha256((body or "").encode("utf-8")).hexdigest()

        # Extract signed headers if needed
        sign_headers_str = ""
        if "Signature-Headers" in headers:
            keys = headers["Signature-Headers"].split(":")
            for k in keys:
                if k in headers:
                    sign_headers_str += f"{k}:{headers[k]}\n"

        string_to_sign = f"{method.upper()}\n{content_hash}\n{sign_headers_str}\n{path}"
        token_part = token if token else ""
        sign_payload = f"{self.client_id}{token_part}{t}{string_to_sign}"

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

    async def request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        require_auth: bool = True,
    ) -> dict[str, Any]:
        """Send authenticated request to Tuya OpenAPI."""
        if require_auth and (not self.access_token or time.time() > self.token_expire_time):
            await self.login()

        session = await self._get_session()

        query_str = ""
        if params:
            sorted_params = sorted(params.items())
            query_str = "?" + "&".join(f"{k}={v}" for k, v in sorted_params)

        full_path = f"{path}{query_str}"
        url = f"{self.endpoint}{full_path}"

        body_str = json.dumps(data) if data is not None else ""
        token = self.access_token if require_auth else None

        req_headers: dict[str, str] = {
            "Content-Type": "application/json",
            "client_id": self.client_id,
            "sign_method": "HMAC-SHA256",
        }

        sign, t = self._calc_sign(method, full_path, req_headers, body=body_str, token=token)
        req_headers["sign"] = sign
        req_headers["t"] = t
        if token:
            req_headers["access_token"] = token

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
                    _LOGGER.warning("Tuya OEM API error %s: %s (path: %s)", code, msg, path)
                    # If token expired, clear token
                    if code in (1010, 1011, 1012):
                        self.access_token = None
                    raise TuyaOEMError(f"API Error {code}: {msg}")
                return resp_json.get("result", {})
        except asyncio.TimeoutError as err:
            raise TuyaOEMError("Tuya API request timeout") from err
        except aiohttp.ClientError as err:
            raise TuyaOEMError(f"Tuya API client network error: {err}") from err

    async def login(self) -> dict[str, Any]:
        """Authenticate user against Tuya OEM Cloud."""
        _LOGGER.debug("Logging in user %s (schema: %s)", self.username, self.schema)
        # 1. First attempt: Direct user login via mobile gateway (/v1.0/iot-03/users/login)
        # Password may be sent plain or sha256 depending on schema backend
        pass_hash = hashlib.sha256(self.password.encode("utf-8")).hexdigest()

        # Tuya supports either MD5, SHA256 or clear password. We try SHA256 first.
        body = {
            "country_code": self.country_code,
            "username": self.username,
            "password": pass_hash,
            "schema": self.schema,
        }

        try:
            res = await self.request(
                "POST",
                "/v1.0/iot-03/users/login",
                data=body,
                require_auth=False,
            )
            self.access_token = res.get("access_token")
            self.refresh_token = res.get("refresh_token")
            self.uid = res.get("uid")
            expire_in = res.get("expire_time", 7200)
            self.token_expire_time = time.time() + expire_in - 300
            _LOGGER.info("Successfully logged in Tuya OEM user (UID: %s)", self.uid)
            return res
        except TuyaOEMError as err:
            _LOGGER.debug("SHA256 user login failed (%s), trying plaintext password...", err)
            # Try plain text password fallback
            try:
                body["password"] = self.password
                res = await self.request(
                    "POST",
                    "/v1.0/iot-03/users/login",
                    data=body,
                    require_auth=False,
                )
                self.access_token = res.get("access_token")
                self.refresh_token = res.get("refresh_token")
                self.uid = res.get("uid")
                expire_in = res.get("expire_time", 7200)
                self.token_expire_time = time.time() + expire_in - 300
                _LOGGER.info("Successfully logged in Tuya OEM user via fallback (UID: %s)", self.uid)
                return res
            except Exception as e:
                _LOGGER.error("Tuya OEM user login failed: %s", e)
                raise TuyaOEMAuthError(f"Échec de connexion au compte {self.schema}: {e}") from e

    async def get_devices(self) -> list[dict[str, Any]]:
        """Fetch all devices linked to this user account."""
        if not self.uid:
            await self.login()

        devices: list[dict[str, Any]] = []

        # 1. Query user devices
        try:
            res = await self.request("GET", f"/v1.0/users/{self.uid}/devices")
            if isinstance(res, list):
                devices.extend(res)
            elif isinstance(res, dict) and "devices" in res:
                devices.extend(res["devices"])
        except Exception as err:
            _LOGGER.debug("Could not fetch from /v1.0/users/{uid}/devices: %s", err)

        # 2. Query iot-03 devices fallback
        if not devices:
            try:
                res = await self.request("GET", "/v1.0/iot-03/devices", params={"page_no": 1, "page_size": 100})
                if isinstance(res, dict) and "list" in res:
                    devices.extend(res["list"])
            except Exception as err:
                _LOGGER.debug("Could not fetch from /v1.0/iot-03/devices: %s", err)

        _LOGGER.info("Found %d devices for user %s", len(devices), self.username)
        return devices

    async def get_device_status(self, device_id: str) -> list[dict[str, Any]]:
        """Fetch real-time data points (DPs) status of a device."""
        try:
            res = await self.request("GET", f"/v1.0/iot-03/devices/{device_id}/status")
            if isinstance(res, list):
                return res
            return []
        except Exception as err:
            _LOGGER.warning("Failed to fetch status for %s: %s", device_id, err)
            return []

    async def send_command(self, device_id: str, commands: list[dict[str, Any]]) -> bool:
        """Send command execution to a device."""
        try:
            res = await self.request(
                "POST",
                f"/v1.0/iot-03/devices/{device_id}/commands",
                data={"commands": commands},
            )
            return bool(res)
        except Exception as err:
            _LOGGER.error("Failed to send command to device %s: %s", device_id, err)
            return False

"""Local LAN Tuya Protocol Client for DomoLink Tuya OEM."""
from __future__ import annotations

import asyncio
from datetime import datetime
import hashlib
import json
import logging
import socket
import struct
import time
from typing import Any

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

import threading
from typing import Callable

try:
    import tinytuya
    HAS_TINYTUYA = True
except ImportError:
    tinytuya = None
    HAS_TINYTUYA = False

_LOGGER = logging.getLogger(__name__)

UDP_KEY = hashlib.md5(b"yGAdlopoPVldABfn").digest()
PREFIX_55AA = 0x000055AA
SUFFIX_AA55 = 0x0000AA55
PREFIX_6699 = 0x00006699
SUFFIX_9966 = 0x00009966

CMD_CONTROL = 0x07
CMD_STATUS = 0x08
CMD_HEARTBEAT = 0x09
CMD_DP_QUERY = 0x0A
CMD_UPDATEDPS = 0x12


def decrypt_udp_packet(raw_data: bytes) -> dict[str, Any] | None:
    """Decrypt and parse a UDP broadcast packet from a local Tuya device (encrypted 6667 or raw 6666)."""
    if len(raw_data) < 16:
        return None

    # 1. Try raw JSON parse first (protocol 3.1 or unencrypted broadcast)
    try:
        start_idx = raw_data.find(b"{")
        end_idx = raw_data.rfind(b"}")
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            data = json.loads(raw_data[start_idx : end_idx + 1].decode("utf-8", errors="ignore"))
            if isinstance(data, dict) and ("gwId" in data or "devId" in data or "ip" in data):
                return data
    except Exception:
        pass

    # 2. Encrypted packet check (starts with 0x000055AA or 0x00006699)
    try:
        prefix = struct.unpack(">I", raw_data[:4])[0]
        if prefix not in (PREFIX_55AA, PREFIX_6699):
            return None

        # Payload is either offset 20 or 16 depending on retcode
        for offset in (20, 16):
            if len(raw_data) <= offset + 8:
                continue
            payload = raw_data[offset:-8]
            if len(payload) % 16 == 0 and len(payload) >= 16:
                cipher = Cipher(algorithms.AES(UDP_KEY), modes.ECB(), backend=default_backend())
                dec = cipher.decryptor()
                decrypted = dec.update(payload) + dec.finalize()
                pad = decrypted[-1]
                if 1 <= pad <= 16:
                    decrypted = decrypted[:-pad]
                try:
                    dec_str = decrypted.decode("utf-8", errors="ignore")
                    start_idx = dec_str.find("{")
                    end_idx = dec_str.rfind("}")
                    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                        data = json.loads(dec_str[start_idx : end_idx + 1])
                        if isinstance(data, dict) and ("ip" in data or "gwId" in data or "devId" in data):
                            return data
                except Exception:
                    pass
    except Exception as err:
        _LOGGER.debug("UDP packet decode error: %s", err)
    return None


async def async_discover_devices(timeout: float = 3.0) -> dict[str, dict[str, Any]]:
    """Scan local network on UDP 6667 and 6666 to discover active Tuya/OEM devices."""
    loop = asyncio.get_running_loop()

    def _scan_udp() -> dict[str, dict[str, Any]]:
        discovered: dict[str, dict[str, Any]] = {}
        sockets: list[socket.socket] = []

        for port in (6667, 6666):
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                if hasattr(socket, "SO_REUSEPORT"):
                    try:
                        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
                    except Exception:
                        pass
                s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                s.bind(("", port))
                s.setblocking(False)
                sockets.append(s)
            except Exception as err:
                _LOGGER.debug("Could not bind UDP discovery socket on port %d: %s", port, err)

        if not sockets:
            return discovered

        import select
        start = time.time()
        while time.time() - start < timeout:
            try:
                readable, _, _ = select.select(sockets, [], [], 0.4)
                for s in readable:
                    try:
                        data, addr = s.recvfrom(4096)
                        parsed = decrypt_udp_packet(data)
                        if parsed and ("gwId" in parsed or "devId" in parsed):
                            dev_id = parsed.get("gwId") or parsed.get("devId")
                            if dev_id and dev_id not in discovered:
                                discovered[dev_id] = {
                                    "id": dev_id,
                                    "ip": parsed.get("ip", addr[0]),
                                    "version": str(parsed.get("version", "3.3")),
                                    "productKey": parsed.get("productKey", ""),
                                }
                    except Exception:
                        pass
            except Exception:
                pass

        for s in sockets:
            try:
                s.close()
            except Exception:
                pass

        return discovered

    return await loop.run_in_executor(None, _scan_udp)


class TuyaLocalDevice:
    """Client for controlling a single Tuya device via Local LAN with multi-protocol support (3.1 to 3.5)."""

    def __init__(
        self,
        device_id: str,
        ip: str,
        local_key: str,
        version: str = "3.3",
        port: int = 6668,
    ) -> None:
        """Initialize local device."""
        self.device_id = device_id
        self.ip = ip
        self.local_key = local_key.encode("utf-8") if isinstance(local_key, str) else local_key
        self.version = str(version)
        self.port = port
        self.seq = 0
        self.dps: dict[str, Any] = {}
        self._push_thread: threading.Thread | None = None
        self._push_running = False

        # Tinytuya Device initialization for 3.1, 3.2, 3.3, 3.4, and 3.5
        self._tt_dev: Any = None
        if HAS_TINYTUYA and tinytuya is not None:
            try:
                raw_key = self.local_key.decode("utf-8", errors="ignore") if isinstance(self.local_key, bytes) else str(self.local_key)
                tt_ver = 3.3
                try:
                    tt_ver = float(self.version)
                except ValueError:
                    tt_ver = 3.3
                self._tt_dev = tinytuya.Device(
                    dev_id=self.device_id,
                    address=self.ip,
                    local_key=raw_key,
                    version=tt_ver,
                )
                self._tt_dev.set_socketTimeout(1.2)
                self._tt_dev.set_socketRetryLimit(1)
            except Exception as e:
                _LOGGER.debug("tinytuya init notice for %s: %s", self.device_id, e)
                self._tt_dev = None

    @property
    def is_connected(self) -> bool:
        """Return True if local device is configured with a valid private LAN IP."""
        return bool(self.ip and is_private_lan_ip(self.ip))

    def _pack_message(self, cmd: int, payload_bytes: bytes) -> bytes:
        """Build binary frame for Tuya protocol 3.1/3.3/3.4."""
        self.seq += 1
        msg_len = len(payload_bytes) + 8  # 4 bytes CRC + 4 bytes suffix
        header = struct.pack(">IIII", PREFIX_55AA, self.seq, cmd, msg_len)

        import binascii
        crc_val = binascii.crc32(header + payload_bytes) & 0xFFFFFFFF
        crc = struct.pack(">I", crc_val)
        suffix = struct.pack(">I", SUFFIX_AA55)
        return header + payload_bytes + crc + suffix

    def _encrypt_payload(self, data_dict: dict[str, Any]) -> bytes:
        """Encrypt payload for Tuya protocol (3.1 or 3.3)."""
        json_bytes = json.dumps(data_dict, separators=(",", ":")).encode("utf-8")
        if self.version == "3.1":
            return json_bytes

        # PKCS7 padding for AES-128-ECB
        pad_len = 16 - (len(json_bytes) % 16)
        padded = json_bytes + bytes([pad_len] * pad_len)

        cipher = Cipher(algorithms.AES(self.local_key), modes.ECB(), backend=default_backend())
        enc = cipher.encryptor()
        encrypted = enc.update(padded) + enc.finalize()

        # Prefix with version 3.3 header
        return b"3.3" + b"\x00" * 12 + encrypted

    def _decrypt_payload(self, raw_resp: bytes) -> dict[str, Any] | None:
        """Decrypt Tuya protocol frame and return JSON payload dict."""
        if len(raw_resp) < 16:
            return None

        # Check for unencrypted JSON inside the frame
        try:
            start_idx = raw_resp.find(b"{")
            end_idx = raw_resp.rfind(b"}")
            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                parsed = json.loads(raw_resp[start_idx : end_idx + 1].decode("utf-8", errors="ignore"))
                if isinstance(parsed, dict):
                    return parsed
        except Exception:
            pass

        # Try decrypting AES payload at offset 20 or 16
        for offset in (20, 16):
            if len(raw_resp) <= offset + 8:
                continue
            enc_data = raw_resp[offset:-8]
            # Strip protocol version prefix if present
            if enc_data.startswith(b"3.3"):
                enc_data = enc_data[15:] if len(enc_data) >= 15 and enc_data[3:15] == b"\x00" * 12 else enc_data[3:]
                while len(enc_data) % 16 != 0 and enc_data and enc_data[0] == 0:
                    enc_data = enc_data[1:]

            if len(enc_data) >= 16 and len(enc_data) % 16 == 0:
                try:
                    cipher = Cipher(algorithms.AES(self.local_key), modes.ECB(), backend=default_backend())
                    dec = cipher.decryptor()
                    decrypted = dec.update(enc_data) + dec.finalize()
                    pad = decrypted[-1]
                    if 1 <= pad <= 16:
                        decrypted = decrypted[:-pad]
                    dec_str = decrypted.decode("utf-8", errors="ignore")
                    s_idx = dec_str.find("{")
                    e_idx = dec_str.rfind("}")
                    if s_idx != -1 and e_idx != -1 and e_idx > s_idx:
                        res = json.loads(dec_str[s_idx : e_idx + 1])
                        if isinstance(res, dict):
                            return res
                except Exception:
                    continue
        return None

    def _send_native(self, dps_update: dict[str, Any]) -> bool:
        """Native socket implementation for sending Tuya commands."""
        now = int(time.time())
        payload_dict = {
            "gwId": self.device_id,
            "devId": self.device_id,
            "uid": self.device_id,
            "t": str(now),
            "dps": dps_update,
        }

        s: socket.socket | None = None
        try:
            enc_payload = self._encrypt_payload(payload_dict)
            frame = self._pack_message(CMD_CONTROL, enc_payload)

            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(1.2)
            s.connect((self.ip, self.port))
            s.sendall(frame)
            resp = s.recv(1024)
            self.dps.update(dps_update)
            return True
        except Exception as err:
            _LOGGER.debug("Local command error on %s (%s): %s", self.device_id, self.ip, err)
            return False
        finally:
            if s:
                try:
                    s.close()
                except Exception:
                    pass

    async def async_send_command(self, commands: list[dict[str, Any]]) -> bool:
        """Send command to device over local TCP with tinytuya (3.1-3.5) and native fallback."""
        loop = asyncio.get_running_loop()
        dps_update = {str(c["code"]): c["value"] for c in commands}

        if self._tt_dev is not None:
            def _send_tt() -> bool:
                try:
                    res = self._tt_dev.set_multiple_values(dps_update)
                    if isinstance(res, dict) and "Error" in res:
                        _LOGGER.debug("tinytuya send noticed error on %s, trying native: %s", self.ip, res.get("Error"))
                        return self._send_native(dps_update)
                    self.dps.update(dps_update)
                    return True
                except Exception:
                    return self._send_native(dps_update)

            return await loop.run_in_executor(None, _send_tt)

        return await loop.run_in_executor(None, self._send_native, dps_update)

    def _poll_native(self) -> dict[str, Any]:
        """Native socket implementation for polling Tuya status."""
        now = int(time.time())
        payload_dict = {
            "gwId": self.device_id,
            "devId": self.device_id,
            "uid": self.device_id,
            "t": str(now),
            "dps": {},
        }
        s: socket.socket | None = None
        try:
            enc_payload = self._encrypt_payload(payload_dict)
            frame = self._pack_message(CMD_DP_QUERY, enc_payload)

            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(1.2)
            s.connect((self.ip, self.port))
            s.sendall(frame)
            resp = s.recv(2048)

            parsed = self._decrypt_payload(resp)
            if parsed and "dps" in parsed and isinstance(parsed["dps"], dict):
                self.dps.update(parsed["dps"])
        except Exception as err:
            _LOGGER.debug("Local poll error on %s: %s", self.ip, err)
        finally:
            if s:
                try:
                    s.close()
                except Exception:
                    pass
        return self.dps

    async def async_poll_status(self) -> dict[str, Any]:
        """Poll DPS status from device over local TCP (tinytuya 3.1-3.5 + native fallback)."""
        loop = asyncio.get_running_loop()

        if self._tt_dev is not None:
            def _poll_tt() -> dict[str, Any]:
                # Try preferred protocol version first, then fallback across 3.3, 3.1, 3.4
                versions_to_try: list[float] = []
                try:
                    versions_to_try.append(float(self.version))
                except ValueError:
                    pass
                for v in (3.3, 3.1, 3.4, 3.5):
                    if v not in versions_to_try:
                        versions_to_try.append(v)

                for v in versions_to_try:
                    try:
                        self._tt_dev.set_version(v)
                        res = self._tt_dev.status()
                        if isinstance(res, dict) and "dps" in res and isinstance(res["dps"], dict) and res["dps"]:
                            self.version = str(v)
                            self.dps.update(res["dps"])
                            return self.dps
                    except Exception:
                        continue

                return self._poll_native()

            return await loop.run_in_executor(None, _poll_tt)

        return await loop.run_in_executor(None, self._poll_native)

    def start_push_listener(
        self,
        loop: asyncio.AbstractEventLoop,
        callback: Callable[[dict[str, Any]], None],
    ) -> None:
        """Start background listening thread for real-time unsolicited push packets."""
        if self._push_thread is not None or self._tt_dev is None:
            return
        self._push_running = True
        self._push_thread = threading.Thread(
            target=self._run_push_listener,
            args=(loop, callback),
            daemon=True,
            name=f"TuyaPush_{self.device_id[:6]}",
        )
        self._push_thread.start()

    def stop_push_listener(self) -> None:
        """Stop real-time push listener and close socket."""
        self._push_running = False
        if self._tt_dev is not None:
            try:
                self._tt_dev.close()
            except Exception:
                pass
        if self._push_thread and self._push_thread.is_alive():
            self._push_thread.join(timeout=0.5)
            self._push_thread = None

    def close(self) -> None:
        """Close connection and stop any running thread."""
        self.stop_push_listener()

    def _run_push_listener(
        self,
        loop: asyncio.AbstractEventLoop,
        callback: Callable[[dict[str, Any]], None],
    ) -> None:
        """Worker loop reading pushed packets from device over persistent connection."""
        if not self._tt_dev:
            return
        try:
            self._tt_dev.set_socketPersistent(True)
        except Exception:
            pass

        while self._push_running:
            try:
                msg = self._tt_dev.receive()
                if isinstance(msg, dict) and "dps" in msg and isinstance(msg["dps"], dict) and msg["dps"]:
                    self.dps.update(msg["dps"])
                    loop.call_soon_threadsafe(callback, msg["dps"])
            except Exception:
                time.sleep(1.0)


class TuyaLocalDiscoveryListener:
    """Continuous background UDP listener for Tuya local broadcasts (ports 6667 and 6666)."""

    def __init__(self, loop: asyncio.AbstractEventLoop, callback: Callable[[str, str, str], None]) -> None:
        """Initialize background discovery listener."""
        self.loop = loop
        self.callback = callback
        self._thread: threading.Thread | None = None
        self._running = False

    def start(self) -> None:
        """Start discovery thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._run,
            daemon=True,
            name="TuyaLocalDiscoveryListener",
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop discovery thread."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
            self._thread = None

    def _run(self) -> None:
        """Thread worker loop selecting on UDP ports 6667 and 6666."""
        sockets: list[socket.socket] = []
        for port in (6667, 6666):
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                if hasattr(socket, "SO_REUSEPORT"):
                    try:
                        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
                    except Exception:
                        pass
                s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                s.bind(("", port))
                s.setblocking(False)
                sockets.append(s)
            except Exception as err:
                _LOGGER.debug("Could not bind background discovery on port %d: %s", port, err)

        if not sockets:
            _LOGGER.debug("TuyaLocalDiscoveryListener: No UDP sockets could be bound")
            return

        import select
        while self._running:
            try:
                readable, _, _ = select.select(sockets, [], [], 1.0)
                for s in readable:
                    try:
                        data, addr = s.recvfrom(4096)
                        parsed = decrypt_udp_packet(data)
                        if parsed and ("gwId" in parsed or "devId" in parsed):
                            dev_id = str(parsed.get("gwId") or parsed.get("devId"))
                            ip = str(parsed.get("ip") or addr[0])
                            ver = str(parsed.get("version", "3.3"))
                            if dev_id and ip:
                                self.loop.call_soon_threadsafe(self.callback, dev_id, ip, ver)
                    except Exception:
                        pass
            except Exception:
                pass

        for s in sockets:
            try:
                s.close()
            except Exception:
                pass


async def async_validate_ip(
    device_id: str,
    ip: str,
    local_key: str,
    version: str = "3.3",
    timeout: float = 0.8,
) -> bool:
    """Cryptographically validate that an IP belongs to device_id using its local_key."""
    try:
        dev = TuyaLocalDevice(
            device_id=device_id,
            ip=ip,
            local_key=local_key,
            version=version,
        )
        dps = await asyncio.wait_for(dev.async_poll_status(), timeout=timeout)
        return bool(dps) or (len(dev.dps) > 0)
    except Exception:
        return False


async def async_scan_subnet_for_device(
    device_id: str,
    local_key: str,
    candidate_ips: list[str],
    version: str = "3.3",
    concurrency: int = 32,
) -> str | None:
    """Probe candidate IPs on port 6668 in parallel and return the cryptographically verified IP."""
    if not candidate_ips:
        return None

    semaphore = asyncio.Semaphore(concurrency)

    async def _probe(ip: str) -> str | None:
        async with semaphore:
            # 1. Fast TCP handshake check (0.25s)
            try:
                _, writer = await asyncio.wait_for(
                    asyncio.open_connection(ip, 6668),
                    timeout=0.25,
                )
                writer.close()
                await writer.wait_closed()
            except Exception:
                return None

            # 2. Cryptographic payload validation with local_key
            valid = await async_validate_ip(device_id, ip, local_key, version=version, timeout=0.8)
            if valid:
                return ip
            return None

    tasks = [asyncio.create_task(_probe(ip)) for ip in candidate_ips]
    for fut in asyncio.as_completed(tasks):
        try:
            res = await fut
            if res:
                for t in tasks:
                    if not t.done():
                        t.cancel()
                return res
        except Exception:
            pass

    return None

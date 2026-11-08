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

_LOGGER = logging.getLogger(__name__)

UDP_KEY = hashlib.md5(b"yGAdlopoPVldABfn").digest()
PREFIX_55AA = 0x000055AA
SUFFIX_AA55 = 0x0000AA55

CMD_CONTROL = 0x07
CMD_STATUS = 0x08
CMD_HEARTBEAT = 0x09
CMD_DP_QUERY = 0x0A
CMD_UPDATEDPS = 0x12


def decrypt_udp_packet(raw_data: bytes) -> dict[str, Any] | None:
    """Decrypt and parse a UDP broadcast packet from a local Tuya device."""
    if len(raw_data) < 24:
        return None
    try:
        prefix = struct.unpack(">I", raw_data[:4])[0]
        if prefix != PREFIX_55AA:
            return None

        # Payload is either offset 20 or 16 depending on retcode
        for offset in (20, 16):
            payload = raw_data[offset:-8]
            if len(payload) % 16 == 0:
                cipher = Cipher(algorithms.AES(UDP_KEY), modes.ECB(), backend=default_backend())
                dec = cipher.decryptor()
                decrypted = dec.update(payload) + dec.finalize()
                pad = decrypted[-1]
                if 1 <= pad <= 16:
                    decrypted = decrypted[:-pad]
                try:
                    data = json.loads(decrypted.decode("utf-8", errors="ignore"))
                    if isinstance(data, dict) and "ip" in data and "gwId" in data:
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
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

        try:
            sock.bind(("", 6667))
            sock.settimeout(0.5)
            start = time.time()
            while time.time() - start < timeout:
                try:
                    data, addr = sock.recvfrom(4096)
                    parsed = decrypt_udp_packet(data)
                    if parsed and "gwId" in parsed:
                        dev_id = parsed["gwId"]
                        if dev_id not in discovered:
                            discovered[dev_id] = {
                                "id": dev_id,
                                "ip": parsed.get("ip", addr[0]),
                                "version": parsed.get("version", "3.3"),
                                "productKey": parsed.get("productKey", ""),
                            }
                except socket.timeout:
                    pass
        except Exception as err:
            _LOGGER.debug("Error while scanning local Tuya devices: %s", err)
        finally:
            sock.close()
        return discovered

    return await loop.run_in_executor(None, _scan_udp)


class TuyaLocalDevice:
    """Client for controlling a single Tuya device via Local LAN."""

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
        self.local_key = local_key.encode("utf-8")
        self.version = version
        self.port = port
        self.seq = 0
        self.dps: dict[str, Any] = {}

    def _pack_message(self, cmd: int, payload_bytes: bytes) -> bytes:
        """Build binary frame for Tuya protocol 3.3/3.4."""
        self.seq += 1
        msg_len = len(payload_bytes) + 8  # 4 bytes CRC + 4 bytes suffix
        header = struct.pack(">IIII", PREFIX_55AA, self.seq, cmd, msg_len)

        # CRC32 of header + payload
        crc = struct.pack(">I", 0)  # Simple zero crc or standard crc32
        import binascii
        crc_val = binascii.crc32(header + payload_bytes) & 0xFFFFFFFF
        crc = struct.pack(">I", crc_val)
        suffix = struct.pack(">I", SUFFIX_AA55)
        return header + payload_bytes + crc + suffix

    def _encrypt_payload_33(self, data_dict: dict[str, Any]) -> bytes:
        """Encrypt payload for Tuya protocol 3.3."""
        json_data = json.dumps(data_dict, separators=(",", ":")).encode("utf-8")
        # PKCS7 padding
        pad_len = 16 - (len(json_data) % 16)
        padded = json_data + bytes([pad_len] * pad_len)

        cipher = Cipher(algorithms.AES(self.local_key), modes.ECB(), backend=default_backend())
        enc = cipher.encryptor()
        encrypted = enc.update(padded) + enc.finalize()

        # Prefix with version if protocol 3.3
        return b"3.3" + b"\x00" * 12 + encrypted

    async def async_send_command(self, commands: list[dict[str, Any]]) -> bool:
        """Send command to device over local TCP."""
        loop = asyncio.get_running_loop()

        def _send() -> bool:
            # Build DPS dictionary
            dps_update = {str(c["code"]): c["value"] for c in commands}
            now = int(time.time())
            payload_dict = {
                "gwId": self.device_id,
                "devId": self.device_id,
                "uid": self.device_id,
                "t": str(now),
                "dps": dps_update,
            }

            try:
                enc_payload = self._encrypt_payload_33(payload_dict)
                frame = self._pack_message(CMD_CONTROL, enc_payload)

                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(3.0)
                s.connect((self.ip, self.port))
                s.sendall(frame)
                # Read response
                resp = s.recv(1024)
                s.close()
                self.dps.update(dps_update)
                return True
            except Exception as err:
                _LOGGER.error("Failed to send local command to %s (%s): %s", self.device_id, self.ip, err)
                return False

        return await loop.run_in_executor(None, _send)

    async def async_poll_status(self) -> dict[str, Any]:
        """Poll DPS status from device over local TCP."""
        loop = asyncio.get_running_loop()

        def _poll() -> dict[str, Any]:
            now = int(time.time())
            payload_dict = {
                "gwId": self.device_id,
                "devId": self.device_id,
                "uid": self.device_id,
                "t": str(now),
                "dps": {},
            }
            try:
                enc_payload = self._encrypt_payload_33(payload_dict)
                frame = self._pack_message(CMD_DP_QUERY, enc_payload)

                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(3.0)
                s.connect((self.ip, self.port))
                s.sendall(frame)
                resp = s.recv(2048)
                s.close()

                if len(resp) > 28:
                    # Decrypt response
                    enc_data = resp[20:-8]
                    if len(enc_data) % 16 == 0:
                        cipher = Cipher(algorithms.AES(self.local_key), modes.ECB(), backend=default_backend())
                        dec = cipher.decryptor()
                        decrypted = dec.update(enc_data) + dec.finalize()
                        pad = decrypted[-1]
                        if 1 <= pad <= 16:
                            decrypted = decrypted[:-pad]
                        try:
                            res_json = json.loads(decrypted.decode("utf-8", errors="ignore"))
                            if "dps" in res_json:
                                self.dps.update(res_json["dps"])
                        except Exception:
                            pass
            except Exception as err:
                _LOGGER.debug("Local poll error on %s: %s", self.ip, err)
            return self.dps

        return await loop.run_in_executor(None, _poll)

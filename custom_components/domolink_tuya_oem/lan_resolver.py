"""Intelligent LAN IP Resolver with multi-stage cascade discovery for Tuya OEM devices."""
from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from typing import TYPE_CHECKING, Any

try:
    from .tuya_api import is_private_lan_ip
    from .tuya_local import (
        TuyaLocalDevice,
        TuyaLocalDiscoveryListener,
        async_discover_devices,
        async_scan_subnet_for_device,
        async_validate_ip,
    )
except (ImportError, ValueError):
    from tuya_api import is_private_lan_ip
    from tuya_local import (
        TuyaLocalDevice,
        TuyaLocalDiscoveryListener,
        async_discover_devices,
        async_scan_subnet_for_device,
        async_validate_ip,
    )

if TYPE_CHECKING:
    from .coordinator import TuyaOEMDataCoordinator

_LOGGER = logging.getLogger(__name__)


def normalize_mac(mac: str | None) -> str:
    """Normalize MAC address string to lowercase alphanumeric representation."""
    if not mac:
        return ""
    return re.sub(r"[^0-9a-fA-F]", "", str(mac)).lower()


def read_system_arp_table() -> dict[str, str]:
    """Read local system ARP table and return mapping of normalized MAC -> IP."""
    arp_map: dict[str, str] = {}

    # 1. Linux /proc/net/arp (standard in Home Assistant OS and Docker)
    if os.path.exists("/proc/net/arp"):
        try:
            with open("/proc/net/arp", "r", encoding="ascii", errors="ignore") as f:
                lines = f.readlines()[1:]  # skip header
                for line in lines:
                    parts = line.split()
                    if len(parts) >= 4:
                        ip = parts[0]
                        mac = normalize_mac(parts[3])
                        if mac and mac != "000000000000" and is_private_lan_ip(ip):
                            arp_map[mac] = ip
            if arp_map:
                return arp_map
        except Exception as e:
            _LOGGER.debug("Could not read /proc/net/arp: %s", e)

    # 2. Fallback using 'arp -an' command (macOS / BSD / Linux fallback)
    try:
        import subprocess

        output = subprocess.check_output(["arp", "-an"], text=True, stderr=subprocess.DEVNULL)
        for line in output.splitlines():
            # Matches formats like: ? (192.168.1.42) at d8:f1:5b:12:34:56 on en0 ...
            match = re.search(r"\(([\d\.]+)\)\s+at\s+([0-9a-fA-F:]+)", line)
            if match:
                ip = match.group(1)
                mac = normalize_mac(match.group(2))
                if mac and is_private_lan_ip(ip):
                    arp_map[mac] = ip
    except Exception as e:
        _LOGGER.debug("Could not read ARP table via command: %s", e)

    return arp_map


class LanResolver:
    """Orchestrates multi-stage LAN discovery: UDP passive -> ARP table -> TCP Subnet scan."""

    def __init__(self, coordinator: TuyaOEMDataCoordinator) -> None:
        """Initialize LAN resolver."""
        self.coordinator = coordinator
        self.hass = coordinator.hass
        self._listener: TuyaLocalDiscoveryListener | None = None
        self._failed_attempts: dict[str, int] = {}
        self._last_attempt: dict[str, float] = {}
        self._resolution_methods: dict[str, str] = {}  # "udp", "arp", "scan", "manual"
        self._last_verified: dict[str, float] = {}

    def get_device_lan_info(self, device_id: str) -> dict[str, Any]:
        """Return diagnostic LAN status for a device."""
        dev = self.coordinator.devices.get(device_id) or self.coordinator.data.get(device_id) or {}
        ip = dev.get("ip") or ""
        lan_active = bool(dev.get("lan_active", False))
        return {
            "device_id": device_id,
            "ip": ip,
            "lan_active": lan_active,
            "method": self._resolution_methods.get(device_id, "unknown" if ip else "none"),
            "last_verified": self._last_verified.get(device_id),
            "failed_attempts": self._failed_attempts.get(device_id, 0),
        }

    def get_device_lan_status(self, device_id: str) -> dict[str, Any]:
        """Alias for get_device_lan_info for backward compatibility."""
        return self.get_device_lan_info(device_id)

    def start_udp_listener(self) -> None:
        """Start background continuous UDP discovery listener."""
        if self._listener is None and self.hass:
            self._listener = TuyaLocalDiscoveryListener(
                self.hass.loop,
                self._handle_udp_broadcast,
            )
            self._listener.start()

    def stop_udp_listener(self) -> None:
        """Stop background UDP discovery listener."""
        if self._listener is not None:
            self._listener.stop()
            self._listener = None

    def _handle_udp_broadcast(self, dev_id: str, ip: str, version: str) -> None:
        """Callback when a Tuya device announces itself on UDP."""
        if not is_private_lan_ip(ip):
            return

        dev = self.coordinator.devices.get(dev_id) or self.coordinator.data.get(dev_id)
        if not dev:
            return

        local_key = dev.get("local_key")
        if not local_key:
            return

        self._bind_device(dev_id, ip, local_key, version, method="udp")

    def _bind_device(
        self,
        dev_id: str,
        ip: str,
        local_key: str,
        version: str = "3.3",
        method: str = "udp",
    ) -> None:
        """Register local device and persist IP override."""
        current_local = self.coordinator.local_devices.get(dev_id)
        if current_local is None or current_local.ip != ip:
            dev_name = self.coordinator.devices.get(dev_id, {}).get("name", dev_id)
            _LOGGER.info(
                "Liaison LAN locale réussie pour %s (%s, IP: %s, méthode: %s, v%s)",
                dev_name,
                dev_id,
                ip,
                method,
                version,
            )
            if current_local:
                try:
                    current_local.close()
                except Exception:
                    pass

            new_local = TuyaLocalDevice(
                device_id=dev_id,
                ip=ip,
                local_key=local_key,
                version=version,
            )
            self.coordinator.local_devices[dev_id] = new_local
            if self.hass:
                new_local.start_push_listener(
                    self.hass.loop,
                    lambda dps, d_id=dev_id: self.coordinator._handle_local_device_push(d_id, dps),
                )
            self._resolution_methods[dev_id] = method
            self._last_verified[dev_id] = time.time()
            self._failed_attempts[dev_id] = 0

            # Update devices and data dicts
            if dev_id in self.coordinator.devices:
                self.coordinator.devices[dev_id]["ip"] = ip
                self.coordinator.devices[dev_id]["lan_active"] = True

            if self.coordinator.data and dev_id in self.coordinator.data:
                self.coordinator.data[dev_id]["ip"] = ip
                self.coordinator.data[dev_id]["lan_active"] = True
                self.coordinator.async_set_updated_data(self.coordinator.data)

            if self.hass:
                self.hass.async_create_task(
                    self.coordinator.async_save_device_override(dev_id, {"ip": ip})
                )

    async def async_resolve_missing_ips(self, force: bool = False) -> int:
        """Run multi-stage resolution for all devices currently missing a verified LAN IP."""
        devices = self.coordinator.devices or self.coordinator.data or {}
        missing_devs: list[dict[str, Any]] = []

        now = time.time()
        for dev_id, dev in devices.items():
            if dev_id in self.coordinator.local_devices and not force:
                continue

            local_key = dev.get("local_key")
            if not local_key:
                continue

            # Exponential backoff for sleeping/battery or unreachable devices
            failed = self._failed_attempts.get(dev_id, 0)
            last_att = self._last_attempt.get(dev_id, 0)
            if not force and failed >= 3 and (now - last_att) < 3600:
                continue

            missing_devs.append(dev)

        if not missing_devs:
            return 0

        resolved_count = 0

        # --- ÉTAPE 1 : Découverte passive UDP (rapide 1.5s) ---
        try:
            discovered = await async_discover_devices(timeout=1.5)
            for d in list(missing_devs):
                d_id = d["id"]
                if d_id in discovered:
                    info = discovered[d_id]
                    self._bind_device(
                        d_id,
                        info["ip"],
                        d["local_key"],
                        version=info.get("version", "3.3"),
                        method="udp",
                    )
                    missing_devs.remove(d)
                    resolved_count += 1
        except Exception as e:
            _LOGGER.debug("UDP discovery notice: %s", e)

        if not missing_devs:
            return resolved_count

        # --- ÉTAPE 2 : Correspondance ARP via adresse MAC ---
        try:
            arp_table = await self.hass.async_add_executor_job(read_system_arp_table)
            for d in list(missing_devs):
                d_id = d["id"]
                mac = normalize_mac(d.get("mac"))
                if mac and mac in arp_table:
                    candidate_ip = arp_table[mac]
                    # Cryptographic verification with local key
                    valid = await async_validate_ip(
                        d_id,
                        candidate_ip,
                        d["local_key"],
                        version=str(d.get("protocol_version") or "3.3"),
                        timeout=0.8,
                    )
                    if valid:
                        self._bind_device(
                            d_id,
                            candidate_ip,
                            d["local_key"],
                            version=str(d.get("protocol_version") or "3.3"),
                            method="arp",
                        )
                        missing_devs.remove(d)
                        resolved_count += 1
        except Exception as e:
            _LOGGER.debug("ARP resolution notice: %s", e)

        if not missing_devs:
            return resolved_count

        # --- ÉTAPE 3 : Scan TCP ciblé du sous-réseau local ---
        candidate_subnets = self._get_candidate_subnets()
        for subnet_ips in candidate_subnets:
            for d in list(missing_devs):
                d_id = d["id"]
                self._last_attempt[d_id] = time.time()
                try:
                    found_ip = await async_scan_subnet_for_device(
                        device_id=d_id,
                        local_key=d["local_key"],
                        candidate_ips=subnet_ips,
                        version=str(d.get("protocol_version") or "3.3"),
                    )
                    if found_ip:
                        self._bind_device(
                            d_id,
                            found_ip,
                            d["local_key"],
                            version=str(d.get("protocol_version") or "3.3"),
                            method="scan",
                        )
                        missing_devs.remove(d)
                        resolved_count += 1
                    else:
                        self._failed_attempts[d_id] = self._failed_attempts.get(d_id, 0) + 1
                except Exception as e:
                    _LOGGER.debug("Subnet scan error for %s: %s", d_id, e)

        return resolved_count

    def _get_candidate_subnets(self) -> list[list[str]]:
        """Compute list of /24 IP ranges to probe based on known IPs and network adapters."""
        known_ips: set[str] = set()
        devices = self.coordinator.devices or self.coordinator.data or {}
        for dev in devices.values():
            ip = dev.get("ip")
            if is_private_lan_ip(ip):
                known_ips.add(ip)

        for dev in self.coordinator.local_devices.values():
            if is_private_lan_ip(dev.ip):
                known_ips.add(dev.ip)

        subnets_found: set[str] = set()
        for ip in known_ips:
            parts = ip.split(".")
            if len(parts) == 4:
                prefix = f"{parts[0]}.{parts[1]}.{parts[2]}"
                subnets_found.add(prefix)

        # Fallback to standard RFC1918 home subnets if none detected yet
        subnets_found.add("192.168.1")
        subnets_found.add("192.168.0")

        # Generate all 1-254 addresses for each detected prefix (capped to /24)
        result: list[list[str]] = []
        for prefix in subnets_found:
            ips = [f"{prefix}.{i}" for i in range(1, 255)]
            result.append(ips)

        return result

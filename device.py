"""Device discovery, connection, handshake, and reconnect handling via hidapi."""

import time
import logging
from typing import Any, Dict, List, Optional

import hid

from config import DEFAULT_SWITCH_PID, DEFAULT_SWITCH_VID, KNOWN_CLONE_IDS, BridgeConfig
from protocol import (
    NEUTRAL_RUMBLE,
    OUTPUT_REPORT_RUMBLE_AND_SUBCMD,
    OUTPUT_REPORT_USB_CMD,
    SUBCMD_ENABLE_VIBRATION,
    SUBCMD_SET_INPUT_REPORT_MODE,
    SUBCMD_SET_PLAYER_LIGHTS,
    REPORT_MODE_STANDARD_FULL,
    USB_HANDSHAKE_EN_USB,
    USB_HANDSHAKE_INIT,
    USB_HANDSHAKE_STATUS,
    USB_HANDSHAKE_TIMEOUT,
)
from rumble import build_rumble_packet

logger = logging.getLogger("GamepadBridge.Device")


def enumerate_all_hid() -> List[Dict[str, Any]]:
    """Enumerate all connected HID devices."""
    try:
        return hid.enumerate()
    except Exception as e:
        logger.error(f"Failed to enumerate HID devices: {e}")
        return []


def is_gamepad_or_joystick(d: Dict[str, Any]) -> bool:
    """Checks if a device looks like a game controller based on HID Usage or known clones."""
    usage_page = d.get("usage_page", 0)
    usage = d.get("usage", 0)
    vid = d.get("vendor_id", 0)
    pid = d.get("product_id", 0)

    # Standard HID Usage Page 0x01 (Generic Desktop), Usage 0x04 (Joystick) or 0x05 (Gamepad)
    if usage_page == 0x01 and usage in (0x04, 0x05, 0x08):
        return True

    # Known Switch or clone VID/PID
    for known_vid, known_pid, _ in KNOWN_CLONE_IDS:
        if vid == known_vid and pid == known_pid:
            return True

    # Check product string heuristics
    prod_name = (d.get("product_string") or "").lower()
    if any(k in prod_name for k in ("controller", "gamepad", "joystick", "switch", "pro con")):
        return True

    return False


def find_target_device(vid: int, pid: int, path: Optional[bytes] = None) -> Optional[Dict[str, Any]]:
    """Find a connected device matching VID/PID or specific path."""
    devices = enumerate_all_hid()
    if path:
        for d in devices:
            if d.get("path") == path:
                return d

    # Find matching VID and PID
    for d in devices:
        if d.get("vendor_id") == vid and d.get("product_id") == pid:
            return d

    return None


def list_connected_gamepads() -> List[Dict[str, Any]]:
    """List all connected gamepads and potential controllers."""
    devices = enumerate_all_hid()
    seen_keys = set()
    controllers = []

    for d in devices:
        vid = d.get("vendor_id", 0)
        pid = d.get("product_id", 0)
        path = d.get("path")

        # Skip virtual devices or system mouse/keyboards unless matching gamepad usage
        if not is_gamepad_or_joystick(d):
            continue

        key = (vid, pid, path)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        controllers.append(d)

    return controllers


class ControllerDevice:
    """Manages raw HID communication, handshake, and auto-reconnect with a controller."""

    def __init__(self, config: BridgeConfig):
        self.config = config
        self.handle: Optional[hid.device] = None
        self.device_info: Optional[Dict[str, Any]] = None
        self._counter = 0

    @property
    def is_connected(self) -> bool:
        return self.handle is not None

    def open(self) -> bool:
        """Attempt to discover and open the controller HID handle."""
        target = find_target_device(
            self.config.vendor_id,
            self.config.product_id,
            self.config.device_path
        )

        if not target:
            return False

        try:
            handle = hid.device()
            if target.get("path"):
                handle.open_path(target["path"])
            else:
                handle.open(target["vendor_id"], target["product_id"])

            handle.set_nonblocking(True)
            self.handle = handle
            self.device_info = target

            vid = target.get("vendor_id", 0)
            pid = target.get("product_id", 0)
            prod = target.get("product_string") or "Generic Controller"
            mfr = target.get("manufacturer_string") or "Unknown"
            print(f"[Device] Connected: {mfr} {prod} (VID: 0x{vid:04X}, PID: 0x{pid:04X})")

            # Run handshake
            self.perform_handshake()
            return True

        except Exception as e:
            logger.warning(f"Failed to open device handle: {e}")
            if self.handle:
                try:
                    self.handle.close()
                except Exception:
                    pass
                self.handle = None
            return False

    def perform_handshake(self) -> None:
        """Attempt standard Switch Pro handshake (USB / BT) with graceful fallback."""
        if not self.handle:
            return

        is_usb = True
        if self.device_info and self.device_info.get("path"):
            path_str = str(self.device_info["path"]).lower()
            if "bth" in path_str or "bluetooth" in path_str:
                is_usb = False

        print(f"[Handshake] Initiating Switch Pro initialization ({'USB' if is_usb else 'Bluetooth'})...")

        # 1. USB initialization handshakes (if connected via USB)
        if is_usb:
            try:
                self._send_usb_command(USB_HANDSHAKE_STATUS)
                time.sleep(0.02)
                self._send_usb_command(USB_HANDSHAKE_EN_USB)
                time.sleep(0.02)
                self._send_usb_command(USB_HANDSHAKE_STATUS)
                time.sleep(0.02)
                self._send_usb_command(USB_HANDSHAKE_TIMEOUT)
                time.sleep(0.02)
            except Exception as e:
                logger.debug(f"USB command sequence skipped or not supported: {e}")

        # 2. Subcommand 0x03, 0x30: Request Standard Full 60Hz input reports
        try:
            self.send_subcommand(SUBCMD_SET_INPUT_REPORT_MODE, [REPORT_MODE_STANDARD_FULL])
            time.sleep(0.02)
            # Turn on Player 1 LED
            self.send_subcommand(SUBCMD_SET_PLAYER_LIGHTS, [0x01])
            time.sleep(0.02)
            # Enable vibration
            self.send_subcommand(SUBCMD_ENABLE_VIBRATION, [0x01])
            time.sleep(0.02)
            print("[Handshake] Subcommands sent successfully.")
        except Exception as e:
            print(f"[Handshake] Controller bypassed subcommands ({e}). DirectInput fallback active.")

    def _send_usb_command(self, cmd_bytes: bytes) -> None:
        """Send raw USB command report 0x80."""
        if not self.handle:
            return
        # Windows hidapi requires Report ID as first byte
        packet = bytes([OUTPUT_REPORT_USB_CMD]) + cmd_bytes
        # Pad to 64 bytes
        packet = packet.ljust(64, b"\x00")
        try:
            self.handle.write(packet)
        except Exception as e:
            logger.debug(f"Error writing USB command: {e}")

    def send_subcommand(self, subcommand: int, arguments: List[int]) -> bool:
        """Send a standard Switch Pro subcommand with neutral rumble data."""
        if not self.handle:
            return False

        self._counter = (self._counter + 1) & 0x0F

        # Packet layout:
        # Byte 0: Output Report ID (0x01)
        # Byte 1: Packet counter (0x00 - 0x0F)
        # Bytes 2-9: Neutral rumble
        # Byte 10: Subcommand
        # Bytes 11+: Subcommand arguments
        packet = bytearray()
        packet.append(OUTPUT_REPORT_RUMBLE_AND_SUBCMD)
        packet.append(self._counter)
        packet.extend(NEUTRAL_RUMBLE)
        packet.append(subcommand)
        packet.extend(arguments)

        # Pad to 49 or 64 bytes
        packet = packet.ljust(64, b"\x00")

        try:
            written = self.handle.write(bytes(packet))
            return written > 0
        except Exception as e:
            logger.debug(f"Failed to write subcommand 0x{subcommand:02X}: {e}")
            return False

    def read(self, max_length: int = 64, timeout_ms: int = 5) -> Optional[bytes]:
        """Non-blocking read of raw HID packet."""
        if not self.handle:
            return None

        try:
            raw = self.handle.read(max_length, timeout_ms)
            if raw:
                return bytes(raw)
            return None
        except Exception as e:
            # Device disconnected or communication lost
            logger.warning(f"Device read error: {e}")
            self.close()
            return None

    def send_rumble(self, large_motor: int, small_motor: int) -> bool:
        """Send Switch Pro output report 0x10 with HD rumble data."""
        if not self.handle:
            return False

        self._counter = (self._counter + 1) & 0x0F
        packet = build_rumble_packet(large_motor, small_motor, self._counter)
        try:
            written = self.handle.write(packet)
            return written > 0
        except Exception as e:
            logger.debug(f"Failed to write rumble packet: {e}")
            return False

    def close(self) -> None:
        """Close HID device handle."""
        if self.handle:
            # Send neutral rumble before closing to ensure motors stop
            try:
                self.send_rumble(0, 0)
            except Exception:
                pass
            try:
                self.handle.close()
            except Exception:
                pass
            self.handle = None
            print("[Device] Disconnected.")

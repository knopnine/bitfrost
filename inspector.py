"""Real-time HID packet inspector for diagnosing third-party and ODM gamepads."""

import sys
import time
from typing import Optional

from config import BridgeConfig
from device import ControllerDevice


def run_inspector(config: BridgeConfig) -> None:
    """Reads raw HID packets and displays live hex view with changes highlighted."""
    device = ControllerDevice(config)
    print("\n========================================================")
    print("  LIVE HID PACKET INSPECTOR (Press Ctrl+C to exit)       ")
    print("========================================================")
    print(f"Target VID: 0x{config.vendor_id:04X}, PID: 0x{config.product_id:04X}")

    if not device.open():
        print("[Inspector] Device not found. Waiting for connection...")
        while not device.open():
            time.sleep(0.5)

    last_packet: Optional[bytes] = None
    packet_count = 0
    start_time = time.time()

    try:
        while True:
            packet = device.read(64, timeout_ms=10)
            if not packet:
                time.sleep(0.01)
                continue

            packet_count += 1
            now = time.time()
            rate = packet_count / max(0.001, now - start_time)

            # Check if bytes changed
            if last_packet != packet:
                # Format hex string with changed bytes marked
                hex_parts = []
                for i, b in enumerate(packet):
                    if last_packet and i < len(last_packet) and b != last_packet[i]:
                        # Highlight changed byte
                        hex_parts.append(f"*{b:02X}*")
                    else:
                        hex_parts.append(f" {b:02X} ")

                hex_view = " ".join(hex_parts)
                sys.stdout.write(f"\r[Len: {len(packet):02d} | Rate: {rate:4.0f}Hz] {hex_view}\n")
                sys.stdout.flush()
                last_packet = packet

    except KeyboardInterrupt:
        print("\n[Inspector] Stopped.")
    finally:
        device.close()

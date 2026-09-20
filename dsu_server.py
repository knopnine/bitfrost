"""Cemuhook DSU (DualShock UDP) protocol server for motion control streaming."""

import binascii
import logging
import socket
import struct
import threading
import time
from typing import Dict, Optional, Tuple

from parser import GamepadState
from protocol import BatteryStatus

logger = logging.getLogger("GamepadBridge.DSU")

DSU_MAGIC_SERVER = b"DSUS"
DSU_MAGIC_CLIENT = b"DSUC"
DSU_PROTOCOL_VERSION = 1001

MSG_TYPE_VERSION = 0x100000
MSG_TYPE_CONTROLLER_INFO = 0x100001
MSG_TYPE_DATA = 0x100002


def compute_crc32(data: bytes) -> int:
    """Calculates standard CRC32 checksum."""
    return binascii.crc32(data) & 0xFFFFFFFF


class DsuServer:
    """Lightweight UDP server streaming 6-axis motion packets to emulators (Cemu, Yuzu, Ryujinx, Dolphin)."""

    def __init__(self, host: str = "127.0.0.1", port: int = 26760):
        self.host = host
        self.port = port
        self.server_id = 0x12345678
        self._running = False
        self._socket: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None
        self._clients: Dict[Tuple[str, int], float] = {}  # (host, port) -> last_seen_ts
        self._clients_lock = threading.Lock()
        self._packet_counter = 0

    @property
    def is_running(self) -> bool:
        return self._running

    def update_state(self, state: GamepadState) -> None:
        """Alias for broadcast_state."""
        self.broadcast_state(state)

    def start(self) -> bool:
        """Starts the DSU UDP server on background thread."""
        if self._running:
            return True

        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._socket.bind((self.host, self.port))
            self._socket.settimeout(0.1)
            self._running = True

            self._thread = threading.Thread(target=self._listen_loop, daemon=True, name="DsuServerThread")
            self._thread.start()
            logger.info(f"DSU Motion Server running on {self.host}:{self.port}")
            print(f"[DSU Server] Motion streaming active on {self.host}:{self.port} (Cemu / Yuzu / Ryujinx compatible)")
            return True
        except Exception as e:
            logger.error(f"Failed to start DSU server on {self.host}:{self.port}: {e}")
            self._running = False
            return False

    def stop(self) -> None:
        """Stops the DSU server and closes socket."""
        self._running = False
        if self._thread and threading.current_thread() != self._thread:
            self._thread.join(timeout=1.0)
        self._thread = None

        if self._socket:
            try:
                self._socket.close()
            except Exception:
                pass
            self._socket = None
        logger.info("DSU Motion Server stopped.")

    def _listen_loop(self) -> None:
        """Listens for client registrations and heartbeat packets."""
        while self._running:
            if not self._socket:
                break
            try:
                data, addr = self._socket.recvfrom(1024)
                if len(data) < 16:
                    continue

                magic = data[:4]
                if magic not in (DSU_MAGIC_CLIENT, DSU_MAGIC_SERVER):
                    continue

                proto_ver = struct.unpack_from("<H", data, 4)[0]
                msg_len = struct.unpack_from("<H", data, 6)[0]
                msg_type = struct.unpack_from("<I", data, 16)[0]

                # Update client subscription
                now = time.time()
                with self._clients_lock:
                    self._clients[addr] = now
                    # Prune stale clients (> 10s inactivity)
                    stale = [a for a, ts in self._clients.items() if now - ts > 10.0]
                    for s in stale:
                        del self._clients[s]

                if msg_type == MSG_TYPE_VERSION:
                    self._handle_version_request(addr)
                elif msg_type == MSG_TYPE_CONTROLLER_INFO:
                    self._handle_controller_info_request(data, addr)

            except socket.timeout:
                continue
            except Exception as e:
                if self._running:
                    logger.debug(f"DSU listen exception: {e}")

    def _build_header(self, msg_type: int, payload_len: int) -> bytearray:
        """Constructs a standard 20-byte DSU packet header."""
        header = bytearray(20)
        header[0:4] = DSU_MAGIC_SERVER
        struct.pack_into("<H", header, 4, DSU_PROTOCOL_VERSION)
        struct.pack_into("<H", header, 6, payload_len + 4)  # packet payload + msg_type
        struct.pack_into("<I", header, 8, 0)                # CRC placeholder
        struct.pack_into("<I", header, 12, self.server_id)
        struct.pack_into("<I", header, 16, msg_type)
        return header

    def _send_packet(self, header: bytearray, payload: bytes, addr: Tuple[str, int]) -> None:
        """Computes CRC32 and sends UDP packet to target address."""
        packet = header + payload
        # Calculate CRC over entire buffer with CRC field as 0
        crc = compute_crc32(bytes(packet))
        struct.pack_into("<I", packet, 8, crc)
        try:
            if self._socket:
                self._socket.sendto(bytes(packet), addr)
        except Exception:
            pass

    def _handle_version_request(self, addr: Tuple[str, int]) -> None:
        """Responds to Cemuhook protocol version check."""
        header = self._build_header(MSG_TYPE_VERSION, 2)
        payload = struct.pack("<H", DSU_PROTOCOL_VERSION)
        self._send_packet(header, payload, addr)

    def _handle_controller_info_request(self, data: bytes, addr: Tuple[str, int]) -> None:
        """Responds to slot / controller info query."""
        slot = 0
        slot_state = 2      # 2 = connected
        device_model = 2    # 2 = full gyro gamepad
        connection_type = 2 # 2 = Bluetooth / USB wireless
        mac = bytes([0x98, 0xB6, 0xAB, 0xC7, 0x6E, 0x95])  # Standard Switch MAC format
        battery = 0x05      # 0x05 = Full
        payload = struct.pack("<BBBB6sB", slot, slot_state, device_model, connection_type, mac, battery)
        header = self._build_header(MSG_TYPE_CONTROLLER_INFO, len(payload))
        self._send_packet(header, payload, addr)

    def broadcast_state(self, state: GamepadState) -> None:
        """Broadcasts full 6-axis motion and button state to all connected clients at controller poll rate."""
        if not self._running or not self._clients:
            return

        self._packet_counter = (self._packet_counter + 1) & 0xFFFFFFFF
        now_micros = int(time.perf_counter() * 1_000_000) & 0xFFFFFFFFFFFFFFFF

        # Pack DSU data payload:
        # Slot: 0, Slot State: 2 (connected), Model: 2, Connection: 2, MAC (6 bytes), Battery:
        slot = 0
        slot_state = 2
        device_model = 2
        connection_type = 2
        mac = bytes([0x98, 0xB6, 0xAB, 0xC7, 0x6E, 0x95])

        bat_code = 0x05
        if state.battery == BatteryStatus.EMPTY:
            bat_code = 0x01
        elif state.battery == BatteryStatus.CRITICAL:
            bat_code = 0x02
        elif state.battery == BatteryStatus.LOW:
            bat_code = 0x03
        elif state.battery == BatteryStatus.MEDIUM:
            bat_code = 0x04
        elif state.battery == BatteryStatus.FULL:
            bat_code = 0x05

        is_connected = 1

        # Digital buttons 1 (D-Pad, Options, Share, R3, L3)
        b1 = 0
        if state.dpad_left:   b1 |= 0x80
        if state.dpad_down:   b1 |= 0x40
        if state.dpad_right:  b1 |= 0x20
        if state.dpad_up:     b1 |= 0x10
        if state.btn_start:   b1 |= 0x08
        if state.btn_rsb:     b1 |= 0x04
        if state.btn_lsb:     b1 |= 0x02
        if state.btn_back:    b1 |= 0x01

        # Digital buttons 2 (Y, B, A, X, R1, L1, R2, L2)
        b2 = 0
        if state.btn_x:       b2 |= 0x80
        if state.btn_a:       b2 |= 0x40
        if state.btn_b:       b2 |= 0x20
        if state.btn_y:       b2 |= 0x10
        if state.btn_rb:      b2 |= 0x08
        if state.btn_lb:      b2 |= 0x04
        if state.trigger_r > 50: b2 |= 0x02
        if state.trigger_l > 50: b2 |= 0x01

        ps_button = 1 if state.btn_guide else 0
        touch_active = 0

        # Sticks (0 to 255)
        # Left Stick
        lx_u8 = max(0, min(255, int((state.stick_lx + 32768) / 257.0)))
        ly_u8 = max(0, min(255, int((state.stick_ly + 32768) / 257.0)))
        # Right Stick
        rx_u8 = max(0, min(255, int((state.stick_rx + 32768) / 257.0)))
        ry_u8 = max(0, min(255, int((state.stick_ry + 32768) / 257.0)))

        # Analog D-Pad & Trigger levels
        dpad_l_val = 255 if state.dpad_left else 0
        dpad_d_val = 255 if state.dpad_down else 0
        dpad_r_val = 255 if state.dpad_right else 0
        dpad_u_val = 255 if state.dpad_up else 0
        btn_y_val = 255 if state.btn_y else 0
        btn_b_val = 255 if state.btn_b else 0
        btn_a_val = 255 if state.btn_a else 0
        btn_x_val = 255 if state.btn_x else 0
        btn_rb_val = 255 if state.btn_rb else 0
        btn_lb_val = 255 if state.btn_lb else 0
        trigger_r_val = max(0, min(255, state.trigger_r))
        trigger_l_val = max(0, min(255, state.trigger_l))

        # 6-Axis Motion
        # Accel in G (x, y, z)
        ax, ay, az = state.imu_accel
        # Gyro in deg/s (pitch, roll, yaw)
        gp, gr, gy = state.imu_gyro

        # Construct DSU Data Report (80 bytes payload)
        # Layout:
        # 0: Slot (u8)
        # 1: Slot state (u8)
        # 2: Device model (u8)
        # 3: Connection type (u8)
        # 4-9: MAC (6 bytes)
        # 10: Battery (u8)
        # 11: Is Connected (u8)
        # 12-15: Packet counter (u32)
        # 16-17: Buttons 1 & 2 (u8, u8)
        # 18: PS Button (u8)
        # 19: Touch active (u8)
        # 20-23: Sticks (LX, LY, RX, RY: u8 each)
        # 24-35: Analog buttons (12 x u8)
        # 36-41: Touchpad 1 (inactive: 6 bytes)
        # 42-47: Touchpad 2 (inactive: 6 bytes)
        # 48-55: Timestamp (u64)
        # 56-67: Accel X, Y, Z (3 x float32)
        # 68-79: Gyro Pitch, Roll, Yaw (3 x float32)
        payload = bytearray(80)
        struct.pack_into("<BBBB6sBBI", payload, 0, slot, slot_state, device_model, connection_type, mac, bat_code, is_connected, self._packet_counter)
        struct.pack_into("<BBBBBBBB", payload, 16, b1, b2, ps_button, touch_active, lx_u8, ly_u8, rx_u8, ry_u8)
        struct.pack_into("<12B", payload, 24, dpad_l_val, dpad_d_val, dpad_r_val, dpad_u_val, btn_y_val, btn_b_val, btn_a_val, btn_x_val, btn_rb_val, btn_lb_val, trigger_r_val, trigger_l_val)
        struct.pack_into("<Q", payload, 48, now_micros)
        struct.pack_into("<ffffff", payload, 56, float(ax), float(ay), float(az), float(gp), float(gr), float(gy))

        header = self._build_header(MSG_TYPE_DATA, len(payload))
        packet = header + payload
        crc = compute_crc32(bytes(packet))
        struct.pack_into("<I", packet, 8, crc)
        packet_bytes = bytes(packet)

        with self._clients_lock:
            client_addrs = list(self._clients.keys())

        for c_addr in client_addrs:
            try:
                if self._socket:
                    self._socket.sendto(packet_bytes, c_addr)
            except Exception:
                pass

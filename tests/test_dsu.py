"""Unit tests for Cemuhook DSU protocol server."""

import socket
import struct
import time
import unittest

from dsu_server import (
    DSU_MAGIC_CLIENT,
    DSU_MAGIC_SERVER,
    DSU_PROTOCOL_VERSION,
    MSG_TYPE_CONTROLLER_INFO,
    MSG_TYPE_DATA,
    MSG_TYPE_VERSION,
    DsuServer,
    compute_crc32,
)
from parser import GamepadState
from protocol import BatteryStatus, ProtocolMode


class TestDsuServer(unittest.TestCase):
    def setUp(self):
        self.port = 26769
        self.server = DsuServer(host="127.0.0.1", port=self.port)
        self.assertTrue(self.server.start())
        self.client_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.client_sock.settimeout(1.0)

    def tearDown(self):
        self.server.stop()
        self.client_sock.close()

    def _build_client_packet(self, msg_type: int, payload: bytes = b"") -> bytes:
        pkt = bytearray(20 + len(payload))
        pkt[0:4] = DSU_MAGIC_CLIENT
        struct.pack_into("<H", pkt, 4, DSU_PROTOCOL_VERSION)
        struct.pack_into("<H", pkt, 6, len(payload) + 4)
        struct.pack_into("<I", pkt, 8, 0)
        struct.pack_into("<I", pkt, 12, 0xABCDEF01)
        struct.pack_into("<I", pkt, 16, msg_type)
        if payload:
            pkt[20:] = payload
        crc = compute_crc32(bytes(pkt))
        struct.pack_into("<I", pkt, 8, crc)
        return bytes(pkt)

    def test_version_request(self):
        req = self._build_client_packet(MSG_TYPE_VERSION)
        self.client_sock.sendto(req, ("127.0.0.1", self.port))

        resp, _ = self.client_sock.recvfrom(1024)
        self.assertGreaterEqual(len(resp), 22)
        self.assertEqual(resp[:4], DSU_MAGIC_SERVER)
        resp_type = struct.unpack_from("<I", resp, 16)[0]
        self.assertEqual(resp_type, MSG_TYPE_VERSION)
        resp_ver = struct.unpack_from("<H", resp, 20)[0]
        self.assertEqual(resp_ver, DSU_PROTOCOL_VERSION)

    def test_controller_info_request(self):
        payload = struct.pack("<I", 0)  # Slot 0 query
        req = self._build_client_packet(MSG_TYPE_CONTROLLER_INFO, payload)
        self.client_sock.sendto(req, ("127.0.0.1", self.port))

        resp, _ = self.client_sock.recvfrom(1024)
        self.assertGreaterEqual(len(resp), 31)
        self.assertEqual(resp[:4], DSU_MAGIC_SERVER)
        resp_type = struct.unpack_from("<I", resp, 16)[0]
        self.assertEqual(resp_type, MSG_TYPE_CONTROLLER_INFO)

        slot, state, model = struct.unpack_from("<BBB", resp, 20)
        self.assertEqual(slot, 0)
        self.assertEqual(state, 2)  # Connected
        self.assertEqual(model, 2)  # Full gyro gamepad

    def test_motion_broadcast(self):
        # Register client by sending version request first
        req = self._build_client_packet(MSG_TYPE_VERSION)
        self.client_sock.sendto(req, ("127.0.0.1", self.port))
        _, _ = self.client_sock.recvfrom(1024)

        # Broadcast state with IMU motion data
        state = GamepadState(
            btn_a=True,
            stick_lx=10000,
            stick_ly=-15000,
            imu_accel=(0.02, 0.05, 0.98),
            imu_gyro=(12.5, -3.2, 45.0),
            battery=BatteryStatus.FULL,
            protocol_mode=ProtocolMode.SWITCH_FULL,
        )
        self.server.update_state(state)

        data_packet, _ = self.client_sock.recvfrom(1024)
        self.assertEqual(data_packet[:4], DSU_MAGIC_SERVER)
        msg_type = struct.unpack_from("<I", data_packet, 16)[0]
        self.assertEqual(msg_type, MSG_TYPE_DATA)

        # Verify CRC32
        received_crc = struct.unpack_from("<I", data_packet, 8)[0]
        calc_pkt = bytearray(data_packet)
        struct.pack_into("<I", calc_pkt, 8, 0)
        expected_crc = compute_crc32(bytes(calc_pkt))
        self.assertEqual(received_crc, expected_crc)


if __name__ == "__main__":
    unittest.main()

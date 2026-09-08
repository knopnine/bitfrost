"""Unit tests for Switch Pro / ODM rumble packet construction and amplitude encoding."""

import unittest
from rumble import build_rumble_packet, encode_motor_rumble


class TestRumble(unittest.TestCase):
    def test_zero_rumble(self):
        # When motors are 0, should produce neutral rumble
        left = encode_motor_rumble(0)
        self.assertEqual(left, bytes([0x00, 0x01, 0x40, 0x40]))

        pkt = build_rumble_packet(0, 0, packet_counter=5)
        self.assertEqual(pkt[0], 0x10)  # Report ID 0x10
        self.assertEqual(pkt[1], 0x05)  # Packet counter
        self.assertEqual(pkt[2:6], bytes([0x00, 0x01, 0x40, 0x40]))
        self.assertEqual(pkt[6:10], bytes([0x00, 0x01, 0x40, 0x40]))
        self.assertEqual(len(pkt), 64)

    def test_active_rumble_scaling(self):
        # Non-zero rumble should have high/low amplitude bytes set
        pkt_half = build_rumble_packet(128, 128, 0)
        pkt_full = build_rumble_packet(255, 255, 0)

        # High amplitude byte (index 3 and 7) should be greater for full than half
        self.assertGreater(pkt_full[3], pkt_half[3])
        # Low amplitude byte (index 4 and 8) should be non-zero
        self.assertGreater(pkt_full[5], 0)


if __name__ == "__main__":
    unittest.main()

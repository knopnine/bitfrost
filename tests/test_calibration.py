"""Unit tests for stick center calibration and offset compensation."""

import unittest
from config import BridgeConfig
from parser import SwitchProParser, UnifiedGamepadParser


class TestStickCalibration(unittest.TestCase):
    def test_calibrated_center_offset(self):
        # Suppose physical controller rests slightly off-center:
        # LX rests at 2100 (instead of 2048)
        # LY rests at 1980 (instead of 2048)
        config = BridgeConfig(
            deadzone=0.02,
            stick_lx_center=2100,
            stick_ly_center=1980,
            stick_rx_center=2048,
            stick_ry_center=2048,
        )
        parser = SwitchProParser(config)

        # Build packet with raw stick resting at (2100, 1980)
        # 2100 = 0x834, 1980 = 0x7BC
        packet = bytearray(64)
        packet[0] = 0x30
        packet[2] = 0x80
        # LX: 0x834 -> byte 6: 0x34, byte 7 low nibble: 0x8
        # LY: 0x7BC -> byte 7 high nibble: 0xC, byte 8: 0x7B
        packet[6] = 0x34
        packet[7] = 0x8 | (0xC << 4)
        packet[8] = 0x7B

        # RX & RY neutral at 2048 (0x800)
        packet[9] = 0x00
        packet[10] = 0x08
        packet[11] = 0x80

        state = parser.parse(bytes(packet))
        self.assertIsNotNone(state)
        # Because config centers are set to (2100, 1980), the normalized offset is exactly 0.0!
        self.assertEqual(state.stick_lx, 0)
        self.assertEqual(state.stick_ly, 0)

    def test_unified_parser_set_stick_centers(self):
        config = BridgeConfig()
        unified = UnifiedGamepadParser(config)
        unified.set_stick_centers(2080, 2010, 2030, 2050)

        self.assertEqual(config.stick_lx_center, 2080)
        self.assertEqual(config.stick_ly_center, 2010)
        self.assertEqual(config.stick_rx_center, 2030)
        self.assertEqual(config.stick_ry_center, 2050)


if __name__ == "__main__":
    unittest.main()

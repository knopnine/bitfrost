"""Unit tests for Gamepad parser, deadzone processing, and button remapping."""

import unittest
from config import BridgeConfig
from parser import (
    GamepadState,
    SwitchProParser,
    OdmSimple3FParser,
    GenericDirectInputParser,
    UnifiedGamepadParser,
    apply_radial_deadzone,
)
from protocol import BatteryStatus, ProtocolMode


class TestDeadzone(unittest.TestCase):
    def test_center_deadzone(self):
        # Center should produce 0, 0
        x, y = apply_radial_deadzone(0.0, 0.0, deadzone=0.10)
        self.assertEqual(x, 0)
        self.assertEqual(y, 0)

        # Inside deadzone (< 0.10)
        x, y = apply_radial_deadzone(0.05, 0.05, deadzone=0.10)
        self.assertEqual(x, 0)
        self.assertEqual(y, 0)

    def test_deadzone_scaling(self):
        # Right at maximum (1.0)
        x, y = apply_radial_deadzone(1.0, 0.0, deadzone=0.10)
        self.assertEqual(x, 32767)
        self.assertEqual(y, 0)

        # Full negative (-1.0)
        x, y = apply_radial_deadzone(-1.0, 0.0, deadzone=0.10)
        self.assertEqual(x, -32767)
        self.assertEqual(y, 0)

        # Smooth scaling just above deadzone (0.19 with 0.10 deadzone -> 0.10 / 0.90 ~ 11% of 32767 ~ 3640)
        x, y = apply_radial_deadzone(0.19, 0.0, deadzone=0.10)
        self.assertGreater(x, 3000)
        self.assertLess(x, 4000)


class TestSwitchProParser(unittest.TestCase):
    def setUp(self):
        self.config = BridgeConfig(deadzone=0.10, swap_abxy=True)
        self.parser = SwitchProParser(self.config)

    def test_parse_neutral_packet(self):
        # Construct synthetic Report 0x30 packet
        packet = bytearray(64)
        packet[0] = 0x30  # Report ID
        packet[1] = 0x01  # Timer
        packet[2] = 0x82  # Battery Full (0x80) | Switch Pro (0x02)

        # Buttons neutral: 0
        packet[3] = 0x00
        packet[4] = 0x00
        packet[5] = 0x00

        # Sticks center (2048 = 0x800)
        # Left Stick: lx = 0x800, ly = 0x800
        # byte 6: 0x00, byte 7: (0x8) | (0x0 << 4) = 0x08, byte 8: 0x80
        packet[6] = 0x00
        packet[7] = 0x08
        packet[8] = 0x80

        # Right Stick: rx = 0x800, ry = 0x800
        packet[9] = 0x00
        packet[10] = 0x08
        packet[11] = 0x80

        state = self.parser.parse(bytes(packet))
        self.assertIsNotNone(state)
        self.assertEqual(state.protocol_mode, ProtocolMode.SWITCH_FULL)
        self.assertEqual(state.battery, BatteryStatus.FULL)
        self.assertEqual(state.stick_lx, 0)
        self.assertEqual(state.stick_ly, 0)
        self.assertEqual(state.stick_rx, 0)
        self.assertEqual(state.stick_ry, 0)
        self.assertFalse(state.btn_a)
        self.assertFalse(state.btn_b)

    def test_abxy_swap_remapping(self):
        packet = bytearray(64)
        packet[0] = 0x30
        packet[2] = 0x80
        # Neutral sticks
        packet[6] = 0x00; packet[7] = 0x08; packet[8] = 0x80
        packet[9] = 0x00; packet[10] = 0x08; packet[11] = 0x80

        # Press Nintendo B (byte 3, bit 2 = 0x04)
        # With swap_abxy=True, Nintendo B -> Xbox A
        packet[3] = 0x04
        state = self.parser.parse(bytes(packet))
        self.assertTrue(state.btn_a)
        self.assertFalse(state.btn_b)

        # Press Nintendo A (byte 3, bit 3 = 0x08)
        # Nintendo A -> Xbox B
        packet[3] = 0x08
        state = self.parser.parse(bytes(packet))
        self.assertTrue(state.btn_b)
        self.assertFalse(state.btn_a)

        # Press Nintendo Y (byte 3, bit 0 = 0x01) -> Xbox X
        packet[3] = 0x01
        state = self.parser.parse(bytes(packet))
        self.assertTrue(state.btn_x)
        self.assertFalse(state.btn_y)

        # Press Nintendo X (byte 3, bit 1 = 0x02) -> Xbox Y
        packet[3] = 0x02
        state = self.parser.parse(bytes(packet))
        self.assertTrue(state.btn_y)
        self.assertFalse(state.btn_x)

    def test_dpad_and_triggers(self):
        packet = bytearray(64)
        packet[0] = 0x30
        # Neutral sticks
        packet[6] = 0x00; packet[7] = 0x08; packet[8] = 0x80
        packet[9] = 0x00; packet[10] = 0x08; packet[11] = 0x80

        # D-pad Up (byte 5, bit 1 = 0x02) & ZL (byte 5, bit 7 = 0x80)
        packet[5] = 0x02 | 0x80
        # ZR (byte 3, bit 7 = 0x80)
        packet[3] = 0x80

        state = self.parser.parse(bytes(packet))
        self.assertTrue(state.dpad_up)
        self.assertFalse(state.dpad_down)
        self.assertEqual(state.trigger_l, 255)
        self.assertEqual(state.trigger_r, 255)


class TestOdmSimple3FParser(unittest.TestCase):
    def test_odm_report_3f(self):
        config = BridgeConfig(deadzone=0.10, swap_abxy=True)
        parser = OdmSimple3FParser(config)

        # Report 0x3F: [0x3F, LX, LY, RX, RY, Hat+Btns, Btns2, Btns3]
        packet = bytearray([
            0x3F,
            128, 128, 128, 128,  # Center sticks
            0x00 | 0x10,          # Hat=0 (North/Up) + Button B (bit 4 -> Xbox A)
            0x04,                 # ZL pressed (bit 2)
            0x01,                 # Home pressed (bit 0)
        ])

        state = parser.parse(bytes(packet))
        self.assertIsNotNone(state)
        self.assertEqual(state.protocol_mode, ProtocolMode.ODM_SIMPLE_3F)
        self.assertTrue(state.dpad_up)
        self.assertTrue(state.btn_a)
        self.assertEqual(state.trigger_l, 255)
        self.assertTrue(state.btn_guide)


class TestUnifiedParser(unittest.TestCase):
    def test_auto_detect(self):
        config = BridgeConfig(deadzone=0.10)
        unified = UnifiedGamepadParser(config)

        # Send 0x30 report
        pkt30 = bytearray(64)
        pkt30[0] = 0x30
        pkt30[6] = 0x00; pkt30[7] = 0x08; pkt30[8] = 0x80
        pkt30[9] = 0x00; pkt30[10] = 0x08; pkt30[11] = 0x80
        s30 = unified.parse(bytes(pkt30))
        self.assertEqual(s30.protocol_mode, ProtocolMode.SWITCH_FULL)

        # Send 0x3F report
        pkt3f = bytes([0x3F, 128, 128, 128, 128, 0x08, 0x00, 0x00])
        s3f = unified.parse(pkt3f)
        self.assertEqual(s3f.protocol_mode, ProtocolMode.ODM_SIMPLE_3F)


if __name__ == "__main__":
    unittest.main()

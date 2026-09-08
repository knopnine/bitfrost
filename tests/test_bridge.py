"""Integration tests for GamepadBridge and ViGEm virtual Xbox 360 emulation."""

import unittest
from config import BridgeConfig
from bridge import GamepadBridge
from parser import GamepadState
from protocol import ProtocolMode


class TestBridgeIntegration(unittest.TestCase):
    def setUp(self):
        self.config = BridgeConfig()
        self.bridge = GamepadBridge(self.config)

    def tearDown(self):
        self.bridge.stop()

    def test_virtual_pad_lifecycle(self):
        # 1. Initialize pad
        self.bridge._setup_virtual_pad()
        self.assertIsNotNone(self.bridge.virtual_pad)

        # 2. Feed simulated state
        state = GamepadState(
            btn_a=True,
            btn_b=False,
            btn_x=True,
            trigger_l=180,
            trigger_r=255,
            stick_lx=15000,
            stick_ly=-10000,
            protocol_mode=ProtocolMode.SWITCH_FULL
        )
        self.bridge._apply_state_to_virtual_pad(state)

        # Verify XUSB report fields match
        report = self.bridge.virtual_pad.report
        self.assertEqual(report.bLeftTrigger, 180)
        self.assertEqual(report.bRightTrigger, 255)
        self.assertEqual(report.sThumbLX, 15000)
        self.assertEqual(report.sThumbLY, -10000)

        # 3. Teardown
        self.bridge._teardown_virtual_pad()
        self.assertIsNone(self.bridge.virtual_pad)

    def test_ds4_virtual_pad_lifecycle(self):
        import vgamepad as vg
        self.bridge.config.emulation_target = "ds4"
        self.bridge._setup_virtual_pad()
        self.assertIsNotNone(self.bridge.virtual_pad)
        self.assertIsInstance(self.bridge.virtual_pad, vg.VDS4Gamepad)

        state = GamepadState(
            btn_a=True,
            btn_b=True,
            btn_guide=True,
            dpad_up=True,
            dpad_right=True,
            trigger_l=255,
            trigger_r=128,
            stick_lx=16384,
            stick_ly=16384,
            protocol_mode=ProtocolMode.SWITCH_FULL,
        )
        self.bridge._apply_state_to_virtual_pad(state)

        # Verify buttons bitmask
        w_buttons = self.bridge.virtual_pad.report.wButtons
        self.assertTrue(bool(w_buttons & vg.DS4_BUTTONS.DS4_BUTTON_CROSS))
        self.assertTrue(bool(w_buttons & vg.DS4_BUTTONS.DS4_BUTTON_CIRCLE))
        self.assertTrue(bool(self.bridge.virtual_pad.report.bSpecial & vg.DS4_SPECIAL_BUTTONS.DS4_SPECIAL_BUTTON_PS))

        self.bridge._teardown_virtual_pad()
        self.assertIsNone(self.bridge.virtual_pad)


if __name__ == "__main__":
    unittest.main()

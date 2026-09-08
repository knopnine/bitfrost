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


if __name__ == "__main__":
    unittest.main()

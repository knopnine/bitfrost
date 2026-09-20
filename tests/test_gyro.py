"""Unit tests for GyroAimProcessor and motion controls."""

import unittest
from parser import GyroAimProcessor


class TestGyroAimProcessor(unittest.TestCase):
    def setUp(self):
        self.processor = GyroAimProcessor(sensitivity=1.0, deadzone_dps=1.2)

    def test_gyro_deadzone(self):
        # Tremor below 1.2 deg/sec should be ignored
        rx, ry = self.processor.process(gyro_pitch=0.5, gyro_yaw=0.8, stick_rx=0, stick_ry=0)
        self.assertEqual(rx, 0)
        self.assertEqual(ry, 0)

    def test_gyro_aim_blending(self):
        # Substantial yaw angular velocity (e.g. 20 deg/s right turn)
        rx, ry = self.processor.process(gyro_pitch=0.0, gyro_yaw=20.0, stick_rx=0, stick_ry=0)
        # 20 dps * 150 scale * 0.65 filter ~ 1950 deflection
        self.assertGreater(rx, 1500)
        self.assertLess(rx, 3000)
        self.assertEqual(ry, 0)

    def test_gyro_aim_sensitivity_scaling(self):
        proc_high = GyroAimProcessor(sensitivity=2.0, deadzone_dps=1.2)
        proc_low = GyroAimProcessor(sensitivity=0.5, deadzone_dps=1.2)

        rx_high, _ = proc_high.process(0.0, 15.0, 0, 0)
        rx_low, _ = proc_low.process(0.0, 15.0, 0, 0)

        self.assertGreater(rx_high, rx_low * 2)

    def test_gyro_aim_stick_clamping(self):
        # Extreme stick + extreme gyro should saturate at 32767
        rx, ry = self.processor.process(gyro_pitch=-500.0, gyro_yaw=500.0, stick_rx=30000, stick_ry=30000)
        self.assertEqual(rx, 32767)
        self.assertEqual(ry, 32767)


if __name__ == "__main__":
    unittest.main()

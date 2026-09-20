"""Input parser for Nintendo Switch Pro Controller and generic ODM clones.

Decodes raw HID byte buffers into standardized GamepadState with deadzone
filtering, axis normalization, and Nintendo -> Xbox ABXY remapping.
"""

import math
from dataclasses import dataclass
from typing import Optional, Tuple

from config import BridgeConfig
from protocol import BatteryStatus, ProtocolMode


@dataclass
class GamepadState:
    """Standardized representation of all gamepad inputs."""
    # Buttons
    btn_a: bool = False
    btn_b: bool = False
    btn_x: bool = False
    btn_y: bool = False
    btn_lb: bool = False
    btn_rb: bool = False
    btn_back: bool = False
    btn_start: bool = False
    btn_guide: bool = False
    btn_capture: bool = False
    btn_lsb: bool = False
    btn_rsb: bool = False

    # D-Pad
    dpad_up: bool = False
    dpad_down: bool = False
    dpad_left: bool = False
    dpad_right: bool = False

    # Triggers (0 to 255)
    trigger_l: int = 0
    trigger_r: int = 0

    # Analog Sticks (-32768 to 32767, UP is positive)
    stick_lx: int = 0
    stick_ly: int = 0
    stick_rx: int = 0
    stick_ry: int = 0

    # Metadata
    battery: Optional[BatteryStatus] = None
    charging: bool = False
    protocol_mode: ProtocolMode = ProtocolMode.UNKNOWN

    # Raw Stick values (0 to 4095 for calibration & visualizer)
    raw_lx: int = 2048
    raw_ly: int = 2048
    raw_rx: int = 2048
    raw_ry: int = 2048

    # 6-Axis Motion / IMU data
    # Gyro: (pitch, roll, yaw) in degrees per second
    imu_gyro: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    # Accel: (x, y, z) in Gs (1G ~ 9.8 m/s^2)
    imu_accel: Tuple[float, float, float] = (0.0, 0.0, 0.0)


def apply_radial_deadzone(
    norm_x: float,
    norm_y: float,
    deadzone: float,
    outer_deadzone: float = 0.05,
    stick_curve: str = "linear",
) -> Tuple[int, int]:
    """Applies smooth radial deadzone, outer saturation, and sensitivity curves [-1.0, 1.0] -> [-32768, 32767].

    Inner deadzone eliminates center stick drift.
    Outer deadzone (saturation) ensures 100% full sprint/tilt is reached on ODM sticks.
    Sensitivity curves:
      - 'linear': 1:1 direct response
      - 'smooth': exponential (x^1.5) for fine camera aiming / stealth / archery in AC Shadows
      - 'aggressive': power (x^0.75) for rapid twitch responsiveness
    """
    mag = math.hypot(norm_x, norm_y)
    if mag <= deadzone or mag == 0:
        return 0, 0

    max_range = max(0.05, 1.0 - outer_deadzone)
    scaled_mag = min(1.0, max(0.0, (mag - deadzone) / max(0.01, max_range - deadzone)))

    # Apply sensitivity response curve
    if stick_curve == "smooth":
        # Exponential curve: subtle near center for fine archery / camera control, full speed at edge
        scaled_mag = math.pow(scaled_mag, 1.5)
    elif stick_curve == "aggressive":
        # Aggressive curve: quick acceleration for high-action camera turns
        scaled_mag = math.pow(scaled_mag, 0.75)

    res_x = (norm_x / mag) * scaled_mag
    res_y = (norm_y / mag) * scaled_mag

    int_x = max(-32768, min(32767, int(res_x * 32767)))
    int_y = max(-32768, min(32767, int(res_y * 32767)))
    return int_x, int_y


class TriggerRamp:
    """Manages progressive trigger smoothing / ramp state (0 to 255)."""

    def __init__(self, ramp_frames: int = 5):
        # 5 frames at 200 Hz = 25ms ramp duration
        self.ramp_frames = max(1, ramp_frames)
        self.step = 255.0 / self.ramp_frames
        self._left_val: float = 0.0
        self._right_val: float = 0.0

    def reset(self) -> None:
        self._left_val = 0.0
        self._right_val = 0.0

    def process(self, raw_left: int, raw_right: int, mode: str = "hair") -> Tuple[int, int]:
        """Returns processed trigger values (0 to 255) based on mode ('hair' vs 'progressive')."""
        if mode != "progressive":
            self._left_val = float(raw_left)
            self._right_val = float(raw_right)
            return raw_left, raw_right

        # Left trigger progressive pull
        if raw_left > 0:
            target = float(raw_left)
            self._left_val = min(target, self._left_val + self.step)
        else:
            self._left_val = 0.0

        # Right trigger progressive pull
        if raw_right > 0:
            target = float(raw_right)
            self._right_val = min(target, self._right_val + self.step)
        else:
            self._right_val = 0.0

        return int(round(self._left_val)), int(round(self._right_val))


class SwitchProParser:
    """Parser for official and compliant Switch Pro Controller reports (0x30 and 0x21)."""

    def __init__(self, config: BridgeConfig):
        self.config = config

    def parse(self, data: bytes) -> Optional[GamepadState]:
        if len(data) < 12:
            return None

        report_id = data[0]
        if report_id not in (0x30, 0x21):
            return None

        mode = ProtocolMode.SWITCH_FULL if report_id == 0x30 else ProtocolMode.SWITCH_REPLY

        # Byte 2: Battery status & connection
        battery_nibble = (data[2] >> 4) & 0x0F
        charging = bool(data[2] & 0x10)
        battery = BatteryStatus.from_high_nibble(battery_nibble)

        # Byte 3: Right Joy-Con buttons
        raw_y  = bool(data[3] & 0x01)
        raw_x  = bool(data[3] & 0x02)
        raw_b  = bool(data[3] & 0x04)
        raw_a  = bool(data[3] & 0x08)
        raw_r  = bool(data[3] & 0x40)
        raw_zr = bool(data[3] & 0x80)

        # Byte 4: Shared / System buttons
        raw_minus   = bool(data[4] & 0x01)
        raw_plus    = bool(data[4] & 0x02)
        raw_rsb     = bool(data[4] & 0x04)
        raw_lsb     = bool(data[4] & 0x08)
        raw_home    = bool(data[4] & 0x10)
        raw_capture = bool(data[4] & 0x20)

        # Byte 5: Left Joy-Con buttons
        dpad_down  = bool(data[5] & 0x01)
        dpad_up    = bool(data[5] & 0x02)
        dpad_right = bool(data[5] & 0x04)
        dpad_left  = bool(data[5] & 0x08)
        raw_l      = bool(data[5] & 0x40)
        raw_zl     = bool(data[5] & 0x80)

        # Bytes 6-8: Left Stick (12-bit X and Y)
        # lx: 12 bits, ly: 12 bits
        raw_lx = data[6] | ((data[7] & 0x0F) << 8)
        raw_ly = (data[7] >> 4) | (data[8] << 4)

        # Bytes 9-11: Right Stick (12-bit X and Y)
        raw_rx = data[9] | ((data[10] & 0x0F) << 8)
        raw_ry = (data[10] >> 4) | (data[11] << 4)

        # Normalize 12-bit values (0..4095) with hardware calibrated center offsets
        # Note: Switch Pro ly and ry increase when stick is pushed UP
        norm_lx = max(-1.0, min(1.0, (raw_lx - self.config.stick_lx_center) / 2048.0))
        norm_ly = max(-1.0, min(1.0, (raw_ly - self.config.stick_ly_center) / 2048.0))
        norm_rx = max(-1.0, min(1.0, (raw_rx - self.config.stick_rx_center) / 2048.0))
        norm_ry = max(-1.0, min(1.0, (raw_ry - self.config.stick_ry_center) / 2048.0))

        stick_lx, stick_ly = apply_radial_deadzone(
            norm_lx, norm_ly, self.config.deadzone, self.config.outer_deadzone, self.config.stick_curve
        )
        stick_rx, stick_ry = apply_radial_deadzone(
            norm_rx, norm_ry, self.config.deadzone, self.config.outer_deadzone, self.config.stick_curve
        )

        # Decode 6-axis IMU (accelerometer and gyroscope) in Report 0x30
        imu_accel = (0.0, 0.0, 0.0)
        imu_gyro = (0.0, 0.0, 0.0)
        if report_id == 0x30 and len(data) >= 49:
            import struct
            try:
                # Byte 13 starts 3 frames of 12 bytes each. We decode the latest frame (Frame 2: byte 37)
                ax_r, ay_r, az_r, gx_r, gy_r, gz_r = struct.unpack_from("<hhhhhh", data, 37)
                # Accel: ±8G range (~0.000244 G/LSB)
                # Gyro: ±2000 dps range (~0.06103 deg/s/LSB)
                imu_accel = (ax_r * 0.000244, ay_r * 0.000244, az_r * 0.000244)
                imu_gyro = (gx_r * 0.06103, gy_r * 0.06103, gz_r * 0.06103)
            except Exception:
                pass

        # ABXY Remapping:
        # Nintendo physical layout:     Xbox physical layout:
        #       [X]                             [Y]
        #   [Y]     [A]                     [X]     [B]
        #       [B]                             [A]
        if self.config.swap_abxy:
            btn_a = raw_b
            btn_b = raw_a
            btn_x = raw_y
            btn_y = raw_x
        else:
            btn_a = raw_a
            btn_b = raw_b
            btn_x = raw_x
            btn_y = raw_y

        return GamepadState(
            btn_a=btn_a,
            btn_b=btn_b,
            btn_x=btn_x,
            btn_y=btn_y,
            btn_lb=raw_l,
            btn_rb=raw_r,
            btn_back=raw_minus,
            btn_start=raw_plus,
            btn_guide=raw_home,
            btn_capture=raw_capture,
            btn_lsb=raw_lsb,
            btn_rsb=raw_rsb,
            dpad_up=dpad_up,
            dpad_down=dpad_down,
            dpad_left=dpad_left,
            dpad_right=dpad_right,
            trigger_l=255 if raw_zl else 0,
            trigger_r=255 if raw_zr else 0,
            stick_lx=stick_lx,
            stick_ly=stick_ly,
            stick_rx=stick_rx,
            stick_ry=stick_ry,
            raw_lx=raw_lx,
            raw_ly=raw_ly,
            raw_rx=raw_rx,
            raw_ry=raw_ry,
            imu_accel=imu_accel,
            imu_gyro=imu_gyro,
            battery=battery,
            charging=charging,
            protocol_mode=mode,
        )


class GyroAimProcessor:
    """Processes 6-axis gyroscope angular velocity and blends aiming deltas into Right Stick."""

    def __init__(self, sensitivity: float = 1.0, deadzone_dps: float = 1.2):
        self.sensitivity = max(0.1, min(sensitivity, 5.0))
        self.deadzone_dps = deadzone_dps
        self._filtered_dx = 0.0
        self._filtered_dy = 0.0

    def process(
        self,
        gyro_pitch: float,
        gyro_yaw: float,
        stick_rx: int,
        stick_ry: int,
    ) -> Tuple[int, int]:
        """Calculates blended Right Stick position with gyro aim."""
        # Deadzone to eliminate tremor
        yaw_val = gyro_yaw if abs(gyro_yaw) >= self.deadzone_dps else 0.0
        pitch_val = gyro_pitch if abs(gyro_pitch) >= self.deadzone_dps else 0.0

        # Scale deg/sec to stick offset space (-32768 to 32767)
        # 50 deg/sec maps to ~7500 stick deflection at sensitivity 1.0
        scale = 150.0 * self.sensitivity
        target_dx = yaw_val * scale
        target_dy = -pitch_val * scale

        # Low-pass smoothing filter
        self._filtered_dx = self._filtered_dx * 0.35 + target_dx * 0.65
        self._filtered_dy = self._filtered_dy * 0.35 + target_dy * 0.65

        blended_rx = int(max(-32768, min(32767, stick_rx + self._filtered_dx)))
        blended_ry = int(max(-32768, min(32767, stick_ry + self._filtered_dy)))
        return blended_rx, blended_ry



class OdmSimple3FParser:
    """Parser for third-party / ODM Switch clone controllers sending Report 0x3F."""

    def __init__(self, config: BridgeConfig):
        self.config = config

    def parse(self, data: bytes) -> Optional[GamepadState]:
        if len(data) < 8 or data[0] != 0x3F:
            return None

        # Bytes 1-4: 8-bit Analog Sticks (0..255, center ~128)
        raw_lx = data[1]
        raw_ly = data[2]
        raw_rx = data[3]
        raw_ry = data[4]

        # Standard HID sticks have 0 at top (inverted Y relative to XInput UP)
        norm_lx = max(-1.0, min(1.0, (raw_lx - 128) / 128.0))
        norm_ly = max(-1.0, min(1.0, -(raw_ly - 128) / 128.0))
        norm_rx = max(-1.0, min(1.0, (raw_rx - 128) / 128.0))
        norm_ry = max(-1.0, min(1.0, -(raw_ry - 128) / 128.0))

        stick_lx, stick_ly = apply_radial_deadzone(
            norm_lx, norm_ly, self.config.deadzone, self.config.outer_deadzone, self.config.stick_curve
        )
        stick_rx, stick_ry = apply_radial_deadzone(
            norm_rx, norm_ry, self.config.deadzone, self.config.outer_deadzone, self.config.stick_curve
        )

        # Byte 5: D-pad / Hat switch (low nibble) and Buttons (high nibble)
        hat = data[5] & 0x0F
        # 0=N, 1=NE, 2=E, 3=SE, 4=S, 5=SW, 6=W, 7=NW, 8/0x0F=Neutral
        dpad_up    = hat in (0, 1, 7)
        dpad_right = hat in (1, 2, 3)
        dpad_down  = hat in (3, 4, 5)
        dpad_left  = hat in (5, 6, 7)

        # Buttons in byte 5 upper nibble and byte 6
        raw_b = bool(data[5] & 0x10)
        raw_a = bool(data[5] & 0x20)
        raw_y = bool(data[5] & 0x40)
        raw_x = bool(data[5] & 0x80)

        # Byte 6: L, R, ZL, ZR, Minus, Plus, LSB, RSB
        raw_l     = bool(data[6] & 0x01)
        raw_r     = bool(data[6] & 0x02)
        raw_zl    = bool(data[6] & 0x04)
        raw_zr    = bool(data[6] & 0x08)
        raw_minus = bool(data[6] & 0x10)
        raw_plus  = bool(data[6] & 0x20)
        raw_lsb   = bool(data[6] & 0x40)
        raw_rsb   = bool(data[6] & 0x80)

        # Byte 7: Home, Capture (if available)
        raw_home    = bool(data[7] & 0x01) if len(data) > 7 else False
        raw_capture = bool(data[7] & 0x02) if len(data) > 7 else False

        # Triggers: check if byte 8/9 have analog trigger values
        trigger_l = 255 if raw_zl else 0
        trigger_r = 255 if raw_zr else 0
        if len(data) >= 10:
            # If extended analog trigger report is present and non-zero
            if data[8] > 0 or data[9] > 0:
                trigger_l = data[8]
                trigger_r = data[9]

        if self.config.swap_abxy:
            btn_a = raw_b
            btn_b = raw_a
            btn_x = raw_y
            btn_y = raw_x
        else:
            btn_a = raw_a
            btn_b = raw_b
            btn_x = raw_x
            btn_y = raw_y

        return GamepadState(
            btn_a=btn_a,
            btn_b=btn_b,
            btn_x=btn_x,
            btn_y=btn_y,
            btn_lb=raw_l,
            btn_rb=raw_r,
            btn_back=raw_minus,
            btn_start=raw_plus,
            btn_guide=raw_home,
            btn_capture=raw_capture,
            btn_lsb=raw_lsb,
            btn_rsb=raw_rsb,
            dpad_up=dpad_up,
            dpad_down=dpad_down,
            dpad_left=dpad_left,
            dpad_right=dpad_right,
            trigger_l=trigger_l,
            trigger_r=trigger_r,
            stick_lx=stick_lx,
            stick_ly=stick_ly,
            stick_rx=stick_rx,
            stick_ry=stick_ry,
            protocol_mode=ProtocolMode.ODM_SIMPLE_3F,
        )


class GenericDirectInputParser:
    """Robust fallback decoder for generic HID / DirectInput gamepad reports."""

    def __init__(self, config: BridgeConfig):
        self.config = config

    def parse(self, data: bytes) -> Optional[GamepadState]:
        if len(data) < 6:
            return None

        # Check if first byte is a report ID (e.g. 0x01) or raw axes
        offset = 1 if data[0] in (0x01, 0x02) and len(data) > 6 else 0

        raw_lx = data[offset]
        raw_ly = data[offset + 1]
        raw_rx = data[offset + 2] if len(data) > offset + 2 else 128
        raw_ry = data[offset + 3] if len(data) > offset + 3 else 128

        norm_lx = max(-1.0, min(1.0, (raw_lx - 128) / 128.0))
        norm_ly = max(-1.0, min(1.0, -(raw_ly - 128) / 128.0))
        norm_rx = max(-1.0, min(1.0, (raw_rx - 128) / 128.0))
        norm_ry = max(-1.0, min(1.0, -(raw_ry - 128) / 128.0))

        stick_lx, stick_ly = apply_radial_deadzone(
            norm_lx, norm_ly, self.config.deadzone, self.config.outer_deadzone, self.config.stick_curve
        )
        stick_rx, stick_ry = apply_radial_deadzone(
            norm_rx, norm_ry, self.config.deadzone, self.config.outer_deadzone, self.config.stick_curve
        )

        # Buttons bitmask (16-bit)
        btn_idx = offset + 4
        btn_mask = 0
        if len(data) > btn_idx:
            btn_mask = data[btn_idx]
        if len(data) > btn_idx + 1:
            btn_mask |= (data[btn_idx + 1] << 8)

        # Hat switch in next byte or upper nibble
        hat_idx = offset + 6 if len(data) > offset + 6 else btn_idx
        hat = data[hat_idx] & 0x0F if len(data) > hat_idx else 0x0F

        dpad_up    = hat in (0, 1, 7)
        dpad_right = hat in (1, 2, 3)
        dpad_down  = hat in (3, 4, 5)
        dpad_left  = hat in (5, 6, 7)

        # Common bitmask for 12/16 buttons
        raw_a     = bool(btn_mask & (1 << 0))
        raw_b     = bool(btn_mask & (1 << 1))
        raw_x     = bool(btn_mask & (1 << 2))
        raw_y     = bool(btn_mask & (1 << 3))
        raw_lb    = bool(btn_mask & (1 << 4))
        raw_rb    = bool(btn_mask & (1 << 5))
        raw_lt    = bool(btn_mask & (1 << 6))
        raw_rt    = bool(btn_mask & (1 << 7))
        raw_back  = bool(btn_mask & (1 << 8))
        raw_start = bool(btn_mask & (1 << 9))
        raw_lsb   = bool(btn_mask & (1 << 10))
        raw_rsb   = bool(btn_mask & (1 << 11))
        raw_guide = bool(btn_mask & (1 << 12))
        raw_capture = bool(btn_mask & (1 << 13))

        if self.config.swap_abxy:
            btn_a = raw_b
            btn_b = raw_a
            btn_x = raw_y
            btn_y = raw_x
        else:
            btn_a = raw_a
            btn_b = raw_b
            btn_x = raw_x
            btn_y = raw_y

        return GamepadState(
            btn_a=btn_a,
            btn_b=btn_b,
            btn_x=btn_x,
            btn_y=btn_y,
            btn_lb=raw_lb,
            btn_rb=raw_rb,
            btn_back=raw_back,
            btn_start=raw_start,
            btn_guide=raw_guide,
            btn_capture=raw_capture,
            btn_lsb=raw_lsb,
            btn_rsb=raw_rsb,
            dpad_up=dpad_up,
            dpad_down=dpad_down,
            dpad_left=dpad_left,
            dpad_right=dpad_right,
            trigger_l=255 if raw_lt else 0,
            trigger_r=255 if raw_rt else 0,
            stick_lx=stick_lx,
            stick_ly=stick_ly,
            stick_rx=stick_rx,
            stick_ry=stick_ry,
            protocol_mode=ProtocolMode.GENERIC_HID,
        )


class UnifiedGamepadParser:
    """Auto-detecting master parser that delegates to the appropriate protocol decoder."""

    def __init__(self, config: BridgeConfig):
        self.config = config
        self.switch_parser = SwitchProParser(config)
        self.odm_parser = OdmSimple3FParser(config)
        self.generic_parser = GenericDirectInputParser(config)
        self.trigger_ramp = TriggerRamp()
        self.detected_mode: ProtocolMode = ProtocolMode.UNKNOWN

    def set_stick_centers(self, lx: int, ly: int, rx: int, ry: int) -> None:
        """Update calibrated stick center offsets in parser configuration."""
        self.config.stick_lx_center = lx
        self.config.stick_ly_center = ly
        self.config.stick_rx_center = rx
        self.config.stick_ry_center = ry

    def parse(self, data: bytes) -> Optional[GamepadState]:
        if not data:
            return None

        state: Optional[GamepadState] = None

        if self.config.force_generic:
            state = self.generic_parser.parse(data)
            if state:
                self.detected_mode = ProtocolMode.GENERIC_HID
        else:
            first_byte = data[0]

            # 1. Standard Switch Pro Reports (0x30 full, 0x21 subcommand reply)
            if first_byte in (0x30, 0x21) and len(data) >= 12:
                state = self.switch_parser.parse(data)
                if state:
                    self.detected_mode = state.protocol_mode

            # 2. Third-Party ODM Simple Report (0x3F)
            elif first_byte == 0x3F and len(data) >= 8:
                state = self.odm_parser.parse(data)
                if state:
                    self.detected_mode = ProtocolMode.ODM_SIMPLE_3F

            # 3. Fallback: Generic DirectInput HID report
            if state is None:
                is_switch = (self.config.vendor_id == 0x057E and self.config.product_id == 0x2009)
                # On Switch Pro controllers, only allow generic fallback if report ID looks like standard HID (0x01, 0x02)
                # to prevent transitional Bluetooth status bytes from being misread as button masks
                if not is_switch or first_byte in (0x01, 0x02):
                    state = self.generic_parser.parse(data)
                    if state:
                        self.detected_mode = ProtocolMode.GENERIC_HID

        # Apply trigger profile (hair trigger vs progressive smooth ramp)
        if state:
            state.trigger_l, state.trigger_r = self.trigger_ramp.process(
                state.trigger_l, state.trigger_r, mode=self.config.trigger_mode
            )

        return state

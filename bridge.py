"""Core polling engine and virtual Xbox 360 / DS4 bridge using vgamepad and hidapi."""

import collections
import math
import signal
import sys
import threading
import time
from typing import Any, Callable, Dict, Optional, Union

import vgamepad as vg

from config import BridgeConfig
from device import ControllerDevice
from parser import GamepadState, UnifiedGamepadParser
from protocol import BatteryStatus, ProtocolMode


class GamepadBridge:
    """Bridge coordinating controller reads, protocol decoding, and ViGEm virtual gamepad updates."""

    def __init__(
        self,
        config: BridgeConfig,
        status_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        battery_warning_callback: Optional[Callable[[str], None]] = None,
    ):
        self.config = config
        self.status_callback = status_callback
        self.battery_warning_callback = battery_warning_callback
        self.device = ControllerDevice(config)
        self.parser = UnifiedGamepadParser(config)
        self.virtual_pad: Optional[Union[vg.VX360Gamepad, vg.VDS4Gamepad]] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_battery: Optional[BatteryStatus] = None
        self._last_mode: ProtocolMode = ProtocolMode.UNKNOWN
        self._last_state: Optional[GamepadState] = None
        self._packet_count = 0
        self._last_rate_calc = time.time()
        self.current_rate_hz = 0.0

        # Latency & Jitter calculation
        self._packet_intervals = collections.deque(maxlen=60)
        self._last_packet_ts = 0.0
        self.current_latency_ms = 0.0
        self.current_jitter_ms = 0.0

        # Low battery alert debounce
        self._last_battery_alert_ts = 0.0

        # Rumble state tracking
        self._rumble_lock = threading.Lock()
        self._target_large_motor = 0
        self._target_small_motor = 0
        self._current_large_motor = 0
        self._current_small_motor = 0
        self._rumble_changed = False
        self._last_rumble_sent_ts = 0.0

    @property
    def is_running(self) -> bool:
        return self._running

    def _setup_virtual_pad(self) -> None:
        """Initialize the ViGEmBus virtual gamepad (Xbox 360 or DualShock 4) and register rumble callback."""
        if self.virtual_pad is None:
            target = self.config.emulation_target.lower()
            if target == "ds4":
                self.virtual_pad = vg.VDS4Gamepad()
                pad_label = "PlayStation 4 (DualShock 4)"
            else:
                self.virtual_pad = vg.VX360Gamepad()
                pad_label = "Xbox 360"

            # Register force feedback (rumble) notification from games
            try:
                def _on_vigem_notification(client, target, large_motor, small_motor, led_number, user_data):
                    self._on_game_rumble_received(large_motor, small_motor)

                self.virtual_pad.register_notification(_on_vigem_notification)
                print(f"[ViGEmBus] Virtual {pad_label} Controller connected with Force Feedback (Rumble).")
            except Exception as e:
                print(f"[ViGEmBus] Virtual {pad_label} Controller connected (rumble warning: {e}).")

    def _on_game_rumble_received(self, large_motor: int, small_motor: int) -> None:
        """Called by ViGEmBus when a game sends vibration commands to the virtual controller."""
        if not self.config.enable_rumble:
            return

        with self._rumble_lock:
            if large_motor != self._target_large_motor or small_motor != self._target_small_motor:
                self._target_large_motor = large_motor
                self._target_small_motor = small_motor
                self._rumble_changed = True

    def _teardown_virtual_pad(self) -> None:
        """Safely release and destroy the virtual controller."""
        if self.virtual_pad is not None:
            try:
                self.virtual_pad.unregister_notification()
            except Exception:
                pass
            try:
                self.virtual_pad.reset()
                self.virtual_pad.update()
            except Exception:
                pass
            del self.virtual_pad
            self.virtual_pad = None
            print("[ViGEmBus] Virtual controller disconnected.")

    def _apply_state_to_virtual_pad(self, state: GamepadState) -> None:
        """Apply parsed GamepadState to virtual Xbox 360 or DS4 controller."""
        pad = self.virtual_pad
        if not pad:
            return

        if isinstance(pad, vg.VDS4Gamepad):
            # PlayStation 4 DualShock 4 mapping
            w_buttons = 0
            if state.btn_a:
                w_buttons |= vg.DS4_BUTTONS.DS4_BUTTON_CROSS
            if state.btn_b:
                w_buttons |= vg.DS4_BUTTONS.DS4_BUTTON_CIRCLE
            if state.btn_x:
                w_buttons |= vg.DS4_BUTTONS.DS4_BUTTON_SQUARE
            if state.btn_y:
                w_buttons |= vg.DS4_BUTTONS.DS4_BUTTON_TRIANGLE
            if state.btn_lb:
                w_buttons |= vg.DS4_BUTTONS.DS4_BUTTON_SHOULDER_LEFT
            if state.btn_rb:
                w_buttons |= vg.DS4_BUTTONS.DS4_BUTTON_SHOULDER_RIGHT
            if state.btn_back:
                w_buttons |= vg.DS4_BUTTONS.DS4_BUTTON_SHARE
            if state.btn_start:
                w_buttons |= vg.DS4_BUTTONS.DS4_BUTTON_OPTIONS
            if state.btn_lsb:
                w_buttons |= vg.DS4_BUTTONS.DS4_BUTTON_THUMB_LEFT
            if state.btn_rsb:
                w_buttons |= vg.DS4_BUTTONS.DS4_BUTTON_THUMB_RIGHT

            w_special = 0
            if state.btn_guide:
                w_special |= vg.DS4_SPECIAL_BUTTONS.DS4_SPECIAL_BUTTON_PS

            # Calculate D-Pad direction
            dpad_dir = vg.DS4_DPAD_DIRECTIONS.DS4_BUTTON_DPAD_NONE
            if state.dpad_up and state.dpad_right:
                dpad_dir = vg.DS4_DPAD_DIRECTIONS.DS4_BUTTON_DPAD_NORTHEAST
            elif state.dpad_down and state.dpad_right:
                dpad_dir = vg.DS4_DPAD_DIRECTIONS.DS4_BUTTON_DPAD_SOUTHEAST
            elif state.dpad_down and state.dpad_left:
                dpad_dir = vg.DS4_DPAD_DIRECTIONS.DS4_BUTTON_DPAD_SOUTHWEST
            elif state.dpad_up and state.dpad_left:
                dpad_dir = vg.DS4_DPAD_DIRECTIONS.DS4_BUTTON_DPAD_NORTHWEST
            elif state.dpad_up:
                dpad_dir = vg.DS4_DPAD_DIRECTIONS.DS4_BUTTON_DPAD_NORTH
            elif state.dpad_right:
                dpad_dir = vg.DS4_DPAD_DIRECTIONS.DS4_BUTTON_DPAD_EAST
            elif state.dpad_down:
                dpad_dir = vg.DS4_DPAD_DIRECTIONS.DS4_BUTTON_DPAD_SOUTH
            elif state.dpad_left:
                dpad_dir = vg.DS4_DPAD_DIRECTIONS.DS4_BUTTON_DPAD_WEST

            pad.directional_pad(dpad_dir)
            pad.report.wButtons = w_buttons
            pad.report.bSpecial = w_special
            pad.left_trigger_float(max(0.0, min(1.0, state.trigger_l / 255.0)))
            pad.right_trigger_float(max(0.0, min(1.0, state.trigger_r / 255.0)))
            # DS4 thumbstick Y is inverted in raw report (0=up, 255=down)
            pad.left_joystick_float(
                max(-1.0, min(1.0, state.stick_lx / 32767.0)),
                max(-1.0, min(1.0, -state.stick_ly / 32767.0)),
            )
            pad.right_joystick_float(
                max(-1.0, min(1.0, state.stick_rx / 32767.0)),
                max(-1.0, min(1.0, -state.stick_ry / 32767.0)),
            )
            pad.update()

        elif isinstance(pad, vg.VX360Gamepad):
            # Xbox 360 XUSB mapping
            w_buttons = 0
            if state.btn_a:
                w_buttons |= vg.XUSB_BUTTON.XUSB_GAMEPAD_A
            if state.btn_b:
                w_buttons |= vg.XUSB_BUTTON.XUSB_GAMEPAD_B
            if state.btn_x:
                w_buttons |= vg.XUSB_BUTTON.XUSB_GAMEPAD_X
            if state.btn_y:
                w_buttons |= vg.XUSB_BUTTON.XUSB_GAMEPAD_Y
            if state.btn_lb:
                w_buttons |= vg.XUSB_BUTTON.XUSB_GAMEPAD_LEFT_SHOULDER
            if state.btn_rb:
                w_buttons |= vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER
            if state.btn_back:
                w_buttons |= vg.XUSB_BUTTON.XUSB_GAMEPAD_BACK
            if state.btn_start:
                w_buttons |= vg.XUSB_BUTTON.XUSB_GAMEPAD_START
            if state.btn_guide:
                w_buttons |= vg.XUSB_BUTTON.XUSB_GAMEPAD_GUIDE
            if state.btn_lsb:
                w_buttons |= vg.XUSB_BUTTON.XUSB_GAMEPAD_LEFT_THUMB
            if state.btn_rsb:
                w_buttons |= vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_THUMB

            # D-pad directions
            if state.dpad_up:
                w_buttons |= vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP
            if state.dpad_down:
                w_buttons |= vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN
            if state.dpad_left:
                w_buttons |= vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_LEFT
            if state.dpad_right:
                w_buttons |= vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_RIGHT

            pad.report.wButtons = w_buttons
            pad.report.bLeftTrigger = max(0, min(255, state.trigger_l))
            pad.report.bRightTrigger = max(0, min(255, state.trigger_r))
            pad.report.sThumbLX = max(-32768, min(32767, state.stick_lx))
            pad.report.sThumbLY = max(-32768, min(32767, state.stick_ly))
            pad.report.sThumbRX = max(-32768, min(32767, state.stick_rx))
            pad.report.sThumbRY = max(-32768, min(32767, state.stick_ry))
            pad.update()

    def _reset_virtual_pad_inputs(self) -> None:
        """Reset inputs to neutral center/released."""
        if self.virtual_pad:
            self.virtual_pad.reset()
            self.virtual_pad.update()
        try:
            self.device.send_rumble(0, 0)
        except Exception:
            pass

    def test_rumble(self, duration_sec: float = 0.4, intensity: int = 200) -> None:
        """Triggers a brief test vibration on the physical controller."""
        def _run_test():
            if self.device.is_connected:
                self.device.send_rumble(intensity, intensity)
                time.sleep(duration_sec)
                self.device.send_rumble(0, 0)
        threading.Thread(target=_run_test, daemon=True, name="TestRumbleThread").start()

    def _emit_status(self, is_connected: bool, mode: ProtocolMode, battery: Optional[BatteryStatus], charging: bool) -> None:
        """Notify status callback with current snapshot."""
        if not self.status_callback:
            return

        dev_name = "None"
        if is_connected and self.device.device_info:
            mfr = self.device.device_info.get("manufacturer_string") or ""
            prod = self.device.device_info.get("product_string") or "Gamepad"
            dev_name = f"{mfr} {prod}".strip()

        target_label = "PlayStation 4" if self.config.emulation_target.lower() == "ds4" else "Xbox 360"

        info = {
            "is_connected": is_connected,
            "device_name": dev_name,
            "protocol_mode": mode,
            "battery": battery,
            "charging": charging,
            "rate_hz": self.current_rate_hz,
            "latency_ms": self.current_latency_ms,
            "jitter_ms": self.current_jitter_ms,
            "target_label": target_label,
            "rumble_active": (self._current_large_motor > 0 or self._current_small_motor > 0),
        }
        try:
            self.status_callback(info)
        except Exception:
            pass

    def start_background(self) -> None:
        """Start polling loop in a background daemon thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="BridgePollingThread")
        self._thread.start()

    def run(self) -> None:
        """Run blocking polling loop (handles SIGINT / SIGTERM for CLI)."""
        self._running = True

        def _handle_exit(sig, frame):
            print("\n[Bridge] Stopping...")
            self._running = False

        try:
            signal.signal(signal.SIGINT, _handle_exit)
            signal.signal(signal.SIGTERM, _handle_exit)
        except Exception:
            pass

        self._run_loop()

    def _run_loop(self) -> None:
        """Core polling loop."""
        self._setup_virtual_pad()

        interval = self.config.poll_interval_sec
        print(f"[Bridge] Running polling loop at target {self.config.poll_rate_hz} Hz (interval: {interval*1000:.1f}ms).")

        reconnect_cooldown = 1.0
        last_reconnect_attempt = 0.0

        try:
            while self._running:
                # 1. Ensure physical device is connected
                if not self.device.is_connected:
                    self._reset_virtual_pad_inputs()
                    now = time.time()
                    if now - last_reconnect_attempt >= reconnect_cooldown:
                        last_reconnect_attempt = now
                        if not self.device.open():
                            self._emit_status(False, ProtocolMode.UNKNOWN, None, False)
                            time.sleep(0.1)
                            continue
                        else:
                            self._last_battery = None
                            self._last_mode = ProtocolMode.UNKNOWN
                            self._emit_status(True, ProtocolMode.UNKNOWN, None, False)

                # 2. Non-blocking read from controller HID
                loop_start = time.perf_counter()
                packet = self.device.read(max_length=64, timeout_ms=5)

                if packet:
                    self._packet_count += 1
                    now_perf = time.perf_counter()
                    if self._last_packet_ts > 0.0:
                        dt = now_perf - self._last_packet_ts
                        self._packet_intervals.append(dt)
                    self._last_packet_ts = now_perf

                    state = self.parser.parse(packet)
                    if state:
                        self._apply_state_to_virtual_pad(state)

                        # Check protocol mode changes
                        status_updated = False
                        if state.protocol_mode != self._last_mode:
                            self._last_mode = state.protocol_mode
                            status_updated = True
                            mode_name = {
                                ProtocolMode.SWITCH_FULL: "Switch Standard Full (0x30, 12-bit sticks)",
                                ProtocolMode.SWITCH_REPLY: "Switch Subcommand Reply (0x21)",
                                ProtocolMode.ODM_SIMPLE_3F: "ODM Clone Simple (0x3F)",
                                ProtocolMode.GENERIC_HID: "Generic DirectInput Fallback",
                            }.get(state.protocol_mode, "Unknown")
                            print(f"[Protocol] Active mode: {mode_name}")

                        # Check battery changes & notifications
                        if state.battery is not None:
                            if state.battery != self._last_battery:
                                self._last_battery = state.battery
                                status_updated = True
                                charge_str = " (Charging)" if state.charging else ""
                                print(f"[Status] Battery: {state.battery.name}{charge_str}")

                            # Battery warning alert
                            if state.battery in (BatteryStatus.EMPTY, BatteryStatus.CRITICAL, BatteryStatus.LOW) and not state.charging:
                                now_sec = time.time()
                                if self.config.low_battery_notify and (now_sec - self._last_battery_alert_ts > 600.0):
                                    self._last_battery_alert_ts = now_sec
                                    if self.battery_warning_callback:
                                        self.battery_warning_callback(state.battery.name)

                        # Update rate and latency calculation periodically (~1s)
                        now_ts = time.time()
                        if now_ts - self._last_rate_calc >= 1.0:
                            self.current_rate_hz = self._packet_count / (now_ts - self._last_rate_calc)
                            self._packet_count = 0
                            self._last_rate_calc = now_ts
                            if self._packet_intervals:
                                mean_dt = sum(self._packet_intervals) / len(self._packet_intervals)
                                variance = sum((x - mean_dt) ** 2 for x in self._packet_intervals) / len(self._packet_intervals)
                                self.current_latency_ms = mean_dt * 1000.0
                                self.current_jitter_ms = math.sqrt(variance) * 1000.0
                            status_updated = True

                        if status_updated:
                            self._emit_status(True, self._last_mode, self._last_battery, state.charging)

                # 3. Handle Game Force Feedback / Rumble dispatch
                if self.config.enable_rumble and self.device.is_connected:
                    now_perf = time.perf_counter()
                    need_write = False
                    with self._rumble_lock:
                        if self._rumble_changed:
                            self._current_large_motor = self._target_large_motor
                            self._current_small_motor = self._target_small_motor
                            self._rumble_changed = False
                            need_write = True
                            self._last_rumble_sent_ts = now_perf
                        elif (self._current_large_motor > 0 or self._current_small_motor > 0) and (now_perf - self._last_rumble_sent_ts >= 0.040):
                            # Refresh active rumble every 40ms so hardware doesn't time out
                            need_write = True
                            self._last_rumble_sent_ts = now_perf

                    if need_write:
                        self.device.send_rumble(self._current_large_motor, self._current_small_motor)

                # 4. High-precision sleep pacing for target polling rate
                elapsed = time.perf_counter() - loop_start
                sleep_needed = interval - elapsed
                if sleep_needed > 0:
                    time.sleep(sleep_needed)

        except KeyboardInterrupt:
            print("\n[Bridge] Keyboard interrupt received.")
        finally:
            self.stop()

    def stop(self) -> None:
        """Clean teardown of all resources."""
        self._running = False
        try:
            self.device.send_rumble(0, 0)
        except Exception:
            pass
        self.device.close()
        self._teardown_virtual_pad()
        self._emit_status(False, ProtocolMode.UNKNOWN, None, False)
        print("[Bridge] Clean shutdown completed.")

"""Core polling engine and virtual Xbox 360 / DS4 bridge using vgamepad and hidapi."""

import collections
import math
import signal
import sys
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import vgamepad as vg

from config import BridgeConfig
from device import ControllerDevice
from dsu_server import DsuServer
import hidhide
from parser import GamepadState, GyroAimProcessor, UnifiedGamepadParser
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
        self.gyro_processor = GyroAimProcessor(config.gyro_aim_sensitivity)
        self.dsu_server: Optional[DsuServer] = None
        self.virtual_pad: Optional[Union[vg.VX360Gamepad, vg.VDS4Gamepad]] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_battery: Optional[BatteryStatus] = None
        self._last_mode: ProtocolMode = ProtocolMode.UNKNOWN
        self._last_state: Optional[GamepadState] = None
        self._packet_count = 0
        self._last_rate_calc = time.time()
        self.current_rate_hz = 0.0

        # Stick neutral calibration state
        self._calibrating = False
        self._calibrate_samples: List[Tuple[int, int, int, int]] = []

        # HidHide cloaked device tracking
        self._cloaked_device_id: Optional[str] = None

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

        # Wireless inactivity / sleep detection & auto-rehandshake tracking
        self._last_packet_received_wall_ts = time.time()
        self._last_rehandshake_attempt = 0.0


    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def last_state(self) -> Optional[GamepadState]:
        return self._last_state

    @property
    def is_calibrating(self) -> bool:
        return self._calibrating

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
                # Keep strong reference to prevent GC while registered in C driver
                self._vigem_callback = self._on_vigem_notification
                self.virtual_pad.register_notification(self._vigem_callback)
                print(f"[ViGEmBus] Virtual {pad_label} Controller connected with Force Feedback (Rumble).")
            except Exception as e:
                print(f"[ViGEmBus] Virtual {pad_label} Controller connected (rumble warning: {e}).")

        # Start DSU Motion Server if configured
        if self.config.enable_dsu_server and not self.dsu_server:
            self.dsu_server = DsuServer(port=self.config.dsu_server_port)
            self.dsu_server.start()

        # HidHide cloaking if configured
        if self.config.enable_hidhide and not self._cloaked_device_id:
            try:
                target_id = f"HID\\VID_{self.config.vendor_id:04X}&PID_{self.config.product_id:04X}"
                if hidhide.cloak_device_id(target_id):
                    self._cloaked_device_id = target_id
            except Exception as e:
                print(f"[HidHide] Cloak error: {e}")

    def calibrate_stick_centers(self) -> None:
        """Initiate sampling of neutral stick positions to eliminate center drift."""
        with self._rumble_lock:
            self._calibrate_samples.clear()
            self._calibrating = True
        print("[Calibration] Stick center calibration started. Keep sticks centered...")
        if self.device.is_connected:
            self._emit_status(True, self._last_mode, self._last_battery, False)

    def _on_vigem_notification(self, client, target, large_motor, small_motor, led_number, user_data):
        """C-callback invoked by ViGEmBus driver."""
        try:
            self._on_game_rumble_received(large_motor, small_motor)
        except Exception as e:
            print(f"[ViGEmBus] Callback exception: {e}")

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
            self._vigem_callback = None
            print("[ViGEmBus] Virtual controller disconnected.")

    def _apply_state_to_virtual_pad(self, state: GamepadState) -> None:
        """Apply parsed GamepadState to virtual Xbox 360 or DS4 controller."""
        pad = self.virtual_pad
        if not pad:
            return

        # Gyro Aiming: blend gyro angular velocity into Right Stick
        if self.config.enable_gyro_aim and state.imu_gyro:
            is_aiming = (not self.config.gyro_aim_trigger_only) or (state.trigger_l > 30)
            if is_aiming and (state.imu_gyro[0] != 0.0 or state.imu_gyro[2] != 0.0):
                self.gyro_processor.sensitivity = self.config.gyro_aim_sensitivity
                blended_rx, blended_ry = self.gyro_processor.process(
                    state.imu_gyro[0], state.imu_gyro[2], state.stick_rx, state.stick_ry
                )
                state.stick_rx = blended_rx
                state.stick_ry = blended_ry


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
            if state.btn_guide or state.btn_capture:
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
            if state.btn_guide or state.btn_capture:
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
            "calibrating": self._calibrating,
            "dsu_active": bool(self.dsu_server and self.dsu_server.is_running),
            "hidhide_active": bool(self._cloaked_device_id),
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
                            self._last_packet_received_wall_ts = time.time()
                            self._last_rehandshake_attempt = time.time()
                            self._emit_status(True, ProtocolMode.UNKNOWN, None, False)

                # 2. Non-blocking read from controller HID
                loop_start = time.perf_counter()
                packet = self.device.read(max_length=64, timeout_ms=5)

                if packet:
                    self._last_packet_received_wall_ts = time.time()
                    self._packet_count += 1
                    now_perf = time.perf_counter()
                    if self._last_packet_ts > 0.0:
                        dt = now_perf - self._last_packet_ts
                        self._packet_intervals.append(dt)
                    self._last_packet_ts = now_perf

                    state = self.parser.parse(packet)
                    if state:
                        self._last_state = state

                        # Auto re-handshake if Switch controller dropped to boot/simple mode (0x3F or 0x21)
                        if (
                            state.protocol_mode in (ProtocolMode.ODM_SIMPLE_3F, ProtocolMode.SWITCH_REPLY)
                            and self.device.is_switch_controller
                        ):
                            now_wall = time.time()
                            if now_wall - self._last_rehandshake_attempt >= 2.5:
                                self._last_rehandshake_attempt = now_wall
                                print("[Bridge] Switch Pro controller running in boot mode. Re-sending handshake...")
                                threading.Thread(target=self.device.perform_handshake, daemon=True, name="ReHandshakeThread").start()

                        # Calibration sampling if requested
                        if self._calibrating:
                            if (
                                state.raw_lx is not None
                                and state.raw_ly is not None
                                and state.raw_rx is not None
                                and state.raw_ry is not None
                            ):
                                self._calibrate_samples.append((state.raw_lx, state.raw_ly, state.raw_rx, state.raw_ry))
                                if len(self._calibrate_samples) >= 60:
                                    avg_lx = sum(s[0] for s in self._calibrate_samples) // len(self._calibrate_samples)
                                    avg_ly = sum(s[1] for s in self._calibrate_samples) // len(self._calibrate_samples)
                                    avg_rx = sum(s[2] for s in self._calibrate_samples) // len(self._calibrate_samples)
                                    avg_ry = sum(s[3] for s in self._calibrate_samples) // len(self._calibrate_samples)
                                    self.config.stick_lx_center = avg_lx
                                    self.config.stick_ly_center = avg_ly
                                    self.config.stick_rx_center = avg_rx
                                    self.config.stick_ry_center = avg_ry
                                    self.parser.set_stick_centers(avg_lx, avg_ly, avg_rx, avg_ry)
                                    self.config.save_to_json(self.config.config_path)
                                    self._calibrating = False
                                    print(f"[Calibration] Completed: LX={avg_lx}, LY={avg_ly}, RX={avg_rx}, RY={avg_ry}")
                                    self._emit_status(True, self._last_mode, self._last_battery, state.charging)

                        # Motion broadcast to Cemuhook DSU server
                        if self.dsu_server and self.dsu_server.is_running:
                            self.dsu_server.update_state(state)

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

                else:
                    # Inactivity / sleep detection for wireless/Bluetooth controllers
                    if self.device.is_connected:
                        now_wall = time.time()
                        # If no packets received for 1.8 seconds, controller powered off / auto-slept
                        if now_wall - self._last_packet_received_wall_ts > 1.8:
                            print("[Bridge] Wireless controller inactive for >1.8s (auto-sleep or disconnected). Resetting virtual pad.")
                            self._reset_virtual_pad_inputs()
                            self._last_state = None
                            self._last_mode = ProtocolMode.UNKNOWN
                            self.device.close()  # Closes stale Windows Bluetooth handle
                            self._emit_status(False, ProtocolMode.UNKNOWN, None, False)
                            continue

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
        except Exception as e:
            print(f"[Bridge] Error in loop: {e}")
        finally:
            self._cleanup_resources()

    def stop(self) -> None:
        """Clean teardown of all resources."""
        if not self._running and self.virtual_pad is None:
            return

        self._running = False

        # Wait for polling thread to finish its current iteration
        if self._thread and self._thread.is_alive() and threading.current_thread() != self._thread:
            try:
                self._thread.join(timeout=1.5)
            except Exception:
                pass
        self._thread = None

        self._cleanup_resources()

    def _cleanup_resources(self) -> None:
        """Internal resource teardown."""
        self._running = False
        try:
            self.device.send_rumble(0, 0)
        except Exception:
            pass
        self.device.close()
        self._teardown_virtual_pad()
        if self.dsu_server:
            self.dsu_server.stop()
            self.dsu_server = None
        if self._cloaked_device_id:
            try:
                hidhide.uncloak_device_id(self._cloaked_device_id)
                self._cloaked_device_id = None
            except Exception:
                pass
        self._emit_status(False, ProtocolMode.UNKNOWN, None, False)
        print("[Bridge] Clean shutdown completed.")

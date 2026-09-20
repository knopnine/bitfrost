# Changelog
 
All notable changes to the **Bifrost** project will be documented in this file.
 
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
 
---
 
## [1.3.0] - 2026-09-20

### Rebranded
- **Project Rebranded to Bifrost 🌈**:
  - Rebranded from Switch2Xbox to **Bifrost** (universal controller bridge) to establish an independent identity and avoid trademark conflicts.
  - Executable renamed to `Bifrost.exe`, central log renamed to `bifrost.log`.
 
### Added
- **HardwareTester-Style Gamepad Visualizer**:
  - Modeled after the industry-standard visualizer on [hardwaretester.com/gamepad](https://hardwaretester.com/gamepad).
  - **Vector Gamepad Silhouette**: Ergonomic vector gamepad graphic on Canvas with live-moving analog stick caps, glowing ABXY face buttons, directional D-Pad arms, trigger lobes, and bumper badges.
  - **Dual Radars with 5-Decimal Readouts**: 96x96 circular radar displays for Left Stick (`AXIS 0, 1`) and Right Stick (`AXIS 2, 3`) with high-precision float readouts (`AXIS 0: +0.00000` to `AXIS 3: +0.00000`).
  - **Live Circularity Error Benchmark**: Real-time scatter point plotter and mathematical circularity error calculation ($\frac{1}{N} \sum |R - 1.0| \times 100\%$) with toggle, reset, and color-coded error thresholds.
  - **W3C Standard Button Gauges (B0 - B17)**: 18-button meter array with dynamic progress fill meters and live numeric levels (`0.00` to `1.00`), including smooth continuous analog trigger fill bars.
  - **HardwareTester Metadata Header**: Live device metadata (`INDEX`, `DEVICE`, `TARGET`, `MAPPING`, `PROTOCOL`, `TIMING`, `BATTERY`, `VIBRATION`).

### Fixed
- **Wireless Bluetooth Inactivity Sleep & Reconnect Auto-Recovery**:
  - Fixed issue where the gamepad goes to sleep to save battery and triggers random/ghost buttons upon reconnecting.
  - Added 1.8s inactivity heartbeat detection in `GamepadBridge` to immediately zero all virtual gamepad inputs and cleanly close stale Windows Bluetooth HID handles.
  - Added auto-handshake detection to promote the gamepad from boot mode (`0x3F` or `0x21`) back to full 60Hz 12-bit mode (`0x30`) automatically on wake-up.
  - Added spurious transition packet filter in `UnifiedGamepadParser` to drop unhandled Bluetooth state changes before they reach fallback decoders.
- **PyInstaller Build Locking Fix**:
  - `build_exe.py` automatically terminates any running `Bifrost.exe` instances prior to compiling to prevent Windows `[WinError 5]` file locking on `.pyd` dependencies.

---

## [1.2.0] - 2026-09-20

### Added
- **Interactive Live 2D Visualizer**:
  - Real-time 30 FPS visualizer with dual 2D stick canvases displaying dynamic center crosshairs, live deadzone rings, and stick clicks (LSB/RSB).
  - Analog trigger progress meters (LT/RT) displaying live percentage fill.
  - Digital button matrix (ABXY, D-Pad, LB/RB, Back, Guide, Start) providing instant visual feedback.
  - Throttles execution when minimized to system tray to save CPU resources.
- **Hardware Neutral Stick Calibration**:
  - 1-click automatic calibration sampling 60 frames of neutral stick resting positions.
  - Calibrated center offsets are subtracted before deadzone processing, eliminating stick drift with zero center deadzone penalty.
- **Gyro Aiming Assist**:
  - Blends 6-axis gyroscope angular velocity into Right Stick deflections for mouse-like precision aiming.
  - Configurable sensitivity slider (0.2x to 3.0x) and optional hold-to-aim trigger gating (aim only while holding LT / ZL).
  - Subcommand `0x40` handshake enables IMU sensors on Switch Pro controllers.
- **Cemuhook DSU Motion Protocol Server**:
  - Built-in UDP server listening on port `26760` streaming 100Hz 6-axis motion packets to emulators (Dolphin, Cemu, Yuzu, Ryujinx, RPCS3).
  - Implements protocol version negotiation, controller info query, CRC32 checksums, and client subscription tracking.
- **Nefarius HidHide Double-Input Cloaking**:
  - Direct integration with HidHide driver and CLI to cloak the physical Switch Pro controller from games.
  - Ensures games only see the virtual Xbox 360 or DualShock 4 controller, preventing double-input bugs.
- **Configuration Profiles**:
  - Built-in preset profiles ("Default", "Shooter (Gyro Aim)", "Racing (Progressive)", "Retro (1:1 Nintendo)").
  - Support for creating, saving, and deleting custom user profiles persisted to `profiles.json`.
- **Windows 11 Modern Dark Theme**:
  - Complete GUI redesign with a dark Zinc palette (`#121214`), tabbed card navigation, and custom controls.
- **Unit Test Suite Expansion**:
  - Added test suites for DSU UDP protocol, Gyro aim processor, and neutral center calibration (22/22 tests passing).

---

## [1.1.1] - 2026-09-09

### Fixed
- **Resolved Windows `ntdll.dll` Crash (Access Violation `0xc0000005`)**:
  - **Thread-Safe HID I/O**: Synchronized all `hidapi` read, write, and close operations with a reentrant `threading.RLock()`.
  - **Graceful Bridge Shutdown**: Ensured the background polling thread finishes its current iteration and joins before closing handles or unregistering virtual gamepads.
  - **System Tray Icon Debouncing**: Prevented repeated Win32 shell icon allocations every second by updating the tray icon only when the connection state actually changes.
  - **ViGEm Callback Protection**: Kept strong Python references to the C callback function and matched `inspect.signature` precisely to prevent ctypes callback deallocation.

### Added
- **Centralized File Logging (`bifrost.log`)**:
  - Automatically records all runtime events and full exception stack traces to `bifrost.log` with a 5 MB rotating buffer.
  - Installed global `sys.excepthook` and `threading.excepthook` handlers so no crash goes unrecorded.
- **View Logs Button**:
  - Added a `📄 View Logs` button in the GUI and a `View Logs (bifrost.log)` option in the system tray menu to easily open logs in Notepad.

---

## [1.1.0] - 2026-09-09

### Added
- **Dual Virtual Emulation Mode (Xbox 360 & PlayStation 4 DualShock 4)**:
  - Added support for both `vgamepad.VX360Gamepad` (Xbox 360) and `vgamepad.VDS4Gamepad` (PlayStation 4 DualShock 4) via ViGEmBus.
  - Allows games with native PlayStation controller support (e.g. *Assassin's Creed Shadows*, *God of War*, *Spider-Man*, *Cyberpunk 2077*) to natively display PlayStation button prompts ($\times$, $\square$, $\triangle$, $\bigcirc$).
  - Full DS4 button, trigger, and D-pad direction mapping with inverted Y-axis thumbsticks.
  - Dropdown selector in GUI and `--target {xbox360,ds4}` CLI argument.
- **Stick Sensitivity Response Curves**:
  - **Linear (1:1 Standard)**: Default direct 1:1 mapping.
  - **Smooth Aim (Exponential S-Curve, $r^{1.5}$)**: Lower sensitivity near center for ultra-fine stealth movement and archery camera precision, smoothly accelerating to 100% at outer rim.
  - **Aggressive (Snappy, $r^{0.75}$)**: Snappy acceleration for high-action twitch games.
  - Configurable via GUI dropdown and `--curve {linear,smooth,aggressive}` CLI argument.
- **Trigger Emulation Profiles**:
  - **Instant Hair Trigger**: Zero-latency instant 255 on tactile digital switch click.
  - **Progressive Smooth Ramp (~25ms)**: Microsecond 5-tick linear ramp pulling simulation to prevent games from rejecting abrupt digital snaps and provide smooth draw acceleration.
  - Configurable via GUI dropdown and `--trigger {hair,progressive}` CLI argument.
- **Low Battery Desktop Notification**:
  - Automatic desktop notification banner via `pystray` tray integration when battery level drops to Low or Critical (`EMPTY`, `CRITICAL`, `LOW`).
  - Debounced at 10-minute intervals to avoid notification spam.
  - Toggleable via GUI checkbox (`[x] Notify on low battery`).
- **Real-Time Input Latency & Jitter Monitor**:
  - Added high-resolution delta tracking (`time.perf_counter()`) over a 60-sample sliding window.
  - GUI status card displays live latency and jitter: e.g. `Latency: 5.0 ms (±0.3 ms)`.
- **Settings Persistence Extended**:
  - Persists `emulation_target`, `stick_curve`, `trigger_mode`, and `low_battery_notify` in `settings.json`.
- **Expanded Test Suite**:
  - Added tests for `VDS4Gamepad` lifecycle and button bitmask mapping.
  - Added tests for sensitivity curve math and `TriggerRamp` state machine.
  - 13/13 automated unit and integration tests passing.

---

## [1.0.0] - 2026-09-08

### Added
- **Initial Release of Switch2Xbox**:
  - Full XInput emulation of Xbox 360 controller via ViGEmBus.
  - Bi-directional force feedback / vibration (HD rumble translation from in-game XInput motor commands to Switch Pro `0x10` vibration packets).
  - Multi-protocol auto-discovery for official Nintendo Switch Pro controllers (`0x057E:0x2009`), Joy-Cons, and third-party / ODM clones (`0x3F`, generic DirectInput).
  - Physical Nintendo $\leftrightarrow$ Xbox layout swap ($A \leftrightarrow B$, $X \leftrightarrow Y$).
  - 10% radial center deadzone and 5% outer deadzone saturation for guaranteed sprint speed.
  - Modern desktop GUI built with Tkinter and Windows System Tray (`pystray`) integration.
  - Dynamic tray icon color status (Green = Connected, Orange = Searching).
  - Auto-minimize on close (`X`) to keep running in background while playing.
  - Settings persistence (`settings.json`) and Windows Startup auto-start (`HKCU\Software\Microsoft\Windows\CurrentVersion\Run`).
  - Standalone Windows `.exe` packaging with PyInstaller.

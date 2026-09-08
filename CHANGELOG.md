# Changelog

All notable changes to the **Switch2Xbox** project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

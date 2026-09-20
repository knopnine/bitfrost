# Switch2Xbox 🎮 (v1.3.0)

A lightweight, high-performance, low-latency Windows background utility that bridges **Nintendo Switch Pro Controllers** and **third-party / ODM Switch clone gamepads** (USB or Bluetooth) to a virtual **Xbox 360 controller (XInput)** or **PlayStation 4 controller (DualShock 4)** via ViGEmBus.

Designed specifically to eliminate stick drift, restore missing force-feedback (vibration), remap buttons, provide custom sensitivity curves, support motion aiming, and eliminate double-input issues for PC gaming.

---

## What's New in v1.3.0 🚀

- 🕹️ **HardwareTester-Style Gamepad Visualizer**: Inspired by [hardwaretester.com/gamepad](https://hardwaretester.com/gamepad), featuring:
  - **Vector Gamepad Silhouette**: Live animated controller outline with moving analog stick caps, glowing buttons, and trigger indicators.
  - **Dual Precision Radars**: 5-decimal high-precision live readouts (`AXIS 0: +0.00000` to `AXIS 3: +0.00000`) following standard W3C Gamepad API conventions.
  - **Live Circularity Error Benchmark**: Interactive benchmark tool plotting real-time scatter points on radar circles and calculating average outer gate error percentage ($\frac{1}{N} \sum |R - 1.0| \times 100\%$).
  - **Standard Buttons (B0 - B17) Meter Array**: Live progress bar gauges and float levels (`0.00` to `1.00`) for all 18 standard W3C buttons, including analog trigger depression meters.
- 🔋 **Wireless Bluetooth Sleep & Reconnect Auto-Recovery**:
  - Implemented 1.8s inactivity heartbeat detection to immediately zero virtual inputs and close stale Windows Bluetooth HID handles when the controller sleeps.
  - Automatic re-handshake engine when the controller powers back on in boot mode (`0x3F` or `0x21`), seamlessly restoring full 60Hz 12-bit mode without requiring a bridge restart.
  - Spurious transition packet filter preventing phantom/ghost button clicks during Bluetooth reconnection.
- 🎯 **1-Click Hardware Stick Calibration**: Automatically samples physical stick rest positions over 60 frames and saves calibrated center offsets to eliminate hardware drift with zero center deadzone penalty.
- 🎯 **Gyro Aiming Assist**: Blends 6-axis gyroscope angular velocity into Right Stick aiming for mouse-like precision in PC shooters. Supports optional hold-to-aim gating (aim only while holding LT / ZL).
- 📡 **Cemuhook DSU Motion Server**: Integrated UDP server broadcasting 100Hz 6-axis motion data on port `26760` with CRC32 checksums, compatible with Dolphin, Cemu, Yuzu, Ryujinx, and RPCS3.
- 🛡️ **Nefarius HidHide Double-Input Cloaking**: Automatic physical controller cloaking via HidHide, hiding the DirectInput Switch gamepad from games so only the virtual Xbox 360 or DS4 pad is visible.
- 💾 **Configuration Profiles**: Instant switching between customized game profiles ("Default", "Shooter (Gyro Aim)", "Racing (Progressive)", "Retro (1:1 Nintendo)") with support for custom user-created profiles.
- 🌙 **Windows 11 Modern Dark Theme**: Clean Zinc palette (`#121214`) with tabbed card navigation.

---

## Key Features

- ⚡ **Full XInput & DirectInput Emulation**: Emulates native Microsoft Xbox 360 or Sony DualShock 4 controllers via `vgamepad` and ViGEmBus driver. Compatible with 100% of PC games.
- 🎯 **Stick Drift & Deadzone Optimization**:
  - **10% Radial Center Deadzone**: Eliminates stick drift smoothly without sudden jump artifacts.
  - **5% Outer Saturation Deadzone**: Ensures full 100% sprint/tilt is reachable even on budget clone analog sticks.
- 📳 **Real In-Game Force Feedback (Rumble)**:
  - Intercepts force feedback vibration packets (large low-frequency motor & small high-frequency motor) from games.
  - Translates vibration amplitudes into Nintendo Switch HD Rumble / dual-motor frequency packets (`0x10` subcommands) in real time.
- 🔄 **Smart Button Mapping**:
  - Automatic physical Nintendo $\leftrightarrow$ Xbox layout swap ($A \leftrightarrow B$, $X \leftrightarrow Y$) so on-screen button prompts match your finger placements.
- 🔍 **Auto-Discovery & Fallback Decoder**:
  - Automatically identifies official Switch controllers (`0x057E:0x2009`) and initiates official Nintendo handshake (`0x03, 0x30` reports, Player 1 LED, rumble enable).
  - Automatically falls back to generic DirectInput / ODM `0x3F` decoders if clone chips don't support official subcommands.
- 🖥️ **System Tray & Graphical Interface (GUI)**:
  - Clean desktop GUI built with Tkinter and modern card styling.
  - Sits quietly in the Windows notification tray (`pystray`) with dynamic color indicators (Green = Connected, Orange = Searching).
  - Auto-minimizes on close (`X`) so your game session is never interrupted.
- ⚙️ **Settings Persistence & Windows Auto-Start**:
  - Remembers your settings across reboots in `settings.json`.
  - One-click option to start minimized with Windows (`HKCU\Software\Microsoft\Windows\CurrentVersion\Run`).

---

## Quick Start

### 1. Requirements
- Windows 10 or 11 (64-bit)
- [ViGEmBus Driver](https://github.com/ViGEm/ViGEmBus/releases) installed
- Python 3.10+ (if running from source)

### 2. Running the Standalone Executable (.exe)
No Python installation required!
1. Download or locate `dist/Switch2Xbox/Switch2Xbox.exe`.
2. Double-click **`Switch2Xbox.exe`**.
3. Connect your gamepad via USB cable or Bluetooth.
4. The tray icon turns **Green**, and your game detects the virtual controller immediately!

### 3. Running from Source
Install dependencies:
```bash
pip install hidapi vgamepad pystray Pillow
```

Launch the GUI:
```bash
python main.py
```

Launch directly minimized to the system tray:
```bash
python main.py --minimized
```

---

## CLI Options

```bash
python main.py [OPTIONS]
```

| Option | Default | Description |
|---|---|---|
| `--target` | `xbox360` | Emulated controller: `xbox360` or `ds4` |
| `--curve` | `linear` | Stick response curve: `linear`, `smooth`, or `aggressive` |
| `--trigger` | `hair` | Trigger profile: `hair` (instant) or `progressive` (smooth ramp) |
| `--deadzone <float>`| `0.10` | Radial center deadzone fraction (e.g. 0.10 = 10%) |
| `--rate <int>` | `200` | Polling rate in Hz (120 to 250 Hz) |
| `--no-swap` | False | Keep original Nintendo ABXY layout (disable swap) |
| `--no-rumble` | False | Disable in-game force feedback / vibration |
| `--force-generic` | False | Force generic DirectInput fallback decoder |
| `--vid <hex>` | `0x057E` | Target Vendor ID in hexadecimal |
| `--pid <hex>` | `0x2009` | Target Product ID in hexadecimal |
| `--list` | - | List all connected gamepads and exit |
| `--select` | - | Interactively select controller from detected list |
| `--inspect` | - | Launch live raw HID byte packet monitor |
| `--minimized` | False | Start directly minimized to system tray |

---

## Building the Executable

To compile a standalone `.exe` using PyInstaller:
```bash
python build_exe.py
```
The compiled output will be generated in `dist/Switch2Xbox/Switch2Xbox.exe`.

---

## Automated Tests

Run the test suite verifying packet parsing, deadzones, sensitivity curves, trigger smoothing, rumble translation, and ViGEmBus lifecycles:
```bash
python -m unittest discover -s tests -v
```

---

## License

MIT License. Free for personal and commercial use.

# Switch2Xbox 🎮

A lightweight, high-performance, low-latency Windows utility that bridges **Nintendo Switch Pro Controllers** and **third-party / ODM Switch clone gamepads** (USB or Bluetooth) to a virtual **Xbox 360 controller (XInput)** via ViGEmBus.

Designed specifically to solve deadzones, missing force-feedback (vibration), button swapping, and driver compatibility issues on PC games (e.g. Assassin's Creed Shadows, Steam, Game Pass, Epic Games, emulators).

---

## Key Features

- ⚡ **Full XInput Virtual Emulation**: Emulates a native Microsoft Xbox 360 controller via `vgamepad` and ViGEmBus driver. Compatible with 100% of Windows PC games.
- 🎯 **Stick Drift & Deadzone Optimization**:
  - **10% Radial Center Deadzone**: Eliminates stick drift smoothly without sudden jump artifacts.
  - **5% Outer Saturation Deadzone**: Ensures full 100% sprint/tilt is reachable even on budget clone analog sticks.
- 📳 **Real In-Game Force Feedback (Rumble)**:
  - Intercepts XInput force feedback vibration packets (large low-frequency motor & small high-frequency motor) from games.
  - Translates vibration amplitudes into Nintendo Switch HD Rumble / dual-motor frequency packets (`0x10` subcommands) in real time.
- 🔄 **Smart Button Mapping**:
  - Automatic physical Nintendo $\leftrightarrow$ Xbox layout swap ($A \leftrightarrow B$, $X \leftrightarrow Y$) so on-screen button prompts match your finger placements.
  - Toggleable via GUI or CLI.
- 🔍 **Auto-Discovery & Fallback Decoder**:
  - Automatically identifies official Switch controllers (`0x057E:0x2009`) and initiates official Nintendo handshake (`0x03, 0x30` reports, Player 1 LED, rumble enable).
  - Automatically falls back to generic DirectInput / ODM `0x3F` decoders if clone chips don't support official subcommands.
- 🖥️ **System Tray & Graphical Interface (GUI)**:
  - Clean desktop GUI built with Tkinter and modern card styling.
  - Sits quietly in the Windows notification tray (`pystray`) with dynamic color indicators (Green = Connected, Orange = Searching).
  - Auto-minimizes on close (`X`) so your game session is never interrupted.
- ⚙️ **Settings Persistence & Windows Auto-Start**:
  - Remembers your settings (ABXY swap, deadzone, polling rate, rumble) across reboots in `settings.json`.
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
4. The tray icon turns **Green**, and your game will detect a standard Xbox 360 controller immediately!

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

You can also run Switch2Xbox with custom arguments or in headless CLI mode:

```bash
python main.py [OPTIONS]
```

| Option | Default | Description |
|---|---|---|
| `--vid <hex>` | `0x057E` | Target Vendor ID in hexadecimal |
| `--pid <hex>` | `0x2009` | Target Product ID in hexadecimal |
| `--list` | - | List all connected gamepads and exit |
| `--select` | - | Interactively select controller from detected list |
| `--inspect` | - | Launch live raw HID byte packet monitor |
| `--deadzone <float>`| `0.10` | Radial center deadzone (e.g. 0.10 = 10%) |
| `--rate <int>` | `200` | Polling rate in Hz (120 to 250 Hz) |
| `--no-swap` | False | Keep original Nintendo ABXY layout (disable swap) |
| `--no-rumble` | False | Disable in-game force feedback / vibration |
| `--force-generic` | False | Force generic DirectInput fallback decoder |
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

Run the test suite verifying packet parsing, deadzones, rumble translation, and ViGEmBus lifecycle:
```bash
python -m unittest discover -s tests -v
```

---

## License

MIT License. Free for personal and commercial use.

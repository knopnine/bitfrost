# Bifrost 🌈 (v1.3.0)

A lightweight, high-performance, low-latency Windows background utility that seamlessly bridges **Nintendo Switch Pro Controllers** and **third-party / ODM Switch clone gamepads** (USB or Bluetooth) to a virtual **Xbox 360 controller (XInput)** or **PlayStation 4 controller (DualShock 4)** via ViGEmBus.

---

## The Story: Why I Built Bifrost 💡

I have always loved the ergonomics, weight, and battery life of the Nintendo Switch Pro Controller and its modern third-party alternatives. Whether it's an official Pro Controller or a budget-friendly wireless clone from 8BitDo, Gulikit, or generic Shenzhen ODMs, the controller just feels right in your hands.

**However, using a Switch controller on a Windows PC has always been an exercise in pure frustration.**

If you have ever tried pairing a Switch gamepad to a PC for gaming outside of Steam, you have almost certainly encountered the exact same infuriating walls I did:

1. **The Inverted ABXY Nightmare**: PC games overwhelmingly expect Microsoft Xbox controller layouts. Nintendo places **A on the right** and **B at the bottom**—the exact inverse of an Xbox controller. Every time a game prompted *"Press A to jump!"*, muscle memory betrayed me and I pressed B instead, resulting in untimely in-game deaths and constant mental gymnastics.
2. **Missing In-Game Vibration**: Switch controllers have dual vibration motors, but Windows treats them as basic DirectInput devices. Games never triggered vibration. Explosions, gunshots, and tire rumbles were completely silent and devoid of tactile feedback.
3. **The Bluetooth Sleep & Ghost Button Curse**: To save battery, wireless controllers automatically enter sleep mode after a few minutes of inactivity. But on Windows, when waking the gamepad back up, the Bluetooth HID stack would choke on state-transition bytes, firing continuous phantom button presses (phantom A/B spamming or stuck joysticks). The only remedy was unplugging Bluetooth dongles or manually killing background apps.
4. **Boot-Mode Degradation**: Many third-party clone controllers boot into a primitive 8-bit mode (`0x3F` or `0x21`) and never promote to the high-precision 12-bit 60Hz mode (`0x30`) unless they receive a proprietary Nintendo handshake sequence.
5. **Stick Drift & Squaring Gates**: Budget controllers frequently suffer from off-center factory stick calibration and non-circular outer gates, causing unintended drift or preventing characters from reaching a 100% full sprint.
6. **Bloated, Complex Software**: Existing tools on the web were either bloated, required keeping Steam Big Picture open with heavy overlays, demanded paid driver wrappers, or caused nasty double-input conflicts in non-Steam titles (Xbox Game Pass, Epic Games, EA App, emulators).

I wanted something different: **a clean, standalone, zero-bloat Windows utility that "just works"**.

Connect any Switch Pro or clone controller via USB or Bluetooth, and Windows instantly detects a genuine Microsoft Xbox 360 or Sony DualShock 4 controller. Authentic force-feedback rumble works out of the box, ABXY buttons are placed where your fingers expect them, Bluetooth sleep/wake transitions happen seamlessly without ghost inputs, and you get pro-grade tools like Gyro Aiming and a live HardwareTester visualizer.

No bloat. No complex configuration. Just plug, play, and game.

---

## What Bifrost Does ⚡

Bifrost acts as a high-speed, low-latency translation bridge between raw Nintendo Switch HID packets and virtual gaming controllers:

- 🎮 **Universal Virtual Controller Emulation**: Emulates a native Microsoft Xbox 360 or Sony DualShock 4 controller via the rock-solid ViGEmBus kernel driver. Compatible with 100% of PC games across Steam, Xbox Game Pass, Epic Games, EA App, Ubisoft Connect, GOG, and standalone game launchers.
- 📳 **Real Force Feedback (Rumble) Translation**: Intercepts game vibration commands (low-frequency heavy motor and high-frequency light motor) and translates them into authentic Nintendo Switch HD Rumble / dual-motor frequency packets (`0x10` subcommands) in real time.
- 🔄 **Smart ABXY Physical Layout Swap**: Intelligently swaps $A \leftrightarrow B$ and $X \leftrightarrow Y$ so that when a game displays the bottom button prompt, you press the physical bottom button. (Can be toggled off if you prefer standard Nintendo positions).
- 🔋 **Smart Wireless Bluetooth Recovery**: Continuously monitors packet heartbeat. When your controller powers down to save battery, virtual inputs are zeroed immediately and stale Windows handles are closed. When you power it back on, an automatic asynchronous handshake promotes the controller back to full 60Hz 12-bit mode without ghost clicks or bridge restarts.
- 🕹️ **HardwareTester-Style Live Visualizer**: Built-in 30 FPS hardware monitor modeled after [hardwaretester.com/gamepad](https://hardwaretester.com/gamepad):
  - **Vector Gamepad Silhouette**: Live animated controller graphic with moving stick caps, glowing ABXY face buttons, D-Pad cross arms, trigger indicators, and bumpers.
  - **Dual Radars with 5-Decimal Readouts**: 96x96 circular radar displays for Left Stick (`AXIS 0, 1`) and Right Stick (`AXIS 2, 3`) displaying high-precision float values (`AXIS 0: +0.00000` to `AXIS 3: +0.00000`).
  - **Live Circularity Error Benchmark**: Real-time scatter point plotter and mathematical circularity error calculation ($\frac{1}{N} \sum |R - 1.0| \times 100\%$) with color-coded ratings.
  - **Standard Buttons (B0 - B17) Meter Array**: 18-button meter panel with dynamic progress fill meters and live numeric levels (`0.00` to `1.00`), including smooth continuous analog trigger fill bars.
- 🎯 **1-Click Hardware Stick Center Calibration**: Samples physical stick rest positions over 60 frames to eliminate hardware drift at the driver level without deadzone penalties.
- 🎯 **Gyro Aiming Assist**: Decodes 6-axis gyroscope angular velocity from Switch Pro Report `0x30` and blends yaw/pitch deltas into Right Stick deflections for mouse-like precision in PC shooters. Supports optional hold-to-aim trigger gating (aim only while holding LT / ZL).
- 📡 **Cemuhook DSU Motion Server**: Integrated UDP server broadcasting 100Hz 6-axis motion data on port `26760` with CRC32 checksums, compatible with Dolphin, Cemu, Yuzu, Ryujinx, and RPCS3.
- 🛡️ **Nefarius HidHide Double-Input Cloaking**: Automatically conceals the physical DirectInput Switch controller from games so only the emulated virtual controller is visible.
- 💾 **Configuration Profiles**: Instant switching between customized game profiles ("Default", "Shooter (Gyro Aim)", "Racing (Progressive)", "Retro (1:1 Nintendo)") with support for custom user-created profiles.
- 🌙 **Windows 11 Modern Dark Theme**: Clean Zinc palette (`#121214`) with tabbed card navigation and system tray auto-minimization.

---

## What's New in v1.3.0 🚀

- 🕹️ **HardwareTester-Style Gamepad Visualizer**: Interactive vector gamepad silhouette, dual 5-decimal precision stick radars, standard W3C button gauge array (`B0`–`B17`), and live stick circularity benchmark.
- 🔋 **Wireless Bluetooth Sleep & Reconnect Auto-Recovery**: 1.8s inactivity heartbeat detection, auto-zero virtual inputs, stale handle cleanup, and automatic re-handshake engine.
- 🛡️ **Spurious Bluetooth Packet Filter**: Prevents phantom/ghost button presses during Bluetooth reconnection state changes.
- 🚀 **PyInstaller Build Locking Fix**: Automatic process termination before compiling to prevent Windows file-locking conflicts.

---

## Quick Start

### 1. Requirements
- Windows 10 or 11 (64-bit)
- [ViGEmBus Driver](https://github.com/ViGEm/ViGEmBus/releases) installed
- Python 3.10+ (if running from source)

### 2. Running the Standalone Executable (.exe)
No Python installation required!
1. Download or locate `dist/Bifrost/Bifrost.exe`.
2. Double-click **`Bifrost.exe`**.
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
The compiled output will be generated in `dist/Bifrost/Bifrost.exe`.

---

## Automated Tests

Run the test suite verifying packet parsing, deadzones, sensitivity curves, trigger smoothing, rumble translation, and ViGEmBus lifecycles:
```bash
python -m unittest discover -s tests -v
```

---

## License

MIT License. Free for personal and commercial use.

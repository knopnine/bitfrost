"""Main entry point for Nintendo Switch / ODM Gamepad to Virtual Xbox 360 Bridge."""

import argparse
import sys
from typing import Optional

from bridge import GamepadBridge
from config import APP_VERSION, DEFAULT_SWITCH_PID, DEFAULT_SWITCH_VID, BridgeConfig
from device import list_connected_gamepads
from inspector import run_inspector
from logger import logger, setup_logging


def parse_hex_int(val: str) -> int:
    """Parse integer from hex string (e.g. '0x057E' or '057E') or decimal."""
    val = val.strip()
    if val.lower().startswith("0x"):
        return int(val, 16)
    try:
        return int(val, 16)
    except ValueError:
        return int(val)


def print_banner() -> None:
    print("=" * 65)
    print(f"  Switch2Xbox v{APP_VERSION}")
    print("  Nintendo Switch & ODM Gamepad -> Virtual Xbox 360 / DS4 Bridge")
    print("  Low-Latency XInput / DirectInput Emulation (ViGEmBus + Rumble)")
    print("=" * 65)


def list_devices_cli() -> None:
    """Prints all detected controllers and HID gamepads."""
    controllers = list_connected_gamepads()
    print("\nConnected Game Controllers / Gamepad HID Devices:")
    print("-" * 65)
    if not controllers:
        print("  No game controllers or recognized gamepads detected.")
        print("  Check USB cable or pair your controller via Bluetooth.")
        print("-" * 65)
        return

    for idx, d in enumerate(controllers):
        vid = d.get("vendor_id", 0)
        pid = d.get("product_id", 0)
        mfr = d.get("manufacturer_string") or "Unknown"
        prod = d.get("product_string") or "Generic Gamepad"
        page = d.get("usage_page", 0)
        usage = d.get("usage", 0)
        print(f"  [{idx}] VID: 0x{vid:04X} | PID: 0x{pid:04X} | {mfr} - {prod} (Page: 0x{page:04X}, Usage: 0x{usage:04X})")
    print("-" * 65)


def interactive_select_device() -> Optional[BridgeConfig]:
    """Allows user to select from available connected gamepads."""
    controllers = list_connected_gamepads()
    if not controllers:
        print("\n[Discovery] No game controllers detected.")
        custom = input("Would you like to enter custom VID and PID? [y/N]: ").strip().lower()
        if custom == "y":
            vid_str = input("Enter Vendor ID (e.g. 0x057E): ").strip()
            pid_str = input("Enter Product ID (e.g. 0x2009): ").strip()
            try:
                return BridgeConfig(vendor_id=parse_hex_int(vid_str), product_id=parse_hex_int(pid_str))
            except ValueError:
                print("Invalid VID/PID entered.")
        return None

    list_devices_cli()
    choice = input(f"Select controller [0-{len(controllers)-1}] or press Enter for default: ").strip()
    if not choice:
        return BridgeConfig()

    try:
        idx = int(choice)
        if 0 <= idx < len(controllers):
            selected = controllers[idx]
            return BridgeConfig(
                vendor_id=selected.get("vendor_id", DEFAULT_SWITCH_VID),
                product_id=selected.get("product_id", DEFAULT_SWITCH_PID),
                device_path=selected.get("path"),
            )
    except ValueError:
        pass

    return None


def main() -> None:
    setup_logging()
    parser = argparse.ArgumentParser(
        description="Switch2Xbox: Bridge Nintendo Switch & ODM Gamepad to Virtual Xbox 360"
    )
    parser.add_argument("--gui", action="store_true", help="Launch graphical user interface with system tray")
    parser.add_argument("--minimized", action="store_true", help="Start minimized directly to the system tray")
    parser.add_argument("--cli", action="store_true", help="Force command-line interface mode")
    parser.add_argument("--vid", type=str, default=None, help=f"Vendor ID in hex (default: 0x{DEFAULT_SWITCH_VID:04X})")
    parser.add_argument("--pid", type=str, default=None, help=f"Product ID in hex (default: 0x{DEFAULT_SWITCH_PID:04X})")
    parser.add_argument("--list", action="store_true", help="List all connected game controllers and exit")
    parser.add_argument("--select", action="store_true", help="Interactive controller selector")
    parser.add_argument("--inspect", action="store_true", help="Launch live raw HID packet inspector")
    parser.add_argument("--deadzone", type=float, default=0.10, help="Stick center deadzone fraction (default: 0.10 = 10%%)")
    parser.add_argument("--target", choices=["xbox360", "ds4"], default="xbox360", help="Emulated controller type (xbox360 or ds4)")
    parser.add_argument("--curve", choices=["linear", "smooth", "aggressive"], default="linear", help="Stick response curve")
    parser.add_argument("--trigger", choices=["hair", "progressive"], default="hair", help="Trigger profile (hair or progressive)")
    parser.add_argument("--rate", type=int, default=200, help="Polling rate in Hz (default: 200 Hz)")
    parser.add_argument("--no-swap", action="store_true", help="Disable Nintendo -> Xbox ABXY button swap")
    parser.add_argument("--no-rumble", action="store_true", help="Disable in-game force feedback vibration")
    parser.add_argument("--force-generic", action="store_true", help="Force generic DirectInput fallback decoder")

    args = parser.parse_args()

    # Launch GUI by default if no CLI options specified or if --gui / --minimized is passed
    cli_flags = [args.cli, args.list, args.select, args.inspect, args.vid, args.pid, args.no_swap, args.no_rumble, args.force_generic]
    if args.gui or args.minimized or not any(cli_flags):
        from gui import run_gui
        run_gui()
        return

    print_banner()

    if args.list:
        list_devices_cli()
        return

    config = BridgeConfig(
        deadzone=args.deadzone,
        poll_rate_hz=args.rate,
        swap_abxy=not args.no_swap,
        enable_rumble=not args.no_rumble,
        emulation_target=args.target,
        stick_curve=args.curve,
        trigger_mode=args.trigger,
        force_generic=args.force_generic,
    )

    if args.vid:
        config.vendor_id = parse_hex_int(args.vid)
    if args.pid:
        config.product_id = parse_hex_int(args.pid)

    if args.select:
        sel_config = interactive_select_device()
        if sel_config:
            config.vendor_id = sel_config.vendor_id
            config.product_id = sel_config.product_id
            config.device_path = sel_config.device_path

    if args.inspect:
        run_inspector(config)
        return

    # Check if target device is currently visible
    controllers = list_connected_gamepads()
    matching = [c for c in controllers if c.get("vendor_id") == config.vendor_id and c.get("product_id") == config.product_id]

    if not matching and not args.vid and not args.pid:
        # Default Switch IDs not immediately found; check if other gamepads exist
        if controllers:
            print("\n[Discovery] Default Switch Pro Controller (0x057E:0x2009) not found.")
            print(f"[Discovery] Found {len(controllers)} other game controller(s) connected:")
            for idx, c in enumerate(controllers):
                vid = c.get("vendor_id", 0)
                pid = c.get("product_id", 0)
                prod = c.get("product_string") or "Unknown"
                print(f"  [{idx}] VID: 0x{vid:04X} PID: 0x{pid:04X} - {prod}")
            print("\nAuto-selecting controller [0]... (Use --select or --vid/--pid to customize)")
            chosen = controllers[0]
            config.vendor_id = chosen.get("vendor_id", config.vendor_id)
            config.product_id = chosen.get("product_id", config.product_id)
            config.device_path = chosen.get("path")
        else:
            print(f"\n[Discovery] Scanning for controller (VID: 0x{config.vendor_id:04X}, PID: 0x{config.product_id:04X})...")
            print("[Discovery] Waiting for connection. Plug in via USB or pair via Bluetooth.")

    print(f"\nConfiguration:")
    print(f"  Target Controller: VID 0x{config.vendor_id:04X}, PID 0x{config.product_id:04X}")
    print(f"  Deadzone:         {config.deadzone * 100:.1f}%")
    print(f"  Polling Rate:     {config.poll_rate_hz} Hz")
    print(f"  ABXY Remap:       {'Nintendo -> Xbox (A<->B, X<->Y)' if config.swap_abxy else 'Direct (No swap)'}")
    print(f"  Decoder Mode:     {'Force Generic DirectInput' if config.force_generic else 'Auto-Detect (Switch / ODM 0x3F / Generic)'}")
    print()

    bridge = GamepadBridge(config)
    bridge.run()


if __name__ == "__main__":
    main()

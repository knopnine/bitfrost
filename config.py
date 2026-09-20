"""Configuration and settings persistence module for Switch2Xbox."""

import json
import os
import sys
import winreg
from dataclasses import asdict, dataclass
from typing import Optional


APP_NAME = "Switch2Xbox"
APP_VERSION = "1.3.0"
APP_DESCRIPTION = "Nintendo Switch Pro & ODM Gamepad to Virtual Xbox 360 & DS4 Bridge"
SETTINGS_FILENAME = "settings.json"
PROFILES_FILENAME = "profiles.json"

# Default Vendor and Product IDs for Nintendo Switch Pro Controller
DEFAULT_SWITCH_VID = 0x057E
DEFAULT_SWITCH_PID = 0x2009

# Common third-party / clone VID / PIDs (for fallback auto-detection)
KNOWN_CLONE_IDS = [
    (0x057E, 0x2009, "Nintendo Switch Pro Controller (or clone)"),
    (0x057E, 0x2006, "Joy-Con (L)"),
    (0x057E, 0x2007, "Joy-Con (R)"),
    (0x057E, 0x200E, "Joy-Con Charging Grip"),
    (0x2563, 0x0575, "ShanWan / Generic Switch Gamepad"),
    (0x045E, 0x028E, "Generic XInput / Switch clone in PC mode"),
    (0x0079, 0x181C, "DragonRise / Generic Gamepad"),
    (0x1949, 0x0402, "ODM Gamepad Controller"),
]

REG_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def get_settings_path() -> str:
    """Returns absolute path to settings.json next to the executable or script."""
    if getattr(sys, "frozen", False):
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, SETTINGS_FILENAME)


def get_profiles_path() -> str:
    """Returns absolute path to profiles.json next to the executable or script."""
    if getattr(sys, "frozen", False):
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, PROFILES_FILENAME)


def is_windows_autostart_enabled() -> bool:
    """Checks if Switch2Xbox is registered in HKCU Run key."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_RUN_KEY, 0, winreg.KEY_READ) as key:
            winreg.QueryValueEx(key, APP_NAME)
            return True
    except FileNotFoundError:
        return False
    except Exception:
        return False


def set_windows_autostart(enable: bool) -> None:
    """Registers or unregisters Switch2Xbox in Windows Startup."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if enable:
                if getattr(sys, "frozen", False):
                    exe_path = sys.executable
                    cmd = f'"{exe_path}" --minimized'
                else:
                    script_path = os.path.abspath("main.py")
                    py_exe = sys.executable.replace("python.exe", "pythonw.exe")
                    cmd = f'"{py_exe}" "{script_path}" --minimized'
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, cmd)
                print(f"[AutoStart] Registered: {cmd}")
            else:
                try:
                    winreg.DeleteValue(key, APP_NAME)
                    print("[AutoStart] Unregistered from Windows startup.")
                except FileNotFoundError:
                    pass
    except Exception as e:
        print(f"[AutoStart] Warning: failed to modify startup registry: {e}")


@dataclass
class BridgeConfig:
    """Runtime configuration for Switch2Xbox."""
    vendor_id: int = DEFAULT_SWITCH_VID
    product_id: int = DEFAULT_SWITCH_PID
    device_path: Optional[bytes] = None
    deadzone: float = 0.10          # 10% radial center deadzone
    outer_deadzone: float = 0.05    # 5% outer saturation (guarantees 100% full sprint)
    poll_rate_hz: int = 200         # Target polling rate (120 to 250 Hz)
    swap_abxy: bool = True          # Remap Nintendo A<->B, X<->Y to Xbox standard
    enable_rumble: bool = True      # In-game force feedback (rumble)
    emulation_target: str = "xbox360"  # "xbox360" or "ds4"
    stick_curve: str = "linear"     # "linear", "smooth", "aggressive"
    trigger_mode: str = "hair"      # "hair" (instant 100%) or "progressive" (smooth ramp)
    low_battery_notify: bool = True # Windows tray toast when battery is critical
    start_with_windows: bool = False
    start_minimized: bool = False
    debug: bool = False             # Verbose debug logging
    inspect_mode: bool = False      # Packet inspection mode
    force_generic: bool = False     # Force DirectInput generic fallback parser

    # Hardware Stick Neutral Center Offsets (default 2048)
    stick_lx_center: int = 2048
    stick_ly_center: int = 2048
    stick_rx_center: int = 2048
    stick_ry_center: int = 2048

    # Motion / Gyro Aiming
    enable_gyro_aim: bool = False
    gyro_aim_sensitivity: float = 1.0
    gyro_aim_trigger_only: bool = True  # Only active while holding ZL/LT (aiming)

    # Cemuhook / DSU Motion Protocol Server (port 26760)
    enable_dsu_server: bool = False
    dsu_server_port: int = 26760

    # HidHide Double-Input Prevention
    enable_hidhide: bool = False

    # Active Profile Name
    active_profile: str = "Default"

    @property
    def poll_interval_sec(self) -> float:
        """Target time per poll iteration in seconds."""
        return 1.0 / max(50, min(self.poll_rate_hz, 500))

    def to_dict(self) -> dict:
        """Serialize configuration to dict."""
        return {
            "vendor_id": self.vendor_id,
            "product_id": self.product_id,
            "deadzone": self.deadzone,
            "outer_deadzone": self.outer_deadzone,
            "poll_rate_hz": self.poll_rate_hz,
            "swap_abxy": self.swap_abxy,
            "enable_rumble": self.enable_rumble,
            "emulation_target": self.emulation_target,
            "stick_curve": self.stick_curve,
            "trigger_mode": self.trigger_mode,
            "low_battery_notify": self.low_battery_notify,
            "start_with_windows": self.start_with_windows,
            "start_minimized": self.start_minimized,
            "force_generic": self.force_generic,
            "stick_lx_center": self.stick_lx_center,
            "stick_ly_center": self.stick_ly_center,
            "stick_rx_center": self.stick_rx_center,
            "stick_ry_center": self.stick_ry_center,
            "enable_gyro_aim": self.enable_gyro_aim,
            "gyro_aim_sensitivity": self.gyro_aim_sensitivity,
            "gyro_aim_trigger_only": self.gyro_aim_trigger_only,
            "enable_dsu_server": self.enable_dsu_server,
            "dsu_server_port": self.dsu_server_port,
            "enable_hidhide": self.enable_hidhide,
            "active_profile": self.active_profile,
        }

    def apply_dict(self, data: dict) -> None:
        """Update config fields from dict."""
        self.vendor_id = data.get("vendor_id", self.vendor_id)
        self.product_id = data.get("product_id", self.product_id)
        self.deadzone = data.get("deadzone", self.deadzone)
        self.outer_deadzone = data.get("outer_deadzone", self.outer_deadzone)
        self.poll_rate_hz = data.get("poll_rate_hz", self.poll_rate_hz)
        self.swap_abxy = data.get("swap_abxy", self.swap_abxy)
        self.enable_rumble = data.get("enable_rumble", self.enable_rumble)
        self.emulation_target = data.get("emulation_target", self.emulation_target)
        self.stick_curve = data.get("stick_curve", self.stick_curve)
        self.trigger_mode = data.get("trigger_mode", self.trigger_mode)
        self.low_battery_notify = data.get("low_battery_notify", self.low_battery_notify)
        self.start_with_windows = data.get("start_with_windows", self.start_with_windows)
        self.start_minimized = data.get("start_minimized", self.start_minimized)
        self.force_generic = data.get("force_generic", self.force_generic)
        self.stick_lx_center = data.get("stick_lx_center", self.stick_lx_center)
        self.stick_ly_center = data.get("stick_ly_center", self.stick_ly_center)
        self.stick_rx_center = data.get("stick_rx_center", self.stick_rx_center)
        self.stick_ry_center = data.get("stick_ry_center", self.stick_ry_center)
        self.enable_gyro_aim = data.get("enable_gyro_aim", self.enable_gyro_aim)
        self.gyro_aim_sensitivity = data.get("gyro_aim_sensitivity", self.gyro_aim_sensitivity)
        self.gyro_aim_trigger_only = data.get("gyro_aim_trigger_only", self.gyro_aim_trigger_only)
        self.enable_dsu_server = data.get("enable_dsu_server", self.enable_dsu_server)
        self.dsu_server_port = data.get("dsu_server_port", self.dsu_server_port)
        self.enable_hidhide = data.get("enable_hidhide", self.enable_hidhide)
        self.active_profile = data.get("active_profile", self.active_profile)

    def save_to_file(self) -> None:
        """Persist current configuration to settings.json."""
        path = get_settings_path()
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.to_dict(), f, indent=4)
        except Exception as e:
            print(f"[Settings] Failed to save settings: {e}")

    @classmethod
    def load_from_file(cls) -> "BridgeConfig":
        """Load configuration from settings.json if present."""
        path = get_settings_path()
        config = cls()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                config.apply_dict(data)
            except Exception as e:
                print(f"[Settings] Error loading settings: {e}")

        # Sync windows startup state with registry
        config.start_with_windows = is_windows_autostart_enabled()
        return config


def load_all_profiles() -> dict:
    """Loads all saved profiles from profiles.json."""
    path = get_profiles_path()
    if not os.path.exists(path):
        return {
            "Default": {},
            "Shooter (Gyro Aim)": {
                "enable_gyro_aim": True,
                "gyro_aim_sensitivity": 1.2,
                "gyro_aim_trigger_only": True,
                "stick_curve": "smooth",
                "trigger_mode": "hair",
            },
            "Racing (Progressive)": {
                "stick_curve": "linear",
                "trigger_mode": "progressive",
                "swap_abxy": True,
            },
            "Retro (1:1 Nintendo)": {
                "swap_abxy": False,
                "stick_curve": "linear",
                "trigger_mode": "hair",
            },
        }
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"Default": {}}


def save_named_profile(name: str, config: BridgeConfig) -> None:
    """Saves current config state under a named profile in profiles.json."""
    profiles = load_all_profiles()
    profiles[name] = config.to_dict()
    path = get_profiles_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(profiles, f, indent=4)
    except Exception as e:
        print(f"[Profiles] Failed to save profile '{name}': {e}")


def delete_named_profile(name: str) -> None:
    """Deletes a named profile from profiles.json."""
    profiles = load_all_profiles()
    if name in profiles and name != "Default":
        del profiles[name]
        path = get_profiles_path()
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(profiles, f, indent=4)
        except Exception as e:
            print(f"[Profiles] Failed to delete profile '{name}': {e}")


"""HidHide integration module for double-input prevention and device cloaking."""

import logging
import os
import shutil
import subprocess
import sys
import winreg
from typing import List, Optional, Tuple

logger = logging.getLogger("GamepadBridge.HidHide")

HIDHIDE_SERVICE_KEY = r"SYSTEM\CurrentControlSet\Services\HidHide"
HIDHIDE_PARAMS_KEY = r"SYSTEM\CurrentControlSet\Services\HidHide\Parameters"
DEFAULT_CLI_PATH = r"C:\Program Files\Nefarius Software Solutions\HidHide\x64\HidHideCLI.exe"


def find_hidhide_cli() -> Optional[str]:
    """Locate HidHideCLI.exe executable if installed."""
    cli_on_path = shutil.which("HidHideCLI.exe")
    if cli_on_path:
        return cli_on_path
    if os.path.exists(DEFAULT_CLI_PATH):
        return DEFAULT_CLI_PATH
    return None


def is_hidhide_installed() -> bool:
    """Checks whether the Nefarius HidHide driver or CLI is installed on this system."""
    if find_hidhide_cli() is not None:
        return True
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, HIDHIDE_SERVICE_KEY, 0, winreg.KEY_READ):
            return True
    except FileNotFoundError:
        return False
    except Exception:
        return False


def is_hidhide_active() -> bool:
    """Checks if device cloaking is currently active in HidHide."""
    cli = find_hidhide_cli()
    if cli:
        try:
            res = subprocess.run([cli, "--cloak-state"], capture_output=True, text=True, timeout=2)
            if "Active" in res.stdout or "true" in res.stdout.lower():
                return True
            if "Inactive" in res.stdout or "false" in res.stdout.lower():
                return False
        except Exception:
            pass

    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, HIDHIDE_PARAMS_KEY, 0, winreg.KEY_READ) as key:
            val, _ = winreg.QueryValueEx(key, "Active")
            return bool(val)
    except Exception:
        return False


def get_current_app_path() -> str:
    """Returns absolute executable path for whitelisting."""
    if getattr(sys, "frozen", False):
        return os.path.abspath(sys.executable)
    return os.path.abspath(sys.executable)


def ensure_app_whitelisted() -> bool:
    """Whitelists the current Switch2Xbox process (or Python executable) in HidHide."""
    app_path = get_current_app_path()
    cli = find_hidhide_cli()
    if cli:
        try:
            res = subprocess.run([cli, "--app-reg", f'"{app_path}"'], capture_output=True, text=True, timeout=3)
            if res.returncode == 0:
                logger.info(f"Whitelisted via CLI: {app_path}")
                return True
        except Exception as e:
            logger.debug(f"CLI whitelist attempt: {e}")

    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, HIDHIDE_PARAMS_KEY, 0, winreg.KEY_READ | winreg.KEY_SET_VALUE) as key:
            try:
                current, _ = winreg.QueryValueEx(key, "Whitelist")
                whitelist = list(current)
            except FileNotFoundError:
                whitelist = []

            if not any(w.lower() == app_path.lower() for w in whitelist):
                whitelist.append(app_path)
                winreg.SetValueEx(key, "Whitelist", 0, winreg.REG_MULTI_SZ, whitelist)
                logger.info(f"Whitelisted via Registry: {app_path}")
            return True
    except PermissionError:
        logger.warning("Administrator permissions required to update HidHide whitelist registry.")
        return False
    except Exception as e:
        logger.debug(f"Failed to update HidHide whitelist: {e}")
        return False


def cloak_device_id(device_instance_id: str) -> bool:
    """Adds a physical controller device ID to HidHide's hidden blacklist."""
    if not device_instance_id:
        return False

    ensure_app_whitelisted()

    cli = find_hidhide_cli()
    if cli:
        try:
            subprocess.run([cli, "--dev-hide", f'"{device_instance_id}"'], capture_output=True, text=True, timeout=3)
            subprocess.run([cli, "--cloak-on"], capture_output=True, text=True, timeout=3)
            logger.info(f"Cloaked device via CLI: {device_instance_id}")
            return True
        except Exception as e:
            logger.debug(f"CLI cloak attempt: {e}")

    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, HIDHIDE_PARAMS_KEY, 0, winreg.KEY_READ | winreg.KEY_SET_VALUE) as key:
            try:
                current, _ = winreg.QueryValueEx(key, "Blacklist")
                blacklist = list(current)
            except FileNotFoundError:
                blacklist = []

            if not any(b.lower() == device_instance_id.lower() for b in blacklist):
                blacklist.append(device_instance_id)
                winreg.SetValueEx(key, "Blacklist", 0, winreg.REG_MULTI_SZ, blacklist)

            winreg.SetValueEx(key, "Active", 0, winreg.REG_DWORD, 1)
            logger.info(f"Cloaked device via Registry: {device_instance_id}")
            return True
    except PermissionError:
        logger.warning("Administrator permissions required to modify HidHide device blacklist.")
        return False
    except Exception as e:
        logger.debug(f"Failed to cloak device: {e}")
        return False


def uncloak_device_id(device_instance_id: str) -> bool:
    """Removes a device ID from HidHide's blacklist."""
    if not device_instance_id:
        return False

    cli = find_hidhide_cli()
    if cli:
        try:
            subprocess.run([cli, "--dev-unhide", f'"{device_instance_id}"'], capture_output=True, text=True, timeout=3)
            return True
        except Exception:
            pass

    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, HIDHIDE_PARAMS_KEY, 0, winreg.KEY_READ | winreg.KEY_SET_VALUE) as key:
            try:
                current, _ = winreg.QueryValueEx(key, "Blacklist")
                blacklist = [b for b in current if b.lower() != device_instance_id.lower()]
                winreg.SetValueEx(key, "Blacklist", 0, winreg.REG_MULTI_SZ, blacklist)
                return True
            except FileNotFoundError:
                return True
    except Exception:
        return False

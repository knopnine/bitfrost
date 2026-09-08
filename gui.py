"""Modern GUI and System Tray application for Switch2Xbox."""

import os
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any, Dict, List, Optional

import pystray
from PIL import Image, ImageTk

from bridge import GamepadBridge
from config import DEFAULT_SWITCH_PID, DEFAULT_SWITCH_VID, BridgeConfig, set_windows_autostart
from device import list_connected_gamepads
from icon import generate_gamepad_icon, save_ico_file
from protocol import BatteryStatus, ProtocolMode


class GamepadBridgeGUI:
    """Tkinter + pystray System Tray Application for Gamepad Bridge."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Switch2Xbox")
        self.root.geometry("460x650")
        self.root.minsize(440, 620)

        # Set application icon
        self.icon_path = os.path.abspath("app_icon.ico")
        if not os.path.exists(self.icon_path):
            save_ico_file(self.icon_path)
        try:
            self.root.iconbitmap(self.icon_path)
        except Exception:
            pass

        # Load persisted settings
        self.config = BridgeConfig.load_from_file()
        self.bridge: Optional[GamepadBridge] = None
        self.tray_icon: Optional[pystray.Icon] = None
        self.is_connected = False
        self.devices_list: List[Dict[str, Any]] = []

        self._setup_style()
        self._build_ui()
        self._setup_tray()

        # Handle window close event (minimize to tray instead of quitting)
        self.root.protocol("WM_DELETE_WINDOW", self.hide_to_tray)

        # If launched with --minimized flag, hide window immediately
        if "--minimized" in sys.argv:
            self.root.withdraw()
            self.root.after(100, self.root.withdraw)

        # Auto-refresh devices on launch
        self.refresh_devices()

        # Automatically start bridge on launch
        self.root.after(300, self.start_bridge)

    def _setup_style(self) -> None:
        """Configure clean modern ttk styling."""
        self.style = ttk.Style()
        try:
            self.style.theme_use("clam")
        except Exception:
            pass

        # Custom colors
        self.bg_color = "#f4f6f9"
        self.card_bg = "#ffffff"
        self.accent_color = "#0078d7"
        self.text_color = "#2c3e50"
        self.root.configure(bg=self.bg_color)

        self.style.configure("TFrame", background=self.bg_color)
        self.style.configure("Card.TFrame", background=self.card_bg, relief="flat")
        self.style.configure("TLabel", background=self.bg_color, foreground=self.text_color, font=("Segoe UI", 9))
        self.style.configure("Card.TLabel", background=self.card_bg, foreground=self.text_color, font=("Segoe UI", 9))
        self.style.configure("Header.TLabel", background=self.bg_color, foreground="#1a1a1a", font=("Segoe UI", 13, "bold"))
        self.style.configure("SubHeader.TLabel", background=self.bg_color, foreground="#666666", font=("Segoe UI", 8))
        self.style.configure("CardTitle.TLabel", background=self.card_bg, foreground="#333333", font=("Segoe UI", 10, "bold"))

        # Buttons
        self.style.configure("Accent.TButton", font=("Segoe UI", 10, "bold"), padding=6)
        self.style.configure("Secondary.TButton", font=("Segoe UI", 9), padding=4)

    def _build_ui(self) -> None:
        """Construct the GUI interface."""
        main_frame = ttk.Frame(self.root, padding="16 12 16 12")
        main_frame.pack(fill="both", expand=True)

        # --- Header ---
        header_frame = ttk.Frame(main_frame)
        header_frame.pack(fill="x", pady=(0, 10))

        title_lbl = ttk.Label(header_frame, text="Switch2Xbox", style="Header.TLabel")
        title_lbl.pack(anchor="w")
        sub_lbl = ttk.Label(header_frame, text="Nintendo Switch & ODM Gamepad -> Virtual Xbox 360", style="SubHeader.TLabel")
        sub_lbl.pack(anchor="w")

        # --- Status Card ---
        status_card = ttk.Frame(main_frame, style="Card.TFrame", padding=12)
        status_card.pack(fill="x", pady=(0, 10))

        # Status badge row
        badge_row = ttk.Frame(status_card, style="Card.TFrame")
        badge_row.pack(fill="x", pady=(0, 8))

        self.status_pill = tk.Label(
            badge_row,
            text="● SEARCHING...",
            bg="#fff3cd",
            fg="#856404",
            font=("Segoe UI", 10, "bold"),
            padx=10,
            pady=4,
            relief="flat"
        )
        self.status_pill.pack(side="left")

        self.rate_lbl = ttk.Label(badge_row, text="0 Hz", style="Card.TLabel", font=("Segoe UI", 9, "bold"))
        self.rate_lbl.pack(side="right")

        # Device info grid
        info_grid = ttk.Frame(status_card, style="Card.TFrame")
        info_grid.pack(fill="x")

        ttk.Label(info_grid, text="Controller:", style="Card.TLabel", font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w", pady=2)
        self.device_name_lbl = ttk.Label(info_grid, text="Scanning for device...", style="Card.TLabel", foreground="#555555")
        self.device_name_lbl.grid(row=0, column=1, sticky="w", padx=8, pady=2)

        ttk.Label(info_grid, text="Protocol:", style="Card.TLabel", font=("Segoe UI", 9, "bold")).grid(row=1, column=0, sticky="w", pady=2)
        self.protocol_lbl = ttk.Label(info_grid, text="Auto-Detect", style="Card.TLabel", foreground="#555555")
        self.protocol_lbl.grid(row=1, column=1, sticky="w", padx=8, pady=2)

        ttk.Label(info_grid, text="Battery:", style="Card.TLabel", font=("Segoe UI", 9, "bold")).grid(row=2, column=0, sticky="w", pady=2)
        self.battery_lbl = ttk.Label(info_grid, text="Unknown", style="Card.TLabel", foreground="#555555")
        self.battery_lbl.grid(row=2, column=1, sticky="w", padx=8, pady=2)

        ttk.Label(info_grid, text="Vibration:", style="Card.TLabel", font=("Segoe UI", 9, "bold")).grid(row=3, column=0, sticky="w", pady=2)
        self.vibration_lbl = ttk.Label(info_grid, text="Enabled ⚡", style="Card.TLabel", foreground="#28a745")
        self.vibration_lbl.grid(row=3, column=1, sticky="w", padx=8, pady=2)

        # --- Device Selection Card ---
        dev_card = ttk.Frame(main_frame, style="Card.TFrame", padding=12)
        dev_card.pack(fill="x", pady=(0, 10))

        ttk.Label(dev_card, text="Target Device", style="CardTitle.TLabel").pack(anchor="w", pady=(0, 6))

        dev_select_row = ttk.Frame(dev_card, style="Card.TFrame")
        dev_select_row.pack(fill="x")

        self.device_combo = ttk.Combobox(dev_select_row, state="readonly", font=("Segoe UI", 9))
        self.device_combo.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.device_combo.bind("<<ComboboxSelected>>", self._on_device_selected)

        self.refresh_btn = ttk.Button(dev_select_row, text="🔄 Refresh", command=self.refresh_devices, style="Secondary.TButton")
        self.refresh_btn.pack(side="right")

        # --- Settings Card ---
        settings_card = ttk.Frame(main_frame, style="Card.TFrame", padding=12)
        settings_card.pack(fill="x", pady=(0, 12))

        ttk.Label(settings_card, text="Mapping & Feedback", style="CardTitle.TLabel").pack(anchor="w", pady=(0, 6))

        # ABXY Remap Checkbox
        self.swap_abxy_var = tk.BooleanVar(value=self.config.swap_abxy)
        self.swap_cb = ttk.Checkbutton(
            settings_card,
            text="Swap ABXY to Xbox physical layout (A<->B, X<->Y)",
            variable=self.swap_abxy_var,
            command=self._on_settings_change
        )
        self.swap_cb.pack(anchor="w", pady=(0, 4))

        # In-game Rumble Checkbox
        self.rumble_var = tk.BooleanVar(value=self.config.enable_rumble)
        self.rumble_cb = ttk.Checkbutton(
            settings_card,
            text="Enable in-game force feedback (vibration)",
            variable=self.rumble_var,
            command=self._on_settings_change
        )
        self.rumble_cb.pack(anchor="w", pady=(0, 4))

        # Auto-start with Windows Checkbox
        self.autostart_var = tk.BooleanVar(value=self.config.start_with_windows)
        self.autostart_cb = ttk.Checkbutton(
            settings_card,
            text="Start with Windows (Minimized to Tray)",
            variable=self.autostart_var,
            command=self._on_settings_change
        )
        self.autostart_cb.pack(anchor="w", pady=(0, 6))

        # Deadzone Slider
        dz_frame = ttk.Frame(settings_card, style="Card.TFrame")
        dz_frame.pack(fill="x", pady=(0, 4))
        ttk.Label(dz_frame, text="Stick Deadzone:", style="Card.TLabel").pack(side="left")
        self.dz_val_lbl = ttk.Label(dz_frame, text=f"{int(round(self.config.deadzone * 100))}%", style="Card.TLabel", font=("Segoe UI", 9, "bold"))
        self.dz_val_lbl.pack(side="right")

        self.deadzone_slider = ttk.Scale(
            settings_card,
            from_=0.0,
            to=0.25,
            value=self.config.deadzone,
            orient="horizontal",
            command=self._on_deadzone_slide
        )
        self.deadzone_slider.pack(fill="x", pady=(0, 6))

        # Polling Rate Selector
        rate_frame = ttk.Frame(settings_card, style="Card.TFrame")
        rate_frame.pack(fill="x")
        ttk.Label(rate_frame, text="Polling Rate:", style="Card.TLabel").pack(side="left")
        self.rate_combo = ttk.Combobox(rate_frame, values=["120 Hz", "200 Hz", "250 Hz"], state="readonly", width=10)
        self.rate_combo.set(f"{self.config.poll_rate_hz} Hz")
        self.rate_combo.pack(side="right")
        self.rate_combo.bind("<<ComboboxSelected>>", self._on_rate_change)

        # --- Action Buttons ---
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill="x", pady=(0, 8))

        self.toggle_btn = tk.Button(
            btn_frame,
            text="⏹ Stop Bridge",
            bg="#d9534f",
            fg="white",
            activebackground="#c9302c",
            activeforeground="white",
            font=("Segoe UI", 10, "bold"),
            relief="flat",
            padx=10,
            pady=6,
            command=self.toggle_bridge
        )
        self.toggle_btn.pack(side="left", fill="x", expand=True, padx=(0, 3))

        self.rumble_test_btn = tk.Button(
            btn_frame,
            text="⚡ Test Rumble",
            bg="#6f42c1",
            fg="white",
            activebackground="#59359a",
            activeforeground="white",
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            padx=8,
            pady=6,
            command=self._test_rumble_click
        )
        self.rumble_test_btn.pack(side="left", padx=(0, 3))

        self.test_btn = tk.Button(
            btn_frame,
            text="🎮 joy.cpl",
            bg="#0275d8",
            fg="white",
            activebackground="#025aa5",
            activeforeground="white",
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            padx=8,
            pady=6,
            command=self.open_joy_cpl
        )
        self.test_btn.pack(side="right", fill="x", expand=True)

        # Bottom Bar: Hide to tray & Exit
        bottom_frame = ttk.Frame(main_frame)
        bottom_frame.pack(fill="x", pady=(4, 0))

        self.tray_btn = ttk.Button(bottom_frame, text="⬇ Minimize to Tray", command=self.hide_to_tray, style="Secondary.TButton")
        self.tray_btn.pack(side="left")

        self.exit_btn = ttk.Button(bottom_frame, text="Quit App", command=self.quit_app, style="Secondary.TButton")
        self.exit_btn.pack(side="right")

    def _setup_tray(self) -> None:
        """Initialize background system tray icon with pystray."""
        tray_image = generate_gamepad_icon(connected=False, size=64)

        menu = pystray.Menu(
            pystray.MenuItem("Switch2Xbox", self.show_from_tray, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Open Window", self.show_from_tray),
            pystray.MenuItem("Test Controller (joy.cpl)", self.open_joy_cpl),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Start Bridge", self.start_bridge),
            pystray.MenuItem("Stop Bridge", self.stop_bridge),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit", self.quit_app),
        )

        self.tray_icon = pystray.Icon(
            "Switch2Xbox",
            tray_image,
            "Switch2Xbox",
            menu
        )

        # Run tray loop in background thread
        threading.Thread(target=self.tray_icon.run, daemon=True, name="SystemTrayThread").start()

    def update_tray_icon(self, connected: bool) -> None:
        """Update system tray icon color dynamically based on connection status."""
        if self.tray_icon:
            try:
                new_img = generate_gamepad_icon(connected=connected, size=64)
                self.tray_icon.icon = new_img
                status_text = "Connected" if connected else "Waiting for controller..."
                self.tray_icon.title = f"Switch2Xbox ({status_text})"
            except Exception:
                pass

    def refresh_devices(self) -> None:
        """Scan connected game controllers and populate dropdown."""
        self.devices_list = list_connected_gamepads()
        options = ["Auto-Detect (Switch Pro: 0x057E:0x2009)"]

        for d in self.devices_list:
            vid = d.get("vendor_id", 0)
            pid = d.get("product_id", 0)
            prod = d.get("product_string") or "Gamepad"
            mfr = d.get("manufacturer_string") or "Unknown"
            options.append(f"{mfr} {prod} (0x{vid:04X}:0x{pid:04X})")

        self.device_combo["values"] = options
        if not self.device_combo.get():
            self.device_combo.current(0)

    def _on_device_selected(self, event=None) -> None:
        """Handle user changing target device from dropdown."""
        idx = self.device_combo.current()
        if idx <= 0:
            self.config.vendor_id = DEFAULT_SWITCH_VID
            self.config.product_id = DEFAULT_SWITCH_PID
            self.config.device_path = None
        else:
            selected = self.devices_list[idx - 1]
            self.config.vendor_id = selected.get("vendor_id", DEFAULT_SWITCH_VID)
            self.config.product_id = selected.get("product_id", DEFAULT_SWITCH_PID)
            self.config.device_path = selected.get("path")

        # Restart bridge if running to bind to new device
        if self.bridge and self.bridge.is_running:
            self.stop_bridge()
            self.start_bridge()

    def _on_deadzone_slide(self, val: str) -> None:
        float_val = float(val)
        self.config.deadzone = float_val
        self.dz_val_lbl.config(text=f"{int(round(float_val * 100))}%")
        if self.bridge:
            self.bridge.config.deadzone = float_val
        self.config.save_to_file()

    def _on_rate_change(self, event=None) -> None:
        rate_str = self.rate_combo.get()
        rate_int = int(rate_str.replace(" Hz", ""))
        self.config.poll_rate_hz = rate_int
        if self.bridge:
            self.bridge.config.poll_rate_hz = rate_int
        self.config.save_to_file()

    def _on_settings_change(self) -> None:
        swap = self.swap_abxy_var.get()
        rumble = self.rumble_var.get()
        autostart = self.autostart_var.get()

        self.config.swap_abxy = swap
        self.config.enable_rumble = rumble
        self.config.start_with_windows = autostart

        set_windows_autostart(autostart)
        self.config.save_to_file()

        if self.bridge:
            self.bridge.config.swap_abxy = swap
            self.bridge.config.enable_rumble = rumble
        if rumble:
            self.vibration_lbl.config(text="Enabled ⚡", foreground="#28a745")
        else:
            self.vibration_lbl.config(text="Disabled", foreground="#888888")

    def _test_rumble_click(self) -> None:
        """Test physical vibration motors."""
        if self.bridge and self.bridge.is_running:
            self.bridge.test_rumble(duration_sec=0.4, intensity=220)
        else:
            messagebox.showinfo("Info", "Start the bridge first to test vibration.")

    def start_bridge(self) -> None:
        """Start the background bridge thread."""
        if self.bridge and self.bridge.is_running:
            return

        self.bridge = GamepadBridge(self.config, status_callback=self._on_bridge_status)
        self.bridge.start_background()

        self.toggle_btn.config(
            text="⏹ Stop Bridge",
            bg="#d9534f",
            activebackground="#c9302c"
        )

    def stop_bridge(self) -> None:
        """Stop the background bridge thread."""
        if self.bridge:
            self.bridge.stop()
            self.bridge = None

        self.toggle_btn.config(
            text="▶ Start Bridge",
            bg="#5cb85c",
            activebackground="#4cae4c"
        )
        self._update_status_ui({
            "is_connected": False,
            "device_name": "Stopped",
            "protocol_mode": ProtocolMode.UNKNOWN,
            "battery": None,
            "charging": False,
            "rate_hz": 0.0,
        })

    def toggle_bridge(self) -> None:
        if self.bridge and self.bridge.is_running:
            self.stop_bridge()
        else:
            self.start_bridge()

    def _on_bridge_status(self, status: Dict[str, Any]) -> None:
        """Thread-safe status dispatch to GUI main thread."""
        self.root.after(0, lambda: self._update_status_ui(status))

    def _update_status_ui(self, status: Dict[str, Any]) -> None:
        """Update GUI widgets based on latest status."""
        connected = status.get("is_connected", False)
        self.is_connected = connected

        if connected:
            self.status_pill.config(text="● CONNECTED", bg="#d4edda", fg="#155724")
        else:
            self.status_pill.config(text="● SEARCHING...", bg="#fff3cd", fg="#856404")

        self.device_name_lbl.config(text=status.get("device_name", "None"))

        # Protocol mode label
        mode = status.get("protocol_mode", ProtocolMode.UNKNOWN)
        mode_text = {
            ProtocolMode.SWITCH_FULL: "Switch Standard (0x30 Full)",
            ProtocolMode.SWITCH_REPLY: "Switch Subcommand Reply (0x21)",
            ProtocolMode.ODM_SIMPLE_3F: "ODM Clone Simple (0x3F)",
            ProtocolMode.GENERIC_HID: "Generic DirectInput Fallback",
        }.get(mode, "Detecting...")
        self.protocol_lbl.config(text=mode_text)

        # Battery
        bat = status.get("battery")
        charging = status.get("charging", False)
        if bat is not None:
            bat_text = f"{bat.name}{' (Charging ⚡)' if charging else ''}"
        else:
            bat_text = "N/A"
        self.battery_lbl.config(text=bat_text)

        # Rate
        rate_hz = status.get("rate_hz", 0.0)
        self.rate_lbl.config(text=f"{rate_hz:.0f} Hz" if rate_hz > 0 else "")

        # Vibration status
        rumble_active = status.get("rumble_active", False)
        if rumble_active:
            self.vibration_lbl.config(text="Vibrating ⚡⚡", foreground="#e74c3c")
        elif self.config.enable_rumble:
            self.vibration_lbl.config(text="Enabled ⚡", foreground="#28a745")
        else:
            self.vibration_lbl.config(text="Disabled", foreground="#888888")

        # Update tray icon color
        self.update_tray_icon(connected)

    def open_joy_cpl(self) -> None:
        """Launch Windows Gamepad Control Panel."""
        try:
            subprocess.Popen("joy.cpl", shell=True)
        except Exception as e:
            messagebox.showerror("Error", f"Could not launch joy.cpl: {e}")

    def hide_to_tray(self) -> None:
        """Hide window into system tray notification area."""
        self.root.withdraw()
        if self.tray_icon:
            try:
                self.tray_icon.notify(
                    "Switch2Xbox is running in the background.\nDouble-click the tray icon to restore.",
                    "Switch2Xbox Minimized"
                )
            except Exception:
                pass

    def show_from_tray(self, icon=None, item=None) -> None:
        """Restore window from system tray."""
        self.root.after(0, self._restore_window)

    def _restore_window(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def quit_app(self, icon=None, item=None) -> None:
        """Completely exit the application."""
        self.stop_bridge()
        if self.tray_icon:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
        self.root.after(50, self.root.destroy)


def run_gui() -> None:
    root = tk.Tk()
    app = GamepadBridgeGUI(root)
    root.mainloop()


if __name__ == "__main__":
    run_gui()

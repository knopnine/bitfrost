"""Modern Windows 11 Dark-Themed GUI and System Tray application for Switch2Xbox."""

import math
import os
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk, simpledialog
from typing import Any, Dict, List, Optional

import pystray
from PIL import Image, ImageTk

from bridge import GamepadBridge
from config import (
    APP_VERSION,
    DEFAULT_SWITCH_PID,
    DEFAULT_SWITCH_VID,
    BridgeConfig,
    delete_named_profile,
    load_all_profiles,
    save_named_profile,
    set_windows_autostart,
)
from device import list_connected_gamepads
from icon import generate_gamepad_icon, save_ico_file
from logger import logger, open_log_file, setup_logging
from protocol import BatteryStatus, ProtocolMode
import hidhide


class GamepadBridgeGUI:
    """Modern Windows 11 Dark-Themed GUI with Live 2D Visualizer, Profiles, Gyro Aiming, and DSU Server."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(f"Switch2Xbox v{APP_VERSION}")
        self.root.geometry("560x800")
        self.root.minsize(530, 720)

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
        self._last_tray_connected: Optional[bool] = None
        self.devices_list: List[Dict[str, Any]] = []

        # Circularity benchmark state
        self._testing_circularity = False
        self._circ_samples_l: List[float] = []
        self._circ_samples_r: List[float] = []
        self.btn_gauges: Dict[str, Dict[str, Any]] = {}

        # Exception logging
        def _on_tk_exception(exc_type, exc_value, exc_traceback):
            logger.error("Uncaught exception in Tkinter event:", exc_info=(exc_type, exc_value, exc_traceback))
        self.root.report_callback_exception = _on_tk_exception

        self._setup_style()
        self._build_ui()
        self._setup_tray()

        # Window lifecycle
        self.root.protocol("WM_DELETE_WINDOW", self.hide_to_tray)
        if "--minimized" in sys.argv:
            self.root.withdraw()
            self.root.after(100, self.root.withdraw)

        self.refresh_devices()
        self.refresh_profiles()

        # Start bridge and visualizer
        self.root.after(300, self.start_bridge)
        self.root.after(500, self._render_visualizer_tick)

    def _setup_style(self) -> None:
        """Configure clean modern Windows 11 Dark theme styling."""
        self.style = ttk.Style()
        try:
            self.style.theme_use("clam")
        except Exception:
            pass

        # Zinc Dark Palette
        self.c_bg = "#121214"          # Root background
        self.c_card = "#1c1c1f"        # Card container background
        self.c_card_sub = "#27272a"    # Subcard / input background
        self.c_border = "#3f3f46"      # Border stroke
        self.c_text = "#f4f4f5"        # Primary text
        self.c_muted = "#a1a1aa"       # Secondary / muted text
        self.c_subtle = "#71717a"      # Subtle hints
        self.c_blue = "#3b82f6"        # Primary accent
        self.c_emerald = "#10b981"     # Success green
        self.c_amber = "#f59e0b"       # Warning amber
        self.c_rose = "#ef4444"        # Danger red
        self.c_purple = "#8b5cf6"      # Motion purple

        self.root.configure(bg=self.c_bg)

        # TTK elements
        self.style.configure("TFrame", background=self.c_bg)
        self.style.configure("Card.TFrame", background=self.c_card, relief="flat")
        self.style.configure("SubCard.TFrame", background=self.c_card_sub, relief="flat")

        self.style.configure("TNotebook", background=self.c_bg, borderwidth=0)
        self.style.configure(
            "TNotebook.Tab",
            background=self.c_card,
            foreground=self.c_muted,
            padding=[14, 6],
            font=("Segoe UI", 9, "bold"),
            borderwidth=0,
        )
        self.style.map(
            "TNotebook.Tab",
            background=[("selected", self.c_blue)],
            foreground=[("selected", "#ffffff")],
        )

        self.style.configure("TLabel", background=self.c_bg, foreground=self.c_text, font=("Segoe UI", 9))
        self.style.configure("Card.TLabel", background=self.c_card, foreground=self.c_text, font=("Segoe UI", 9))
        self.style.configure("Muted.TLabel", background=self.c_card, foreground=self.c_muted, font=("Segoe UI", 8))
        self.style.configure("CardTitle.TLabel", background=self.c_card, foreground="#ffffff", font=("Segoe UI", 10, "bold"))

        self.style.configure("TCheckbutton", background=self.c_card, foreground=self.c_text, font=("Segoe UI", 9))
        self.style.map("TCheckbutton", background=[("active", self.c_card)])

        self.style.configure("TCombobox", fieldbackground=self.c_card_sub, background=self.c_card, foreground="#ffffff")
        self.style.map("TCombobox", fieldbackground=[("readonly", self.c_card_sub)], foreground=[("readonly", "#ffffff")])

    def _build_ui(self) -> None:
        """Construct full multi-tab interface with live visualizer."""
        main_frame = tk.Frame(self.root, bg=self.c_bg, padx=12, pady=10)
        main_frame.pack(fill="both", expand=True)

        # --- Top Header Bar ---
        top_bar = tk.Frame(main_frame, bg=self.c_bg)
        top_bar.pack(fill="x", pady=(0, 8))

        header_left = tk.Frame(top_bar, bg=self.c_bg)
        header_left.pack(side="left")

        title_lbl = tk.Label(
            header_left,
            text=f"Switch2Xbox v{APP_VERSION} 🎮",
            bg=self.c_bg,
            fg="#ffffff",
            font=("Segoe UI", 13, "bold"),
        )
        title_lbl.pack(anchor="w")
        sub_lbl = tk.Label(
            header_left,
            text="Switch Pro & ODM Clone -> Virtual Xbox 360 / DualShock 4",
            bg=self.c_bg,
            fg=self.c_muted,
            font=("Segoe UI", 8),
        )
        sub_lbl.pack(anchor="w")

        # Top pill badge
        self.status_pill = tk.Label(
            top_bar,
            text="● SEARCHING...",
            bg="#382405",
            fg=self.c_amber,
            font=("Segoe UI", 9, "bold"),
            padx=10,
            pady=3,
            relief="flat",
        )
        self.status_pill.pack(side="right", padx=(6, 0))

        self.rate_badge = tk.Label(
            top_bar,
            text="0 Hz",
            bg=self.c_card_sub,
            fg=self.c_text,
            font=("Segoe UI", 9, "bold"),
            padx=8,
            pady=3,
        )
        self.rate_badge.pack(side="right")

        # --- Tab Notebook ---
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill="both", expand=True, pady=(4, 8))

        # Tab 1: Controller & Live Visualizer
        self.tab_visualizer = ttk.Frame(self.notebook, style="TFrame")
        self.notebook.add(self.tab_visualizer, text="  🎮 Visualizer & Status  ")
        self._build_tab_visualizer(self.tab_visualizer)

        # Tab 2: Profiles & Controls
        self.tab_profiles = ttk.Frame(self.notebook, style="TFrame")
        self.notebook.add(self.tab_profiles, text="  ⚙️ Profiles & Controls  ")
        self._build_tab_profiles(self.tab_profiles)

        # Tab 3: Motion & Advanced (Gyro / DSU / HidHide)
        self.tab_motion = ttk.Frame(self.notebook, style="TFrame")
        self.notebook.add(self.tab_motion, text="  🚀 Motion & Advanced  ")
        self._build_tab_motion(self.tab_motion)

        # --- Bottom Action Bar ---
        bottom_bar = tk.Frame(main_frame, bg=self.c_bg)
        bottom_bar.pack(fill="x", pady=(4, 0))

        self.toggle_btn = tk.Button(
            bottom_bar,
            text="⏹ Stop Bridge",
            bg=self.c_rose,
            fg="#ffffff",
            activebackground="#dc2626",
            activeforeground="#ffffff",
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            padx=10,
            pady=5,
            command=self.toggle_bridge,
        )
        self.toggle_btn.pack(side="left", padx=(0, 6))

        self.tray_btn = tk.Button(
            bottom_bar,
            text="⬇ Minimize to Tray",
            bg=self.c_card_sub,
            fg=self.c_text,
            activebackground=self.c_border,
            activeforeground="#ffffff",
            font=("Segoe UI", 9),
            relief="flat",
            padx=8,
            pady=5,
            command=self.hide_to_tray,
        )
        self.tray_btn.pack(side="left", padx=(0, 6))

        self.logs_btn = tk.Button(
            bottom_bar,
            text="📄 Logs",
            bg=self.c_card_sub,
            fg=self.c_text,
            activebackground=self.c_border,
            activeforeground="#ffffff",
            font=("Segoe UI", 9),
            relief="flat",
            padx=8,
            pady=5,
            command=open_log_file,
        )
        self.logs_btn.pack(side="left")

        self.exit_btn = tk.Button(
            bottom_bar,
            text="Quit App",
            bg=self.c_card_sub,
            fg=self.c_muted,
            activebackground=self.c_border,
            activeforeground="#ffffff",
            font=("Segoe UI", 9),
            relief="flat",
            padx=8,
            pady=5,
            command=self.quit_app,
        )
        self.exit_btn.pack(side="right")

    def _build_tab_visualizer(self, parent: ttk.Frame) -> None:
        """Tab 1: HardwareTester-style Status Card, Dual Radars, Silhouette, and Button Gauges."""
        # 1. Device Info & Protocol Card
        info_card = tk.Frame(parent, bg=self.c_card, padx=10, pady=6)
        info_card.pack(fill="x", pady=(4, 6))

        grid = tk.Frame(info_card, bg=self.c_card)
        grid.pack(fill="x")

        # Row 0
        tk.Label(grid, text="INDEX:", bg=self.c_card, fg=self.c_muted, font=("Segoe UI", 8, "bold")).grid(row=0, column=0, sticky="w")
        self.index_lbl = tk.Label(grid, text="0", bg=self.c_card, fg=self.c_emerald, font=("Segoe UI", 8, "bold"))
        self.index_lbl.grid(row=0, column=1, sticky="w", padx=(2, 10))

        tk.Label(grid, text="DEVICE:", bg=self.c_card, fg=self.c_muted, font=("Segoe UI", 8, "bold")).grid(row=0, column=2, sticky="w")
        self.device_name_lbl = tk.Label(grid, text="Scanning for device...", bg=self.c_card, fg=self.c_text, font=("Segoe UI", 8))
        self.device_name_lbl.grid(row=0, column=3, sticky="w", padx=(2, 10))

        tk.Label(grid, text="TARGET:", bg=self.c_card, fg=self.c_muted, font=("Segoe UI", 8, "bold")).grid(row=0, column=4, sticky="w")
        self.emulating_lbl = tk.Label(grid, text="Xbox 360", bg=self.c_card, fg=self.c_blue, font=("Segoe UI", 8, "bold"))
        self.emulating_lbl.grid(row=0, column=5, sticky="w", padx=(2, 0))

        # Row 1
        tk.Label(grid, text="MAPPING:", bg=self.c_card, fg=self.c_muted, font=("Segoe UI", 8, "bold")).grid(row=1, column=0, sticky="w", pady=2)
        tk.Label(grid, text="standard", bg=self.c_card, fg=self.c_emerald, font=("Segoe UI", 8, "bold")).grid(row=1, column=1, sticky="w", padx=(2, 10), pady=2)

        tk.Label(grid, text="PROTOCOL:", bg=self.c_card, fg=self.c_muted, font=("Segoe UI", 8, "bold")).grid(row=1, column=2, sticky="w", pady=2)
        self.protocol_lbl = tk.Label(grid, text="Auto-Detect", bg=self.c_card, fg=self.c_text, font=("Segoe UI", 8))
        self.protocol_lbl.grid(row=1, column=3, sticky="w", padx=(2, 10), pady=2)

        tk.Label(grid, text="TIMING:", bg=self.c_card, fg=self.c_muted, font=("Segoe UI", 8, "bold")).grid(row=1, column=4, sticky="w", pady=2)
        self.timing_lbl = tk.Label(grid, text="Latency: -- ms", bg=self.c_card, fg=self.c_text, font=("Segoe UI", 8))
        self.timing_lbl.grid(row=1, column=5, sticky="w", padx=(2, 0), pady=2)

        # Row 2
        tk.Label(grid, text="BATTERY:", bg=self.c_card, fg=self.c_muted, font=("Segoe UI", 8, "bold")).grid(row=2, column=0, sticky="w")
        self.battery_lbl = tk.Label(grid, text="Unknown", bg=self.c_card, fg=self.c_text, font=("Segoe UI", 8))
        self.battery_lbl.grid(row=2, column=1, columnspan=3, sticky="w", padx=(2, 10))

        tk.Label(grid, text="VIBRATION:", bg=self.c_card, fg=self.c_muted, font=("Segoe UI", 8, "bold")).grid(row=2, column=4, sticky="w")
        self.vibration_lbl = tk.Label(grid, text="Dual-Motor ⚡", bg=self.c_card, fg=self.c_emerald, font=("Segoe UI", 8, "bold"))
        self.vibration_lbl.grid(row=2, column=5, sticky="w", padx=(2, 0))

        # 2. Live Interactive Input Visualizer Card (Dual Radars + Gamepad Silhouette)
        viz_card = tk.Frame(parent, bg=self.c_card, padx=10, pady=6)
        viz_card.pack(fill="x", pady=(0, 6))

        viz_title_row = tk.Frame(viz_card, bg=self.c_card)
        viz_title_row.pack(fill="x", pady=(0, 4))
        tk.Label(viz_title_row, text="AXES & CONTROLLER VISUALIZER", bg=self.c_card, fg="#ffffff", font=("Segoe UI", 9, "bold")).pack(side="left")
        tk.Label(viz_title_row, text="Live 30 FPS • 5-Decimal Precision", bg=self.c_card, fg=self.c_subtle, font=("Segoe UI", 8)).pack(side="right")

        viz_body = tk.Frame(viz_card, bg=self.c_card)
        viz_body.pack(fill="x")

        # Left Column: Dual Radars and Circularity Tools
        left_col = tk.Frame(viz_body, bg=self.c_card)
        left_col.pack(side="left", fill="y", padx=(0, 6))

        # Row with Left and Right stick radar circles
        radars_row = tk.Frame(left_col, bg=self.c_card)
        radars_row.pack(fill="x")

        # Left Stick Radar Card
        ls_box = tk.Frame(radars_row, bg=self.c_card_sub, highlightthickness=1, highlightbackground=self.c_border, padx=4, pady=4)
        ls_box.pack(side="left", padx=(0, 4))
        tk.Label(ls_box, text="LS (AXIS 0, 1)", bg=self.c_card_sub, fg=self.c_text, font=("Segoe UI", 7, "bold")).pack()
        self.ls_canvas = tk.Canvas(ls_box, width=96, height=96, bg="#18181b", highlightthickness=0)
        self.ls_canvas.pack(pady=2)
        self._init_stick_canvas(self.ls_canvas, "ls")
        self.axis0_lbl = tk.Label(ls_box, text="AXIS 0:  0.00000", bg=self.c_card_sub, fg=self.c_muted, font=("Consolas", 7))
        self.axis0_lbl.pack(anchor="w")
        self.axis1_lbl = tk.Label(ls_box, text="AXIS 1:  0.00000", bg=self.c_card_sub, fg=self.c_muted, font=("Consolas", 7))
        self.axis1_lbl.pack(anchor="w")
        self.circ_l_lbl = tk.Label(ls_box, text="Avg Error: --%", bg=self.c_card_sub, fg=self.c_subtle, font=("Segoe UI", 7))
        self.circ_l_lbl.pack(anchor="w")

        # Right Stick Radar Card
        rs_box = tk.Frame(radars_row, bg=self.c_card_sub, highlightthickness=1, highlightbackground=self.c_border, padx=4, pady=4)
        rs_box.pack(side="left")
        tk.Label(rs_box, text="RS (AXIS 2, 3)", bg=self.c_card_sub, fg=self.c_text, font=("Segoe UI", 7, "bold")).pack()
        self.rs_canvas = tk.Canvas(rs_box, width=96, height=96, bg="#18181b", highlightthickness=0)
        self.rs_canvas.pack(pady=2)
        self._init_stick_canvas(self.rs_canvas, "rs")
        self.axis2_lbl = tk.Label(rs_box, text="AXIS 2:  0.00000", bg=self.c_card_sub, fg=self.c_muted, font=("Consolas", 7))
        self.axis2_lbl.pack(anchor="w")
        self.axis3_lbl = tk.Label(rs_box, text="AXIS 3:  0.00000", bg=self.c_card_sub, fg=self.c_muted, font=("Consolas", 7))
        self.axis3_lbl.pack(anchor="w")
        self.circ_r_lbl = tk.Label(rs_box, text="Avg Error: --%", bg=self.c_card_sub, fg=self.c_subtle, font=("Segoe UI", 7))
        self.circ_r_lbl.pack(anchor="w")

        # Circularity Benchmark Action Bar
        circ_bar = tk.Frame(left_col, bg=self.c_card)
        circ_bar.pack(fill="x", pady=(5, 0))

        self.circ_toggle_btn = tk.Button(
            circ_bar,
            text="▶ Test Circularity",
            bg=self.c_card_sub,
            fg=self.c_text,
            activebackground=self.c_border,
            activeforeground="#ffffff",
            font=("Segoe UI", 8, "bold"),
            relief="flat",
            padx=6,
            pady=2,
            command=self.toggle_circularity_test,
        )
        self.circ_toggle_btn.pack(side="left", fill="x", expand=True, padx=(0, 3))

        self.circ_clear_btn = tk.Button(
            circ_bar,
            text="↺ Reset",
            bg=self.c_card_sub,
            fg=self.c_muted,
            activebackground=self.c_border,
            activeforeground="#ffffff",
            font=("Segoe UI", 8),
            relief="flat",
            padx=5,
            pady=2,
            command=self.clear_circularity_test,
        )
        self.circ_clear_btn.pack(side="right")

        # Right Column: Vector Gamepad Silhouette
        right_col = tk.Frame(viz_body, bg=self.c_card)
        right_col.pack(side="right", fill="both", expand=True)

        self.silhouette_canvas = tk.Canvas(right_col, width=275, height=180, bg=self.c_card, highlightthickness=0)
        self.silhouette_canvas.pack(anchor="center")
        self._init_silhouette_canvas(self.silhouette_canvas)

        # 3. Standard W3C Gamepad Buttons (B0 - B17) Meter Gauges Card
        buttons_card = tk.Frame(parent, bg=self.c_card, padx=10, pady=6)
        buttons_card.pack(fill="x", pady=(0, 6))

        btn_title_row = tk.Frame(buttons_card, bg=self.c_card)
        btn_title_row.pack(fill="x", pady=(0, 4))
        tk.Label(btn_title_row, text="STANDARD BUTTONS (B0 - B17)", bg=self.c_card, fg="#ffffff", font=("Segoe UI", 9, "bold")).pack(side="left")
        tk.Label(btn_title_row, text="W3C Gamepad API Standard Mapping", bg=self.c_card, fg=self.c_subtle, font=("Segoe UI", 8)).pack(side="right")

        btn_grid_frame = tk.Frame(buttons_card, bg=self.c_card)
        btn_grid_frame.pack(fill="x")

        for c_i in range(6):
            btn_grid_frame.columnconfigure(c_i, weight=1)

        BUTTON_DEFS = [
            ("b0", "B0: A"),
            ("b1", "B1: B"),
            ("b2", "B2: X"),
            ("b3", "B3: Y"),
            ("b4", "B4: LB"),
            ("b5", "B5: RB"),
            ("b6", "B6: LT"),
            ("b7", "B7: RT"),
            ("b8", "B8: Back"),
            ("b9", "B9: Start"),
            ("b10", "B10: LSB"),
            ("b11", "B11: RSB"),
            ("b12", "B12: ▲"),
            ("b13", "B13: ▼"),
            ("b14", "B14: ◀"),
            ("b15", "B15: ▶"),
            ("b16", "B16: Guide"),
            ("b17", "B17: Capt"),
        ]

        self.btn_gauges = {}
        for idx, (b_key, b_label) in enumerate(BUTTON_DEFS):
            r_idx = idx // 6
            c_idx = idx % 6

            b_frame = tk.Frame(
                btn_grid_frame,
                bg=self.c_card_sub,
                highlightthickness=1,
                highlightbackground=self.c_border,
                padx=3,
                pady=2,
            )
            b_frame.grid(row=r_idx, column=c_idx, padx=2, pady=2, sticky="nsew")

            top_row = tk.Frame(b_frame, bg=self.c_card_sub)
            top_row.pack(fill="x")

            lbl_tag = tk.Label(top_row, text=b_label, bg=self.c_card_sub, fg=self.c_muted, font=("Segoe UI", 7, "bold"))
            lbl_tag.pack(side="left")

            lbl_val = tk.Label(top_row, text="0.00", bg=self.c_card_sub, fg=self.c_subtle, font=("Consolas", 7))
            lbl_val.pack(side="right")

            bar_cv = tk.Canvas(b_frame, height=3, bg="#18181b", highlightthickness=0)
            bar_cv.pack(fill="x", pady=(2, 0))
            rect_id = bar_cv.create_rectangle(0, 0, 0, 3, fill=self.c_blue, width=0)

            self.btn_gauges[b_key] = {
                "frame": b_frame,
                "lbl_val": lbl_val,
                "canvas": bar_cv,
                "rect_id": rect_id,
            }

        # 4. Quick Actions & Calibration Card
        act_card = tk.Frame(parent, bg=self.c_card, padx=10, pady=6)
        act_card.pack(fill="x")

        act_title_row = tk.Frame(act_card, bg=self.c_card)
        act_title_row.pack(fill="x", pady=(0, 3))
        tk.Label(act_title_row, text="Hardware Stick Calibration & Tools", bg=self.c_card, fg="#ffffff", font=("Segoe UI", 9, "bold")).pack(side="left")

        self.calib_status_lbl = tk.Label(
            act_card,
            text=f"Centers: LX={self.config.stick_lx_center}, LY={self.config.stick_ly_center} | RX={self.config.stick_rx_center}, RY={self.config.stick_ry_center}",
            bg=self.c_card,
            fg=self.c_muted,
            font=("Segoe UI", 8),
        )
        self.calib_status_lbl.pack(anchor="w", pady=(0, 4))

        act_btn_row = tk.Frame(act_card, bg=self.c_card)
        act_btn_row.pack(fill="x")

        self.calib_btn = tk.Button(
            act_btn_row,
            text="🎯 Calibrate Centers",
            bg=self.c_blue,
            fg="#ffffff",
            activebackground="#2563eb",
            activeforeground="#ffffff",
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            padx=8,
            pady=3,
            command=self.start_stick_calibration,
        )
        self.calib_btn.pack(side="left", padx=(0, 4))

        self.rumble_btn = tk.Button(
            act_btn_row,
            text="⚡ Test Rumble",
            bg=self.c_purple,
            fg="#ffffff",
            activebackground="#7c3aed",
            activeforeground="#ffffff",
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            padx=8,
            pady=3,
            command=self._test_rumble_click,
        )
        self.rumble_btn.pack(side="left", padx=(0, 4))

        self.joycpl_btn = tk.Button(
            act_btn_row,
            text="🎮 joy.cpl",
            bg=self.c_card_sub,
            fg=self.c_text,
            activebackground=self.c_border,
            activeforeground="#ffffff",
            font=("Segoe UI", 9),
            relief="flat",
            padx=8,
            pady=3,
            command=self.open_joy_cpl,
        )
        self.joycpl_btn.pack(side="right")

    def _init_stick_canvas(self, canvas: tk.Canvas, prefix: str) -> None:
        """Draw static crosshair and deadzone ring on stick canvas."""
        cx, cy, r = 48, 48, 40
        # Outer boundary ring
        canvas.create_oval(cx - r, cy - r, cx + r, cy + r, outline=self.c_border, width=1)
        # Radar crosshairs
        canvas.create_line(cx - r, cy, cx + r, cy, fill="#27272a")
        canvas.create_line(cx, cy - r, cx, cy + r, fill="#27272a")
        # Deadzone circle
        dz_r = r * self.config.deadzone
        canvas.create_oval(cx - dz_r, cy - dz_r, cx + dz_r, cy + dz_r, outline="#475569", dash=(2, 2), tags=f"{prefix}_dz")
        # Center dot / stick indicator
        canvas.create_oval(cx - 4, cy - 4, cx + 4, cy + 4, fill=self.c_blue, outline="#93c5fd", width=1, tags=f"{prefix}_dot")

    def _init_silhouette_canvas(self, canvas: tk.Canvas) -> None:
        """Draws the vector controller silhouette, buttons, sticks, and D-pad on canvas."""
        # Controller ergonomic body polygon
        body_pts = [
            (105, 38), (135, 42), (165, 38),
            (200, 36), (230, 48), (248, 70),
            (256, 105), (252, 142), (238, 166),
            (222, 172), (206, 160),
            (185, 128), (155, 108), (135, 110),
            (115, 108), (85, 128),
            (64, 160), (48, 172),
            (32, 166), (18, 142), (14, 105),
            (22, 70), (40, 48), (70, 36),
        ]
        canvas.create_polygon(body_pts, fill="#222226", outline="#3f3f46", width=2, smooth=True)

        # Triggers (LT / RT)
        canvas.create_polygon([(44, 20), (78, 20), (74, 34), (48, 34)], fill="#27272a", outline="#52525b", width=1, tags="shp_lt")
        canvas.create_text(61, 27, text="LT", fill="#a1a1aa", font=("Segoe UI", 6, "bold"))
        canvas.create_polygon([(197, 34), (193, 20), (227, 20), (223, 34)], fill="#27272a", outline="#52525b", width=1, tags="shp_rt")
        canvas.create_text(210, 27, text="RT", fill="#a1a1aa", font=("Segoe UI", 6, "bold"))

        # Bumpers (LB / RB)
        canvas.create_rectangle(48, 30, 92, 40, fill="#27272a", outline="#52525b", width=1, tags="shp_lb")
        canvas.create_text(70, 35, text="LB", fill="#a1a1aa", font=("Segoe UI", 6, "bold"))
        canvas.create_rectangle(179, 30, 223, 40, fill="#27272a", outline="#52525b", width=1, tags="shp_rb")
        canvas.create_text(201, 35, text="RB", fill="#a1a1aa", font=("Segoe UI", 6, "bold"))

        # Left Stick Socket & Cap (Switch top-left)
        canvas.create_oval(74 - 19, 80 - 19, 74 + 19, 80 + 19, fill="#18181b", outline="#3f3f46", width=1)
        canvas.create_oval(74 - 12, 80 - 12, 74 + 12, 80 + 12, fill="#27272a", outline="#52525b", width=1, tags="shp_ls")
        canvas.create_text(74, 80, text="LS", fill="#71717a", font=("Segoe UI", 6, "bold"), tags="shp_ls_txt")

        # Right Stick Socket & Cap (Switch bottom-right)
        canvas.create_oval(168 - 19, 114 - 19, 168 + 19, 114 + 19, fill="#18181b", outline="#3f3f46", width=1)
        canvas.create_oval(168 - 12, 114 - 12, 168 + 12, 114 + 12, fill="#27272a", outline="#52525b", width=1, tags="shp_rs")
        canvas.create_text(168, 114, text="RS", fill="#71717a", font=("Segoe UI", 6, "bold"), tags="shp_rs_txt")

        # ABXY Face Buttons (Switch top-right diamond cluster)
        canvas.create_oval(196 - 8, 64 - 8, 196 + 8, 64 + 8, fill="#27272a", outline="#52525b", tags="shp_y")
        canvas.create_text(196, 64, text="Y", fill="#ffffff", font=("Segoe UI", 7, "bold"))

        canvas.create_oval(180 - 8, 80 - 8, 180 + 8, 80 + 8, fill="#27272a", outline="#52525b", tags="shp_x")
        canvas.create_text(180, 80, text="X", fill="#ffffff", font=("Segoe UI", 7, "bold"))

        canvas.create_oval(212 - 8, 80 - 8, 212 + 8, 80 + 8, fill="#27272a", outline="#52525b", tags="shp_b")
        canvas.create_text(212, 80, text="B", fill="#ffffff", font=("Segoe UI", 7, "bold"))

        canvas.create_oval(196 - 8, 96 - 8, 196 + 8, 96 + 8, fill="#27272a", outline="#52525b", tags="shp_a")
        canvas.create_text(196, 96, text="A", fill="#ffffff", font=("Segoe UI", 7, "bold"))

        # D-Pad (Switch bottom-left cross)
        canvas.create_rectangle(74 - 5, 122 - 15, 74 + 5, 122 - 6, fill="#27272a", outline="#52525b", tags="shp_du")
        canvas.create_rectangle(74 - 5, 122 + 6, 74 + 5, 122 + 15, fill="#27272a", outline="#52525b", tags="shp_dd")
        canvas.create_rectangle(74 - 15, 122 - 5, 74 - 6, 122 + 5, fill="#27272a", outline="#52525b", tags="shp_dl")
        canvas.create_rectangle(74 + 6, 122 - 5, 74 + 15, 122 + 5, fill="#27272a", outline="#52525b", tags="shp_dr")
        canvas.create_rectangle(74 - 5, 122 - 5, 74 + 5, 122 + 5, fill="#27272a", outline="#3f3f46")

        # Center Buttons: Minus (-), Plus (+), Home (Guide), Capture
        canvas.create_rectangle(114 - 6, 74 - 3, 114 + 6, 74 + 3, fill="#27272a", outline="#52525b", tags="shp_back")
        canvas.create_text(114, 74, text="-", fill="#a1a1aa", font=("Segoe UI", 8, "bold"))

        canvas.create_rectangle(156 - 6, 74 - 3, 156 + 6, 74 + 3, fill="#27272a", outline="#52525b", tags="shp_start")
        canvas.create_text(156, 74, text="+", fill="#a1a1aa", font=("Segoe UI", 8, "bold"))

        canvas.create_oval(135 - 7, 68 - 7, 135 + 7, 68 + 7, fill="#27272a", outline="#52525b", tags="shp_guide")
        canvas.create_oval(135 - 4, 68 - 4, 135 + 4, 68 + 4, fill="#18181b", outline="#52525b")

        canvas.create_rectangle(135 - 4, 88 - 4, 135 + 4, 88 + 4, fill="#27272a", outline="#52525b", tags="shp_capture")

    def toggle_circularity_test(self) -> None:
        """Toggles the circularity error benchmark mode."""
        self._testing_circularity = not self._testing_circularity
        if self._testing_circularity:
            self.circ_toggle_btn.config(text="⏹ Stop Test", bg=self.c_rose, activebackground="#dc2626")
        else:
            self.circ_toggle_btn.config(text="▶ Test Circularity", bg=self.c_card_sub, activebackground=self.c_border)

    def clear_circularity_test(self) -> None:
        """Clears sampled benchmark points and resets circularity stats."""
        self._circ_samples_l.clear()
        self._circ_samples_r.clear()
        self.ls_canvas.delete("circ_pts_l")
        self.rs_canvas.delete("circ_pts_r")
        self.circ_l_lbl.config(text="Avg Error: --%", fg=self.c_subtle)
        self.circ_r_lbl.config(text="Avg Error: --%", fg=self.c_subtle)

    def _build_tab_profiles(self, parent: ttk.Frame) -> None:
        """Tab 2: Profile Management and Emulation Mapping Settings."""
        # 1. Profile Selection Card
        prof_card = tk.Frame(parent, bg=self.c_card, padx=10, pady=8)
        prof_card.pack(fill="x", pady=(6, 6))

        tk.Label(prof_card, text="Configuration Profiles", bg=self.c_card, fg="#ffffff", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 4))

        prof_row = tk.Frame(prof_card, bg=self.c_card)
        prof_row.pack(fill="x")

        self.profile_combo = ttk.Combobox(prof_row, state="readonly", font=("Segoe UI", 9))
        self.profile_combo.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.profile_combo.bind("<<ComboboxSelected>>", self._on_profile_selected)

        self.save_prof_btn = tk.Button(
            prof_row,
            text="💾 Save As...",
            bg=self.c_card_sub,
            fg=self.c_text,
            activebackground=self.c_border,
            activeforeground="#ffffff",
            font=("Segoe UI", 8, "bold"),
            relief="flat",
            padx=6,
            pady=3,
            command=self._save_profile_click,
        )
        self.save_prof_btn.pack(side="left", padx=(0, 4))

        self.del_prof_btn = tk.Button(
            prof_row,
            text="🗑 Delete",
            bg=self.c_card_sub,
            fg=self.c_rose,
            activebackground=self.c_border,
            activeforeground="#ffffff",
            font=("Segoe UI", 8),
            relief="flat",
            padx=6,
            pady=3,
            command=self._delete_profile_click,
        )
        self.del_prof_btn.pack(side="left")

        # 2. Emulation Settings Card
        sett_card = tk.Frame(parent, bg=self.c_card, padx=10, pady=8)
        sett_card.pack(fill="x", pady=(0, 6))

        tk.Label(sett_card, text="Emulation & Input Mapping", bg=self.c_card, fg="#ffffff", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 6))

        # Target Device Selection
        dev_row = tk.Frame(sett_card, bg=self.c_card)
        dev_row.pack(fill="x", pady=(0, 4))
        tk.Label(dev_row, text="Target Controller:", bg=self.c_card, fg=self.c_text).pack(side="left")
        self.refresh_btn = tk.Button(
            dev_row,
            text="🔄 Refresh",
            bg=self.c_card_sub,
            fg=self.c_text,
            activebackground=self.c_border,
            activeforeground="#ffffff",
            font=("Segoe UI", 8),
            relief="flat",
            padx=4,
            pady=1,
            command=self.refresh_devices,
        )
        self.refresh_btn.pack(side="right")

        self.device_combo = ttk.Combobox(sett_card, state="readonly", font=("Segoe UI", 9))
        self.device_combo.pack(fill="x", pady=(0, 6))
        self.device_combo.bind("<<ComboboxSelected>>", self._on_device_selected)

        # Virtual Emulation Target (Xbox 360 vs DS4)
        target_row = tk.Frame(sett_card, bg=self.c_card)
        target_row.pack(fill="x", pady=(0, 4))
        tk.Label(target_row, text="Virtual Gamepad Device:", bg=self.c_card, fg=self.c_text).pack(side="left")
        self.target_combo = ttk.Combobox(
            target_row,
            values=["Xbox 360 (XInput Default)", "PlayStation 4 (DualShock 4)"],
            state="readonly",
            width=26,
        )
        self.target_combo.set("PlayStation 4 (DualShock 4)" if self.config.emulation_target == "ds4" else "Xbox 360 (XInput Default)")
        self.target_combo.pack(side="right")
        self.target_combo.bind("<<ComboboxSelected>>", self._on_target_change)

        # Stick Response Curve
        curve_row = tk.Frame(sett_card, bg=self.c_card)
        curve_row.pack(fill="x", pady=(0, 4))
        tk.Label(curve_row, text="Stick Response Curve:", bg=self.c_card, fg=self.c_text).pack(side="left")
        self.curve_combo = ttk.Combobox(
            curve_row,
            values=["Linear (1:1 Standard)", "Smooth Aim (Exponential)", "Aggressive (Snappy)"],
            state="readonly",
            width=26,
        )
        curve_map = {"linear": "Linear (1:1 Standard)", "smooth": "Smooth Aim (Exponential)", "aggressive": "Aggressive (Snappy)"}
        self.curve_combo.set(curve_map.get(self.config.stick_curve, "Linear (1:1 Standard)"))
        self.curve_combo.pack(side="right")
        self.curve_combo.bind("<<ComboboxSelected>>", self._on_curve_change)

        # Trigger Profile
        trigger_row = tk.Frame(sett_card, bg=self.c_card)
        trigger_row.pack(fill="x", pady=(0, 6))
        tk.Label(trigger_row, text="Trigger Response Mode:", bg=self.c_card, fg=self.c_text).pack(side="left")
        self.trigger_combo = ttk.Combobox(
            trigger_row,
            values=["Instant Hair Trigger", "Progressive Smooth Ramp (~25ms)"],
            state="readonly",
            width=26,
        )
        self.trigger_combo.set("Progressive Smooth Ramp (~25ms)" if self.config.trigger_mode == "progressive" else "Instant Hair Trigger")
        self.trigger_combo.pack(side="right")
        self.trigger_combo.bind("<<ComboboxSelected>>", self._on_trigger_change)

        # Deadzone Slider
        dz_frame = tk.Frame(sett_card, bg=self.c_card)
        dz_frame.pack(fill="x", pady=(0, 2))
        tk.Label(dz_frame, text="Stick Center Deadzone:", bg=self.c_card, fg=self.c_text).pack(side="left")
        self.dz_val_lbl = tk.Label(dz_frame, text=f"{int(round(self.config.deadzone * 100))}%", bg=self.c_card, fg=self.c_blue, font=("Segoe UI", 9, "bold"))
        self.dz_val_lbl.pack(side="right")

        self.deadzone_slider = ttk.Scale(
            sett_card,
            from_=0.0,
            to=0.25,
            value=self.config.deadzone,
            orient="horizontal",
            command=self._on_deadzone_slide,
        )
        self.deadzone_slider.pack(fill="x", pady=(0, 6))

        # Polling Rate
        rate_frame = tk.Frame(sett_card, bg=self.c_card)
        rate_frame.pack(fill="x", pady=(0, 6))
        tk.Label(rate_frame, text="Target Polling Rate:", bg=self.c_card, fg=self.c_text).pack(side="left")
        self.rate_combo = ttk.Combobox(rate_frame, values=["120 Hz", "200 Hz", "250 Hz"], state="readonly", width=14)
        self.rate_combo.set(f"{self.config.poll_rate_hz} Hz")
        self.rate_combo.pack(side="right")
        self.rate_combo.bind("<<ComboboxSelected>>", self._on_rate_change)

        # Checkboxes
        self.swap_abxy_var = tk.BooleanVar(value=self.config.swap_abxy)
        self.swap_cb = ttk.Checkbutton(
            sett_card,
            text="Swap ABXY physical layout (A<->B, X<->Y for Xbox positions)",
            variable=self.swap_abxy_var,
            command=self._on_settings_change,
        )
        self.swap_cb.pack(anchor="w", pady=(0, 3))

        self.rumble_var = tk.BooleanVar(value=self.config.enable_rumble)
        self.rumble_cb = ttk.Checkbutton(
            sett_card,
            text="Enable in-game force feedback (vibration)",
            variable=self.rumble_var,
            command=self._on_settings_change,
        )
        self.rumble_cb.pack(anchor="w", pady=(0, 3))

    def _build_tab_motion(self, parent: ttk.Frame) -> None:
        """Tab 3: Motion Aiming (Gyro), Cemuhook DSU Server, and HidHide Cloaking."""
        # 1. Gyro Aiming Card
        gyro_card = tk.Frame(parent, bg=self.c_card, padx=10, pady=8)
        gyro_card.pack(fill="x", pady=(6, 6))

        tk.Label(gyro_card, text="Gyro Aiming (Right Stick Motion Blending)", bg=self.c_card, fg="#ffffff", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 4))
        tk.Label(gyro_card, text="Blends 6-axis Switch gyroscope angular velocity into the Right Stick for mouse-like precision.", bg=self.c_card, fg=self.c_muted, font=("Segoe UI", 8)).pack(anchor="w", pady=(0, 4))

        self.gyro_aim_var = tk.BooleanVar(value=self.config.enable_gyro_aim)
        self.gyro_aim_cb = ttk.Checkbutton(
            gyro_card,
            text="Enable Gyro Aiming Assist",
            variable=self.gyro_aim_var,
            command=self._on_gyro_settings_change,
        )
        self.gyro_aim_cb.pack(anchor="w", pady=(0, 2))

        self.gyro_trigger_var = tk.BooleanVar(value=self.config.gyro_aim_trigger_only)
        self.gyro_trigger_cb = ttk.Checkbutton(
            gyro_card,
            text="Aim on Left Trigger (LT / ZL) hold only",
            variable=self.gyro_trigger_var,
            command=self._on_gyro_settings_change,
        )
        self.gyro_trigger_cb.pack(anchor="w", pady=(0, 4))

        # Sensitivity Slider
        gyro_sens_frame = tk.Frame(gyro_card, bg=self.c_card)
        gyro_sens_frame.pack(fill="x", pady=(2, 2))
        tk.Label(gyro_sens_frame, text="Gyro Aim Sensitivity:", bg=self.c_card, fg=self.c_text).pack(side="left")
        self.gyro_sens_lbl = tk.Label(gyro_sens_frame, text=f"{self.config.gyro_aim_sensitivity:.1f}x", bg=self.c_card, fg=self.c_purple, font=("Segoe UI", 9, "bold"))
        self.gyro_sens_lbl.pack(side="right")

        self.gyro_slider = ttk.Scale(
            gyro_card,
            from_=0.2,
            to=3.0,
            value=self.config.gyro_aim_sensitivity,
            orient="horizontal",
            command=self._on_gyro_slider_slide,
        )
        self.gyro_slider.pack(fill="x", pady=(0, 4))

        # 2. Cemuhook DSU Server Card
        dsu_card = tk.Frame(parent, bg=self.c_card, padx=10, pady=8)
        dsu_card.pack(fill="x", pady=(0, 6))

        tk.Label(dsu_card, text="Cemuhook DSU Motion Protocol Server", bg=self.c_card, fg="#ffffff", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 4))
        tk.Label(
            dsu_card,
            text="Streams 6-axis motion to Dolphin, Cemu, Yuzu, Ryujinx, RPCS3 on port 26760.",
            bg=self.c_card,
            fg=self.c_muted,
            font=("Segoe UI", 8),
        ).pack(anchor="w", pady=(0, 4))

        self.dsu_var = tk.BooleanVar(value=self.config.enable_dsu_server)
        self.dsu_cb = ttk.Checkbutton(
            dsu_card,
            text="Enable Cemuhook DSU UDP Server (Port 26760)",
            variable=self.dsu_var,
            command=self._on_dsu_change,
        )
        self.dsu_cb.pack(anchor="w", pady=(0, 2))

        self.dsu_status_lbl = tk.Label(
            dsu_card,
            text="Status: Server Inactive",
            bg=self.c_card,
            fg=self.c_subtle,
            font=("Segoe UI", 8),
        )
        self.dsu_status_lbl.pack(anchor="w")

        # 3. HidHide Cloaking Card
        hid_card = tk.Frame(parent, bg=self.c_card, padx=10, pady=8)
        hid_card.pack(fill="x", pady=(0, 6))

        tk.Label(hid_card, text="HidHide Double-Input Cloaking", bg=self.c_card, fg="#ffffff", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 4))
        tk.Label(
            hid_card,
            text="Hides physical Switch controller from games to prevent double-input detection.",
            bg=self.c_card,
            fg=self.c_muted,
            font=("Segoe UI", 8),
        ).pack(anchor="w", pady=(0, 4))

        self.hidhide_var = tk.BooleanVar(value=self.config.enable_hidhide)
        self.hidhide_cb = ttk.Checkbutton(
            hid_card,
            text="Cloak Physical Controller with HidHide",
            variable=self.hidhide_var,
            command=self._on_hidhide_change,
        )
        self.hidhide_cb.pack(anchor="w", pady=(0, 2))

        hh_installed = hidhide.is_hidhide_installed()
        hh_text = "✓ Nefarius HidHide driver detected" if hh_installed else "⚠ HidHide driver not detected (Optional: install to hide physical controller)"
        hh_fg = self.c_emerald if hh_installed else self.c_amber
        self.hidhide_status_lbl = tk.Label(
            hid_card,
            text=hh_text,
            bg=self.c_card,
            fg=hh_fg,
            font=("Segoe UI", 8),
        )
        self.hidhide_status_lbl.pack(anchor="w")

        # 4. System & Notifications Card
        sys_card = tk.Frame(parent, bg=self.c_card, padx=10, pady=8)
        sys_card.pack(fill="x")

        tk.Label(sys_card, text="System & Background Options", bg=self.c_card, fg="#ffffff", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 4))

        self.battery_notify_var = tk.BooleanVar(value=self.config.low_battery_notify)
        self.battery_notify_cb = ttk.Checkbutton(
            sys_card,
            text="Desktop notification on low battery",
            variable=self.battery_notify_var,
            command=self._on_settings_change,
        )
        self.battery_notify_cb.pack(anchor="w", pady=(0, 2))

        self.autostart_var = tk.BooleanVar(value=self.config.start_with_windows)
        self.autostart_cb = ttk.Checkbutton(
            sys_card,
            text="Start with Windows (Minimized to System Tray)",
            variable=self.autostart_var,
            command=self._on_settings_change,
        )
        self.autostart_cb.pack(anchor="w", pady=(0, 2))

    def _render_visualizer_tick(self) -> None:
        """Periodic high-efficiency 30 FPS tick to update stick positions, silhouette, and button gauges."""
        if not self.root.winfo_viewable():
            # Throttle when minimized to system tray
            self.root.after(150, self._render_visualizer_tick)
            return

        bridge = self.bridge
        state = bridge.last_state if bridge else None

        cx, cy, r = 48, 48, 40

        if state and bridge and bridge.is_running:
            # Normalized axes [-1.00000 to +1.00000]
            # Standard W3C Gamepad API convention: AXIS 1 & 3 are inverted (Up is negative)
            axis_0 = max(-1.0, min(1.0, state.stick_lx / 32768.0))
            axis_1 = max(-1.0, min(1.0, -state.stick_ly / 32768.0))
            axis_2 = max(-1.0, min(1.0, state.stick_rx / 32768.0))
            axis_3 = max(-1.0, min(1.0, -state.stick_ry / 32768.0))

            # 1. Update 5-decimal numeric readouts
            self.axis0_lbl.config(text=f"AXIS 0: {axis_0:+.5f}")
            self.axis1_lbl.config(text=f"AXIS 1: {axis_1:+.5f}")
            self.axis2_lbl.config(text=f"AXIS 2: {axis_2:+.5f}")
            self.axis3_lbl.config(text=f"AXIS 3: {axis_3:+.5f}")

            # 2. Update Left Stick Radar
            dot_lx = cx + axis_0 * (r - 4)
            dot_ly = cy + axis_1 * (r - 4)
            self.ls_canvas.coords("ls_dot", dot_lx - 4, dot_ly - 4, dot_lx + 4, dot_ly + 4)
            self.ls_canvas.itemconfig("ls_dot", fill=self.c_rose if state.btn_lsb else self.c_blue)

            # 3. Update Right Stick Radar
            dot_rx = cx + axis_2 * (r - 4)
            dot_ry = cy + axis_3 * (r - 4)
            self.rs_canvas.coords("rs_dot", dot_rx - 4, dot_ry - 4, dot_rx + 4, dot_ry + 4)
            self.rs_canvas.itemconfig("rs_dot", fill=self.c_rose if state.btn_rsb else self.c_blue)

            # 4. Circularity Benchmark Tracking
            if self._testing_circularity:
                rad_l = math.sqrt(axis_0 ** 2 + axis_1 ** 2)
                if rad_l > 0.60:
                    self._circ_samples_l.append(rad_l)
                    self.ls_canvas.create_oval(
                        dot_lx - 1, dot_ly - 1, dot_lx + 1, dot_ly + 1,
                        fill=self.c_rose, outline="", tags="circ_pts_l"
                    )
                    err_l = (sum(abs(s - 1.0) for s in self._circ_samples_l) / len(self._circ_samples_l)) * 100.0
                    col_l = self.c_emerald if err_l < 10.0 else (self.c_amber if err_l < 16.0 else self.c_rose)
                    self.circ_l_lbl.config(text=f"Avg Error: {err_l:.1f}%", fg=col_l)

                rad_r = math.sqrt(axis_2 ** 2 + axis_3 ** 2)
                if rad_r > 0.60:
                    self._circ_samples_r.append(rad_r)
                    self.rs_canvas.create_oval(
                        dot_rx - 1, dot_ry - 1, dot_rx + 1, dot_ry + 1,
                        fill=self.c_rose, outline="", tags="circ_pts_r"
                    )
                    err_r = (sum(abs(s - 1.0) for s in self._circ_samples_r) / len(self._circ_samples_r)) * 100.0
                    col_r = self.c_emerald if err_r < 10.0 else (self.c_amber if err_r < 16.0 else self.c_rose)
                    self.circ_r_lbl.config(text=f"Avg Error: {err_r:.1f}%", fg=col_r)

            # 5. Interactive Gamepad Silhouette Updates
            # Moving Stick Caps
            cap_lx = 74 + axis_0 * 7
            cap_ly = 80 + axis_1 * 7
            self.silhouette_canvas.coords("shp_ls", cap_lx - 12, cap_ly - 12, cap_lx + 12, cap_ly + 12)
            self.silhouette_canvas.coords("shp_ls_txt", cap_lx, cap_ly)
            self.silhouette_canvas.itemconfig("shp_ls", fill=self.c_rose if state.btn_lsb else "#27272a")

            cap_rx = 168 + axis_2 * 7
            cap_ry = 114 + axis_3 * 7
            self.silhouette_canvas.coords("shp_rs", cap_rx - 12, cap_ry - 12, cap_rx + 12, cap_ry + 12)
            self.silhouette_canvas.coords("shp_rs_txt", cap_rx, cap_ry)
            self.silhouette_canvas.itemconfig("shp_rs", fill=self.c_rose if state.btn_rsb else "#27272a")

            # ABXY Face Buttons
            self.silhouette_canvas.itemconfig("shp_a", fill=self.c_emerald if state.btn_a else "#27272a", outline="#34d399" if state.btn_a else "#52525b")
            self.silhouette_canvas.itemconfig("shp_b", fill=self.c_rose if state.btn_b else "#27272a", outline="#f87171" if state.btn_b else "#52525b")
            self.silhouette_canvas.itemconfig("shp_x", fill=self.c_blue if state.btn_x else "#27272a", outline="#60a5fa" if state.btn_x else "#52525b")
            self.silhouette_canvas.itemconfig("shp_y", fill=self.c_amber if state.btn_y else "#27272a", outline="#fbbf24" if state.btn_y else "#52525b")

            # D-Pad
            self.silhouette_canvas.itemconfig("shp_du", fill=self.c_blue if state.dpad_up else "#27272a")
            self.silhouette_canvas.itemconfig("shp_dd", fill=self.c_blue if state.dpad_down else "#27272a")
            self.silhouette_canvas.itemconfig("shp_dl", fill=self.c_blue if state.dpad_left else "#27272a")
            self.silhouette_canvas.itemconfig("shp_dr", fill=self.c_blue if state.dpad_right else "#27272a")

            # Bumpers and Triggers
            self.silhouette_canvas.itemconfig("shp_lb", fill=self.c_blue if state.btn_lb else "#27272a")
            self.silhouette_canvas.itemconfig("shp_rb", fill=self.c_blue if state.btn_rb else "#27272a")
            self.silhouette_canvas.itemconfig("shp_lt", fill=self.c_blue if state.trigger_l > 12 else "#27272a")
            self.silhouette_canvas.itemconfig("shp_rt", fill=self.c_blue if state.trigger_r > 12 else "#27272a")

            # Center buttons
            self.silhouette_canvas.itemconfig("shp_back", fill=self.c_muted if state.btn_back else "#27272a")
            self.silhouette_canvas.itemconfig("shp_start", fill=self.c_muted if state.btn_start else "#27272a")
            self.silhouette_canvas.itemconfig("shp_guide", fill=self.c_purple if state.btn_guide else "#27272a")
            self.silhouette_canvas.itemconfig("shp_capture", fill=self.c_amber if state.btn_capture else "#27272a")

            # 6. Standard Buttons Array Gauges (B0 - B17)
            b_vals = {
                "b0": 1.0 if state.btn_a else 0.0,
                "b1": 1.0 if state.btn_b else 0.0,
                "b2": 1.0 if state.btn_x else 0.0,
                "b3": 1.0 if state.btn_y else 0.0,
                "b4": 1.0 if state.btn_lb else 0.0,
                "b5": 1.0 if state.btn_rb else 0.0,
                "b6": state.trigger_l / 255.0,
                "b7": state.trigger_r / 255.0,
                "b8": 1.0 if state.btn_back else 0.0,
                "b9": 1.0 if state.btn_start else 0.0,
                "b10": 1.0 if state.btn_lsb else 0.0,
                "b11": 1.0 if state.btn_rsb else 0.0,
                "b12": 1.0 if state.dpad_up else 0.0,
                "b13": 1.0 if state.dpad_down else 0.0,
                "b14": 1.0 if state.dpad_left else 0.0,
                "b15": 1.0 if state.dpad_right else 0.0,
                "b16": 1.0 if state.btn_guide else 0.0,
                "b17": 1.0 if state.btn_capture else 0.0,
            }

            for key, val in b_vals.items():
                if key in self.btn_gauges:
                    g = self.btn_gauges[key]
                    active = val > 0.05
                    cv = g["canvas"]
                    w = cv.winfo_width()
                    if w < 10:
                        w = 68
                    fill_w = int(w * max(0.0, min(1.0, val)))
                    cv.coords(g["rect_id"], 0, 0, fill_w, 3)
                    cv.itemconfig(g["rect_id"], fill=self.c_emerald if active else self.c_blue)
                    g["lbl_val"].config(
                        text=f"{val:.2f}",
                        fg="#ffffff" if active else self.c_subtle,
                        font=("Consolas", 7, "bold" if active else "normal"),
                    )
                    g["frame"].config(highlightbackground=self.c_blue if active else self.c_border)

        else:
            # Reset canvas dots to center
            self.ls_canvas.coords("ls_dot", cx - 4, cy - 4, cx + 4, cy + 4)
            self.rs_canvas.coords("rs_dot", cx - 4, cy - 4, cx + 4, cy + 4)
            self.axis0_lbl.config(text="AXIS 0:  0.00000")
            self.axis1_lbl.config(text="AXIS 1:  0.00000")
            self.axis2_lbl.config(text="AXIS 2:  0.00000")
            self.axis3_lbl.config(text="AXIS 3:  0.00000")

            # Reset silhouette shapes
            self.silhouette_canvas.coords("shp_ls", 74 - 12, 80 - 12, 74 + 12, 80 + 12)
            self.silhouette_canvas.coords("shp_ls_txt", 74, 80)
            self.silhouette_canvas.itemconfig("shp_ls", fill="#27272a")

            self.silhouette_canvas.coords("shp_rs", 168 - 12, 114 - 12, 168 + 12, 114 + 12)
            self.silhouette_canvas.coords("shp_rs_txt", 168, 114)
            self.silhouette_canvas.itemconfig("shp_rs", fill="#27272a")

            for tag in ("shp_a", "shp_b", "shp_x", "shp_y", "shp_du", "shp_dd", "shp_dl", "shp_dr", "shp_lb", "shp_rb", "shp_lt", "shp_rt", "shp_back", "shp_start", "shp_guide", "shp_capture"):
                self.silhouette_canvas.itemconfig(tag, fill="#27272a")

            # Reset all button gauges
            for g in self.btn_gauges.values():
                g["canvas"].coords(g["rect_id"], 0, 0, 0, 3)
                g["lbl_val"].config(text="0.00", fg=self.c_subtle, font=("Consolas", 7))
                g["frame"].config(highlightbackground=self.c_border)

        self.root.after(33, self._render_visualizer_tick)

    def _setup_tray(self) -> None:
        """Initialize background system tray icon with pystray."""
        tray_image = generate_gamepad_icon(connected=False, size=64)

        menu = pystray.Menu(
            pystray.MenuItem(f"Switch2Xbox v{APP_VERSION}", self.show_from_tray, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Open Window", self.show_from_tray),
            pystray.MenuItem("Test Controller (joy.cpl)", self.open_joy_cpl),
            pystray.MenuItem("View Logs (switch2xbox.log)", open_log_file),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Start Bridge", self.start_bridge),
            pystray.MenuItem("Stop Bridge", self.stop_bridge),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit", self.quit_app),
        )

        self.tray_icon = pystray.Icon("Switch2Xbox", tray_image, f"Switch2Xbox v{APP_VERSION}", menu)
        threading.Thread(target=self.tray_icon.run, daemon=True, name="SystemTrayThread").start()

    def update_tray_icon(self, connected: bool) -> None:
        """Update system tray icon color dynamically on connection status change."""
        if not self.tray_icon or not getattr(self.tray_icon, "visible", False):
            return

        if connected == self._last_tray_connected:
            return

        self._last_tray_connected = connected
        try:
            new_img = generate_gamepad_icon(connected=connected, size=64)
            self.tray_icon.icon = new_img
            status_text = "Connected" if connected else "Waiting for controller..."
            self.tray_icon.title = f"Switch2Xbox ({status_text})"
        except Exception as e:
            logger.debug(f"Error updating tray icon: {e}")

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

    def refresh_profiles(self) -> None:
        """Load profiles from profiles.json and update profile dropdown."""
        profiles = load_all_profiles()
        names = list(profiles.keys())
        self.profile_combo["values"] = names
        active = self.config.active_profile
        if active in names:
            self.profile_combo.set(active)
        elif names:
            self.profile_combo.current(0)

    def _on_profile_selected(self, event=None) -> None:
        """Switch active configuration profile."""
        name = self.profile_combo.get()
        profiles = load_all_profiles()
        if name in profiles:
            p_dict = profiles[name]
            self.config.apply_dict(p_dict)
            self.config.active_profile = name
            self.config.save_to_file()
            self._sync_controls_from_config()
            if self.bridge:
                self.bridge.config = self.config

    def _sync_controls_from_config(self) -> None:
        """Updates GUI widget values to match current config."""
        self.target_combo.set("PlayStation 4 (DualShock 4)" if self.config.emulation_target == "ds4" else "Xbox 360 (XInput Default)")
        curve_map = {"linear": "Linear (1:1 Standard)", "smooth": "Smooth Aim (Exponential)", "aggressive": "Aggressive (Snappy)"}
        self.curve_combo.set(curve_map.get(self.config.stick_curve, "Linear (1:1 Standard)"))
        self.trigger_combo.set("Progressive Smooth Ramp (~25ms)" if self.config.trigger_mode == "progressive" else "Instant Hair Trigger")
        self.swap_abxy_var.set(self.config.swap_abxy)
        self.rumble_var.set(self.config.enable_rumble)
        self.deadzone_slider.set(self.config.deadzone)
        self.dz_val_lbl.config(text=f"{int(round(self.config.deadzone * 100))}%")
        self.rate_combo.set(f"{self.config.poll_rate_hz} Hz")
        self.gyro_aim_var.set(self.config.enable_gyro_aim)
        self.gyro_trigger_var.set(self.config.gyro_aim_trigger_only)
        self.gyro_slider.set(self.config.gyro_aim_sensitivity)
        self.gyro_sens_lbl.config(text=f"{self.config.gyro_aim_sensitivity:.1f}x")
        self.dsu_var.set(self.config.enable_dsu_server)
        self.hidhide_var.set(self.config.enable_hidhide)

    def _save_profile_click(self) -> None:
        """Prompts user to save current config as a new profile."""
        name = simpledialog.askstring("Save Profile", "Enter a name for this profile:", initialvalue=self.config.active_profile)
        if name and name.strip():
            name = name.strip()
            self.config.active_profile = name
            save_named_profile(name, self.config)
            self.refresh_profiles()
            self.profile_combo.set(name)

    def _delete_profile_click(self) -> None:
        """Deletes the currently selected custom profile."""
        name = self.profile_combo.get()
        if name == "Default":
            messagebox.showinfo("Info", "Cannot delete the Default profile.")
            return
        if messagebox.askyesno("Confirm Delete", f"Delete profile '{name}'?"):
            delete_named_profile(name)
            self.refresh_profiles()
            self.profile_combo.current(0)
            self._on_profile_selected()

    def start_stick_calibration(self) -> None:
        """Triggers hardware stick center offset calibration."""
        if self.bridge and self.bridge.is_running:
            self.calib_status_lbl.config(text="Calibrating... Keep sticks in neutral center position!", fg=self.c_amber)
            self.bridge.calibrate_stick_centers()
        else:
            messagebox.showinfo("Info", "Please start the bridge first to calibrate sticks.")

    def _on_device_selected(self, event=None) -> None:
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

        if self.bridge and self.bridge.is_running:
            self.stop_bridge()
            self.start_bridge()

    def _on_target_change(self, event=None) -> None:
        choice = self.target_combo.get()
        new_target = "ds4" if "PlayStation" in choice else "xbox360"
        if self.config.emulation_target != new_target:
            self.config.emulation_target = new_target
            self.config.save_to_file()
            if self.bridge and self.bridge.is_running:
                self.stop_bridge()
                self.start_bridge()

    def _on_curve_change(self, event=None) -> None:
        choice = self.curve_combo.get()
        if "Smooth" in choice:
            self.config.stick_curve = "smooth"
        elif "Aggressive" in choice:
            self.config.stick_curve = "aggressive"
        else:
            self.config.stick_curve = "linear"
        if self.bridge:
            self.bridge.config.stick_curve = self.config.stick_curve
        self.config.save_to_file()

    def _on_trigger_change(self, event=None) -> None:
        choice = self.trigger_combo.get()
        self.config.trigger_mode = "progressive" if "Progressive" in choice else "hair"
        if self.bridge:
            self.bridge.config.trigger_mode = self.config.trigger_mode
        self.config.save_to_file()

    def _on_deadzone_slide(self, val: str) -> None:
        float_val = float(val)
        self.config.deadzone = float_val
        self.dz_val_lbl.config(text=f"{int(round(float_val * 100))}%")
        # Update deadzone rings on canvas
        r = 40
        dz_r = r * float_val
        cx, cy = 48, 48
        self.ls_canvas.coords("ls_dz", cx - dz_r, cy - dz_r, cx + dz_r, cy + dz_r)
        self.rs_canvas.coords("rs_dz", cx - dz_r, cy - dz_r, cx + dz_r, cy + dz_r)
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
        notify = self.battery_notify_var.get()
        autostart = self.autostart_var.get()

        self.config.swap_abxy = swap
        self.config.enable_rumble = rumble
        self.config.low_battery_notify = notify
        self.config.start_with_windows = autostart

        set_windows_autostart(autostart)
        self.config.save_to_file()

        if self.bridge:
            self.bridge.config.swap_abxy = swap
            self.bridge.config.enable_rumble = rumble
            self.bridge.config.low_battery_notify = notify
        self.vibration_lbl.config(text="Enabled ⚡" if rumble else "Disabled", fg=self.c_emerald if rumble else self.c_subtle)

    def _on_gyro_settings_change(self) -> None:
        enable_gyro = self.gyro_aim_var.get()
        trigger_only = self.gyro_trigger_var.get()
        self.config.enable_gyro_aim = enable_gyro
        self.config.gyro_aim_trigger_only = trigger_only
        self.config.save_to_file()
        if self.bridge:
            self.bridge.config.enable_gyro_aim = enable_gyro
            self.bridge.config.gyro_aim_trigger_only = trigger_only

    def _on_gyro_slider_slide(self, val: str) -> None:
        float_val = float(val)
        self.config.gyro_aim_sensitivity = float_val
        self.gyro_sens_lbl.config(text=f"{float_val:.1f}x")
        if self.bridge:
            self.bridge.config.gyro_aim_sensitivity = float_val
            self.bridge.gyro_processor.sensitivity = float_val
        self.config.save_to_file()

    def _on_dsu_change(self) -> None:
        enabled = self.dsu_var.get()
        self.config.enable_dsu_server = enabled
        self.config.save_to_file()
        if self.bridge and self.bridge.is_running:
            self.stop_bridge()
            self.start_bridge()

    def _on_hidhide_change(self) -> None:
        enabled = self.hidhide_var.get()
        self.config.enable_hidhide = enabled
        self.config.save_to_file()
        if self.bridge and self.bridge.is_running:
            self.stop_bridge()
            self.start_bridge()

    def _on_battery_warning(self, battery_level: str) -> None:
        if self.tray_icon:
            try:
                self.tray_icon.notify(
                    f"⚠️ Gamepad battery is {battery_level}! Please connect charging cable.",
                    "Switch2Xbox Battery Warning",
                )
            except Exception:
                pass

    def _test_rumble_click(self) -> None:
        if self.bridge and self.bridge.is_running:
            self.bridge.test_rumble(duration_sec=0.4, intensity=220)
        else:
            messagebox.showinfo("Info", "Start the bridge first to test vibration.")

    def start_bridge(self) -> None:
        if self.bridge and self.bridge.is_running:
            return

        self.bridge = GamepadBridge(
            self.config,
            status_callback=self._on_bridge_status,
            battery_warning_callback=self._on_battery_warning,
        )
        self.bridge.start_background()

        self.toggle_btn.config(text="⏹ Stop Bridge", bg=self.c_rose, activebackground="#dc2626")

    def stop_bridge(self) -> None:
        if self.bridge:
            self.bridge.stop()
            self.bridge = None

        self.toggle_btn.config(text="▶ Start Bridge", bg=self.c_emerald, activebackground="#059669")
        self._update_status_ui({
            "is_connected": False,
            "device_name": "Stopped",
            "protocol_mode": ProtocolMode.UNKNOWN,
            "battery": None,
            "charging": False,
            "rate_hz": 0.0,
            "latency_ms": 0.0,
            "jitter_ms": 0.0,
            "target_label": "PlayStation 4" if self.config.emulation_target == "ds4" else "Xbox 360",
            "calibrating": False,
            "dsu_active": False,
            "hidhide_active": False,
        })

    def toggle_bridge(self) -> None:
        if self.bridge and self.bridge.is_running:
            self.stop_bridge()
        else:
            self.start_bridge()

    def _on_bridge_status(self, status: Dict[str, Any]) -> None:
        self.root.after(0, lambda: self._update_status_ui(status))

    def _update_status_ui(self, status: Dict[str, Any]) -> None:
        connected = status.get("is_connected", False)
        self.is_connected = connected

        if connected:
            self.status_pill.config(text="● CONNECTED", bg="#064e3b", fg=self.c_emerald)
            if hasattr(self, "index_lbl"):
                self.index_lbl.config(text="0", fg=self.c_emerald)
        elif self.bridge and self.bridge.is_running:
            self.status_pill.config(text="● SEARCHING...", bg="#451a03", fg=self.c_amber)
            if hasattr(self, "index_lbl"):
                self.index_lbl.config(text="-", fg=self.c_amber)
        else:
            self.status_pill.config(text="● STOPPED", bg=self.c_card_sub, fg=self.c_subtle)
            if hasattr(self, "index_lbl"):
                self.index_lbl.config(text="-", fg=self.c_subtle)

        self.device_name_lbl.config(text=status.get("device_name", "None"))
        self.emulating_lbl.config(text=status.get("target_label", "Xbox 360"))

        mode = status.get("protocol_mode", ProtocolMode.UNKNOWN)
        mode_text = {
            ProtocolMode.SWITCH_FULL: "Switch Standard (0x30 Full)",
            ProtocolMode.SWITCH_REPLY: "Switch Subcommand (0x21)",
            ProtocolMode.ODM_SIMPLE_3F: "ODM Clone Simple (0x3F)",
            ProtocolMode.GENERIC_HID: "Generic DirectInput Fallback",
        }.get(mode, "Detecting...")
        self.protocol_lbl.config(text=mode_text)

        lat = status.get("latency_ms", 0.0)
        jit = status.get("jitter_ms", 0.0)
        self.timing_lbl.config(text=f"{lat:.1f} ms (±{jit:.1f} ms)" if lat > 0 else "Measuring...")

        bat = status.get("battery")
        charging = status.get("charging", False)
        self.battery_lbl.config(text=f"{bat.name}{' (⚡ Charging)' if charging else ''}" if bat else "N/A")

        rate_hz = status.get("rate_hz", 0.0)
        self.rate_badge.config(text=f"{rate_hz:.0f} Hz" if rate_hz > 0 else "0 Hz")

        rumble_active = status.get("rumble_active", False)
        if rumble_active:
            self.vibration_lbl.config(text="Vibrating ⚡⚡", fg=self.c_rose)
        elif self.config.enable_rumble:
            self.vibration_lbl.config(text="Enabled ⚡", fg=self.c_emerald)
        else:
            self.vibration_lbl.config(text="Disabled", fg=self.c_subtle)

        # Calibration status update
        calibrating = status.get("calibrating", False)
        if calibrating:
            self.calib_status_lbl.config(text="Calibrating... Keep sticks in neutral center position!", fg=self.c_amber)
        else:
            self.calib_status_lbl.config(
                text=f"Centers: LX={self.config.stick_lx_center}, LY={self.config.stick_ly_center} | RX={self.config.stick_rx_center}, RY={self.config.stick_ry_center}",
                fg=self.c_muted,
            )

        # DSU server status
        dsu_active = status.get("dsu_active", False)
        if dsu_active:
            self.dsu_status_lbl.config(text=f"Status: Active on 127.0.0.1:{self.config.dsu_server_port} (Streaming)", fg=self.c_emerald)
        else:
            self.dsu_status_lbl.config(text="Status: Server Inactive", fg=self.c_subtle)

        self.update_tray_icon(connected)

    def open_joy_cpl(self) -> None:
        try:
            subprocess.Popen("joy.cpl", shell=True)
        except Exception as e:
            messagebox.showerror("Error", f"Could not launch joy.cpl: {e}")

    def hide_to_tray(self) -> None:
        self.root.withdraw()
        if self.tray_icon:
            try:
                self.tray_icon.notify(
                    "Switch2Xbox is running in background.\nDouble-click tray icon to restore.",
                    "Switch2Xbox Minimized",
                )
            except Exception:
                pass

    def show_from_tray(self, icon=None, item=None) -> None:
        self.root.after(0, self._restore_window)

    def _restore_window(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def quit_app(self, icon=None, item=None) -> None:
        self.stop_bridge()
        if self.tray_icon:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
        self.root.after(50, self.root.destroy)


def run_gui() -> None:
    setup_logging()
    root = tk.Tk()
    app = GamepadBridgeGUI(root)
    root.mainloop()


if __name__ == "__main__":
    run_gui()

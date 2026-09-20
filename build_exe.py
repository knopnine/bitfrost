"""Build script to compile Switch2Xbox into a standalone Windows .exe."""

import os
import shutil
import subprocess
import sys
from icon import save_ico_file


def build() -> None:
    print("=======================================================")
    print("  Switch2Xbox - Building Standalone Windows Executable ")
    print("=======================================================")

    # Terminate any running instances before building to prevent file lock errors
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/F", "/IM", "Switch2Xbox.exe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Ensure icon exists
    ico_path = os.path.abspath("app_icon.ico")
    if not os.path.exists(ico_path):
        save_ico_file(ico_path)

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--onedir",             # onedir is faster to launch and avoids temp unpacking issues
        "--windowed",           # GUI application without console window
        "--name", "Switch2Xbox",
        "--icon", "app_icon.ico",
        "--add-data", f"app_icon.ico{os.pathsep}.",
        "--collect-all", "vgamepad",
        "--collect-all", "hid",
        "--collect-all", "pystray",
        "--collect-all", "PIL",
        "main.py",
    ]

    print("Running PyInstaller command:")
    print(" ".join(cmd))
    print("-" * 55)

    result = subprocess.run(cmd)
    if result.returncode == 0:
        print("-" * 55)
        print("Build SUCCESSFUL!")
        dist_dir = os.path.abspath(os.path.join("dist", "Switch2Xbox"))
        exe_path = os.path.join(dist_dir, "Switch2Xbox.exe")
        print(f"Executable output: {exe_path}")
        print("You can run Switch2Xbox.exe directly from Windows Explorer!")
    else:
        print(f"Build failed with exit code {result.returncode}")


if __name__ == "__main__":
    build()


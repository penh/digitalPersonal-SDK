#!/usr/bin/env python3
"""
Cross-platform builder script for generating standalone executables using PyInstaller.

Usage:
  python build_exe.py
"""

import os
import sys
import shutil
import subprocess

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))


def check_pyinstaller():
    try:
        import PyInstaller
        return True
    except ImportError:
        return False


def build_target(spec_file: str):
    print(f"\n---> Building target from '{spec_file}'...")
    cmd = [sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm", spec_file]
    res = subprocess.run(cmd, cwd=PROJECT_ROOT)
    if res.returncode != 0:
        print(f"[Error] Failed to build {spec_file}")
        return False
    return True


def main():
    print("=" * 60)
    print(" DigitalPersona 4500 - Executable Builder")
    print(f" Target Platform: {sys.platform}")
    print("=" * 60)

    if not check_pyinstaller():
        print("[!] PyInstaller is not installed in the current environment.")
        print("    Installing PyInstaller...")
        subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"], check=True)

    # 1. Build server
    ok_server = build_target("dp4500_server.spec")

    # 2. Build CLI
    ok_cli = build_target("dp4500_cli.spec")

    if ok_server and ok_cli:
        dist_dir = os.path.join(PROJECT_ROOT, "dist")
        print("\n" + "=" * 60)
        print(" [✓] Build Successful!")
        print(" Output directory:", dist_dir)
        if os.path.exists(dist_dir):
            for item in os.listdir(dist_dir):
                print(f"   -> {item}")
        print("=" * 60)
    else:
        print("\n[!] Build completed with errors.")
        sys.exit(1)


if __name__ == "__main__":
    main()

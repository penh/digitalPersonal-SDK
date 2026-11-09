"""
Linux USB permission and udev configuration helpers for DigitalPersona 4500 readers.
"""

from __future__ import annotations
import os
import sys
import glob
from typing import Dict, Any, Optional

DEFAULT_RULE_FILENAME = "/etc/udev/rules.d/99-digitalpersona-uareu.rules"
UDEV_RULE_CONTENT = """# Udev rule for DigitalPersona (U.are.U) 4500 Fingerprint Reader (05ba:000a)
# Allows non-root users access to the biometric USB device node.
SUBSYSTEM=="usb", ATTRS{idVendor}=="05ba", ATTRS{idProduct}=="000a", MODE="0666", GROUP="plugdev", TAG+="uaccess"
"""


def check_usb_permissions() -> Dict[str, Any]:
    """
    Inspect the host environment to diagnose whether the connected
    DigitalPersona 4500 reader can be opened in read-write mode.
    """
    report: Dict[str, Any] = {
        "is_linux": sys.platform.startswith("linux"),
        "device_found": False,
        "device_path": None,
        "can_read": False,
        "can_write": False,
        "has_udev_rule": False,
        "udev_rule_path": None,
        "advice": [],
    }

    if not report["is_linux"]:
        return report

    # 1. Search for 05ba:000a in /sys/bus/usb/devices
    device_usb_node = None
    for sys_path in glob.glob("/sys/bus/usb/devices/*"):
        id_vendor_path = os.path.join(sys_path, "idVendor")
        id_product_path = os.path.join(sys_path, "idProduct")
        if os.path.exists(id_vendor_path) and os.path.exists(id_product_path):
            try:
                with open(id_vendor_path, "r") as f:
                    vid = f.read().strip().lower()
                with open(id_product_path, "r") as f:
                    pid = f.read().strip().lower()

                if vid == "05ba" and pid == "000a":
                    report["device_found"] = True
                    # Find bus and devnum
                    bus_p = os.path.join(sys_path, "busnum")
                    dev_p = os.path.join(sys_path, "devnum")
                    if os.path.exists(bus_p) and os.path.exists(dev_p):
                        with open(bus_p, "r") as f:
                            bus = int(f.read().strip())
                        with open(dev_p, "r") as f:
                            dev = int(f.read().strip())
                        device_usb_node = f"/dev/bus/usb/{bus:03d}/{dev:03d}"
                        break
            except Exception:
                continue

    if not report["device_found"]:
        report["advice"].append("DigitalPersona reader (05ba:000a) not detected on any USB bus.")
        return report

    report["device_path"] = device_usb_node
    if device_usb_node and os.path.exists(device_usb_node):
        report["can_read"] = os.access(device_usb_node, os.R_OK)
        report["can_write"] = os.access(device_usb_node, os.W_OK)

    # 2. Check existing udev rules
    for rpath in glob.glob("/etc/udev/rules.d/*.rules") + glob.glob("/lib/udev/rules.d/*.rules"):
        try:
            with open(rpath, "r", errors="ignore") as f:
                content = f.read()
                if "05ba" in content.lower() and "000a" in content.lower():
                    report["has_udev_rule"] = True
                    report["udev_rule_path"] = rpath
                    break
        except Exception:
            continue

    if not report["can_write"]:
        report["advice"].append(
            f"Insufficient permissions on USB node '{device_usb_node}'. Write access is required by libusb."
        )
        if not report["has_udev_rule"]:
            report["advice"].append(
                f"No udev rule for 05ba:000a was found in /etc/udev/rules.d/.\n"
                f"Run: sudo dp4500 setup-udev\n"
                f"Or create {DEFAULT_RULE_FILENAME} with:\n"
                f"{UDEV_RULE_CONTENT}\n"
                f"Then run:\n"
                f"  sudo udevadm control --reload-rules && sudo udevadm trigger"
            )

    return report


def get_udev_rule_content() -> str:
    """Return the recommended udev rule text."""
    return UDEV_RULE_CONTENT


def install_udev_rule(path: str = DEFAULT_RULE_FILENAME) -> bool:
    """
    Attempt to write the udev rule file directly (requires root privileges).
    """
    try:
        with open(path, "w") as f:
            f.write(UDEV_RULE_CONTENT)
        os.system("udevadm control --reload-rules 2>/dev/null || true")
        os.system("udevadm trigger 2>/dev/null || true")
        return True
    except PermissionError:
        return False

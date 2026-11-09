"""
Command-line interface (CLI) for the DigitalPersona U.are.U 4500 SDK.
"""

from __future__ import annotations
import argparse
import sys
import os
import time
import glob
from typing import Optional

# Ensure safe output encoding on Windows terminals
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from dp4500 import (
    UareU4500,
    ReaderManager,
    FingerprintImage,
    FingerprintTemplate,
    check_usb_permissions,
    get_udev_rule_content,
    install_udev_rule,
)
from dp4500.backends.mock import MockBackend


def cmd_list(args):
    """List connected devices and available backends."""
    print("=" * 60)
    print(" DigitalPersona U.are.U 4500 - Device Enumeration")
    print("=" * 60)

    backends = ReaderManager.available_backends()
    print(f"Available Backends on this System: {', '.join(backends)}")

    devices = ReaderManager.list_readers()
    if not devices:
        print("\nNo physical DigitalPersona devices detected.")
        if "mock" in backends:
            print("Hint: You can use the virtual device with --mock flag.")
        return

    print(f"\nFound {len(devices)} device(s):")
    for i, dev in enumerate(devices):
        print(f"  [{i}] {dev.name}")
        print(f"      ID:     {dev.device_id}")
        print(f"      Driver: {dev.driver}")
        print(f"      USB:    {dev.vendor_id:04x}:{dev.product_id:04x}")
        if dev.serial_number:
            print(f"      Serial: {dev.serial_number}")
    print()


def cmd_info(args):
    """Display detailed hardware, driver, and permission diagnostics."""
    print("=" * 60)
    print(" System and Hardware Diagnostics")
    print("=" * 60)

    # 1. Backends
    backends = ReaderManager.available_backends()
    print(f"Supported Backends: {', '.join(backends)}")

    # 2. USB Permissions (Linux)
    report = check_usb_permissions()
    if report["is_linux"]:
        print("\nLinux USB Device & Permissions:")
        print(f"  Device Found:   {report['device_found']}")
        if report["device_path"]:
            print(f"  Device Node:    {report['device_path']}")
            print(f"  Read Access:    {'YES' if report['can_read'] else 'NO'}")
            print(f"  Write Access:   {'YES' if report['can_write'] else 'NO'}")
            print(f"  Udev Rule Configured: {'YES' if report['has_udev_rule'] else 'NO'}")
            if report['udev_rule_path']:
                print(f"  Rule File:      {report['udev_rule_path']}")

        if report["advice"]:
            print("\n  [!] Action Required:")
            for adv in report["advice"]:
                print(f"    - {adv}")

    # 3. Readers
    try:
        backend = MockBackend() if args.mock else None
        reader = UareU4500(backend=backend)
        print("\nActive Reader Connection:")
        print(f"  Device Name:   {reader.name}")
        print(f"  Driver:        {reader.driver}")
        print(f"  Backend:       {reader.backend.backend_name()}")
        print(f"  Vendor/PID:    {reader.vendor_id:04x}:{reader.product_id:04x}")
        if reader.serial_number:
            print(f"  Serial:        {reader.serial_number}")
    except Exception as e:
        print(f"\nCould not open reader: {e}")


def cmd_capture(args):
    """Capture a fingerprint image to disk."""
    backend = MockBackend() if args.mock else None
    out_path = args.out or f"fingerprint_{int(time.time())}.{args.format.lower()}"

    print(f"Initializing reader ({'Mock' if args.mock else 'Hardware'})...")
    with UareU4500(backend=backend) as reader:
        print("Reader ready. Please place your finger on the sensor...")
        img = reader.capture(wait_for_finger=True)
        img.save(out_path, format=args.format)
        print(f"[OK] Fingerprint captured successfully!")
        print(f"    Dimensions: {img.width}x{img.height} pixels @ {img.dpi} DPI")
        print(f"    Quality:    {img.quality_score}%")
        print(f"    Saved to:   {out_path}")


def cmd_enroll(args):
    """Interactively enroll a user's fingerprint."""
    backend = MockBackend() if args.mock else None
    out_path = args.out or f"{args.user or 'user'}.fpt"

    print(f"Starting enrollment for user '{args.user or 'default'}' ({args.stages} stages)...")
    with UareU4500(backend=backend) as reader:
        def on_progress(completed, total):
            print(f"  -> Scan {completed}/{total} acquired. Lift and place finger again...")

        print("Place finger on the scanner...")
        tpl = reader.enroll(
            stages=args.stages,
            on_stage_progress=on_progress,
            username=args.user,
            finger_name=args.finger,
        )
        tpl.save(out_path)
        print(f"[OK] Enrollment complete!")
        print(f"    Template size: {tpl.size} bytes (Format: {tpl.format_type})")
        print(f"    Saved to:      {out_path}")


def cmd_verify(args):
    """Verify live finger against an enrolled template file."""
    if not os.path.exists(args.template):
        print(f"Error: Template file '{args.template}' not found.")
        sys.exit(1)

    tpl = FingerprintTemplate.load(args.template)
    print(f"Loaded reference template for user '{tpl.username or 'unknown'}' ({tpl.format_type}).")

    backend = MockBackend() if args.mock else None
    with UareU4500(backend=backend) as reader:
        print("Place finger on the reader to verify...")
        result = reader.verify(tpl)
        if result.matched:
            print(f"[OK] VERIFIED: Fingerprint matches! (Confidence score: {result.score:.2f})")
        else:
            print(f"[FAIL] REJECTED: Fingerprint does NOT match! (Score: {result.score:.2f})")
            sys.exit(2)


def cmd_identify(args):
    """Identify live finger against a folder of template files."""
    if not os.path.isdir(args.dir):
        print(f"Error: Templates directory '{args.dir}' does not exist.")
        sys.exit(1)

    template_files = glob.glob(os.path.join(args.dir, "*.fpt"))
    if not template_files:
        print(f"No .fpt template files found in '{args.dir}'.")
        sys.exit(1)

    templates = [FingerprintTemplate.load(f) for f in template_files]
    print(f"Loaded {len(templates)} candidate template(s) from '{args.dir}'.")

    backend = MockBackend() if args.mock else None
    with UareU4500(backend=backend) as reader:
        print("Place finger on reader to identify...")
        res = reader.identify(templates)
        if res.matched and res.template:
            matched_file = template_files[res.index] if res.index is not None else "unknown"
            print(f"[OK] IDENTIFIED as user '{res.template.username or matched_file}'!")
            print(f"    File:  {matched_file}")
            print(f"    Score: {res.score:.2f}")
        else:
            print("[FAIL] NOT IDENTIFIED: No matching fingerprint found in gallery.")
            sys.exit(2)


def cmd_setup_udev(args):
    """Show or install Linux udev rules for non-root USB access."""
    if not sys.platform.startswith("linux"):
        print("udev rules are only applicable on Linux operating systems.")
        return

    print("Recommended Udev Rule for DigitalPersona 4500 (05ba:000a):")
    print("-" * 60)
    print(get_udev_rule_content())
    print("-" * 60)

    if args.install:
        success = install_udev_rule()
        if success:
            print("[OK] Udev rule installed successfully! USB permissions updated.")
        else:
            print("[FAIL] Permission denied. Run with sudo: sudo dp4500 setup-udev --install")
    else:
        print("To install automatically, run:")
        print("  sudo dp4500 setup-udev --install")
        print("\nOr install manually by saving the content to /etc/udev/rules.d/99-digitalpersona-uareu.rules")
        print("and running:")
        print("  sudo udevadm control --reload-rules && sudo udevadm trigger")


def cmd_test(args):
    """Run full automated self-test of the SDK."""
    print("=" * 60)
    print(" Running DigitalPersona U.are.U 4500 SDK Self-Test")
    print("=" * 60)

    # 1. Image generation and conversion
    print("[1/5] Testing synthetic image generation & processing...")
    mock = MockBackend()
    img = mock.generate_synthetic_fingerprint(seed=123)
    assert img.width == 290 and img.height == 384
    assert img.quality_score > 50
    pil = img.to_pil()
    assert pil.size == (290, 384)
    b64 = img.to_base64()
    img_restored = FingerprintImage.from_base64(b64)
    assert img_restored.width == 290
    print("      Image tests passed.")

    # 2. Template serialization
    print("[2/5] Testing template serialization & metadata...")
    tpl = FingerprintTemplate(
        data=b"SAMPLE_FINGERPRINT_MINUTIAE_DATA_12345",
        format_type="libfprint",
        username="alice",
        finger_name="right_index",
    )
    raw_bytes = tpl.to_bytes()
    restored_tpl = FingerprintTemplate.from_bytes(raw_bytes)
    assert restored_tpl.username == "alice"
    assert restored_tpl.finger_name == "right_index"
    assert restored_tpl.data == b"SAMPLE_FINGERPRINT_MINUTIAE_DATA_12345"
    print("      Template tests passed.")

    # 3. Minutiae matching
    print("[3/5] Testing biometric minutiae matcher...")
    from dp4500.matching import FingerprintMatcher
    matcher = FingerprintMatcher()
    m_list = matcher.extract_minutiae(img)
    assert len(m_list) > 0
    matched, score = matcher.match_minutiae(m_list, m_list)
    assert matched is True and score >= 0.9
    print(f"      Extracted {len(m_list)} minutiae. Self-match score: {score:.2f}")

    # 4. Mock device capture and enrollment
    print("[4/5] Testing simulated reader capture, enroll, verify...")
    with UareU4500(backend=MockBackend()) as reader:
        captured = reader.capture()
        assert captured.width == 290
        enrolled = reader.enroll(stages=3, username="test_user")
        assert enrolled.username == "test_user"
        v_res = reader.verify(enrolled)
        assert v_res.matched is True
    print("      Reader operations passed.")

    # 5. Hardware check
    print("[5/5] Checking connected physical hardware...")
    devs = ReaderManager.list_readers()
    if devs:
        print(f"      Detected {len(devs)} hardware reader(s): {devs[0].name}")
    else:
        print("      No hardware reader detected (Mock mode verified).")

    print("\n[OK] ALL TESTS PASSED SUCCESSFULLY!")


def main():
    parser = argparse.ArgumentParser(
        description="DigitalPersona U.are.U 4500 Fingerprint Reader CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # list
    subparsers.add_parser("list", help="List connected readers")

    # info
    p_info = subparsers.add_parser("info", help="Show hardware and environment diagnostics")
    p_info.add_argument("--mock", action="store_true", help="Inspect mock virtual reader")

    # capture
    p_cap = subparsers.add_parser("capture", help="Capture fingerprint image to file")
    p_cap.add_argument("-o", "--out", help="Output file path (default: fingerprint_<time>.png)")
    p_cap.add_argument("-f", "--format", default="PNG", choices=["PNG", "BMP", "JPEG", "RAW"], help="Image format")
    p_cap.add_argument("--mock", action="store_true", help="Use virtual mock reader")

    # enroll
    p_enr = subparsers.add_parser("enroll", help="Enroll a fingerprint into a template file")
    p_enr.add_argument("-u", "--user", default="user", help="User account name")
    p_enr.add_argument("-f", "--finger", default="right_index", help="Finger name (e.g. right_index)")
    p_enr.add_argument("-s", "--stages", type=int, default=5, help="Number of enrollment touches")
    p_enr.add_argument("-o", "--out", help="Output .fpt template file")
    p_enr.add_argument("--mock", action="store_true", help="Use virtual mock reader")

    # verify
    p_ver = subparsers.add_parser("verify", help="Verify finger against an enrolled template")
    p_ver.add_argument("-t", "--template", required=True, help="Path to .fpt template file")
    p_ver.add_argument("--mock", action="store_true", help="Use virtual mock reader")

    # identify
    p_id = subparsers.add_parser("identify", help="1:N search against a directory of templates")
    p_id.add_argument("-d", "--dir", required=True, help="Directory containing .fpt template files")
    p_id.add_argument("--mock", action="store_true", help="Use virtual mock reader")

    # setup-udev
    p_udev = subparsers.add_parser("setup-udev", help="Inspect and configure Linux udev USB permissions")
    p_udev.add_argument("--install", action="store_true", help="Attempt to install udev rule file directly")

    # test
    subparsers.add_parser("test", help="Run end-to-end SDK diagnostics and self-test")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(0)

    dispatch = {
        "list": cmd_list,
        "info": cmd_info,
        "capture": cmd_capture,
        "enroll": cmd_enroll,
        "verify": cmd_verify,
        "identify": cmd_identify,
        "setup-udev": cmd_setup_udev,
        "test": cmd_test,
    }

    try:
        dispatch[args.command](args)
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
        sys.exit(130)
    except Exception as e:
        print(f"\n[Error] {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

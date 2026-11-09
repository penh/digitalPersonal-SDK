#!/usr/bin/env python3
"""
Example 2: Interactive Enrollment & 1:1 Biometric Verification
Demonstrates multi-stage enrollment, template creation, saving to file,
and subsequent verification.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dp4500 import UareU4500, FingerprintTemplate, PermissionError
from dp4500.backends.mock import MockBackend

def main():
    use_mock = "--mock" in sys.argv
    backend = MockBackend() if use_mock else None

    print(f"DigitalPersona 4500 - Enroll & Verify Workflow ({'MOCK' if use_mock else 'HARDWARE'})")

    try:
        with UareU4500(backend=backend) as reader:
            print(f"Reader: {reader.name} ({reader.driver})")

            # -----------------------------------------------------------------
            # Step 1: Enroll new user (e.g. 5 touches for composite quality)
            # -----------------------------------------------------------------
            username = "alice"
            print(f"\n--- Starting Enrollment for '{username}' ---")

            def progress_callback(stage, total):
                print(f"  [+] Touch {stage}/{total} captured. Lift and replace finger...")

            template = reader.enroll(
                stages=5,
                on_stage_progress=progress_callback,
                username=username,
                finger_name="right_index",
            )

            # Save enrolled template to file
            template_filename = f"{username}.fpt"
            template.save(template_filename)
            print(f"[✓] Enrolled successfully! Saved template to '{template_filename}'")

            # -----------------------------------------------------------------
            # Step 2: 1:1 Verification against enrolled template
            # -----------------------------------------------------------------
            print(f"\n--- Starting Verification ---")
            print("Place your finger on the reader to authenticate...")

            # Load template from disk (or use in-memory instance)
            loaded_template = FingerprintTemplate.load(template_filename)
            result = reader.verify(loaded_template)

            if result.matched:
                print(f"[✓] AUTHENTICATION GRANTED! Welcome {loaded_template.username}!")
                print(f"    Confidence Score: {result.score:.2f}")
            else:
                print(f"[✗] ACCESS DENIED: Fingerprint does not match.")
                print(f"    Confidence Score: {result.score:.2f}")

    except PermissionError as e:
        print(f"\n[Permission Error] {e}")
    except Exception as e:
        print(f"\n[Error] {e}")
        print("Tip: Run with --mock flag to test in simulation mode: python3 02_enroll_and_verify.py --mock")

if __name__ == "__main__":
    main()

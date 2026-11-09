#!/usr/bin/env python3
"""
Example 1: Simplest Fingerprint Image Capture
Connects to the DigitalPersona 4500 reader, captures a single image,
and saves it as PNG and BMP.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dp4500 import UareU4500, ReaderManager, PermissionError

def main():
    print("DigitalPersona U.are.U 4500 - Simple Capture Example")

    try:
        # Connect to reader (context manager automatically handles open/close)
        with UareU4500() as reader:
            print(f"Connected to reader: {reader.name}")
            print("Please place your finger on the sensor...")

            # Wait for finger and acquire 500 DPI image
            img = reader.capture(wait_for_finger=True)

            print(f"Captured {img.width}x{img.height} image at {img.dpi} DPI!")
            print(f"Estimated image quality: {img.quality_score}%")

            # Save as PNG
            img.save("fingerprint.png", format="PNG")
            print("Saved image to 'fingerprint.png'")

            # Convert to PIL Image for further manipulation if desired
            pil_image = img.to_pil()
            print(f"PIL Image format: {pil_image.format or 'RAW'}, mode: {pil_image.mode}")

    except PermissionError as e:
        print(f"\n[Permission Error] {e}")
    except Exception as e:
        print(f"\n[Error] {e}")
        print("Note: To run in mock mode without physical hardware, pass backend=MockBackend():")
        print("  from dp4500.backends.mock import MockBackend")
        print("  with UareU4500(backend=MockBackend()) as reader: ...")

if __name__ == "__main__":
    main()

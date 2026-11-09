# dp4500: Python SDK for DigitalPersona (U.are.U) 4500 Fingerprint Reader

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Hardware: DigitalPersona 4500](https://img.shields.io/badge/Hardware-05ba%3A000a-green.svg)](https://www.hidglobal.com)

A production-grade Python SDK for the **DigitalPersona (U.are.U) 4500** optical USB fingerprint scanner (`05ba:000a`).

Designed for reliability, simplicity, and flexibility across environments. Operates out-of-the-box on Linux using native open-source drivers (`libfprint`), supports the official proprietary HID/DigitalPersona C SDK (`dpfpdd`/`dpfj`), and includes a built-in virtual mock backend for simulation and CI/CD testing without physical hardware.

---

## 🌟 Key Features

- **Multi-Backend Architecture**:
  - **`libfprint` Backend**: Native Linux integration using the kernel `uru4000` driver. No proprietary drivers needed.
  - **`official_sdk` Backend**: Direct ctypes binding to the official DigitalPersona C SDK (`dpfpdd.dll` / `libdpfpdd.so` and `dpfj.dll` / `libdpfj.so`).
  - **`mock` Backend**: Built-in virtual reader producing realistic 500 DPI synthetic fingerprints for unit testing and offline development.
- **Biometric Workflows**:
  - **Image Capture**: Acquire uncompressed 8-bit grayscale optical images (500 DPI).
  - **Image Processing**: Otsu thresholding, ridge enhancement, inversion, and Base64 export.
  - **Multi-Stage Enrollment**: High-quality composite templates (typically 5 touches) with real-time progress callbacks.
  - **1:1 Biometric Verification**: Verify live fingers against stored templates with match scoring.
  - **1:N Biometric Identification**: Fast identification across large galleries of enrolled templates.
- **Pure-Python Minutiae Matcher**:
  - Zhang-Suen ridge skeletonization.
  - Crossing Number (CN) extraction for ridge terminations and bifurcations.
  - Point-pattern alignment and spatial matching independent of vendor libraries.
- **Developer Experience**:
  - Pythonic context management (`with UareU4500() as reader: ...`).
  - Built-in CLI tool (`dp4500`).
  - Linux `udev` diagnostics and automated permissions configuration.

---

## 📦 Installation

```bash
# Clone and install in editable mode
cd /path/to/sdk
pip install -e .
```

### Dependencies

- Python >= 3.8
- `numpy >= 1.20.0`
- `pillow >= 9.0.0`

### Linux System Prerequisites (`libfprint`)

On Ubuntu / Debian:
```bash
sudo apt update
sudo apt install libfprint-2-2 libglib2.0-0
```

---

## ⚡ Quick Start

### 1. Simple Image Capture

```python
from dp4500 import UareU4500

with UareU4500() as reader:
    print(f"Connected to: {reader.name}")
    print("Touch the sensor...")

    # Acquire 500 DPI fingerprint image
    img = reader.capture(wait_for_finger=True)

    print(f"Captured {img.width}x{img.height} @ {img.dpi} DPI (Quality: {img.quality_score}%)")
    img.save("fingerprint.png")
```

### 2. Multi-Stage Enrollment & Verification (1:1)

```python
from dp4500 import UareU4500, FingerprintTemplate

with UareU4500() as reader:
    # 1. Enroll user with 5 touches
    def on_touch(stage, total):
        print(f"Scan {stage}/{total} completed. Lift and place finger again...")

    template = reader.enroll(
        stages=5,
        on_stage_progress=on_touch,
        username="alice",
        finger_name="right_index"
    )
    template.save("alice.fpt")
    print("Template saved to alice.fpt")

    # 2. Verify live finger against enrolled template
    ref_template = FingerprintTemplate.load("alice.fpt")
    result = reader.verify(ref_template)

    if result.matched:
        print(f"Verified! Match confidence: {result.score:.2f}")
    else:
        print("Fingerprint did not match.")
```

### 3. 1:N Biometric Identification

```python
from dp4500 import UareU4500, FingerprintTemplate

# Load candidate templates
templates = [
    FingerprintTemplate.load("alice.fpt"),
    FingerprintTemplate.load("bob.fpt"),
]

with UareU4500() as reader:
    print("Place finger to identify...")
    res = reader.identify(templates)

    if res.matched:
        print(f"Identified as: {res.template.username} (Score: {res.score:.2f})")
    else:
        print("User not recognized in database.")
```

---

## 🛠️ Linux Permissions & Udev Configuration

On Linux, accessing raw USB devices requires non-root user permissions.

### Automated Diagnostic
Run the built-in diagnostic tool:
```bash
dp4500 info
```

### Setup Udev Rule
Generate and install the permission rule:
```bash
sudo dp4500 setup-udev --install
```

Or manually create `/etc/udev/rules.d/99-digitalpersona-uareu.rules`:
```udev
SUBSYSTEM=="usb", ATTRS{idVendor}=="05ba", ATTRS{idProduct}=="000a", MODE="0666", GROUP="plugdev", TAG+="uaccess"
```

Then reload udev:
```bash
sudo udevadm control --reload-rules && sudo udevadm trigger
```

---

## 💻 Command Line Interface (CLI)

The package provides the `dp4500` command:

| Command | Description | Example |
|---|---|---|
| `dp4500 list` | List connected readers and available backends | `dp4500 list` |
| `dp4500 info` | Display USB node, driver, and permission report | `dp4500 info` |
| `dp4500 capture` | Capture fingerprint to an image file | `dp4500 capture -o scan.png` |
| `dp4500 enroll` | Interactively enroll a user into `.fpt` file | `dp4500 enroll -u alice -o alice.fpt` |
| `dp4500 verify` | Verify finger against a template file | `dp4500 verify -t alice.fpt` |
| `dp4500 identify` | 1:N search against a directory of templates | `dp4500 identify -d ./templates` |
| `dp4500 setup-udev` | Diagnose or install Linux USB udev rules | `sudo dp4500 setup-udev --install` |
| `dp4500 test` | Run complete end-to-end self-test | `dp4500 test` |

*Tip: Pass `--mock` to any command to test using simulated hardware!*

---

## 🪟 Compiling to Windows Executable (`.exe`)

You can compile the SDK into standalone Windows `.exe` binaries with zero Python installation required on the client machine.

### Method 1: One-Click Build Script (Recommended)
On your Windows machine, double-click:
```cmd
build_windows_exe.bat
```
*(Or in PowerShell: `.\build_windows_exe.ps1`)*

### Method 2: Manual PyInstaller Build
```cmd
pip install pyinstaller numpy pillow
pyinstaller --clean --noconfirm dp4500_server.spec
pyinstaller --clean --noconfirm dp4500_cli.spec
```

### Generated Executables
The build creates two portable executables in the `dist\` folder:
1. **`dist\dp4500_server.exe`**:
   - Standalone Biometric Web Console & REST API Server.
   - Automatically bundles the web UI (`web_client.html`) and JavaScript SDK (`dp4500-client.js`).
   - When double-clicked, starts on `http://127.0.0.1:8000` and automatically opens your default browser!
2. **`dist\dp4500.exe`**:
   - Standalone command-line biometric tool (`capture`, `enroll`, `verify`, `identify`).

### Windows Driver DLLs (`dpfpdd.dll` & `dpfj.dll`)
On Windows, the reader uses the official DigitalPersona U.are.U driver runtime. The builder automatically detects and bundles them from:
`C:\Program Files\DigitalPersona\U.are.U SDK\Windows\Lib\x64\`
*(If installed elsewhere, simply copy `dpfpdd.dll` and `dpfj.dll` into the project root before running the build script).*

---

## 🧪 Simulation / Offline Mock Mode

To develop, test in Docker, or run CI/CD workflows without physical hardware attached:

```python
from dp4500 import UareU4500
from dp4500.backends.mock import MockBackend

with UareU4500(backend=MockBackend()) as reader:
    img = reader.capture()
    print(f"Generated mock fingerprint: {img.size}")
```

---

## 📁 Repository Structure

```
dp4500/
├── __init__.py          # Top-level SDK exports
├── reader.py            # UareU4500 controller & context manager
├── manager.py           # Reader discovery & backend selection
├── image.py             # FingerprintImage (PIL, numpy, Otsu, base64)
├── template.py          # FingerprintTemplate (serialization, persistence)
├── matching.py          # Pure-Python minutiae extractor & matcher
├── cli.py               # Command-line interface
├── backends/
│   ├── base.py          # Abstract backend contract
│   ├── libfprint.py     # Native Linux ctypes driver (uru4000)
│   ├── official_sdk.py  # Proprietary HID/DP C SDK (dpfpdd / dpfj)
│   └── mock.py          # Synthetic virtual reader
└── utils/
    └── udev.py          # Linux permission & udev configuration
```

---

## 📄 License

MIT License. See [LICENSE](LICENSE) for details.

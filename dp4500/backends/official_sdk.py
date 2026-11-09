"""
Official DigitalPersona (Crossmatch / HID Global) U.are.U C SDK ctypes backend.
Supports:
1. One Touch for Windows SDK (DPFPApi.dll + dpfj.dll / dpHFtrEx.dll / dpHMatch.dll) with legacy usbdpfp driver.
2. Crossmatch U.are.U C SDK (dpfpdd.dll + dpfj.dll).
"""

from __future__ import annotations
import ctypes
from ctypes import wintypes
import io
import os
import sys
import time
import struct
import logging
from typing import List, Optional, Tuple, Callable, Any, Dict
from PIL import Image

from dp4500.backends.base import BaseBackend, DeviceInfo, MatchResult, IdentifyResult, LEDMode
from dp4500.image import FingerprintImage
from dp4500.template import FingerprintTemplate
from dp4500.exceptions import (
    DeviceNotFoundError,
    DeviceBusyError,
    PermissionError as DPPermissionError,
    CaptureError,
    EnrollmentError,
    VerificationError,
    IdentificationError,
    BackendNotAvailableError,
)

logger = logging.getLogger("dp4500.backends.official_sdk")

# Constants from dpfpdd.h (facility mask 0x05BA0000 on Windows)
DPFPDD_SUCCESS = 0
DPFPDD_E_FAILURE = 0x0B
DPFPDD_E_NO_DATA = 0x0C
DPFPDD_E_MORE_DATA = 0x0D
DPFPDD_E_INVALID_DEVICE = 0x15
DPFPDD_E_DEVICE_BUSY = 0x1E
DPFPDD_E_DEVICE_FAILURE = 0x1F

DPFPDD_QUALITY_GOOD = 0
DPFPDD_QUALITY_TIMED_OUT = 1
DPFPDD_QUALITY_CANCELED = 2
DPFPDD_QUALITY_NO_FINGER = 3

# Constants from dpfj.h
DPFJ_SUCCESS = 0
DPFJ_E_MORE_DATA = 0x0D
DPFJ_FMD_ANSI_378_2004 = 0x001B0001
DPFJ_FMD_ISO_19794_2_2005 = 0x01010001
DPFJ_FMD_DP_PRE_REG_FEATURES = 0
DPFJ_FMD_DP_REG_FEATURES = 1

# Window message constants for DPFPApi
WM_USER_NOTIFY = 0x0400 + 100
WN_COMPLETED = 0
WN_ERROR = 1
WN_DISCONNECT = 2
WN_RECONNECT = 3
WN_SAMPLE_QUALITY = 4
WN_FINGER_TOUCHED = 5
WN_FINGER_GONE = 6
WN_IMAGE_READY = 7
WN_OPERATION_STOPPED = 10

DP_SAMPLE_TYPE_IMAGE = 4
DP_PRIORITY_NORMAL = 2
DP_PRIORITY_LOW = 3


def _mask_code(code: int) -> int:
    """Mask out facility code (0x05BA0000) to obtain standard lower 16-bit status code."""
    if code is None:
        return 0
    return code & 0xFFFF


# Structures for dpfpdd (U.are.U SDK 3.x)
class DPFPDD_DEV_CAPS(ctypes.Structure):
    _fields_ = [
        ("size", ctypes.c_uint),
        ("can_capture_image", ctypes.c_int),
        ("can_stream_image", ctypes.c_int),
        ("can_extract_features", ctypes.c_int),
        ("can_match", ctypes.c_int),
        ("can_identify", ctypes.c_int),
        ("has_fingerprint_storage", ctypes.c_int),
        ("indicator_type", ctypes.c_uint),
        ("has_pwr_mgmt", ctypes.c_int),
        ("has_calibration", ctypes.c_int),
        ("piv_compliant", ctypes.c_int),
        ("resolution_cnt", ctypes.c_uint),
        ("resolutions", ctypes.c_uint * 1),
    ]


class DPFPDD_VER_INFO(ctypes.Structure):
    _fields_ = [
        ("major", ctypes.c_int),
        ("minor", ctypes.c_int),
        ("maintenance", ctypes.c_int),
    ]


class DPFPDD_HW_DESCR(ctypes.Structure):
    _fields_ = [
        ("vendor_name", ctypes.c_char * 128),
        ("product_name", ctypes.c_char * 128),
        ("serial_num", ctypes.c_char * 128),
    ]


class DPFPDD_HW_ID(ctypes.Structure):
    _fields_ = [
        ("vendor_id", ctypes.c_ushort),
        ("product_id", ctypes.c_ushort),
    ]


class DPFPDD_HW_VERSION(ctypes.Structure):
    _fields_ = [
        ("hw_ver", DPFPDD_VER_INFO),
        ("fw_ver", DPFPDD_VER_INFO),
        ("bcd_rev", ctypes.c_ushort),
    ]


class DPFPDD_DEV_INFO(ctypes.Structure):
    _fields_ = [
        ("size", ctypes.c_uint),
        ("name", ctypes.c_char * 1024),
        ("descr", DPFPDD_HW_DESCR),
        ("id", DPFPDD_HW_ID),
        ("ver", DPFPDD_HW_VERSION),
        ("modality", ctypes.c_uint),
        ("technology", ctypes.c_uint),
    ]


class DPFPDD_IMAGE_INFO(ctypes.Structure):
    _fields_ = [
        ("size", ctypes.c_uint),
        ("width", ctypes.c_uint),
        ("height", ctypes.c_uint),
        ("res", ctypes.c_uint),
        ("bpp", ctypes.c_uint),
    ]


class DPFPDD_CAPTURE_RESULT(ctypes.Structure):
    _fields_ = [
        ("size", ctypes.c_uint),
        ("success", ctypes.c_int),
        ("quality", ctypes.c_uint),
        ("score", ctypes.c_uint),
        ("info", DPFPDD_IMAGE_INFO),
    ]


class DPFPDD_CAPTURE_PARAM(ctypes.Structure):
    _fields_ = [
        ("size", ctypes.c_uint),
        ("image_fmt", ctypes.c_uint),
        ("image_proc", ctypes.c_uint),
        ("image_res", ctypes.c_uint),
    ]


# Structures for DPFPApi (One Touch for Windows SDK)
class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]

    def to_str(self) -> str:
        d4_1 = "".join(f"{b:02x}" for b in self.Data4[:2])
        d4_2 = "".join(f"{b:02x}" for b in self.Data4[2:])
        return f"{self.Data1:08x}-{self.Data2:04x}-{self.Data3:04x}-{d4_1}-{d4_2}"

    @classmethod
    def from_str(cls, s: str) -> GUID:
        clean = s.strip().strip("{}").replace("-", "")
        if len(clean) != 32:
            return cls()
        data1 = int(clean[0:8], 16)
        data2 = int(clean[8:12], 16)
        data3 = int(clean[12:16], 16)
        d4 = (ctypes.c_ubyte * 8)(*(int(clean[i:i+2], 16) for i in range(16, 32, 2)))
        return cls(data1, data2, data3, d4)


class DP_DEVICE_VERSION(ctypes.Structure):
    _fields_ = [
        ("uMajor", ctypes.c_ulong),
        ("uMinor", ctypes.c_ulong),
        ("uBuild", ctypes.c_ulong),
    ]


class DP_HW_INFO(ctypes.Structure):
    _fields_ = [
        ("uLanguageId", ctypes.c_uint),
        ("szVendor", ctypes.c_wchar * 128),
        ("szProduct", ctypes.c_wchar * 128),
        ("szSerialNb", ctypes.c_wchar * 128),
        ("HardwareRevision", DP_DEVICE_VERSION),
        ("FirmwareRevision", DP_DEVICE_VERSION),
    ]


class DP_DEVICE_INFO(ctypes.Structure):
    _fields_ = [
        ("DeviceUid", GUID),
        ("eUidType", ctypes.c_int),
        ("eDeviceModality", ctypes.c_int),
        ("eDeviceTech", ctypes.c_int),
        ("HwInfo", DP_HW_INFO),
    ]


class DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD if sys.platform.startswith("win") else ctypes.c_uint32),
        ("pbData", ctypes.c_void_p),
    ]


# Global capture message dispatcher registry for Windows message loops
_active_window_captures: Dict[int, Dict[str, Any]] = {}
_wndclass_registered = False


def _init_windows_capture_subsystem():
    global _wndclass_registered
    if not sys.platform.startswith("win") or _wndclass_registered:
        return

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_int64, ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint64, ctypes.c_int64)
    user32.DefWindowProcW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint64, ctypes.c_int64]
    user32.DefWindowProcW.restype = ctypes.c_int64

    user32.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT]
    user32.PeekMessageW.restype = wintypes.BOOL

    user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
    user32.TranslateMessage.restype = wintypes.BOOL

    user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
    user32.DispatchMessageW.restype = ctypes.c_int64

    user32.CreateWindowExW.argtypes = [
        wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID
    ]
    user32.CreateWindowExW.restype = wintypes.HWND

    def _global_wnd_proc(hwnd, msg, wparam, lparam):
        if msg == WM_USER_NOTIFY:
            container = _active_window_captures.get(hwnd)
            if container is None and _active_window_captures:
                container = next(iter(_active_window_captures.values()))
            if container is not None:
                if wparam == WN_COMPLETED and lparam:
                    try:
                        p_sample = ctypes.c_void_p(lparam & 0xFFFFFFFFFFFFFFFF)
                        dpfpapi = container.get("api")
                        if dpfpapi:
                            size = ctypes.c_size_t(0)
                            dpfpapi.DPFPConvertSampleToBitmap(p_sample, None, ctypes.byref(size))
                            if size.value > 0:
                                buf = (ctypes.c_ubyte * size.value)()
                                dpfpapi.DPFPConvertSampleToBitmap(p_sample, buf, ctypes.byref(size))
                                container["dib"] = bytes(buf)
                                logger.info(f"Captured fingerprint sample converted to {size.value} byte bitmap.")
                    except Exception as ex:
                        logger.exception(f"Error converting captured sample: {ex}")
                        container["error"] = ex
                elif wparam == WN_FINGER_TOUCHED:
                    logger.info("Physical finger touch detected on sensor prism.")
                elif wparam == WN_IMAGE_READY:
                    logger.info("Sensor optical image ready.")
                elif wparam == WN_ERROR:
                    logger.error(f"Acquisition error received: 0x{lparam & 0xFFFFFFFF:X}")
                    container["error"] = lparam
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    # Keep a reference to prevent garbage collection
    _init_windows_capture_subsystem.proc_ref = WNDPROC(_global_wnd_proc)

    class WNDCLASSEXW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.UINT),
            ("style", wintypes.UINT),
            ("lpfnWndProc", WNDPROC),
            ("cbClsExtra", ctypes.c_int),
            ("cbWndExtra", ctypes.c_int),
            ("hInstance", ctypes.c_void_p),
            ("hIcon", ctypes.c_void_p),
            ("hCursor", ctypes.c_void_p),
            ("hbrBackground", ctypes.c_void_p),
            ("lpszMenuName", wintypes.LPCWSTR),
            ("lpszClassName", wintypes.LPCWSTR),
            ("hIconSm", ctypes.c_void_p),
        ]

    wc = WNDCLASSEXW()
    wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
    wc.lpfnWndProc = _init_windows_capture_subsystem.proc_ref
    wc.lpszClassName = "DPFP_Capture_Window"
    wc.hInstance = kernel32.GetModuleHandleW(None)
    user32.RegisterClassExW(ctypes.byref(wc))
    _wndclass_registered = True


def _dib_to_fingerprint_image(dib_bytes: bytes) -> FingerprintImage:
    """Parse raw DIB bitmap memory block into FingerprintImage."""
    bi_size, bi_width, bi_height, bi_planes, bi_bit_count, bi_compression, bi_size_image, bi_x_pels, bi_y_pels, bi_clr_used, bi_clr_important = struct.unpack_from("<IiiHHIIiiII", dib_bytes, 0)
    if bi_clr_used == 0 and bi_bit_count <= 8:
        num_colors = 1 << bi_bit_count
    else:
        num_colors = bi_clr_used
    offset_bits = 14 + bi_size + (num_colors * 4)
    file_size = 14 + len(dib_bytes)
    file_header = struct.pack("<2sIHHI", b"BM", file_size, 0, 0, offset_bits)
    full_bmp = file_header + dib_bytes
    pil_img = Image.open(io.BytesIO(full_bmp)).convert("L")
    return FingerprintImage(
        data=pil_img.tobytes(),
        width=pil_img.width,
        height=pil_img.height,
        dpi=500,
    )


class OfficialSdkBackend(BaseBackend):
    """
    ctypes backend for official proprietary DigitalPersona / HID U.are.U SDKs.
    Supports Windows One Touch for Windows (DPFPApi.dll), U.are.U 3.x (dpfpdd.dll), and Linux.
    """

    _dpfpdd = None
    _dpfpapi = None
    _dpfj = None
    _init_attempted = False

    @classmethod
    def _find_and_load(cls):
        if cls._init_attempted:
            return cls.is_available()
        cls._init_attempted = True

        custom_path = os.environ.get("DP_SDK_PATH")
        search_paths = []
        if custom_path:
            search_paths.append(custom_path)

        if sys.platform.startswith("win"):
            exe_dir = os.path.dirname(sys.executable)
            meipass = getattr(sys, "_MEIPASS", "")
            prog_files = os.environ.get("PROGRAMFILES", r"C:\Program Files")
            prog_files_x86 = os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
            windir = os.environ.get("WINDIR", r"C:\Windows")

            search_paths.extend([
                os.getcwd(),
                exe_dir,
                meipass,
                os.path.join(windir, "System32"),
                os.path.join(prog_files, r"DigitalPersona\Bin"),
                os.path.join(prog_files, r"DigitalPersona\One Touch SDK\C-C++\Lib\x64"),
                os.path.join(prog_files, r"DigitalPersona\U.are.U SDK\Windows\Lib\x64"),
                os.path.join(prog_files, r"Crossmatch\U.are.U SDK\Windows\Lib\x64"),
                os.path.join(prog_files_x86, r"DigitalPersona\Bin"),
                os.path.join(windir, "SysWOW64"),
            ])
            for p in search_paths:
                if p and os.path.isdir(p) and hasattr(os, "add_dll_directory"):
                    try:
                        os.add_dll_directory(p)
                    except Exception:
                        pass

            # 1. Probe DPFPApi.dll (One Touch for Windows legacy driver API)
            for p in search_paths:
                full = os.path.join(p, "DPFPApi.dll")
                if os.path.exists(full):
                    try:
                        cls._dpfpapi = ctypes.CDLL(full)
                        break
                    except OSError:
                        pass
            if not cls._dpfpapi:
                try:
                    cls._dpfpapi = ctypes.CDLL("DPFPApi.dll")
                except OSError:
                    pass

            # 2. Probe dpfpdd.dll (U.are.U SDK 3.x)
            for p in search_paths:
                full = os.path.join(p, "dpfpdd.dll")
                if os.path.exists(full):
                    try:
                        cls._dpfpdd = ctypes.CDLL(full)
                        break
                    except OSError:
                        pass
            if not cls._dpfpdd:
                try:
                    cls._dpfpdd = ctypes.CDLL("dpfpdd.dll")
                except OSError:
                    pass

            # 3. Probe dpfj.dll (Feature extraction & biometric matching engine)
            for p in search_paths:
                full = os.path.join(p, "dpfj.dll")
                if os.path.exists(full):
                    try:
                        cls._dpfj = ctypes.CDLL(full)
                        break
                    except OSError:
                        pass
            if not cls._dpfj:
                try:
                    cls._dpfj = ctypes.CDLL("dpfj.dll")
                except OSError:
                    pass

        else:
            # Linux search paths
            search_paths.extend([
                "/opt/DigitalPersona/UareUSDK/Linux/lib/x64",
                "/opt/DigitalPersona/UareUSDK/Linux/lib",
                "/usr/local/lib",
                "/usr/lib",
            ])
            for name in ["libdpfpdd.so", "libdpfpdd.so.1"]:
                try:
                    cls._dpfpdd = ctypes.CDLL(name)
                    break
                except OSError:
                    pass
            for name in ["libdpfj.so", "libdpfj.so.1"]:
                try:
                    cls._dpfj = ctypes.CDLL(name)
                    break
                except OSError:
                    pass

        # Configure ctypes prototypes for DPFPApi if loaded
        if cls._dpfpapi:
            try:
                cls._dpfpapi.DPFPInit.restype = ctypes.c_long
                cls._dpfpapi.DPFPTerm.restype = None
                cls._dpfpapi.DPFPEnumerateDevices.argtypes = [ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.POINTER(GUID))]
                cls._dpfpapi.DPFPEnumerateDevices.restype = ctypes.c_long
                cls._dpfpapi.DPFPGetDeviceInfo.argtypes = [ctypes.POINTER(GUID), ctypes.POINTER(DP_DEVICE_INFO)]
                cls._dpfpapi.DPFPGetDeviceInfo.restype = ctypes.c_long
                cls._dpfpapi.DPFPCreateAcquisition.argtypes = [ctypes.c_uint, ctypes.POINTER(GUID), ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint, ctypes.POINTER(ctypes.c_ulong)]
                cls._dpfpapi.DPFPCreateAcquisition.restype = ctypes.c_long
                cls._dpfpapi.DPFPStartAcquisition.argtypes = [ctypes.c_ulong]
                cls._dpfpapi.DPFPStartAcquisition.restype = ctypes.c_long
                cls._dpfpapi.DPFPStopAcquisition.argtypes = [ctypes.c_ulong]
                cls._dpfpapi.DPFPStopAcquisition.restype = ctypes.c_long
                cls._dpfpapi.DPFPDestroyAcquisition.argtypes = [ctypes.c_ulong]
                cls._dpfpapi.DPFPDestroyAcquisition.restype = ctypes.c_long
                cls._dpfpapi.DPFPConvertSampleToBitmap.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_size_t)]
                cls._dpfpapi.DPFPConvertSampleToBitmap.restype = ctypes.c_long
                cls._dpfpapi.DPFPBufferFree.argtypes = [ctypes.c_void_p]
                cls._dpfpapi.DPFPBufferFree.restype = None
            except Exception as e:
                logger.warning(f"Error configuring DPFPApi prototypes: {e}")

        # Configure ctypes prototypes for dpfj if loaded
        if cls._dpfj:
            try:
                cls._dpfj.dpfj_create_fmd_from_raw.argtypes = [
                    ctypes.c_char_p,
                    ctypes.c_uint,
                    ctypes.c_uint,
                    ctypes.c_uint,
                    ctypes.c_uint,
                    ctypes.c_uint,
                    ctypes.c_uint,
                    ctypes.c_uint,
                    ctypes.c_char_p,
                    ctypes.POINTER(ctypes.c_uint),
                ]
                cls._dpfj.dpfj_create_fmd_from_raw.restype = ctypes.c_int
                cls._dpfj.dpfj_compare.argtypes = [
                    ctypes.c_uint,
                    ctypes.c_char_p,
                    ctypes.c_uint,
                    ctypes.c_uint,
                    ctypes.c_uint,
                    ctypes.c_char_p,
                    ctypes.c_uint,
                    ctypes.c_uint,
                    ctypes.POINTER(ctypes.c_uint),
                ]
                cls._dpfj.dpfj_compare.restype = ctypes.c_int
                cls._dpfj.dpfj_start_enrollment.argtypes = [ctypes.c_uint]
                cls._dpfj.dpfj_start_enrollment.restype = ctypes.c_int
                cls._dpfj.dpfj_add_to_enrollment.argtypes = [ctypes.c_uint, ctypes.c_char_p, ctypes.c_uint, ctypes.c_uint]
                cls._dpfj.dpfj_add_to_enrollment.restype = ctypes.c_int
                cls._dpfj.dpfj_create_enrollment_fmd.argtypes = [ctypes.c_char_p, ctypes.POINTER(ctypes.c_uint)]
                cls._dpfj.dpfj_create_enrollment_fmd.restype = ctypes.c_int
                cls._dpfj.dpfj_finish_enrollment.restype = ctypes.c_int
            except Exception as e:
                logger.warning(f"Error configuring dpfj prototypes: {e}")

        return cls.is_available()

    @classmethod
    def is_available(cls) -> bool:
        if not cls._init_attempted:
            cls._find_and_load()
        # Either DPFPApi or dpfpdd must be available, plus dpfj (or standalone)
        has_capture = cls._dpfpapi is not None or cls._dpfpdd is not None
        return has_capture

    @classmethod
    def backend_name(cls) -> str:
        return "official_sdk"

    def __init__(self):
        if not self._find_and_load():
            raise BackendNotAvailableError(
                "Official DigitalPersona SDK libraries (DPFPApi.dll or dpfpdd.dll) could not be located. "
                "Ensure the DigitalPersona driver and SDK are installed or set DP_SDK_PATH."
            )
        self._dpfpapi_initialized = False
        self._dpfpdd_initialized = False

        # Initialize dpfpdd first (direct driver access, does not require Windows focus or RPC services)
        if self._dpfpdd:
            res = self._dpfpdd.dpfpdd_init()
            if _mask_code(res) == DPFPDD_SUCCESS:
                self._dpfpdd_initialized = True

        # Fallback to DPFPApi if dpfpdd failed
        if self._dpfpapi and not self._dpfpdd_initialized:
            res = self._dpfpapi.DPFPInit()
            # S_OK (0) or S_FALSE (1) indicates success
            if res in (0, 1):
                self._dpfpapi_initialized = True
                _init_windows_capture_subsystem()

        if not self._dpfpapi_initialized and not self._dpfpdd_initialized:
            raise BackendNotAvailableError("Failed to initialize any DigitalPersona capture interface.")

    def __del__(self):
        if self._dpfpdd_initialized and self._dpfpdd:
            try:
                self._dpfpdd.dpfpdd_exit()
            except Exception:
                pass
        if self._dpfpapi_initialized and self._dpfpapi:
            try:
                self._dpfpapi.DPFPTerm()
            except Exception:
                pass

    def list_devices(self) -> List[DeviceInfo]:
        results: List[DeviceInfo] = []

        # 1. Try dpfpdd first (direct driver access, exclusive priority, no window focus required)
        if self._dpfpdd:
            if not self._dpfpdd_initialized:
                res_init = self._dpfpdd.dpfpdd_init()
                if _mask_code(res_init) == DPFPDD_SUCCESS:
                    self._dpfpdd_initialized = True

            if self._dpfpdd_initialized:
                dev_cnt = ctypes.c_uint(0)
                res = self._dpfpdd.dpfpdd_query_devices(ctypes.byref(dev_cnt), None)
                if _mask_code(res) in (DPFPDD_SUCCESS, DPFPDD_E_MORE_DATA) and dev_cnt.value > 0:
                    dev_array = (DPFPDD_DEV_INFO * dev_cnt.value)()
                    for d in dev_array:
                        d.size = ctypes.sizeof(DPFPDD_DEV_INFO)
                    res = self._dpfpdd.dpfpdd_query_devices(ctypes.byref(dev_cnt), dev_array)
                    if _mask_code(res) == DPFPDD_SUCCESS:
                        for i in range(dev_cnt.value):
                            d = dev_array[i]
                            name = d.name.decode("utf-8", errors="ignore")
                            ser = d.descr.serial_num.decode("utf-8", errors="ignore")
                            fw = f"{d.ver.fw_ver.major}.{d.ver.fw_ver.minor}"
                            results.append(
                                DeviceInfo(
                                    device_id=name,
                                    name=f"DigitalPersona 4500 ({ser})" if ser else "DigitalPersona 4500",
                                    driver="dpfpdd",
                                    vendor_id=d.id.vendor_id if d.id.vendor_id else 0x05BA,
                                    product_id=d.id.product_id if d.id.product_id else 0x000A,
                                    serial_number=ser,
                                    firmware_version=fw,
                                )
                            )
                if results:
                    return results

        # 2. Try DPFPApi fallback (standard for One Touch for Windows & legacy driver)
        if self._dpfpapi_initialized and self._dpfpapi:
            p_guids = ctypes.POINTER(GUID)()
            cnt = ctypes.c_ulong(0)
            res = self._dpfpapi.DPFPEnumerateDevices(ctypes.byref(cnt), ctypes.byref(p_guids))
            if res == 0 and cnt.value > 0 and p_guids:
                for i in range(cnt.value):
                    g = p_guids[i]
                    guid_str = g.to_str()
                    dev_info = DP_DEVICE_INFO()
                    res_info = self._dpfpapi.DPFPGetDeviceInfo(ctypes.byref(g), ctypes.byref(dev_info))
                    prod = dev_info.HwInfo.szProduct if res_info == 0 and dev_info.HwInfo.szProduct else "DigitalPersona 4500"
                    serial = dev_info.HwInfo.szSerialNb if res_info == 0 and dev_info.HwInfo.szSerialNb else guid_str
                    fw_ver = f"{dev_info.HwInfo.FirmwareRevision.uMajor}.{dev_info.HwInfo.FirmwareRevision.uMinor}.{dev_info.HwInfo.FirmwareRevision.uBuild}"
                    results.append(
                        DeviceInfo(
                            device_id=guid_str,
                            name=f"{prod} ({serial})",
                            driver="DPFPApi / usbdpfp",
                            vendor_id=0x05BA,
                            product_id=0x000A,
                            serial_number=serial,
                            firmware_version=fw_ver,
                        )
                    )
                self._dpfpapi.DPFPBufferFree(p_guids)
                if results:
                    return results

        return results

    def open_device(self, device_id: str) -> Any:
        if self._dpfpdd_initialized and self._dpfpdd:
            handle = ctypes.c_void_p(0)
            c_name = ctypes.c_char_p(device_id.encode("utf-8"))
            # Open with EXCLUSIVE priority (4) on Windows so capture works without window focus
            DPFPDD_PRIORITY_EXCLUSIVE = 4
            res = self._dpfpdd.dpfpdd_open_ext(c_name, DPFPDD_PRIORITY_EXCLUSIVE, ctypes.byref(handle))
            if _mask_code(res) != DPFPDD_SUCCESS:
                res = self._dpfpdd.dpfpdd_open(c_name, ctypes.byref(handle))

            masked = _mask_code(res)
            if masked != DPFPDD_SUCCESS:
                if masked == DPFPDD_E_DEVICE_BUSY:
                    raise DeviceBusyError(f"Device {device_id} is busy or claimed by another application.")
                raise DeviceNotFoundError(f"Failed to open device {device_id} (error 0x{res:X})")
            return {
                "engine": "dpfpdd",
                "device_id": device_id,
                "handle": handle,
            }

        if self._dpfpapi_initialized and self._dpfpapi:
            # Handle object wraps device GUID and engine type
            return {
                "engine": "dpfpapi",
                "device_id": device_id,
                "guid": GUID.from_str(device_id),
            }

        raise DeviceNotFoundError(f"No active backend available to open device {device_id}")

    def close_device(self, handle: Any) -> None:
        if isinstance(handle, dict):
            if handle.get("engine") == "dpfpdd" and handle.get("handle") and self._dpfpdd:
                self._dpfpdd.dpfpdd_close(handle["handle"])

    def capture_image(
        self,
        handle: Any,
        wait_for_finger: bool = True,
        timeout_ms: Optional[int] = None,
    ) -> FingerprintImage:
        timeout = timeout_ms if timeout_ms is not None else 10000

        # Branch 1: DPFPApi capture on Windows
        if isinstance(handle, dict) and handle.get("engine") == "dpfpapi":
            ole32 = ctypes.windll.ole32
            ole32.CoInitialize(None)

            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32

            hwnd = user32.CreateWindowExW(0, "DPFP_Capture_Window", "DPCapture", 0, 0, 0, 0, 0, 0, 0, kernel32.GetModuleHandleW(None), 0)
            if not hwnd:
                ole32.CoUninitialize()
                raise CaptureError("Failed to create capture listener window.")

            container = {"dib": None, "error": None, "api": self._dpfpapi}
            _active_window_captures[hwnd] = container

            h_op = ctypes.c_ulong(0)
            guid_obj = handle.get("guid", GUID())
            guid_null = GUID()

            # Prefer DP_PRIORITY_LOW (3) so background server/daemon receives touch events without needing foreground focus.
            # Fall back to DP_PRIORITY_NORMAL (2) if needed.
            res = self._dpfpapi.DPFPCreateAcquisition(DP_PRIORITY_LOW, ctypes.byref(guid_null), DP_SAMPLE_TYPE_IMAGE, hwnd, WM_USER_NOTIFY, ctypes.byref(h_op))
            if res != 0 and guid_obj:
                res = self._dpfpapi.DPFPCreateAcquisition(DP_PRIORITY_LOW, ctypes.byref(guid_obj), DP_SAMPLE_TYPE_IMAGE, hwnd, WM_USER_NOTIFY, ctypes.byref(h_op))
            if res != 0:
                res = self._dpfpapi.DPFPCreateAcquisition(DP_PRIORITY_NORMAL, ctypes.byref(guid_null), DP_SAMPLE_TYPE_IMAGE, hwnd, WM_USER_NOTIFY, ctypes.byref(h_op))

            if res != 0 or h_op.value == 0:
                user32.DestroyWindow(hwnd)
                _active_window_captures.pop(hwnd, None)
                ole32.CoUninitialize()
                raise CaptureError(f"DPFPCreateAcquisition failed with error 0x{res & 0xFFFFFFFF:X}")

            res_start = self._dpfpapi.DPFPStartAcquisition(h_op)
            if res_start != 0:
                self._dpfpapi.DPFPDestroyAcquisition(h_op)
                user32.DestroyWindow(hwnd)
                _active_window_captures.pop(hwnd, None)
                ole32.CoUninitialize()
                raise CaptureError(f"DPFPStartAcquisition failed with error 0x{res_start & 0xFFFFFFFF:X}")

            msg = wintypes.MSG()
            start_t = time.time()
            deadline = start_t + (timeout / 1000.0)

            try:
                while time.time() < deadline and container["dib"] is None and container["error"] is None:
                    while user32.PeekMessageW(ctypes.byref(msg), 0, 0, 0, 1):
                        user32.TranslateMessage(ctypes.byref(msg))
                        user32.DispatchMessageW(ctypes.byref(msg))
                    if container["dib"] is not None:
                        break
                    time.sleep(0.01)
            finally:
                try:
                    self._dpfpapi.DPFPStopAcquisition(h_op)
                    self._dpfpapi.DPFPDestroyAcquisition(h_op)
                except Exception:
                    pass
                user32.DestroyWindow(hwnd)
                _active_window_captures.pop(hwnd, None)
                ole32.CoUninitialize()

            if container["dib"] is not None:
                return _dib_to_fingerprint_image(container["dib"])

            if container["error"] is not None:
                raise CaptureError(f"Acquisition error occurred: 0x{container['error'] & 0xFFFFFFFF:X}")

            raise CaptureError("Capture timed out waiting for finger.")

        # Branch 2: dpfpdd capture (U.are.U 3.x)
        raw_h = handle.get("handle") if isinstance(handle, dict) else handle
        param = DPFPDD_CAPTURE_PARAM()
        param.size = ctypes.sizeof(DPFPDD_CAPTURE_PARAM)
        param.image_fmt = 0  # Raw PIXMAP (DPFPDD_IMG_FMT_PIXEL_BUFFER)
        param.image_proc = 0  # Default processing (DPFPDD_IMG_PROC_DEFAULT)
        param.image_res = 500  # 500 DPI

        cap_res = DPFPDD_CAPTURE_RESULT()
        cap_res.size = ctypes.sizeof(DPFPDD_CAPTURE_RESULT)

        # Query required image buffer size using timeout=0 and NULL buffer
        img_size = ctypes.c_uint(0)
        self._dpfpdd.dpfpdd_capture(raw_h, ctypes.byref(param), 0, ctypes.byref(cap_res), ctypes.byref(img_size), None)

        if img_size.value == 0:
            img_size.value = 200000

        buf = (ctypes.c_uint8 * img_size.value)()
        # Blocking synchronous capture waiting for physical finger placement
        res = self._dpfpdd.dpfpdd_capture(raw_h, ctypes.byref(param), timeout, ctypes.byref(cap_res), ctypes.byref(img_size), buf)

        if _mask_code(res) != DPFPDD_SUCCESS or not cap_res.success:
            if cap_res.quality == DPFPDD_QUALITY_TIMED_OUT:
                raise CaptureError("Capture timed out waiting for finger.")
            raise CaptureError(f"Image capture failed (res=0x{res:X}, quality={cap_res.quality})")

        w = cap_res.info.width
        h = cap_res.info.height
        dpi = cap_res.info.res if cap_res.info.res > 0 else 500

        # In DPFPDD_IMG_FMT_PIXEL_BUFFER, buf contains raw pixel bytes directly
        if w > 0 and h > 0:
            pixel_bytes = bytes(buf[: w * h])
        else:
            pixel_bytes = bytes(buf[: img_size.value])

        return FingerprintImage(
            data=pixel_bytes,
            width=w,
            height=h,
            dpi=dpi,
        )

    def enroll(
        self,
        handle: Any,
        stages: int = 5,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        timeout_ms: Optional[int] = None,
    ) -> FingerprintTemplate:
        if not self._dpfj:
            raise EnrollmentError("Biometric engine library (dpfj) is not available.")

        # Start enrollment in dpfj
        res = self._dpfj.dpfj_start_enrollment(DPFJ_FMD_ANSI_378_2004)
        if _mask_code(res) != DPFJ_SUCCESS:
            raise EnrollmentError(f"dpfj_start_enrollment failed: 0x{res:X}")

        for s in range(stages):
            if progress_callback:
                progress_callback(s, stages)

            img = self.capture_image(handle, wait_for_finger=True, timeout_ms=timeout_ms)

            # Create pre-reg FMD from image
            fmd_size = ctypes.c_uint(2048)
            fmd_buf = ctypes.create_string_buffer(2048)
            res = self._dpfj.dpfj_create_fmd_from_raw(
                img.data,
                len(img.data),
                img.width,
                img.height,
                img.dpi,
                0,  # finger position
                0,  # cbeff_id
                DPFJ_FMD_ANSI_378_2004,
                fmd_buf,
                ctypes.byref(fmd_size),
            )
            if _mask_code(res) != DPFJ_SUCCESS:
                raise EnrollmentError(f"Failed to extract features from scan {s+1}: 0x{res:X}")

            # Add to enrollment
            res = self._dpfj.dpfj_add_to_enrollment(DPFJ_FMD_ANSI_378_2004, fmd_buf, fmd_size.value, 0)
            masked = _mask_code(res)
            if masked == DPFJ_SUCCESS:
                # Enrollment is ready
                break
            elif masked == DPFJ_E_MORE_DATA:
                continue
            else:
                raise EnrollmentError(f"dpfj_add_to_enrollment failed: 0x{res:X}")

        # Create master enrollment FMD
        master_size = ctypes.c_uint(4096)
        master_buf = ctypes.create_string_buffer(4096)
        res = self._dpfj.dpfj_create_enrollment_fmd(master_buf, ctypes.byref(master_size))
        try:
            self._dpfj.dpfj_finish_enrollment()
        except Exception:
            pass

        if _mask_code(res) != DPFJ_SUCCESS:
            raise EnrollmentError(f"Failed to generate final enrollment template: 0x{res:X}")

        if progress_callback:
            progress_callback(stages, stages)

        return FingerprintTemplate(
            data=bytes(master_buf.raw[: master_size.value]),
            format_type="ansi_378",
        )

    def verify(
        self,
        handle: Any,
        template: FingerprintTemplate,
        timeout_ms: Optional[int] = None,
    ) -> MatchResult:
        if not self._dpfj:
            raise VerificationError("Biometric engine library (dpfj) is not available.")

        img = self.capture_image(handle, wait_for_finger=True, timeout_ms=timeout_ms)

        fmd_size = ctypes.c_uint(2048)
        fmd_buf = ctypes.create_string_buffer(2048)
        res = self._dpfj.dpfj_create_fmd_from_raw(
            img.data,
            len(img.data),
            img.width,
            img.height,
            img.dpi,
            0,
            0,
            DPFJ_FMD_ANSI_378_2004,
            fmd_buf,
            ctypes.byref(fmd_size),
        )
        if _mask_code(res) != DPFJ_SUCCESS:
            raise VerificationError(f"Feature extraction failed: 0x{res:X}")

        score = ctypes.c_uint(0)
        res = self._dpfj.dpfj_compare(
            DPFJ_FMD_ANSI_378_2004,
            fmd_buf,
            fmd_size.value,
            0,
            DPFJ_FMD_ANSI_378_2004,
            template.data,
            len(template.data),
            0,
            ctypes.byref(score),
        )
        if _mask_code(res) != DPFJ_SUCCESS:
            raise VerificationError(f"dpfj_compare failed: 0x{res:X}")

        # In DPFJ, dissimilarity score < 21474 (FAR 0.001%) is a match
        is_match = score.value < 21474
        norm_score = max(0.0, 1.0 - (score.value / 214740.0))
        return MatchResult(matched=is_match, score=norm_score)

    def identify(
        self,
        handle: Any,
        templates: List[FingerprintTemplate],
        timeout_ms: Optional[int] = None,
    ) -> IdentifyResult:
        if not self._dpfj:
            raise IdentificationError("Biometric engine library (dpfj) is not available.")
        if not templates:
            return IdentifyResult(matched=False, index=None, template=None, score=0.0)

        # 1. Capture once
        img = self.capture_image(handle, wait_for_finger=True, timeout_ms=timeout_ms)

        # 2. Extract verification feature set once
        fmd_size = ctypes.c_uint(2048)
        fmd_buf = ctypes.create_string_buffer(2048)
        res = self._dpfj.dpfj_create_fmd_from_raw(
            img.data,
            len(img.data),
            img.width,
            img.height,
            img.dpi,
            0,
            0,
            DPFJ_FMD_ANSI_378_2004,
            fmd_buf,
            ctypes.byref(fmd_size),
        )
        if _mask_code(res) != DPFJ_SUCCESS:
            raise IdentificationError(f"Feature extraction failed: 0x{res:X}")

        # 3. Match against all templates
        best_match = None
        best_score = 0.0
        best_idx = None

        for idx, tpl in enumerate(templates):
            score = ctypes.c_uint(0)
            res = self._dpfj.dpfj_compare(
                DPFJ_FMD_ANSI_378_2004,
                fmd_buf,
                fmd_size.value,
                0,
                DPFJ_FMD_ANSI_378_2004,
                tpl.data,
                len(tpl.data),
                0,
                ctypes.byref(score),
            )
            if _mask_code(res) == DPFJ_SUCCESS:
                is_match = score.value < 21474
                norm_score = max(0.0, 1.0 - (score.value / 214740.0))
                if is_match and norm_score > best_score:
                    best_match = tpl
                    best_score = norm_score
                    best_idx = idx

        if best_match is not None:
            return IdentifyResult(matched=True, index=best_idx, template=best_match, score=best_score)
        return IdentifyResult(matched=False, index=None, template=None, score=0.0)

    def set_led(self, handle: Any, mode: LEDMode) -> bool:
        if isinstance(handle, dict) and handle.get("engine") == "dpfpdd" and self._dpfpdd:
            raw_h = handle.get("handle")
            if raw_h:
                try:
                    # DPFPDD_LED_MAIN = 0x01
                    # DPFPDD_LED_AUTO = 1, DPFPDD_LED_CLIENT = 2, DPFPDD_LED_CLIENT_BLINK = 4
                    # DPFPDD_LED_CMD_OFF = 0, DPFPDD_LED_CMD_ON = 1
                    if mode == LEDMode.ON:
                        self._dpfpdd.dpfpdd_led_config(raw_h, 1, 2, None)
                        self._dpfpdd.dpfpdd_led_ctrl(raw_h, 1, 1)
                    elif mode == LEDMode.OFF:
                        self._dpfpdd.dpfpdd_led_config(raw_h, 1, 2, None)
                        self._dpfpdd.dpfpdd_led_ctrl(raw_h, 1, 0)
                    elif mode == LEDMode.BLINK:
                        self._dpfpdd.dpfpdd_led_config(raw_h, 1, 4, None)
                        self._dpfpdd.dpfpdd_led_ctrl(raw_h, 1, 500)
                    else:
                        self._dpfpdd.dpfpdd_led_config(raw_h, 1, 1, None)
                    return True
                except Exception:
                    pass
        return True

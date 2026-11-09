"""
Official DigitalPersona (Crossmatch / HID Global) U.are.U C SDK ctypes backend.
Interfaces with dpfpdd (capture) and dpfj (biometric engine) dynamic libraries.
"""

from __future__ import annotations
import ctypes
import os
import sys
import logging
from typing import List, Optional, Tuple, Callable, Any

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

# Constants from dpfpdd.h
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
DPFJ_FMD_ANSI_378_2004 = 0x001B0001
DPFJ_FMD_ISO_19794_2_2005 = 0x01010001
DPFJ_FMD_DP_PRE_REG_FEATURES = 0
DPFJ_FMD_DP_REG_FEATURES = 1


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


class DPFPDD_DEV_INFO(ctypes.Structure):
    _fields_ = [
        ("size", ctypes.c_uint),
        ("name", ctypes.c_char * 128),
        ("mod_name", ctypes.c_char * 128),
        ("ser_num", ctypes.c_char * 128),
        ("hw_ver", ctypes.c_char * 128),
        ("fw_ver", ctypes.c_char * 128),
    ]


class DPFPDD_CAPTURE_PARAM(ctypes.Structure):
    _fields_ = [
        ("size", ctypes.c_uint),
        ("image_fmt", ctypes.c_uint),
        ("image_proc", ctypes.c_uint),
        ("image_res", ctypes.c_uint),
    ]


class DPFPDD_CAPTURE_RESULT(ctypes.Structure):
    _fields_ = [
        ("size", ctypes.c_uint),
        ("success", ctypes.c_int),
        ("quality", ctypes.c_uint),
        ("score", ctypes.c_uint),
        ("info_size", ctypes.c_uint),
    ]


class DPFPDD_IMAGE_INFO(ctypes.Structure):
    _fields_ = [
        ("size", ctypes.c_uint),
        ("width", ctypes.c_uint),
        ("height", ctypes.c_uint),
        ("res", ctypes.c_uint),
        ("bpp", ctypes.c_uint),
    ]


class DPFJ_CANDIDATE(ctypes.Structure):
    _fields_ = [
        ("size", ctypes.c_uint),
        ("fmd_idx", ctypes.c_uint),
        ("view_idx", ctypes.c_uint),
    ]


class OfficialSdkBackend(BaseBackend):
    """
    ctypes backend for the official proprietary DigitalPersona / HID U.are.U SDK.
    Supports Windows (dpfpdd.dll / dpfj.dll) and Linux (libdpfpdd.so / libdpfj.so).
    """

    _dpfpdd = None
    _dpfj = None
    _init_attempted = False

    @classmethod
    def _find_and_load(cls):
        if cls._init_attempted:
            return cls._dpfpdd is not None and cls._dpfj is not None
        cls._init_attempted = True

        custom_path = os.environ.get("DP_SDK_PATH")
        search_paths = []
        if custom_path:
            search_paths.append(custom_path)

        if sys.platform.startswith("win"):
            # Windows standard directories
            exe_dir = os.path.dirname(sys.executable)
            meipass = getattr(sys, "_MEIPASS", "")
            prog_files = os.environ.get("PROGRAMFILES", r"C:\Program Files")
            prog_files_x86 = os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
            windir = os.environ.get("WINDIR", r"C:\Windows")

            search_paths.extend([
                exe_dir,
                meipass,
                os.getcwd(),
                os.path.join(prog_files, r"DigitalPersona\U.are.U SDK\Windows\Lib\x64"),
                os.path.join(prog_files_x86, r"DigitalPersona\U.are.U SDK\Windows\Lib\win32"),
                os.path.join(prog_files, r"Crossmatch\U.are.U SDK\Windows\Lib\x64"),
                os.path.join(windir, "System32"),
                os.path.join(windir, "SysWOW64"),
            ])
            dpfpdd_names = ["dpfpdd.dll"]
            dpfj_names = ["dpfj.dll"]
        else:
            # Linux standard directories
            search_paths.extend([
                "/opt/DigitalPersona/UareUSDK/Linux/lib/x64",
                "/opt/DigitalPersona/UareUSDK/Linux/lib",
                "/usr/local/lib",
                "/usr/lib",
            ])
            dpfpdd_names = ["libdpfpdd.so", "libdpfpdd.so.1"]
            dpfj_names = ["libdpfj.so", "libdpfj.so.1"]

        dpfpdd_lib = None
        dpfj_lib = None

        # Try exact names first
        for name in dpfpdd_names:
            try:
                dpfpdd_lib = ctypes.CDLL(name)
                break
            except OSError:
                pass

        if not dpfpdd_lib:
            for p in search_paths:
                for name in dpfpdd_names:
                    full = os.path.join(p, name)
                    if os.path.exists(full):
                        try:
                            dpfpdd_lib = ctypes.CDLL(full)
                            break
                        except OSError:
                            pass
                if dpfpdd_lib:
                    break

        for name in dpfj_names:
            try:
                dpfj_lib = ctypes.CDLL(name)
                break
            except OSError:
                pass

        if not dpfj_lib:
            for p in search_paths:
                for name in dpfj_names:
                    full = os.path.join(p, name)
                    if os.path.exists(full):
                        try:
                            dpfj_lib = ctypes.CDLL(full)
                            break
                        except OSError:
                            pass
                if dpfj_lib:
                    break

        cls._dpfpdd = dpfpdd_lib
        cls._dpfj = dpfj_lib
        return cls._dpfpdd is not None and cls._dpfj is not None

    @classmethod
    def is_available(cls) -> bool:
        return cls._find_and_load()

    @classmethod
    def backend_name(cls) -> str:
        return "official_sdk"

    def __init__(self):
        if not self._find_and_load():
            raise BackendNotAvailableError(
                "Official DigitalPersona SDK libraries (dpfpdd / dpfj) could not be located. "
                "Ensure the U.are.U SDK is installed or set DP_SDK_PATH."
            )
        res = self._dpfpdd.dpfpdd_init()
        if res != DPFPDD_SUCCESS:
            raise BackendNotAvailableError(f"dpfpdd_init failed with error code: {res}")

    def __del__(self):
        if self._dpfpdd:
            try:
                self._dpfpdd.dpfpdd_exit()
            except Exception:
                pass

    def list_devices(self) -> List[DeviceInfo]:
        dev_cnt = ctypes.c_uint(0)
        res = self._dpfpdd.dpfpdd_query_devices(ctypes.byref(dev_cnt), None)
        if res not in (DPFPDD_SUCCESS, DPFPDD_E_MORE_DATA) or dev_cnt.value == 0:
            return []

        dev_array = (DPFPDD_DEV_INFO * dev_cnt.value)()
        for d in dev_array:
            d.size = ctypes.sizeof(DPFPDD_DEV_INFO)

        res = self._dpfpdd.dpfpdd_query_devices(ctypes.byref(dev_cnt), dev_array)
        if res != DPFPDD_SUCCESS:
            return []

        results: List[DeviceInfo] = []
        for i in range(dev_cnt.value):
            d = dev_array[i]
            name = d.name.decode("utf-8", errors="ignore")
            ser = d.ser_num.decode("utf-8", errors="ignore")
            fw = d.fw_ver.decode("utf-8", errors="ignore")
            results.append(
                DeviceInfo(
                    device_id=name,
                    name=f"DigitalPersona 4500 ({ser})",
                    driver="dpfpdd",
                    vendor_id=0x05BA,
                    product_id=0x000A,
                    serial_number=ser,
                    firmware_version=fw,
                )
            )
        return results

    def open_device(self, device_id: str) -> Any:
        handle = ctypes.c_void_p(0)
        c_name = ctypes.c_char_p(device_id.encode("utf-8"))
        res = self._dpfpdd.dpfpdd_open(c_name, ctypes.byref(handle))
        if res != DPFPDD_SUCCESS:
            if res == DPFPDD_E_DEVICE_BUSY:
                raise DeviceBusyError(f"Device {device_id} is busy or claimed by another application.")
            raise DeviceNotFoundError(f"Failed to open device {device_id} (error {res})")
        return handle

    def close_device(self, handle: Any) -> None:
        if handle:
            self._dpfpdd.dpfpdd_close(handle)

    def capture_image(
        self,
        handle: Any,
        wait_for_finger: bool = True,
        timeout_ms: Optional[int] = None,
    ) -> FingerprintImage:
        param = DPFPDD_CAPTURE_PARAM()
        param.size = ctypes.sizeof(DPFPDD_CAPTURE_PARAM)
        param.image_fmt = 0  # Raw PIXMAP
        param.image_proc = 0  # Default processing
        param.image_res = 500  # 500 DPI

        cap_res = DPFPDD_CAPTURE_RESULT()
        cap_res.size = ctypes.sizeof(DPFPDD_CAPTURE_RESULT)

        timeout = timeout_ms if timeout_ms is not None else 10000
        # Image buffer query size
        img_size = ctypes.c_uint(0)
        self._dpfpdd.dpfpdd_capture(handle, ctypes.byref(param), timeout, ctypes.byref(cap_res), ctypes.byref(img_size), None)

        if img_size.value == 0:
            # Fallback default buffer size for 4500 (approx 290x384 + header)
            img_size.value = 290 * 384 + ctypes.sizeof(DPFPDD_IMAGE_INFO)

        buf = (ctypes.c_uint8 * img_size.value)()
        res = self._dpfpdd.dpfpdd_capture(
            handle,
            ctypes.byref(param),
            timeout,
            ctypes.byref(cap_res),
            ctypes.byref(img_size),
            buf,
        )

        if res != DPFPDD_SUCCESS or not cap_res.success:
            if cap_res.quality == DPFPDD_QUALITY_TIMED_OUT:
                raise CaptureError("Capture timed out waiting for finger.")
            raise CaptureError(f"Image capture failed (res={res}, quality={cap_res.quality})")

        # Parse DPFPDD_IMAGE_INFO header followed by pixel data
        info = DPFPDD_IMAGE_INFO.from_buffer_copy(bytes(buf[: ctypes.sizeof(DPFPDD_IMAGE_INFO)]))
        pixel_bytes = bytes(buf[ctypes.sizeof(DPFPDD_IMAGE_INFO) : ctypes.sizeof(DPFPDD_IMAGE_INFO) + (info.width * info.height)])

        return FingerprintImage(
            data=pixel_bytes,
            width=info.width,
            height=info.height,
            dpi=info.res if info.res > 0 else 500,
        )

    def enroll(
        self,
        handle: Any,
        stages: int = 5,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        timeout_ms: Optional[int] = None,
    ) -> FingerprintTemplate:
        # Start enrollment in dpfj
        res = self._dpfj.dpfj_start_enrollment(DPFJ_FMD_ANSI_378_2004)
        if res != DPFJ_SUCCESS:
            raise EnrollmentError(f"dpfj_start_enrollment failed: {res}")

        for s in range(stages):
            if progress_callback:
                progress_callback(s, stages)

            img = self.capture_image(handle, wait_for_finger=True, timeout_ms=timeout_ms)

            # Create pre-reg FMD from image
            fmd_size = ctypes.c_uint(2048)
            fmd_buf = (ctypes.c_uint8 * fmd_size.value)()
            res = self._dpfj.dpfj_create_fmd_from_raw(
                img.data,
                len(img.data),
                img.width,
                img.height,
                img.dpi,
                0,  # finger position
                DPFJ_FMD_DP_PRE_REG_FEATURES,
                fmd_buf,
                ctypes.byref(fmd_size),
            )
            if res != DPFJ_SUCCESS:
                raise EnrollmentError(f"Failed to extract features from scan {s+1}: {res}")

            # Add to enrollment
            ready = ctypes.c_int(0)
            res = self._dpfj.dpfj_add_to_enrollment(DPFJ_FMD_DP_PRE_REG_FEATURES, fmd_buf, fmd_size.value, 0, ctypes.byref(ready))
            if res != DPFJ_SUCCESS:
                raise EnrollmentError(f"dpfj_add_to_enrollment failed: {res}")

            if ready.value:
                break

        # Create master enrollment FMD
        master_size = ctypes.c_uint(4096)
        master_buf = (ctypes.c_uint8 * master_size.value)()
        res = self._dpfj.dpfj_create_enrollment_fmd(
            DPFJ_FMD_ANSI_378_2004,
            master_buf,
            ctypes.byref(master_size),
        )
        if res != DPFJ_SUCCESS:
            raise EnrollmentError(f"Failed to generate final enrollment template: {res}")

        if progress_callback:
            progress_callback(stages, stages)

        return FingerprintTemplate(
            data=bytes(master_buf[: master_size.value]),
            format_type="ansi_378",
        )

    def verify(
        self,
        handle: Any,
        template: FingerprintTemplate,
        timeout_ms: Optional[int] = None,
    ) -> MatchResult:
        img = self.capture_image(handle, wait_for_finger=True, timeout_ms=timeout_ms)

        # Extract FMD from live capture
        fmd_size = ctypes.c_uint(2048)
        fmd_buf = (ctypes.c_uint8 * fmd_size.value)()
        res = self._dpfj.dpfj_create_fmd_from_raw(
            img.data,
            len(img.data),
            img.width,
            img.height,
            img.dpi,
            0,
            DPFJ_FMD_ANSI_378_2004,
            fmd_buf,
            ctypes.byref(fmd_size),
        )
        if res != DPFJ_SUCCESS:
            raise VerificationError(f"Feature extraction failed: {res}")

        # Compare with enrolled template
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
        if res != DPFJ_SUCCESS:
            raise VerificationError(f"dpfj_compare failed: {res}")

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
        for idx, tpl in enumerate(templates):
            res = self.verify(handle, tpl, timeout_ms=timeout_ms)
            if res.matched:
                return IdentifyResult(matched=True, index=idx, template=tpl, score=res.score)
        return IdentifyResult(matched=False, index=None, template=None, score=0.0)

    def set_led(self, handle: Any, mode: LEDMode) -> bool:
        # dpfpdd_set_parameter(handle, DPFPDD_PARMID_LED_CLIENT, ...)
        return True

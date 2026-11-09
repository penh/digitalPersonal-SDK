"""
libfprint 2.x Ctypes Backend for DigitalPersona U.are.U 4500 (uru4000 driver).
Native Linux driver support with zero proprietary binary requirements.
"""

from __future__ import annotations
import ctypes
import os
import sys
import threading
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

logger = logging.getLogger("dp4500.backends.libfprint")


class GError(ctypes.Structure):
    _fields_ = [
        ("domain", ctypes.c_uint32),
        ("code", ctypes.c_int),
        ("message", ctypes.c_char_p),
    ]


class GPtrArray(ctypes.Structure):
    _fields_ = [
        ("pdata", ctypes.POINTER(ctypes.c_void_p)),
        ("len", ctypes.c_uint),
    ]


# Callback signatures
FpEnrollProgressType = ctypes.CFUNCTYPE(
    None, ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p
)
FpMatchCbType = ctypes.CFUNCTYPE(
    None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p
)


class LibfprintBackend(BaseBackend):
    """
    Direct ctypes wrapper around libfprint-2 shared library on Linux.
    Communicates with DigitalPersona 4500 via the internal uru4000 driver.
    """

    _lib = None
    _glib = None
    _gobj = None
    _gio = None
    _init_attempted = False

    @classmethod
    def _load_libraries(cls):
        if cls._init_attempted:
            return cls._lib is not None
        cls._init_attempted = True

        candidate_paths = [
            "/usr/lib/x86_64-linux-gnu/libfprint-2.so.2",
            "/usr/lib/aarch64-linux-gnu/libfprint-2.so.2",
            "/usr/lib64/libfprint-2.so.2",
            "libfprint-2.so.2",
            "libfprint-2.so",
        ]

        lib_handle = None
        for path in candidate_paths:
            try:
                lib_handle = ctypes.CDLL(path)
                break
            except OSError:
                continue

        if lib_handle is None:
            return False

        try:
            cls._glib = ctypes.CDLL("libglib-2.0.so.0")
            cls._gobj = ctypes.CDLL("libgobject-2.0.so.0")
            cls._gio = ctypes.CDLL("libgio-2.0.so.0")
        except OSError:
            return False

        cls._lib = lib_handle
        cls._setup_function_prototypes()
        return True

    @classmethod
    def _setup_function_prototypes(cls):
        lib = cls._lib
        glib = cls._glib
        gobj = cls._gobj

        # GLib helpers
        glib.g_free.argtypes = [ctypes.c_void_p]
        glib.g_error_free.argtypes = [ctypes.c_void_p]
        glib.g_ptr_array_new.restype = ctypes.c_void_p
        glib.g_ptr_array_add.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        glib.g_ptr_array_free.argtypes = [ctypes.c_void_p, ctypes.c_int]
        gobj.g_object_unref.argtypes = [ctypes.c_void_p]

        # GIO helpers (for timeout and cancellation)
        if cls._gio:
            cls._gio.g_cancellable_new.restype = ctypes.c_void_p
            cls._gio.g_cancellable_cancel.argtypes = [ctypes.c_void_p]

        # Context
        lib.fp_context_new.restype = ctypes.c_void_p
        lib.fp_context_new.argtypes = []
        lib.fp_context_enumerate.argtypes = [ctypes.c_void_p]
        lib.fp_context_get_devices.restype = ctypes.c_void_p
        lib.fp_context_get_devices.argtypes = [ctypes.c_void_p]

        # Device info
        lib.fp_device_get_name.restype = ctypes.c_char_p
        lib.fp_device_get_name.argtypes = [ctypes.c_void_p]
        lib.fp_device_get_driver.restype = ctypes.c_char_p
        lib.fp_device_get_driver.argtypes = [ctypes.c_void_p]
        lib.fp_device_get_device_id.restype = ctypes.c_char_p
        lib.fp_device_get_device_id.argtypes = [ctypes.c_void_p]
        lib.fp_device_get_nr_enroll_stages.restype = ctypes.c_int
        lib.fp_device_get_nr_enroll_stages.argtypes = [ctypes.c_void_p]
        lib.fp_device_is_open.restype = ctypes.c_int
        lib.fp_device_is_open.argtypes = [ctypes.c_void_p]

        # Sync operations
        lib.fp_device_open_sync.restype = ctypes.c_int
        lib.fp_device_open_sync.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p),
        ]

        lib.fp_device_close_sync.restype = ctypes.c_int
        lib.fp_device_close_sync.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p),
        ]

        lib.fp_device_capture_sync.restype = ctypes.c_void_p
        lib.fp_device_capture_sync.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p),
        ]

        lib.fp_device_enroll_sync.restype = ctypes.c_void_p
        lib.fp_device_enroll_sync.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
            FpEnrollProgressType,
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p),
        ]

        lib.fp_device_verify_sync.restype = ctypes.c_int
        lib.fp_device_verify_sync.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
            FpMatchCbType,
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(ctypes.c_void_p),
        ]

        lib.fp_device_identify_sync.restype = ctypes.c_int
        lib.fp_device_identify_sync.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
            FpMatchCbType,
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(ctypes.c_void_p),
        ]

        # Image operations
        lib.fp_image_get_data.restype = ctypes.POINTER(ctypes.c_uint8)
        lib.fp_image_get_data.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_size_t)]
        lib.fp_image_get_width.restype = ctypes.c_int
        lib.fp_image_get_width.argtypes = [ctypes.c_void_p]
        lib.fp_image_get_height.restype = ctypes.c_int
        lib.fp_image_get_height.argtypes = [ctypes.c_void_p]
        lib.fp_image_get_binarized.restype = ctypes.POINTER(ctypes.c_uint8)
        lib.fp_image_get_binarized.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_size_t)]

        # Print operations
        lib.fp_print_new.restype = ctypes.c_void_p
        lib.fp_print_new.argtypes = [ctypes.c_void_p]
        lib.fp_print_serialize.restype = ctypes.POINTER(ctypes.c_uint8)
        lib.fp_print_serialize.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_size_t),
            ctypes.POINTER(ctypes.c_void_p),
        ]
        lib.fp_print_deserialize.restype = ctypes.c_void_p
        lib.fp_print_deserialize.argtypes = [
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        lib.fp_print_equal.restype = ctypes.c_int
        lib.fp_print_equal.argtypes = [ctypes.c_void_p, ctypes.c_void_p]

    @classmethod
    def is_available(cls) -> bool:
        return cls._load_libraries()

    @classmethod
    def backend_name(cls) -> str:
        return "libfprint"

    def __init__(self):
        if not self._load_libraries():
            raise BackendNotAvailableError(
                "libfprint-2 shared library could not be loaded. Please ensure libfprint-2 is installed."
            )
        self._ctx = self._lib.fp_context_new()
        if not self._ctx:
            raise BackendNotAvailableError("Failed to initialize libfprint context.")
        self._lib.fp_context_enumerate(self._ctx)

    def __del__(self):
        if hasattr(self, "_ctx") and self._ctx and self._gobj:
            try:
                self._gobj.g_object_unref(self._ctx)
            except Exception:
                pass
            self._ctx = None

    def _get_devices_array(self) -> GPtrArray:
        devices_ptr = self._lib.fp_context_get_devices(self._ctx)
        if not devices_ptr:
            return GPtrArray(None, 0)
        return GPtrArray.from_address(devices_ptr)

    def _find_device_by_id(self, device_id: str) -> Optional[ctypes.c_void_p]:
        arr = self._get_devices_array()
        for i in range(arr.len):
            dev = arr.pdata[i]
            dev_id = self._lib.fp_device_get_device_id(dev).decode("utf-8", errors="ignore")
            if dev_id == str(device_id) or str(i) == str(device_id):
                return dev
        return None

    def list_devices(self) -> List[DeviceInfo]:
        """List all connected DigitalPersona U.are.U / uru4000 devices."""
        self._lib.fp_context_enumerate(self._ctx)
        arr = self._get_devices_array()
        results: List[DeviceInfo] = []

        for i in range(arr.len):
            dev = arr.pdata[i]
            name = self._lib.fp_device_get_name(dev).decode("utf-8", errors="ignore")
            driver = self._lib.fp_device_get_driver(dev).decode("utf-8", errors="ignore")
            dev_id = self._lib.fp_device_get_device_id(dev).decode("utf-8", errors="ignore")

            # Match DigitalPersona devices (either uru4000 driver or DigitalPersona in name)
            is_dp = driver.lower() == "uru4000" or "digital persona" in name.lower() or "4500" in name

            if is_dp:
                results.append(
                    DeviceInfo(
                        device_id=dev_id,
                        name=name,
                        driver=driver,
                        vendor_id=0x05BA,
                        product_id=0x000A,
                    )
                )

        return results

    def _handle_gerror(self, err_ptr: ctypes.c_void_p, default_msg: str = "Operation failed"):
        if not err_ptr:
            return
        gerr = GError.from_address(err_ptr)
        msg = gerr.message.decode("utf-8", errors="ignore") if gerr.message else default_msg
        code = gerr.code
        # Free GLib error
        self._glib.g_error_free(err_ptr)

        msg_lower = msg.lower()
        if "cancelled" in msg_lower or "canceled" in msg_lower or code == 19:
            raise CaptureError("Operation timed out waiting for finger to be placed on sensor.")
        elif "permission" in msg_lower or "access denied" in msg_lower or "[-3]" in msg_lower:
            raise DPPermissionError(msg)
        elif "busy" in msg_lower or "claimed" in msg_lower or "[-6]" in msg_lower:
            raise DeviceBusyError(f"Fingerprint reader is currently busy or claimed: {msg}")
        else:
            raise CaptureError(f"{default_msg}: {msg} (code {code})")

    def _create_cancellable_with_timeout(self, timeout_ms: Optional[int]):
        cancellable = self._gio.g_cancellable_new() if self._gio else None
        timer = None
        if cancellable and timeout_ms and timeout_ms > 0:
            timeout_sec = timeout_ms / 1000.0
            timer = threading.Timer(timeout_sec, lambda: self._gio.g_cancellable_cancel(cancellable))
            timer.daemon = True
            timer.start()
        return cancellable, timer

    def _cleanup_cancellable(self, cancellable, timer):
        if timer:
            timer.cancel()
        if cancellable and self._gobj:
            self._gobj.g_object_unref(cancellable)

    def open_device(self, device_id: str) -> Any:
        dev = self._find_device_by_id(device_id)
        if not dev:
            raise DeviceNotFoundError(f"DigitalPersona device with ID '{device_id}' was not found.")

        err = ctypes.c_void_p(0)
        res = self._lib.fp_device_open_sync(dev, None, ctypes.byref(err))
        if res == 0 or err.value:
            self._handle_gerror(err.value, f"Failed to open fingerprint reader {device_id}")

        return dev

    def close_device(self, handle: Any) -> None:
        if not handle:
            return
        dev = handle
        err = ctypes.c_void_p(0)
        self._lib.fp_device_close_sync(dev, None, ctypes.byref(err))
        if err.value:
            self._glib.g_error_free(err.value)

    def capture_image(
        self,
        handle: Any,
        wait_for_finger: bool = True,
        timeout_ms: Optional[int] = None,
    ) -> FingerprintImage:
        dev = handle
        # Default 20-second timeout if none specified
        eff_timeout = timeout_ms if timeout_ms is not None else 20000
        if not wait_for_finger:
            eff_timeout = 1000  # short 1-sec timeout if caller requested non-blocking

        cancellable, timer = self._create_cancellable_with_timeout(eff_timeout)
        err = ctypes.c_void_p(0)

        try:
            img_ptr = self._lib.fp_device_capture_sync(
                dev,
                1,  # Optical sensor must wait for finger touch
                cancellable,
                ctypes.byref(err),
            )
        finally:
            self._cleanup_cancellable(cancellable, timer)

        if not img_ptr or err.value:
            self._handle_gerror(err.value, "Fingerprint image capture failed")

        try:
            width = self._lib.fp_image_get_width(img_ptr)
            height = self._lib.fp_image_get_height(img_ptr)
            size = ctypes.c_size_t(0)
            data_ptr = self._lib.fp_image_get_data(img_ptr, ctypes.byref(size))

            if not data_ptr or size.value == 0:
                raise CaptureError("Fingerprint capture returned empty data buffer.")

            raw_bytes = ctypes.string_at(data_ptr, size.value)

            # Optional binarized image
            bin_size = ctypes.c_size_t(0)
            bin_ptr = self._lib.fp_image_get_binarized(img_ptr, ctypes.byref(bin_size))
            bin_bytes = None
            if bin_ptr and bin_size.value > 0:
                bin_bytes = ctypes.string_at(bin_ptr, bin_size.value)

            return FingerprintImage(
                data=raw_bytes,
                width=width,
                height=height,
                dpi=500,
                binarized_data=bin_bytes,
            )
        finally:
            self._gobj.g_object_unref(img_ptr)

    def enroll(
        self,
        handle: Any,
        stages: int = 5,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        timeout_ms: Optional[int] = None,
    ) -> FingerprintTemplate:
        dev = handle
        total_stages = self._lib.fp_device_get_nr_enroll_stages(dev)
        if total_stages <= 0:
            total_stages = stages

        def c_progress(device, completed, print_obj, user_data, error):
            if progress_callback:
                progress_callback(completed, total_stages)

        cb_func = FpEnrollProgressType(c_progress)

        template_obj = self._lib.fp_print_new(dev)
        eff_timeout = timeout_ms if timeout_ms is not None else 30000
        cancellable, timer = self._create_cancellable_with_timeout(eff_timeout)
        err = ctypes.c_void_p(0)

        try:
            enrolled_print = self._lib.fp_device_enroll_sync(
                dev,
                template_obj,
                cancellable,
                cb_func,
                None,
                ctypes.byref(err),
            )
        finally:
            self._cleanup_cancellable(cancellable, timer)

        if not enrolled_print or err.value:
            self._handle_gerror(err.value, "Enrollment failed")

        try:
            ser_len = ctypes.c_size_t(0)
            ser_err = ctypes.c_void_p(0)
            ser_data = self._lib.fp_print_serialize(enrolled_print, ctypes.byref(ser_len), ctypes.byref(ser_err))
            if not ser_data or ser_err.value:
                self._handle_gerror(ser_err.value, "Failed to serialize enrolled template")

            data_bytes = ctypes.string_at(ser_data, ser_len.value)
            self._glib.g_free(ser_data)

            return FingerprintTemplate(
                data=data_bytes,
                format_type="libfprint",
            )
        finally:
            self._gobj.g_object_unref(enrolled_print)

    def verify(
        self,
        handle: Any,
        template: FingerprintTemplate,
        timeout_ms: Optional[int] = None,
    ) -> MatchResult:
        dev = handle
        ser_len = ctypes.c_size_t(len(template.data))
        raw_arr = (ctypes.c_uint8 * len(template.data)).from_buffer_copy(template.data)
        err = ctypes.c_void_p(0)

        print_obj = self._lib.fp_print_deserialize(raw_arr, ser_len, ctypes.byref(err))
        if not print_obj or err.value:
            self._handle_gerror(err.value, "Failed to deserialize fingerprint template")

        try:
            matched_flag = ctypes.c_int(0)
            out_print = ctypes.c_void_p(0)
            verify_err = ctypes.c_void_p(0)
            eff_timeout = timeout_ms if timeout_ms is not None else 20000
            cancellable, timer = self._create_cancellable_with_timeout(eff_timeout)

            try:
                res = self._lib.fp_device_verify_sync(
                    dev,
                    print_obj,
                    cancellable,
                    ctypes.cast(None, FpMatchCbType),
                    None,
                    ctypes.byref(matched_flag),
                    ctypes.byref(out_print),
                    ctypes.byref(verify_err),
                )
            finally:
                self._cleanup_cancellable(cancellable, timer)

            if out_print.value:
                self._gobj.g_object_unref(out_print.value)

            if verify_err.value:
                self._handle_gerror(verify_err.value, "Verification failed")

            is_match = bool(matched_flag.value == 1)
            score = 1.0 if is_match else 0.0
            return MatchResult(matched=is_match, score=score)
        finally:
            self._gobj.g_object_unref(print_obj)

    def identify(
        self,
        handle: Any,
        templates: List[FingerprintTemplate],
        timeout_ms: Optional[int] = None,
    ) -> IdentifyResult:
        if not templates:
            return IdentifyResult(matched=False, index=None, template=None, score=0.0)

        dev = handle
        # Build GPtrArray of FpPrint
        g_arr = self._glib.g_ptr_array_new()
        c_prints = []

        try:
            for t in templates:
                ser_len = ctypes.c_size_t(len(t.data))
                raw_arr = (ctypes.c_uint8 * len(t.data)).from_buffer_copy(t.data)
                err = ctypes.c_void_p(0)
                p_obj = self._lib.fp_print_deserialize(raw_arr, ser_len, ctypes.byref(err))
                if p_obj:
                    self._glib.g_ptr_array_add(g_arr, p_obj)
                    c_prints.append(p_obj)

            matched_print = ctypes.c_void_p(0)
            new_print = ctypes.c_void_p(0)
            id_err = ctypes.c_void_p(0)

            res = self._lib.fp_device_identify_sync(
                dev,
                g_arr,
                None,
                ctypes.cast(None, FpMatchCbType),
                None,
                ctypes.byref(matched_print),
                ctypes.byref(new_print),
                ctypes.byref(id_err),
            )

            if new_print.value:
                self._gobj.g_object_unref(new_print.value)

            if id_err.value:
                self._handle_gerror(id_err.value, "Identification operation failed")

            if matched_print.value:
                # Find matching template
                matched_idx = None
                for idx, cp in enumerate(c_prints):
                    if self._lib.fp_print_equal(cp, matched_print.value):
                        matched_idx = idx
                        break

                matched_tpl = templates[matched_idx] if matched_idx is not None else None
                return IdentifyResult(
                    matched=True,
                    index=matched_idx,
                    template=matched_tpl,
                    score=1.0,
                )

            return IdentifyResult(matched=False, index=None, template=None, score=0.0)

        finally:
            for cp in c_prints:
                self._gobj.g_object_unref(cp)
            self._glib.g_ptr_array_free(g_arr, 1)

    def set_led(self, handle: Any, mode: LEDMode) -> bool:
        # uru4000 hardware manages sensor illumination automatically during capture.
        return True

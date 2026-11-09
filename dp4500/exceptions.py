"""
Custom exceptions for the DigitalPersona U.are.U 4500 SDK.
"""

class DPError(Exception):
    """Base exception for all DigitalPersona SDK operations."""
    pass


class DeviceNotFoundError(DPError):
    """Raised when no compatible DigitalPersona 4500 reader is found."""
    pass


class DeviceBusyError(DPError):
    """Raised when the reader is currently claimed by another process or thread."""
    pass


class PermissionError(DPError):
    """
    Raised when USB access permissions are denied on Linux.
    Includes instructions to setup udev rules.
    """
    def __init__(self, message: str = "Access to USB device denied."):
        full_msg = (
            f"{message}\n\n"
            "Tip: On Linux, non-root users require udev permissions to communicate with USB devices.\n"
            "Run 'dp4500 setup-udev' or create '/etc/udev/rules.d/99-digitalpersona-uareu.rules' with:\n"
            'SUBSYSTEM=="usb", ATTRS{idVendor}=="05ba", ATTRS{idProduct}=="000a", MODE="0666", TAG+="uaccess"\n'
            "Then run: sudo udevadm control --reload-rules && sudo udevadm trigger"
        )
        super().__init__(full_msg)


class DeviceNotOpenError(DPError):
    """Raised when an operation is attempted on an unopened or closed reader."""
    pass


class CaptureError(DPError):
    """Raised when image capture fails or times out."""
    pass


class EnrollmentError(DPError):
    """Raised when enrollment fails (e.g. inconsistent touches, swipe too fast, bad quality)."""
    pass


class VerificationError(DPError):
    """Raised when verification encounters an internal error."""
    pass


class IdentificationError(DPError):
    """Raised when 1:N identification encounters an error."""
    pass


class BackendNotAvailableError(DPError):
    """Raised when the requested backend library is not available in the current environment."""
    pass

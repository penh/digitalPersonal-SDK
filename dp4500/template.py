"""
Fingerprint template representation, metadata, and serialization.
"""

from __future__ import annotations
import base64
import json
import struct
import time
from typing import Optional, Dict, Any

MAGIC_HEADER = b"DP4500\x01"


class FingerprintTemplate:
    """
    Encapsulates an enrolled fingerprint template, supporting serialization,
    metadata tagging (user, finger position, timestamp), and persistence.
    """

    def __init__(
        self,
        data: bytes,
        format_type: str = "libfprint",
        username: Optional[str] = None,
        finger_name: Optional[str] = None,
        created_at: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        if not data:
            raise ValueError("Template data cannot be empty.")
        self._data = bytes(data)
        self._format_type = str(format_type)
        self._username = username
        self._finger_name = finger_name
        self._created_at = created_at or time.time()
        self._metadata = metadata or {}

    @property
    def data(self) -> bytes:
        """Raw template byte buffer."""
        return self._data

    @property
    def size(self) -> int:
        """Byte size of the raw template."""
        return len(self._data)

    @property
    def format_type(self) -> str:
        """Template format ('libfprint', 'ansi_378', 'iso_19794_2', 'minutiae_json')."""
        return self._format_type

    @property
    def username(self) -> Optional[str]:
        """Associated user account or identifier."""
        return self._username

    @username.setter
    def username(self, val: Optional[str]) -> None:
        self._username = val

    @property
    def finger_name(self) -> Optional[str]:
        """Name of the finger (e.g. 'right_index', 'left_thumb')."""
        return self._finger_name

    @finger_name.setter
    def finger_name(self, val: Optional[str]) -> None:
        self._finger_name = val

    @property
    def created_at(self) -> float:
        """Timestamp of enrollment."""
        return self._created_at

    @property
    def metadata(self) -> Dict[str, Any]:
        """Custom dictionary of extra attributes."""
        return self._metadata

    def to_bytes(self) -> bytes:
        """
        Serialize template with header, metadata JSON, and raw payload.
        Format:
        [MAGIC_HEADER: 7 bytes]
        [Header JSON length: uint32]
        [Header JSON UTF-8 bytes]
        [Payload length: uint32]
        [Payload raw bytes]
        """
        meta = {
            "format_type": self._format_type,
            "username": self._username,
            "finger_name": self._finger_name,
            "created_at": self._created_at,
            "extra": self._metadata,
        }
        meta_bytes = json.dumps(meta).encode("utf-8")
        payload = self._data
        return (
            MAGIC_HEADER
            + struct.pack(">II", len(meta_bytes), len(payload))
            + meta_bytes
            + payload
        )

    @classmethod
    def from_bytes(cls, raw: bytes) -> FingerprintTemplate:
        """Deserialize from binary representation or raw template bytes."""
        if raw.startswith(MAGIC_HEADER):
            # Formatted container
            offset = len(MAGIC_HEADER)
            meta_len, payload_len = struct.unpack_from(">II", raw, offset)
            offset += 8
            meta_bytes = raw[offset : offset + meta_len]
            offset += meta_len
            payload = raw[offset : offset + payload_len]

            meta = json.loads(meta_bytes.decode("utf-8"))
            return cls(
                data=payload,
                format_type=meta.get("format_type", "libfprint"),
                username=meta.get("username"),
                finger_name=meta.get("finger_name"),
                created_at=meta.get("created_at"),
                metadata=meta.get("extra"),
            )
        else:
            # Raw template buffer without container header
            return cls(data=raw, format_type="raw")

    def to_base64(self) -> str:
        """Encode the full serialized container to Base64."""
        return base64.b64encode(self.to_bytes()).decode("ascii")

    @classmethod
    def from_base64(cls, b64_str: str) -> FingerprintTemplate:
        """Decode from Base64 string."""
        raw = base64.b64decode(b64_str.strip())
        return cls.from_bytes(raw)

    def save(self, filepath: str) -> None:
        """Save template file (.fpt) to disk."""
        with open(filepath, "wb") as f:
            f.write(self.to_bytes())

    @classmethod
    def load(cls, filepath: str) -> FingerprintTemplate:
        """Load template file (.fpt) from disk."""
        with open(filepath, "rb") as f:
            return cls.from_bytes(f.read())

    def __repr__(self) -> str:
        user_info = f" user='{self._username}'" if self._username else ""
        finger_info = f" finger='{self._finger_name}'" if self._finger_name else ""
        return (
            f"<FingerprintTemplate format='{self._format_type}'{user_info}{finger_info} "
            f"bytes={len(self._data)}>"
        )

"""QR settings, encoding, and persistent group metadata."""

from __future__ import annotations

import base64
import binascii
import json
import zlib
from dataclasses import dataclass
from typing import Iterator, Sequence

from .vendor.qrcodegen import DataTooLongError, QrCode, QrSegment


METADATA_PREFIX = "BQR1:"
ERROR_CORRECTION_LEVELS = ("L", "M", "Q", "H")

_ECC = {
    "L": QrCode.Ecc.LOW,
    "M": QrCode.Ecc.MEDIUM,
    "Q": QrCode.Ecc.QUARTILE,
    "H": QrCode.Ecc.HIGH,
}


class QrSettingsError(ValueError):
    """Raised when settings cannot produce a valid QR code."""


@dataclass(frozen=True)
class QrSettings:
    data: str
    error_correction: str = "M"
    size_mm: float = 20.0
    layer_name: str = "F.Silkscreen"

    def validated(self) -> "QrSettings":
        data = self.data
        error_correction = self.error_correction.upper()

        if not data.strip():
            raise QrSettingsError("Enter content for the QR code.")
        if error_correction not in ERROR_CORRECTION_LEVELS:
            raise QrSettingsError("Choose a valid error-correction level.")
        if not 1.0 <= self.size_mm <= 500.0:
            raise QrSettingsError("Size must be between 1 mm and 500 mm.")
        if not self.layer_name:
            raise QrSettingsError("Choose a board layer.")

        return QrSettings(data, error_correction, float(self.size_mm), self.layer_name)


@dataclass(frozen=True)
class EncodedQr:
    modules: tuple[tuple[bool, ...], ...]
    version: int
    mask: int

    @property
    def module_count(self) -> int:
        return len(self.modules)


def encode_qr(settings: QrSettings) -> EncodedQr:
    """Encode a regular QR Code Model 2 symbol without changing the requested ECC."""
    settings = settings.validated()
    try:
        qr = QrCode.encode_segments(
            QrSegment.make_segments(settings.data),
            _ECC[settings.error_correction],
            boostecl=False,
        )
    except DataTooLongError as error:
        raise QrSettingsError("The content is too long for a regular QR code.") from error

    size = qr.get_size()
    modules = tuple(
        tuple(qr.get_module(x, y) for x in range(size))
        for y in range(size)
    )
    return EncodedQr(modules, qr.get_version(), qr.get_mask())


def dark_runs(modules: Sequence[Sequence[bool]]) -> Iterator[tuple[int, int, int]]:
    """Yield each horizontal dark run as (row, inclusive start, exclusive end)."""
    for y, row in enumerate(modules):
        x = 0
        while x < len(row):
            if not row[x]:
                x += 1
                continue
            start = x
            while x < len(row) and row[x]:
                x += 1
            yield y, start, x


def encode_metadata(settings: QrSettings) -> str:
    """Serialize editable settings into the KiCad group's persisted name."""
    settings = settings.validated()
    payload = json.dumps(
        {"data": settings.data, "ecc": settings.error_correction},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    packed = base64.urlsafe_b64encode(zlib.compress(payload, 9)).decode("ascii").rstrip("=")
    return METADATA_PREFIX + packed


def decode_metadata(group_name: str, *, size_mm: float, layer_name: str) -> QrSettings | None:
    """Recover editable settings from a Better QR Codes group name."""
    if not group_name.startswith(METADATA_PREFIX):
        return None

    try:
        packed = group_name[len(METADATA_PREFIX):]
        packed += "=" * (-len(packed) % 4)
        payload = zlib.decompress(base64.urlsafe_b64decode(packed)).decode("utf-8")
        values = json.loads(payload)
        return QrSettings(
            data=values["data"],
            error_correction=values["ecc"],
            size_mm=size_mm,
            layer_name=layer_name,
        ).validated()
    except (KeyError, TypeError, ValueError, binascii.Error, zlib.error, json.JSONDecodeError):
        return None

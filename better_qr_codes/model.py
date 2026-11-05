"""QR settings, encoding, and persistent group metadata."""

from __future__ import annotations

import base64
import binascii
import json
import math
import zlib
from dataclasses import dataclass
from typing import Iterator, Sequence

from .vendor.qrcodegen import DataTooLongError, QrCode, QrSegment


# Settings stored in a footprint field (current format).
METADATA_PREFIX = "BQR2:"
# Settings stored in a PCB_GROUP name by releases up to 0.1.1.
LEGACY_METADATA_PREFIX = "BQR1:"
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
    error_correction: str = "L"
    size_mm: float = 15.0
    layer_name: str = "F.Silkscreen"
    corner_radius_percent: int = 0
    knockout: bool = False
    knockout_margin_modules: int = 4
    finder_radius_percent: int = 0
    knockout_corner_radius_percent: int = 0
    # The footprint orientation, as KiCad shows it: counter-clockwise, -180..180.
    rotation_degrees: float = 0.0

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
        if not 0 <= self.corner_radius_percent <= 100:
            raise QrSettingsError("Corner radius must be between 0% and 100%.")
        if not 0 <= self.finder_radius_percent <= 100:
            raise QrSettingsError("Finder radius must be between 0% and 100%.")
        if not 0 <= self.knockout_corner_radius_percent <= 100:
            raise QrSettingsError("Knockout corner radius must be between 0% and 100%.")
        if int(self.knockout_margin_modules) != self.knockout_margin_modules:
            raise QrSettingsError("Knockout margin must be a whole number of modules.")
        if not 0 <= self.knockout_margin_modules <= 20:
            raise QrSettingsError("Knockout margin must be between 0 and 20 modules.")
        if not math.isfinite(self.rotation_degrees):
            raise QrSettingsError("Rotation must be a number of degrees.")

        return QrSettings(
            data,
            error_correction,
            float(self.size_mm),
            self.layer_name,
            int(self.corner_radius_percent),
            bool(self.knockout),
            int(self.knockout_margin_modules),
            int(self.finder_radius_percent),
            int(self.knockout_corner_radius_percent),
            _normalize_degrees(self.rotation_degrees),
        )


def _normalize_degrees(degrees: float) -> float:
    angle = round(float(degrees) % 360.0, 4) % 360.0
    return angle - 360.0 if angle > 180.0 else angle


def flipped_rotation(degrees: float) -> float:
    """Orientation after KiCad flips a footprint to the other side (30 -> 150).

    Back-side codes default to 180, KiCad's natural orientation for a flipped
    footprint, which reads upright when the board is viewed from below.
    """
    return _normalize_degrees(180.0 - degrees)


def rotate_point(
    x: float, y: float, center_x: float, center_y: float, degrees: float
) -> tuple[float, float]:
    """Rotate counter-clockwise on screen (board Y grows downward), like KiCad."""
    angle = math.radians(degrees)
    cos, sin = math.cos(angle), math.sin(angle)
    dx, dy = x - center_x, y - center_y
    return center_x + dx * cos + dy * sin, center_y - dx * sin + dy * cos


def place_polygons(
    polygons, center_x: float, center_y: float, degrees: float, back_side: bool = False
):
    """Map unrotated artwork the way a KiCad footprint shows it from the top.

    A back-side footprint mirrors its local Y axis before applying its displayed
    orientation (measured in KiCad 10.0.6).
    """
    if not degrees and not back_side:
        return tuple(polygons)
    return tuple(
        tuple(
            rotate_point(x, 2 * center_y - y if back_side else y, center_x, center_y, degrees)
            for x, y in polygon
        )
        for polygon in polygons
    )


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


def knockout_modules(
    modules: Sequence[Sequence[bool]], margin: int
) -> tuple[tuple[bool, ...], ...]:
    """Return material cells for an inverted symbol with a module-based margin."""
    count = len(modules)
    total = count + margin * 2
    return tuple(
        tuple(
            not (margin <= y < margin + count and margin <= x < margin + count)
            or not modules[y - margin][x - margin]
            for x in range(total)
        )
        for y in range(total)
    )


def rounded_module_polygons(
    modules: Sequence[Sequence[bool]],
    corner_radius_percent: int,
    finder_radius_percent: int | None = None,
    finder_outer_style: str = "rounded",
    finder_inner_style: str = "rounded",
) -> Iterator[tuple[tuple[float, float], ...]]:
    """Yield dark-module polygons with only exposed corners rounded."""
    for row, values in enumerate(modules):
        for column, dark in enumerate(values):
            if not dark:
                continue
            finder_part = _finder_part(len(modules), row, column)
            finder_style = finder_outer_style if finder_part == "outer" else finder_inner_style
            if finder_part and finder_style == "circle":
                continue
            radius = _module_radius(
                modules,
                row,
                column,
                corner_radius_percent,
                finder_radius_percent if finder_style == "rounded" else 0,
            )
            yield _module_polygon(modules, row, column, radius)

    for origin_x, origin_y in _finder_origins(len(modules)):
        if finder_outer_style == "circle":
            yield from _annulus_polygons(origin_x + 3.5, origin_y + 3.5, 3.5, 2.5)
        if finder_inner_style == "circle":
            yield _circle_polygon(origin_x + 3.5, origin_y + 3.5, 1.5)


def rounded_corner_wedges(
    modules: Sequence[Sequence[bool]],
    corner_radius_percent: int,
    finder_radius_percent: int | None = None,
) -> Iterator[tuple[tuple[float, float], ...]]:
    """Yield the cell-corner material needed around rounded knockout holes."""
    for row, values in enumerate(modules):
        for column, dark in enumerate(values):
            if not dark:
                continue
            radius = _module_radius(
                modules,
                row,
                column,
                corner_radius_percent,
                finder_radius_percent,
            )
            if radius <= 0:
                continue
            for corner, rounded in zip(("tl", "tr", "br", "bl"), _rounded_corners(modules, row, column)):
                if rounded:
                    yield _corner_wedge(row, column, radius, corner)


def knockout_background_polygons(
    module_count: int,
    margin: int,
    corner_radius_percent: int,
) -> tuple[tuple[tuple[float, float], ...], ...]:
    """Return a knockout border with a radius capped to its module margin."""
    if margin <= 0:
        return ()

    x0 = y0 = float(-margin)
    x1 = y1 = float(module_count + margin)
    radius = margin * corner_radius_percent / 100.0

    if radius <= 0:
        top = ((x0, y0), (x1, y0), (x1, 0.0), (x0, 0.0))
        bottom = ((x0, float(module_count)), (x1, float(module_count)), (x1, y1), (x0, y1))
    else:
        top = (
            (x0, 0.0),
            (x0, y0 + radius),
            *_arc_points(x0 + radius, y0 + radius, radius, 180, 270),
            *_arc_points(x1 - radius, y0 + radius, radius, 270, 360),
            (x1, 0.0),
        )
        bottom = (
            (x1, float(module_count)),
            (x1, y1 - radius),
            *_arc_points(x1 - radius, y1 - radius, radius, 0, 90),
            *_arc_points(x0 + radius, y1 - radius, radius, 90, 180),
            (x0, float(module_count)),
        )

    left = ((x0, 0.0), (0.0, 0.0), (0.0, float(module_count)), (x0, float(module_count)))
    right = (
        (float(module_count), 0.0),
        (x1, 0.0),
        (x1, float(module_count)),
        (float(module_count), float(module_count)),
    )
    return top, right, bottom, left


def knockout_outline_polygon(
    module_count: int,
    margin: int,
    corner_radius_percent: int,
) -> tuple[tuple[float, float], ...]:
    """Return the complete rounded knockout background outline."""
    x0 = y0 = float(-margin)
    x1 = y1 = float(module_count + margin)
    radius = margin * corner_radius_percent / 100.0
    if radius <= 0:
        return ((x0, y0), (x1, y0), (x1, y1), (x0, y1))
    return (
        *_arc_points(x0 + radius, y0 + radius, radius, 180, 270),
        *_arc_points(x1 - radius, y0 + radius, radius, 270, 360),
        *_arc_points(x1 - radius, y1 - radius, radius, 0, 90),
        *_arc_points(x0 + radius, y1 - radius, radius, 90, 180),
    )


def _module_radius(modules, row, column, data_percent, finder_percent):
    use_finder_radius = finder_percent is not None and _is_finder_module(
        len(modules), row, column
    )
    percent = finder_percent if use_finder_radius else data_percent
    return percent / 200.0


def _is_finder_module(count: int, row: int, column: int) -> bool:
    return (
        (row < 7 and column < 7)
        or (row < 7 and column >= count - 7)
        or (row >= count - 7 and column < 7)
    )


def _finder_part(count: int, row: int, column: int) -> str | None:
    for origin_x, origin_y in _finder_origins(count):
        local_x = column - origin_x
        local_y = row - origin_y
        if 0 <= local_x < 7 and 0 <= local_y < 7:
            if local_x in (0, 6) or local_y in (0, 6):
                return "outer"
            if 2 <= local_x <= 4 and 2 <= local_y <= 4:
                return "inner"
    return None


def _finder_origins(count: int):
    return ((0, 0), (count - 7, 0), (0, count - 7))


def _circle_polygon(center_x: float, center_y: float, radius: float, segments: int = 32):
    return tuple(
        (
            center_x + radius * math.cos(2 * math.pi * index / segments),
            center_y + radius * math.sin(2 * math.pi * index / segments),
        )
        for index in range(segments)
    )


def _annulus_polygons(center_x: float, center_y: float, outer_radius: float, inner_radius: float):
    segments = 32
    for index in range(segments):
        angle0 = 2 * math.pi * index / segments
        angle1 = 2 * math.pi * (index + 1) / segments
        yield (
            (center_x + outer_radius * math.cos(angle0), center_y + outer_radius * math.sin(angle0)),
            (center_x + outer_radius * math.cos(angle1), center_y + outer_radius * math.sin(angle1)),
            (center_x + inner_radius * math.cos(angle1), center_y + inner_radius * math.sin(angle1)),
            (center_x + inner_radius * math.cos(angle0), center_y + inner_radius * math.sin(angle0)),
        )


def _module_polygon(modules, row: int, column: int, radius: float):
    x0, y0 = float(column), float(row)
    x1, y1 = x0 + 1.0, y0 + 1.0
    tl, tr, br, bl = _rounded_corners(modules, row, column)
    if radius <= 0:
        return ((x0, y0), (x1, y0), (x1, y1), (x0, y1))

    points: list[tuple[float, float]] = []
    points.extend(_arc_points(x0 + radius, y0 + radius, radius, 180, 270) if tl else ((x0, y0),))
    points.extend(_arc_points(x1 - radius, y0 + radius, radius, 270, 360) if tr else ((x1, y0),))
    points.extend(_arc_points(x1 - radius, y1 - radius, radius, 0, 90) if br else ((x1, y1),))
    points.extend(_arc_points(x0 + radius, y1 - radius, radius, 90, 180) if bl else ((x0, y1),))
    return tuple(points)


def _rounded_corners(modules, row: int, column: int) -> tuple[bool, bool, bool, bool]:
    top = _is_dark(modules, row - 1, column)
    right = _is_dark(modules, row, column + 1)
    bottom = _is_dark(modules, row + 1, column)
    left = _is_dark(modules, row, column - 1)
    return not top and not left, not top and not right, not bottom and not right, not bottom and not left


def _is_dark(modules, row: int, column: int) -> bool:
    return 0 <= row < len(modules) and 0 <= column < len(modules[row]) and bool(modules[row][column])


def _arc_points(center_x: float, center_y: float, radius: float, start: int, end: int):
    return tuple(
        (
            center_x + radius * math.cos(math.radians(angle)),
            center_y + radius * math.sin(math.radians(angle)),
        )
        for angle in range(start, end + 1, 15)
    )


def _corner_wedge(row: int, column: int, radius: float, corner: str):
    x0, y0 = float(column), float(row)
    x1, y1 = x0 + 1.0, y0 + 1.0
    definitions = {
        "tl": ((x0, y0), (x0 + radius, y0 + radius), -90, -180),
        "tr": ((x1, y0), (x1 - radius, y0 + radius), 0, -90),
        "br": ((x1, y1), (x1 - radius, y1 - radius), 90, 0),
        "bl": ((x0, y1), (x0 + radius, y1 - radius), 180, 90),
    }
    corner_point, center, start, end = definitions[corner]
    step = -15 if end < start else 15
    arc = tuple(
        (
            center[0] + radius * math.cos(math.radians(angle)),
            center[1] + radius * math.sin(math.radians(angle)),
        )
        for angle in range(start, end + step, step)
    )
    return (corner_point, *arc)


def encode_metadata(settings: QrSettings) -> str:
    """Serialize editable settings into the QR footprint's settings field.

    Position, rotation, side and layer are deliberately absent: KiCad owns them on
    the footprint, so moving or rotating it natively can never go stale.
    """
    settings = settings.validated()
    payload = json.dumps(
        {
            "data": settings.data,
            "ecc": settings.error_correction,
            "size": settings.size_mm,
            "radius": settings.corner_radius_percent,
            "ko": settings.knockout,
            "margin": settings.knockout_margin_modules,
            "finder_radius": settings.finder_radius_percent,
            "ko_radius": settings.knockout_corner_radius_percent,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    packed = base64.urlsafe_b64encode(zlib.compress(payload, 9)).decode("ascii").rstrip("=")
    return METADATA_PREFIX + packed


def decode_metadata(
    text: str,
    *,
    layer_name: str,
    rotation_degrees: float = 0.0,
    size_mm: float | None = None,
) -> QrSettings | None:
    """Recover editable settings from a footprint field or a legacy group name.

    Legacy ``BQR1:`` group names carry no size, so the caller measures it and
    passes ``size_mm``.
    """
    if text.startswith(METADATA_PREFIX):
        packed = text[len(METADATA_PREFIX):]
    elif text.startswith(LEGACY_METADATA_PREFIX) and size_mm is not None:
        packed = text[len(LEGACY_METADATA_PREFIX):]
    else:
        return None

    try:
        packed += "=" * (-len(packed) % 4)
        payload = zlib.decompress(base64.urlsafe_b64decode(packed)).decode("utf-8")
        values = json.loads(payload)
        return QrSettings(
            data=values["data"],
            error_correction=values["ecc"],
            size_mm=values["size"] if text.startswith(METADATA_PREFIX) else size_mm,
            layer_name=layer_name,
            corner_radius_percent=values.get("radius", 0),
            knockout=values.get("ko", False),
            knockout_margin_modules=values.get("margin", 4),
            finder_radius_percent=_finder_radius_from_metadata(values),
            knockout_corner_radius_percent=values.get("ko_radius", 0),
            rotation_degrees=rotation_degrees,
        ).validated()
    except (KeyError, TypeError, ValueError, binascii.Error, zlib.error, json.JSONDecodeError):
        return None


def _finder_radius_from_metadata(values: dict) -> int:
    radius = values.get("finder_radius", 0)
    # Brief development builds stored separate finder shape choices. Preserve
    # their circular appearance when opening those groups with the unified
    # finder-rounding control.
    if not radius and "circle" in (
        values.get("finder_outer"),
        values.get("finder_inner"),
    ):
        return 100
    return radius

"""Shared KiCad polygon geometry for board artwork and the live preview."""

from __future__ import annotations

import math

import pcbnew

from .model import EncodedQr, QrSettings


_MODULE_UNITS = 10_000


def material_polygons(
    settings: QrSettings,
    encoded: EncodedQr,
) -> tuple[tuple[tuple[float, float], ...], ...]:
    """Return scale-safe simple polygons for the final placed material."""
    material = _dark_geometry(settings, encoded)
    if settings.knockout:
        margin = settings.knockout_margin_modules * _MODULE_UNITS
        radius = round(
            margin * settings.knockout_corner_radius_percent / 100
        )
        background = _rounded_rect(
            -margin,
            -margin,
            encoded.module_count * _MODULE_UNITS + margin,
            encoded.module_count * _MODULE_UNITS + margin,
            radius,
        )
        background.BooleanSubtract(material)
        material = background

    # PCB_SHAPE is a simple-polygon board item. Fracturing replaces holes with
    # explicit bridges so KiCad's native scale tool cannot cross-connect them.
    material.Fracture()
    polygons = []
    for index in range(material.OutlineCount()):
        points = material.Outline(index).CPoints()
        polygons.append(tuple(
            (point.x / _MODULE_UNITS, point.y / _MODULE_UNITS)
            for point in points
        ))
    return tuple(polygons)


def _dark_geometry(settings: QrSettings, encoded: EncodedQr):
    count = encoded.module_count
    data = pcbnew.SHAPE_POLY_SET()
    for row, values in enumerate(encoded.modules):
        for column, dark in enumerate(values):
            if dark and not _inside_finder(count, row, column):
                data.AddOutline(_rectangle_chain(
                    column * _MODULE_UNITS,
                    row * _MODULE_UNITS,
                    (column + 1) * _MODULE_UNITS,
                    (row + 1) * _MODULE_UNITS,
                ))
    data.Simplify()

    data_radius = round(
        _MODULE_UNITS * settings.corner_radius_percent / 200
    )
    if data_radius:
        data = data.Fillet(data_radius, _curve_error(data_radius))

    finder_percent = settings.finder_radius_percent / 100
    for origin_x, origin_y in _finder_origins(count):
        x = origin_x * _MODULE_UNITS
        y = origin_y * _MODULE_UNITS
        outer = _rounded_rect(
            x,
            y,
            x + 7 * _MODULE_UNITS,
            y + 7 * _MODULE_UNITS,
            round(3.5 * _MODULE_UNITS * finder_percent),
        )
        # The white gap is a one-module inset from the outer boundary. Its
        # radius therefore needs to be one module smaller, not independently
        # scaled, so the dark finder ring keeps a constant apparent width.
        inner_radius = max(
            0,
            round(3.5 * _MODULE_UNITS * finder_percent) - _MODULE_UNITS,
        )
        gap = _rounded_rect(
            x + _MODULE_UNITS,
            y + _MODULE_UNITS,
            x + 6 * _MODULE_UNITS,
            y + 6 * _MODULE_UNITS,
            inner_radius,
        )
        center = _rounded_rect(
            x + 2 * _MODULE_UNITS,
            y + 2 * _MODULE_UNITS,
            x + 5 * _MODULE_UNITS,
            y + 5 * _MODULE_UNITS,
            round(1.5 * _MODULE_UNITS * finder_percent),
        )
        outer.BooleanSubtract(gap)
        outer.BooleanAdd(center)
        data.BooleanAdd(outer)
    return data


def _rounded_rect(x0: int, y0: int, x1: int, y1: int, radius: int):
    radius = min(radius, (x1 - x0) // 2, (y1 - y0) // 2)
    if radius <= 0:
        result = pcbnew.SHAPE_POLY_SET()
        result.AddOutline(_rectangle_chain(x0, y0, x1, y1))
        return result

    points = []
    for center_x, center_y, start in (
        (x0 + radius, y0 + radius, 180),
        (x1 - radius, y0 + radius, 270),
        (x1 - radius, y1 - radius, 0),
        (x0 + radius, y1 - radius, 90),
    ):
        for angle in range(start, start + 91, 15):
            points.append(pcbnew.VECTOR2I(
                round(center_x + radius * math.cos(math.radians(angle))),
                round(center_y + radius * math.sin(math.radians(angle))),
            ))
    chain = pcbnew.SHAPE_LINE_CHAIN()
    for point in points:
        chain.Append(point)
    chain.SetClosed(True)
    result = pcbnew.SHAPE_POLY_SET()
    result.AddOutline(chain)
    return result


def _rectangle_chain(x0: int, y0: int, x1: int, y1: int):
    chain = pcbnew.SHAPE_LINE_CHAIN()
    for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
        chain.Append(pcbnew.VECTOR2I(x, y))
    chain.SetClosed(True)
    return chain


def _curve_error(radius: int) -> int:
    return max(1, radius // 50)


def _inside_finder(count: int, row: int, column: int) -> bool:
    return any(
        origin_x <= column < origin_x + 7
        and origin_y <= row < origin_y + 7
        for origin_x, origin_y in _finder_origins(count)
    )


def _finder_origins(count: int):
    return ((0, 0), (count - 7, 0), (0, count - 7))

"""Persistent defaults for newly-created Better QR Codes."""

from __future__ import annotations

import json
from pathlib import Path

from .model import QrSettings


def load_last_settings(
    default_layer: str,
    available_layers: set[str],
    path: Path | None = None,
) -> QrSettings:
    fallback = QrSettings("https://example.com", "L", 15.0, default_layer)
    try:
        values = json.loads((path or _settings_path()).read_text(encoding="utf-8"))
        layer_name = values.get("layer", default_layer)
        if layer_name not in available_layers:
            layer_name = default_layer
        return QrSettings(
            data=fallback.data,
            error_correction=values.get("ecc", fallback.error_correction),
            size_mm=values.get("size_mm", fallback.size_mm),
            layer_name=layer_name,
            corner_radius_percent=values.get("radius", 0),
            knockout=values.get("knockout", False),
            knockout_margin_modules=values.get("margin", 4),
            finder_radius_percent=_finder_radius(values),
            knockout_corner_radius_percent=values.get("knockout_radius", 0),
        ).validated()
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
        return fallback


def save_last_settings(settings: QrSettings, path: Path | None = None) -> None:
    settings = settings.validated()
    destination = path or _settings_path()
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        temporary.write_text(
            json.dumps(
                {
                    "ecc": settings.error_correction,
                    "size_mm": settings.size_mm,
                    "layer": settings.layer_name,
                    "radius": settings.corner_radius_percent,
                    "knockout": settings.knockout,
                    "margin": settings.knockout_margin_modules,
                    "finder_radius": settings.finder_radius_percent,
                    "knockout_radius": settings.knockout_corner_radius_percent,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        temporary.replace(destination)
    except OSError:
        pass


def _settings_path() -> Path:
    from .appearance import _settings_dir

    return _settings_dir() / "better_qr_codes.json"


def _finder_radius(values: dict) -> int:
    radius = values.get("finder_radius", 0)
    if not radius and "circle" in (
        values.get("finder_outer"),
        values.get("finder_inner"),
    ):
        return 100
    return radius

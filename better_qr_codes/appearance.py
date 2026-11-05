"""KiCad layer choices and color-theme helpers."""

from __future__ import annotations

import json
import os
import platform
import re
from dataclasses import dataclass
from pathlib import Path

import pcbnew


Rgb = tuple[int, int, int]


@dataclass(frozen=True)
class LayerOption:
    name: str
    layer_id: int
    color: Rgb
    enabled: bool
    # Back layers are built front-side and flipped, so the code mirrors.
    back_side: bool = False


@dataclass(frozen=True)
class ThemeColors:
    background: Rgb
    grid: Rgb
    board: dict


_DEFAULT_BACKGROUND = (40, 40, 40)
_DEFAULT_GRID = (90, 90, 90)
_FALLBACK_LAYER_COLORS = (
    (220, 55, 55),
    (75, 150, 220),
    (235, 200, 70),
    (70, 200, 190),
    (220, 100, 190),
    (170, 170, 170),
)


def load_theme_colors() -> ThemeColors:
    """Load the PCB editor's selected theme, falling back to a dark preview."""
    try:
        settings_dir = _settings_dir()
        settings = json.loads((settings_dir / "pcbnew.json").read_text(encoding="utf-8"))
        theme_name = settings.get("appearance", {}).get("color_theme") or "user"
        theme = json.loads((settings_dir / "colors" / f"{theme_name}.json").read_text(encoding="utf-8"))
        board = theme.get("board", {})
        return ThemeColors(
            _parse_color(board.get("background"), _DEFAULT_BACKGROUND),
            _parse_color(board.get("grid"), _DEFAULT_GRID),
            board,
        )
    except (AttributeError, KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
        return ThemeColors(_DEFAULT_BACKGROUND, _DEFAULT_GRID, {})


def _settings_dir() -> Path:
    version = ".".join(str(pcbnew.Version()).split("-")[0].split(".")[:2])
    configured = os.environ.get("KICAD_CONFIG_HOME")
    if configured:
        return Path(configured) / version
    if platform.system() == "Windows":
        return Path(os.environ["APPDATA"]) / "kicad" / version
    if platform.system() == "Darwin":
        return Path.home() / "Library" / "Preferences" / "kicad" / version
    config_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return config_home / "kicad" / version


def available_layers(board, theme: ThemeColors | None = None) -> list[LayerOption]:
    """Return active physical board layers in KiCad's native UI order."""
    theme = theme or load_theme_colors()
    layers: list[LayerOption] = []
    for layer in pcbnew.LSET.AllLayersMask().UIOrder():
        layer_id = int(layer)
        try:
            name = str(board.GetLayerName(layer_id))
            enabled = bool(board.IsLayerEnabled(layer_id))
        except (TypeError, RuntimeError):
            continue
        if not enabled:
            continue
        layers.append(LayerOption(
            name,
            layer_id,
            _layer_color(layer_id, theme),
            enabled,
            bool(pcbnew.IsBackLayer(layer_id)),
        ))
    return layers


def _layer_color(layer_id: int, theme: ThemeColors) -> Rgb:
    canonical = str(pcbnew.LSET.Name(layer_id))
    key = _theme_key(canonical)
    value = theme.board
    for part in key.split("."):
        value = value.get(part) if isinstance(value, dict) else None
    return _parse_color(value, _FALLBACK_LAYER_COLORS[layer_id % len(_FALLBACK_LAYER_COLORS)])


def _theme_key(layer_name: str) -> str:
    if layer_name == "F.Cu":
        return "copper.f"
    if layer_name == "B.Cu":
        return "copper.b"
    match = re.fullmatch(r"In(\d+)\.Cu", layer_name)
    if match:
        return f"copper.in{match.group(1)}"
    match = re.fullmatch(r"User\.(\d+)", layer_name)
    if match:
        return f"user_{match.group(1)}"
    return {
        "F.Adhes": "f_adhes",
        "B.Adhes": "b_adhes",
        "F.Paste": "f_paste",
        "B.Paste": "b_paste",
        "F.SilkS": "f_silks",
        "B.SilkS": "b_silks",
        "F.Mask": "f_mask",
        "B.Mask": "b_mask",
        "Dwgs.User": "dwgs_user",
        "Cmts.User": "cmts_user",
        "Eco1.User": "eco1_user",
        "Eco2.User": "eco2_user",
        "Edge.Cuts": "edge_cuts",
        "Margin": "margin",
        "F.CrtYd": "f_crtyd",
        "B.CrtYd": "b_crtyd",
        "F.Fab": "f_fab",
        "B.Fab": "b_fab",
    }.get(layer_name, layer_name.lower().replace(".", "_"))


def _parse_color(value, fallback: Rgb) -> Rgb:
    if not isinstance(value, str):
        return fallback
    components = re.match(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)", value)
    if not components:
        return fallback
    return tuple(int(component) for component in components.groups())

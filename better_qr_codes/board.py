"""KiCad board integration for plugin-owned, editable QR artwork."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pcbnew

from .model import EncodedQr, QrSettings, dark_runs, decode_metadata, encode_metadata


# Keep newly-created SWIG wrappers alive. KiCad 10's group member iterator only
# restores concrete Python types after a save/reload, while loaded groups work normally.
_LIVE_ITEMS: dict[str, list] = {}


@dataclass(frozen=True)
class EditableQr:
    group: object
    settings: QrSettings
    center: object


def selected_editable_qr(board) -> EditableQr | None:
    """Find a Better QR Codes group from the current KiCad selection."""
    for selected in pcbnew.GetCurrentSelection():
        candidates = [selected]
        try:
            parent_group = selected.GetParentGroup()
            if parent_group:
                candidates.append(parent_group)
        except (AttributeError, RuntimeError):
            pass

        for candidate in candidates:
            editable = _editable_from_group(candidate, board)
            if editable is not None:
                return editable
    return None


def _editable_from_group(candidate, board) -> EditableQr | None:
    try:
        if not pcbnew.PCB_GROUP.ClassOf(candidate):
            return None
        items = _group_items(board, candidate)
        if not items:
            return None
        artwork = items[0]
        min_x = min(min(item.GetStart().x, item.GetEnd().x) for item in items)
        min_y = min(min(item.GetStart().y, item.GetEnd().y) for item in items)
        max_x = max(max(item.GetStart().x, item.GetEnd().x) for item in items)
        max_y = max(max(item.GetStart().y, item.GetEnd().y) for item in items)
        size_mm = max(pcbnew.ToMM(max_x - min_x), pcbnew.ToMM(max_y - min_y))
        layer_name = str(artwork.GetLayerName())
        settings = decode_metadata(str(candidate.GetName()), size_mm=size_mm, layer_name=layer_name)
        if settings is None:
            return None
        return EditableQr(candidate, settings, pcbnew.VECTOR2I((min_x + max_x) // 2, (min_y + max_y) // 2))
    except (AttributeError, RuntimeError, TypeError, ValueError):
        return None


def default_position(board):
    """Choose a predictable initial position near the existing board artwork."""
    bbox = board.ComputeBoundingBox(False, False)
    if bbox.GetWidth() > 0 and bbox.GetHeight() > 0:
        return bbox.GetCenter()
    return pcbnew.VECTOR2I(pcbnew.FromMM(100), pcbnew.FromMM(100))


def add_qr(board, settings: QrSettings, encoded: EncodedQr, position):
    group = pcbnew.PCB_GROUP(board)
    group.SetName(encode_metadata(settings))
    board.Add(group)

    artwork_items = list(_make_artwork(board, settings, encoded, position))
    for artwork in artwork_items:
        board.Add(artwork)
        group.AddItem(artwork)
    _LIVE_ITEMS[_group_key(group)] = artwork_items
    return group


def update_qr(board, editable: EditableQr, settings: QrSettings, encoded: EncodedQr):
    group = editable.group
    old_items = _group_items(board, group)
    group.RemoveAll()
    for item in old_items:
        board.Delete(item)

    artwork_items = list(_make_artwork(board, settings, encoded, editable.center))
    for artwork in artwork_items:
        board.Add(artwork)
        group.AddItem(artwork)
    _LIVE_ITEMS[_group_key(group)] = artwork_items
    group.SetName(encode_metadata(settings))
    return group


def _group_items(board, group) -> list:
    """Return concrete member wrappers for both loaded and newly-created groups."""
    cached = _LIVE_ITEMS.get(_group_key(group))
    if cached is not None:
        return list(cached)
    return list(group.GetItems())


def _group_key(group) -> str:
    return str(group.m_Uuid.AsString())


def _make_artwork(board, settings: QrSettings, encoded: EncodedQr, center):
    size_iu = pcbnew.FromMM(settings.size_mm)
    count = encoded.module_count
    left = center.x - size_iu // 2
    top = center.y - size_iu // 2

    for row, start, end in dark_runs(encoded.modules):
        x0 = left + round(start * size_iu / count)
        x1 = left + round(end * size_iu / count)
        y0 = top + round(row * size_iu / count)
        y1 = top + round((row + 1) * size_iu / count)
        artwork = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_RECT)
        artwork.SetStart(pcbnew.VECTOR2I(x0, y0))
        artwork.SetEnd(pcbnew.VECTOR2I(x1, y1))
        artwork.SetFilled(True)
        artwork.SetWidth(0)
        artwork.SetLayer(board.GetLayerID(settings.layer_name))
        yield artwork


def select_group(group) -> None:
    for item in pcbnew.GetCurrentSelection():
        try:
            item.ClearSelected()
        except AttributeError:
            pass
    group.SetSelected()
    pcbnew.Refresh()

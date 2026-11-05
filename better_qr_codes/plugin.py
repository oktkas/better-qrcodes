"""KiCad toolbar action for creating and editing Better QR Codes."""

from __future__ import annotations

import json
import re
import sys
import threading
from dataclasses import replace
from pathlib import Path

import pcbnew
import wx

from .appearance import available_layers, load_theme_colors
from .board import add_qr, default_position, select_item, selected_editable_qr, update_qr
from .dialog import BetterQrDialog
from .ipc import IpcError, interactive_move
from .model import QrSettings, flipped_rotation
from .preferences import load_last_settings, save_last_settings


_DOUBLE_CLICK_FILTER = None
_EDITOR_OPEN = False


class BetterQrCodesPlugin(pcbnew.ActionPlugin):
    def defaults(self):
        self.name = "Better QR Codes"
        self.category = "PCB Art"
        self.description = "Create editable QR-code artwork"
        self.show_toolbar_button = True
        self.icon_file_name = str(Path(__file__).with_name("icon.png"))

    def Run(self):
        open_editor()


def open_editor(*, selected_only: bool = False):
    """Open the add/edit dialog for the current board selection."""
    global _EDITOR_OPEN
    if _EDITOR_OPEN:
        return

    board = pcbnew.GetBoard()
    if board is None:
        if not selected_only:
            wx.MessageBox("Open a PCB before using Better QR Codes.", "Better QR Codes", wx.OK | wx.ICON_INFORMATION)
        return

    editable = selected_editable_qr(board)
    if selected_only and editable is None:
        return

    theme = load_theme_colors()
    layers = available_layers(board, theme)
    if not layers:
        wx.MessageBox("The board has no available layers.", "Better QR Codes", wx.OK | wx.ICON_ERROR)
        return
    default_layer = next(
        (option.name for option in layers if option.layer_id == int(pcbnew.F_SilkS)),
        layers[0].name,
    )
    if editable is not None:
        initial = editable.settings
    else:
        initial = load_last_settings(default_layer, {option.name for option in layers})
        if any(option.back_side and option.name == initial.layer_name for option in layers):
            # Upright when viewed from below, like any footprint KiCad flips.
            initial = replace(initial, rotation_degrees=flipped_rotation(0.0))

    _EDITOR_OPEN = True
    dialog = None
    try:
        dialog = BetterQrDialog(None, layers, theme, initial, editing=editable is not None)
        if dialog.ShowModal() != wx.ID_OK:
            return
        settings, encoded = dialog.result
        pointer = wx.GetMousePosition()
    finally:
        if dialog is not None:
            dialog.Destroy()
        _EDITOR_OPEN = False

    if editable is None:
        # Create the code under the cursor so picking it up does not jump.
        position = _cursor_board_position(board) or default_position(board)
        item = add_qr(board, settings, encoded, position)
    else:
        item = update_qr(board, editable, settings, encoded)
    select_item(item)
    if editable is None:
        # Hand the new code to the user like a freshly placed footprint.
        _hand_to_user(board, item, pointer)
    save_last_settings(settings)


class BetterQrDoubleClickFilter(wx.EventFilter):
    """Route double-clicks on plugin-owned QR footprints (and legacy groups) to
    the plugin editor instead of KiCad's footprint properties dialog."""

    def FilterEvent(self, event):
        if event.GetEventType() != wx.EVT_LEFT_DCLICK.typeId or _EDITOR_OPEN:
            return self.Event_Skip
        source = event.GetEventObject()
        if source is None:
            return self.Event_Skip
        top_level = wx.GetTopLevelParent(source)
        size = source.GetClientSize()
        if (
            isinstance(top_level, wx.Dialog)
            or size.width < 200
            or size.height < 200
        ):
            return self.Event_Skip
        board = pcbnew.GetBoard()
        if board is None or selected_editable_qr(board) is None:
            return self.Event_Skip
        wx.CallAfter(open_editor, selected_only=True)
        return self.Event_Processed


def install_double_click_filter() -> None:
    global _DOUBLE_CLICK_FILTER
    if _DOUBLE_CLICK_FILTER is None:
        _DOUBLE_CLICK_FILTER = BetterQrDoubleClickFilter()
        wx.EvtHandler.AddFilter(_DOUBLE_CLICK_FILTER)



def _hand_to_user(board, item, pointer) -> None:
    """Start KiCad's interactive move on ``item`` through the IPC API.

    The request runs on a worker thread because KiCad answers API calls on its
    main thread. KiCad's Move tool warps the pointer to the item's anchor, so
    the pointer is put back where the user clicked OK; the item follows it.
    Without the API server the code simply stays where it was placed.
    """
    item_uuid = str(item.m_Uuid.AsString())
    board_filename = str(board.GetFileName())

    def worker():
        try:
            interactive_move(item_uuid, board_filename)
        except (IpcError, OSError) as error:
            print(f"Better QR Codes: could not start interactive move: {error}", file=sys.stderr)
            return
        wx.CallAfter(wx.CallLater, 150, _warp_pointer, pointer)

    threading.Thread(target=worker, name="better-qr-codes-move", daemon=True).start()


def _pcb_frame():
    return wx.FindWindowByName("PcbFrame") or next(
        (
            window
            for window in wx.GetTopLevelWindows()
            if window.IsShown() and "PCB Editor" in window.GetTitle()
        ),
        None,
    )


def _warp_pointer(screen_position) -> None:
    frame = _pcb_frame()
    if frame is not None and wx.GetMousePosition() != screen_position:
        frame.WarpPointer(*frame.ScreenToClient(screen_position))


_STATUS_XY = re.compile(r"^\s*X\s+(-?[\d.,]+)\s+Y\s+(-?[\d.,]+)")


def _cursor_board_position(board):
    # Best effort only: never let this break adding a code.
    try:
        return _read_cursor_board_position(board)
    except Exception as error:  # noqa: BLE001 - wx/KiCad raise varied types
        print(f"Better QR Codes: cursor position unavailable: {error!r}", file=sys.stderr)
        return None


def _read_cursor_board_position(board):
    """Read the cursor's board position from the PCB Editor status bar.

    The Python API has no view transform, but the status bar shows the cursor
    position in display units and origin. Nudge the pointer so the canvas
    refreshes it, then undo KiCad's display origin and axis settings. Returns
    None when the reading is unavailable; the pointer restore in
    ``_hand_to_user`` then still brings the code to the cursor.
    """
    frame = _pcb_frame()
    status_bar = frame.GetStatusBar() if frame is not None else None
    if status_bar is None:
        return None

    def reading():
        for index in range(status_bar.GetFieldsCount()):
            match = _STATUS_XY.match(status_bar.GetStatusText(index))
            if match:
                return match.groups()
        return None

    before = reading()
    pointer = wx.GetMousePosition()
    # KiCad's wxPython has no UIActionSimulator; warping the real pointer makes
    # the OS deliver genuine motion events to the canvas under it.
    client = frame.ScreenToClient(pointer)
    for dx in (1, 0):
        frame.WarpPointer(client.x + dx, client.y)
        for _ in range(3):
            wx.GetApp().Yield(True)
    after = reading()
    # Unchanged means the pointer is not over the canvas (or nothing updated).
    if after is None or after == before:
        return None

    try:
        units = pcbnew.GetUserUnits()
        x, y = (
            pcbnew.FromUserUnit(units, float(value.replace(",", ".")))
            for value in after
        )
    except (AttributeError, TypeError, ValueError):
        return None

    origin_x = origin_y = 0
    invert_x = invert_y = False
    try:
        from .appearance import _settings_dir

        values = json.loads((_settings_dir() / "pcbnew.json").read_text(encoding="utf-8"))
        settings = values.get("pcb_display", {})
        mode = settings.get("origin_mode", 0)
        invert_x = bool(settings.get("origin_invert_x_axis", False))
        invert_y = bool(settings.get("origin_invert_y_axis", False))
        design = board.GetDesignSettings()
        origin = {1: design.GetAuxOrigin, 2: design.GetGridOrigin}.get(mode)
        if origin is not None:
            origin_x, origin_y = origin().x, origin().y
    except (AttributeError, OSError, TypeError, ValueError, json.JSONDecodeError):
        pass

    return pcbnew.VECTOR2I(
        round(origin_x + (-x if invert_x else x)),
        round(origin_y + (-y if invert_y else y)),
    )

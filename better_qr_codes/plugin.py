"""KiCad toolbar action for creating and editing Better QR Codes."""

from __future__ import annotations

from pathlib import Path

import pcbnew
import wx

from .appearance import available_layers, load_theme_colors
from .board import add_qr, default_position, select_group, selected_editable_qr, update_qr
from .dialog import BetterQrDialog
from .model import QrSettings
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
    initial = editable.settings if editable else load_last_settings(
        default_layer,
        {option.name for option in layers},
    )

    _EDITOR_OPEN = True
    dialog = None
    try:
        dialog = BetterQrDialog(None, layers, theme, initial, editing=editable is not None)
        if dialog.ShowModal() != wx.ID_OK:
            return
        settings, encoded = dialog.result
    finally:
        if dialog is not None:
            dialog.Destroy()
        _EDITOR_OPEN = False

    if editable is None:
        group = add_qr(board, settings, encoded, default_position(board))
    else:
        group = update_qr(board, editable, settings, encoded)
    select_group(group)
    save_last_settings(settings)


class BetterQrDoubleClickFilter(wx.EventFilter):
    """Route double-clicks on plugin-owned groups to their editor."""

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

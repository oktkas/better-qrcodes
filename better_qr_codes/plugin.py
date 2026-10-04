"""KiCad toolbar action for creating and editing Better QR Codes."""

from __future__ import annotations

from pathlib import Path

import pcbnew
import wx

from .board import add_qr, default_position, enabled_layers, select_group, selected_editable_qr, update_qr
from .dialog import BetterQrDialog
from .model import QrSettings


class BetterQrCodesPlugin(pcbnew.ActionPlugin):
    def defaults(self):
        self.name = "Better QR Codes"
        self.category = "PCB Art"
        self.description = "Create editable QR-code artwork"
        self.show_toolbar_button = True
        self.icon_file_name = str(Path(__file__).with_name("icon.png"))

    def Run(self):
        board = pcbnew.GetBoard()
        if board is None:
            wx.MessageBox("Open a PCB before using Better QR Codes.", self.name, wx.OK | wx.ICON_INFORMATION)
            return

        layers = enabled_layers(board)
        if not layers:
            wx.MessageBox("The board has no enabled layers.", self.name, wx.OK | wx.ICON_ERROR)
            return

        editable = selected_editable_qr(board)
        default_layer = next(
            (name for name, layer_id in layers if layer_id == int(pcbnew.F_SilkS)),
            layers[0][0],
        )
        initial = editable.settings if editable else QrSettings("https://example.com", "M", 20.0, default_layer)

        dialog = BetterQrDialog(None, layers, initial, editing=editable is not None)
        try:
            if dialog.ShowModal() != wx.ID_OK:
                return
            settings, encoded = dialog.result
        finally:
            dialog.Destroy()

        if editable is None:
            group = add_qr(board, settings, encoded, default_position(board))
        else:
            group = update_qr(board, editable, settings, encoded)

        select_group(group)

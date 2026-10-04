"""wxPython dialog and live preview for Better QR Codes."""

from __future__ import annotations

import wx

from .model import EncodedQr, QrSettings, QrSettingsError, encode_qr


ERROR_CHOICES = (
    ("L — about 7%", "L"),
    ("M — about 15%", "M"),
    ("Q — about 25%", "Q"),
    ("H — about 30%", "H"),
)


class QrPreview(wx.Panel):
    def __init__(self, parent):
        super().__init__(parent, size=(330, 330), style=wx.BORDER_SIMPLE)
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self._encoded: EncodedQr | None = None
        self.Bind(wx.EVT_PAINT, self._on_paint)

    def set_qr(self, encoded: EncodedQr | None) -> None:
        self._encoded = encoded
        self.Refresh()

    def _on_paint(self, _event) -> None:
        dc = wx.AutoBufferedPaintDC(self)
        dc.SetBackground(wx.Brush(wx.Colour(245, 245, 245)))
        dc.Clear()

        if self._encoded is None:
            return

        width, height = self.GetClientSize()
        quiet_zone = 4
        total = self._encoded.module_count + quiet_zone * 2
        scale = min(width, height) / total
        origin_x = (width - total * scale) / 2 + quiet_zone * scale
        origin_y = (height - total * scale) / 2 + quiet_zone * scale

        dc.SetPen(wx.TRANSPARENT_PEN)
        dc.SetBrush(wx.BLACK_BRUSH)
        for y, row in enumerate(self._encoded.modules):
            for x, dark in enumerate(row):
                if dark:
                    x0 = round(origin_x + x * scale)
                    y0 = round(origin_y + y * scale)
                    x1 = round(origin_x + (x + 1) * scale)
                    y1 = round(origin_y + (y + 1) * scale)
                    dc.DrawRectangle(x0, y0, max(1, x1 - x0), max(1, y1 - y0))


class BetterQrDialog(wx.Dialog):
    def __init__(self, parent, layers, initial: QrSettings, *, editing: bool):
        title = "Edit Better QR Code" if editing else "Add Better QR Code"
        super().__init__(parent, title=title, style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)

        self._layers = layers
        self._encoded: EncodedQr | None = None
        self._settings: QrSettings | None = None
        self._update_later: wx.CallLater | None = None

        root = wx.BoxSizer(wx.VERTICAL)
        body = wx.BoxSizer(wx.HORIZONTAL)
        form = wx.FlexGridSizer(cols=2, vgap=10, hgap=12)
        form.AddGrowableCol(1, 1)

        form.Add(wx.StaticText(self, label="Content"), 0, wx.ALIGN_TOP | wx.TOP, 5)
        self.data = wx.TextCtrl(self, value=initial.data, style=wx.TE_MULTILINE, size=(310, 90))
        form.Add(self.data, 1, wx.EXPAND)

        form.Add(wx.StaticText(self, label="Error correction"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.error = wx.Choice(self, choices=[label for label, _value in ERROR_CHOICES])
        self.error.SetSelection(next(
            (index for index, (_label, value) in enumerate(ERROR_CHOICES) if value == initial.error_correction),
            1,
        ))
        form.Add(self.error, 1, wx.EXPAND)

        form.Add(wx.StaticText(self, label="Layer"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.layer = wx.Choice(self, choices=[name for name, _layer_id in layers])
        layer_index = next((i for i, (name, _id) in enumerate(layers) if name == initial.layer_name), 0)
        self.layer.SetSelection(layer_index)
        form.Add(self.layer, 1, wx.EXPAND)

        form.Add(wx.StaticText(self, label="Size"), 0, wx.ALIGN_CENTER_VERTICAL)
        size_row = wx.BoxSizer(wx.HORIZONTAL)
        self.size = wx.SpinCtrlDouble(self, min=1.0, max=500.0, initial=initial.size_mm, inc=0.5)
        self.size.SetDigits(2)
        size_row.Add(self.size, 1, wx.EXPAND)
        size_row.Add(wx.StaticText(self, label=" mm"), 0, wx.ALIGN_CENTER_VERTICAL)
        form.Add(size_row, 1, wx.EXPAND)

        self.info = wx.StaticText(self, label="")
        form.Add((0, 0))
        form.Add(self.info, 0, wx.EXPAND)

        self.error_text = wx.StaticText(self, label="")
        self.error_text.SetForegroundColour(wx.Colour(190, 35, 35))
        form.Add((0, 0))
        form.Add(self.error_text, 0, wx.EXPAND)

        body.Add(form, 1, wx.ALL | wx.EXPAND, 16)
        self.preview = QrPreview(self)
        body.Add(self.preview, 0, wx.TOP | wx.RIGHT | wx.BOTTOM, 16)
        root.Add(body, 1, wx.EXPAND)

        buttons = self.CreateSeparatedButtonSizer(wx.OK | wx.CANCEL)
        self.ok_button = self.FindWindowById(wx.ID_OK)
        self.ok_button.SetLabel("Update QR Code" if editing else "Add to Board")
        root.Add(buttons, 0, wx.ALL | wx.EXPAND, 12)

        self.SetSizerAndFit(root)
        self.SetMinSize(self.GetSize())

        for control in (self.data, self.error, self.layer, self.size):
            control.Bind(wx.EVT_TEXT, self._schedule_update)
            control.Bind(wx.EVT_CHOICE, self._schedule_update)
            control.Bind(wx.EVT_SPINCTRLDOUBLE, self._schedule_update)
        self.Bind(wx.EVT_BUTTON, self._on_ok, id=wx.ID_OK)

        self._refresh_preview()
        self.data.SetFocus()

    @property
    def result(self) -> tuple[QrSettings, EncodedQr]:
        if self._settings is None or self._encoded is None:
            raise RuntimeError("The dialog has no valid QR code result")
        return self._settings, self._encoded

    def _schedule_update(self, event) -> None:
        event.Skip()
        if self._update_later is not None:
            self._update_later.Stop()
        self._update_later = wx.CallLater(120, self._refresh_preview)

    def _read_settings(self) -> QrSettings:
        error_index = max(0, self.error.GetSelection())
        layer_index = max(0, self.layer.GetSelection())
        return QrSettings(
            data=self.data.GetValue(),
            error_correction=ERROR_CHOICES[error_index][1],
            size_mm=self.size.GetValue(),
            layer_name=self._layers[layer_index][0],
        )

    def _refresh_preview(self) -> None:
        try:
            settings = self._read_settings().validated()
            encoded = encode_qr(settings)
            module_size = settings.size_mm / encoded.module_count
            self.info.SetLabel(
                f"Version {encoded.version} · {encoded.module_count}×{encoded.module_count} modules · "
                f"{module_size:.3f} mm/module"
            )
            self.error_text.SetLabel("")
            self._settings = settings
            self._encoded = encoded
            self.preview.set_qr(encoded)
            self.ok_button.Enable(True)
        except (QrSettingsError, ValueError) as error:
            self.info.SetLabel("")
            self.error_text.SetLabel(str(error))
            self._settings = None
            self._encoded = None
            self.preview.set_qr(None)
            self.ok_button.Enable(False)
        self.Layout()

    def _on_ok(self, _event) -> None:
        self._refresh_preview()
        if self._settings is not None:
            self.EndModal(wx.ID_OK)


"""wxPython dialog and live preview for Better QR Codes."""

from __future__ import annotations

import wx
import wx.adv

from .appearance import LayerOption, ThemeColors
from .model import EncodedQr, QrSettings, QrSettingsError, dark_runs, encode_qr


ERROR_CHOICES = (
    ("L — about 7%", "L"),
    ("M — about 15%", "M"),
    ("Q — about 25%", "Q"),
    ("H — about 30%", "H"),
)


class QrPreview(wx.Panel):
    def __init__(self, parent, theme: ThemeColors):
        super().__init__(parent, size=(330, 330), style=wx.BORDER_SIMPLE)
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self._encoded: EncodedQr | None = None
        self._module_color = (255, 255, 255)
        self._background = theme.background
        self._grid = tuple(
            round(background * 0.75 + grid * 0.25)
            for background, grid in zip(theme.background, theme.grid)
        )
        self.Bind(wx.EVT_PAINT, self._on_paint)

    def set_qr(self, encoded: EncodedQr | None, color: tuple[int, int, int]) -> None:
        self._encoded = encoded
        self._module_color = color
        self.Refresh()

    def _on_paint(self, _event) -> None:
        dc = wx.AutoBufferedPaintDC(self)
        dc.SetBackground(wx.Brush(wx.Colour(*self._background)))
        dc.Clear()

        dot_color = wx.Colour(*self._grid)
        dc.SetPen(wx.Pen(dot_color))
        dc.SetBrush(wx.Brush(dot_color))
        for x in range(8, self.GetClientSize().width, 16):
            for y in range(8, self.GetClientSize().height, 16):
                dc.DrawCircle(x, y, 1)

        if self._encoded is None:
            return

        width, height = self.GetClientSize()
        quiet_zone = 4
        total = self._encoded.module_count + quiet_zone * 2
        scale = min(width, height) / total
        origin_x = (width - total * scale) / 2 + quiet_zone * scale
        origin_y = (height - total * scale) / 2 + quiet_zone * scale

        module_color = wx.Colour(*self._module_color)
        dc.SetPen(wx.Pen(module_color))
        dc.SetBrush(wx.Brush(module_color))
        for row, start, end in dark_runs(self._encoded.modules):
            x0 = round(origin_x + start * scale)
            y0 = round(origin_y + row * scale)
            x1 = round(origin_x + end * scale)
            y1 = round(origin_y + (row + 1) * scale)
            dc.DrawRectangle(x0, y0, max(1, x1 - x0), max(1, y1 - y0))


class BetterQrDialog(wx.Dialog):
    def __init__(
        self,
        parent,
        layers: list[LayerOption],
        theme: ThemeColors,
        initial: QrSettings,
        *,
        editing: bool,
    ):
        title = "Edit Better QR Code" if editing else "Add Better QR Code"
        super().__init__(parent, title=title, style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)

        self._layers = layers
        self._encoded: EncodedQr | None = None
        self._settings: QrSettings | None = None
        self._update_later: wx.CallLater | None = None

        root = wx.BoxSizer(wx.VERTICAL)
        root.Add(wx.StaticText(self, label="Content"), 0, wx.LEFT | wx.RIGHT | wx.TOP, 16)
        self.data = wx.TextCtrl(self, value=initial.data, style=wx.TE_MULTILINE, size=(-1, 90))
        root.Add(self.data, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, 16)

        body = wx.BoxSizer(wx.HORIZONTAL)
        form = wx.FlexGridSizer(cols=2, vgap=10, hgap=12)
        form.AddGrowableCol(1, 1)

        form.Add(wx.StaticText(self, label="Error correction"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.error = wx.Choice(self, choices=[label for label, _value in ERROR_CHOICES])
        self.error.SetSelection(next(
            (index for index, (_label, value) in enumerate(ERROR_CHOICES) if value == initial.error_correction),
            1,
        ))
        form.Add(self.error, 1, wx.EXPAND)

        form.Add(wx.StaticText(self, label="Layer"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.layer = wx.adv.BitmapComboBox(self, style=wx.CB_READONLY)
        for option in layers:
            self.layer.Append(option.name, _color_swatch(option.color))
        layer_index = next((i for i, option in enumerate(layers) if option.name == initial.layer_name), 0)
        self.layer.SetSelection(layer_index)
        form.Add(self.layer, 1, wx.EXPAND)

        form.Add(wx.StaticText(self, label="Size"), 0, wx.ALIGN_CENTER_VERTICAL)
        size_row = wx.BoxSizer(wx.HORIZONTAL)
        self.size = wx.TextCtrl(self, value=f"{initial.size_mm:g}")
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
        self.preview = QrPreview(self, theme)
        body.Add(self.preview, 0, wx.TOP | wx.RIGHT | wx.BOTTOM, 16)
        root.Add(body, 1, wx.EXPAND)

        buttons = self.CreateSeparatedButtonSizer(wx.OK | wx.CANCEL)
        self.ok_button = self.FindWindowById(wx.ID_OK)
        self.ok_button.SetLabel("Update QR Code" if editing else "Add to Board")
        root.Add(buttons, 0, wx.ALL | wx.EXPAND, 12)

        self.SetSizerAndFit(root)
        fitted_size = self.GetSize()
        self.SetMinSize(fitted_size)
        self.SetSize((max(900, fitted_size.width), fitted_size.height))

        self.data.Bind(wx.EVT_TEXT, self._schedule_update)
        self.size.Bind(wx.EVT_TEXT, self._schedule_update)
        self.error.Bind(wx.EVT_CHOICE, self._schedule_update)
        self.layer.Bind(wx.EVT_COMBOBOX, self._schedule_update)
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
            size_mm=float(self.size.GetValue().replace(",", ".")),
            layer_name=self._layers[layer_index].name,
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
            self.preview.set_qr(encoded, self._layers[max(0, self.layer.GetSelection())].color)
            self.ok_button.Enable(True)
        except (QrSettingsError, ValueError) as error:
            self.info.SetLabel("")
            self.error_text.SetLabel(str(error))
            self._settings = None
            self._encoded = None
            layer_index = max(0, self.layer.GetSelection())
            color = self._layers[layer_index].color if self._layers else (255, 255, 255)
            self.preview.set_qr(None, color)
            self.ok_button.Enable(False)
        self.Layout()

    def _on_ok(self, _event) -> None:
        self._refresh_preview()
        if self._settings is not None:
            self.EndModal(wx.ID_OK)


def _color_swatch(color: tuple[int, int, int]) -> wx.Bitmap:
    bitmap = wx.Bitmap(16, 16)
    dc = wx.MemoryDC(bitmap)
    dc.SetBackground(wx.Brush(wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOW)))
    dc.Clear()
    dc.SetPen(wx.Pen(wx.Colour(80, 80, 80)))
    dc.SetBrush(wx.Brush(wx.Colour(*color)))
    dc.DrawRectangle(1, 1, 14, 14)
    dc.SelectObject(wx.NullBitmap)
    return bitmap

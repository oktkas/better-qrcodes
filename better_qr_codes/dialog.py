"""wxPython dialog and live preview for Better QR Codes."""

from __future__ import annotations

import math

import wx
import wx.adv

from .appearance import LayerOption, ThemeColors
from .geometry import material_polygons
from .model import (
    EncodedQr,
    QrSettings,
    QrSettingsError,
    encode_qr,
)


ERROR_CHOICES = (
    ("L — about 7%", "L"),
    ("M — about 15%", "M"),
    ("Q — about 25%", "Q"),
    ("H — about 30%", "H"),
)

KNOCKOUT_CHOICES = (
    ("Standard — 4 modules", 4),
    ("Thin — 2 modules", 2),
    ("Custom", None),
)

class QrPreview(wx.Panel):
    def __init__(self, parent, _theme: ThemeColors):
        super().__init__(parent, size=(330, 330), style=wx.BORDER_SIMPLE)
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self._encoded: EncodedQr | None = None
        self._settings: QrSettings | None = None
        self._polygons: tuple[tuple[tuple[float, float], ...], ...] = ()
        self._span_cache: dict[tuple[int, int], tuple[tuple[int, int, int], ...]] = {}
        self._module_color = (255, 255, 255)
        self._background = (32, 35, 40)
        self._grid = (58, 62, 70)
        self.Bind(wx.EVT_PAINT, self._on_paint)

    def set_qr(
        self,
        encoded: EncodedQr | None,
        color: tuple[int, int, int],
        settings: QrSettings | None,
    ) -> None:
        self._encoded = encoded
        self._module_color = color
        self._settings = settings
        self._polygons = (
            material_polygons(settings, encoded)
            if settings is not None and encoded is not None
            else ()
        )
        self._span_cache.clear()
        self.Refresh()

    def _on_paint(self, _event) -> None:
        dc = wx.AutoBufferedPaintDC(self)
        width, height = self.GetClientSize()
        self._paint(dc, width, height)

    def _paint(self, dc, width: int, height: int) -> None:
        dc.SetBackground(wx.Brush(wx.Colour(*self._background)))
        dc.Clear()

        dot_color = wx.Colour(*self._grid)
        dc.SetPen(wx.Pen(dot_color))
        dc.SetBrush(wx.Brush(dot_color))
        for x in range(8, width, 16):
            for y in range(8, height, 16):
                dc.DrawCircle(x, y, 1)

        if self._encoded is None or self._settings is None:
            return

        quiet_zone = 4
        knockout_margin = self._settings.knockout_margin_modules if self._settings.knockout else 0
        viewport_margin = max(quiet_zone, knockout_margin) + 1
        total = self._encoded.module_count + viewport_margin * 2
        scale = min(width, height) / total
        origin_x = (width - self._encoded.module_count * scale) / 2
        origin_y = (height - self._encoded.module_count * scale) / 2

        module_color = wx.Colour(*self._module_color)
        dc.SetPen(wx.Pen(module_color))
        dc.SetBrush(wx.Brush(module_color))

        cache_key = (width, height)
        spans = self._span_cache.get(cache_key)
        if spans is None:
            spans = tuple(self._scanline_spans(
                self._polygons,
                origin_x,
                origin_y,
                scale,
                height,
            ))
            self._span_cache[cache_key] = spans
        for y, start_x, end_x in spans:
            dc.DrawRectangle(start_x, y, end_x - start_x + 1, 1)

        outline_color = wx.Colour(220, 220, 220) if sum(self._background) < 384 else wx.Colour(55, 55, 55)
        dc.SetPen(wx.Pen(outline_color, 1, wx.PENSTYLE_SHORT_DASH))
        dc.SetBrush(wx.TRANSPARENT_BRUSH)
        quiet_x = round(origin_x - quiet_zone * scale)
        quiet_y = round(origin_y - quiet_zone * scale)
        quiet_size = round((self._encoded.module_count + quiet_zone * 2) * scale)
        dc.DrawRectangle(quiet_x, quiet_y, quiet_size, quiet_size)

    @staticmethod
    def _scanline_spans(
        polygons,
        origin_x: float,
        origin_y: float,
        scale: float,
        height: int,
    ):
        """Rasterize fractured polygons without relying on platform fill rules."""
        for polygon in polygons:
            points = tuple(
                (origin_x + x * scale, origin_y + y * scale)
                for x, y in polygon
            )
            if len(points) < 3:
                continue
            first_y = max(0, math.floor(min(y for _x, y in points)))
            last_y = min(height - 1, math.ceil(max(y for _x, y in points)))
            edges = tuple(zip(points, points[1:] + points[:1]))
            for y in range(first_y, last_y + 1):
                scan_y = y + 0.5
                intersections = []
                for (x0, y0), (x1, y1) in edges:
                    if (y0 <= scan_y < y1) or (y1 <= scan_y < y0):
                        intersections.append(
                            x0 + (scan_y - y0) * (x1 - x0) / (y1 - y0)
                        )
                intersections.sort()
                for index in range(0, len(intersections) - 1, 2):
                    start_x = math.ceil(intersections[index] - 0.5)
                    end_x = math.floor(intersections[index + 1] - 0.5)
                    if end_x >= start_x:
                        yield y, start_x, end_x


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
            0,
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

        form.Add(wx.StaticText(self, label="Corner radius"), 0, wx.ALIGN_CENTER_VERTICAL)
        corner_row = wx.BoxSizer(wx.HORIZONTAL)
        self.corner_radius = wx.Slider(
            self,
            value=initial.corner_radius_percent,
            minValue=0,
            maxValue=100,
        )
        self.corner_radius_value = wx.StaticText(self, label="", size=(42, -1))
        corner_row.Add(self.corner_radius, 1, wx.EXPAND)
        corner_row.Add(self.corner_radius_value, 0, wx.LEFT | wx.ALIGN_CENTER_VERTICAL, 8)
        form.Add(corner_row, 1, wx.EXPAND)

        form.Add(wx.StaticText(self, label="Finder rounding"), 0, wx.ALIGN_CENTER_VERTICAL)
        finder_row = wx.BoxSizer(wx.HORIZONTAL)
        self.finder_radius = wx.Slider(
            self,
            value=initial.finder_radius_percent,
            minValue=0,
            maxValue=100,
        )
        self.finder_radius_value = wx.StaticText(self, label="", size=(42, -1))
        finder_row.Add(self.finder_radius, 1, wx.EXPAND)
        finder_row.Add(self.finder_radius_value, 0, wx.LEFT | wx.ALIGN_CENTER_VERTICAL, 8)
        form.Add(finder_row, 1, wx.EXPAND)

        form.Add(wx.StaticText(self, label="Knockout"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.knockout = wx.CheckBox(self, label="Invert into solid background")
        self.knockout.SetValue(initial.knockout)
        form.Add(self.knockout, 1, wx.EXPAND)

        form.Add(wx.StaticText(self, label="Knockout margin"), 0, wx.ALIGN_CENTER_VERTICAL)
        margin_row = wx.BoxSizer(wx.HORIZONTAL)
        self.knockout_margin = wx.Choice(self, choices=[label for label, _value in KNOCKOUT_CHOICES])
        margin_index = next(
            (
                index
                for index, (_label, value) in enumerate(KNOCKOUT_CHOICES)
                if value == initial.knockout_margin_modules
            ),
            len(KNOCKOUT_CHOICES) - 1,
        )
        self.knockout_margin.SetSelection(margin_index)
        self.custom_margin = wx.TextCtrl(self, value=str(initial.knockout_margin_modules), size=(55, -1))
        self.custom_margin_units = wx.StaticText(self, label=" modules")
        margin_row.Add(self.knockout_margin, 1, wx.EXPAND)
        margin_row.Add(self.custom_margin, 0, wx.LEFT, 8)
        margin_row.Add(self.custom_margin_units, 0, wx.ALIGN_CENTER_VERTICAL)
        form.Add(margin_row, 1, wx.EXPAND)

        form.Add(wx.StaticText(self, label="Knockout corners"), 0, wx.ALIGN_CENTER_VERTICAL)
        knockout_corner_row = wx.BoxSizer(wx.HORIZONTAL)
        self.knockout_corner_radius = wx.Slider(
            self,
            value=initial.knockout_corner_radius_percent,
            minValue=0,
            maxValue=100,
        )
        self.knockout_corner_radius_value = wx.StaticText(self, label="", size=(42, -1))
        knockout_corner_row.Add(self.knockout_corner_radius, 1, wx.EXPAND)
        knockout_corner_row.Add(
            self.knockout_corner_radius_value,
            0,
            wx.LEFT | wx.ALIGN_CENTER_VERTICAL,
            8,
        )
        form.Add(knockout_corner_row, 1, wx.EXPAND)

        self.info = wx.StaticText(self, label="")
        form.Add((0, 0))
        form.Add(self.info, 0, wx.EXPAND)

        self.warning_text = wx.StaticText(self, label="")
        self.warning_text.SetForegroundColour(wx.Colour(185, 120, 20))
        form.Add((0, 0))
        form.Add(self.warning_text, 0, wx.EXPAND)

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
        self.corner_radius.Bind(wx.EVT_SLIDER, self._on_style_change)
        self.finder_radius.Bind(wx.EVT_SLIDER, self._on_style_change)
        self.knockout.Bind(wx.EVT_CHECKBOX, self._on_style_change)
        self.knockout_margin.Bind(wx.EVT_CHOICE, self._on_style_change)
        self.custom_margin.Bind(wx.EVT_TEXT, self._schedule_update)
        self.knockout_corner_radius.Bind(wx.EVT_SLIDER, self._on_style_change)
        self.Bind(wx.EVT_BUTTON, self._on_ok, id=wx.ID_OK)

        self._update_style_controls()
        self._refresh_preview()
        self.data.SetFocus()

    @property
    def result(self) -> tuple[QrSettings, EncodedQr]:
        if self._settings is None or self._encoded is None:
            raise RuntimeError("The dialog has no valid QR code result")
        return self._settings, self._encoded

    def Destroy(self):
        if self._update_later is not None:
            self._update_later.Stop()
            self._update_later = None
        return super().Destroy()

    def _schedule_update(self, event) -> None:
        event.Skip()
        if self._update_later is not None:
            self._update_later.Stop()
        self._update_later = wx.CallLater(120, self._refresh_preview)

    def _read_settings(self) -> QrSettings:
        error_index = max(0, self.error.GetSelection())
        layer_index = max(0, self.layer.GetSelection())
        margin_choice = KNOCKOUT_CHOICES[max(0, self.knockout_margin.GetSelection())][1]
        if margin_choice is None:
            custom_value = self.custom_margin.GetValue().strip()
            margin = int(custom_value) if custom_value or self.knockout.GetValue() else 4
        else:
            margin = margin_choice
        return QrSettings(
            data=self.data.GetValue(),
            error_correction=ERROR_CHOICES[error_index][1],
            size_mm=float(self.size.GetValue().replace(",", ".")),
            layer_name=self._layers[layer_index].name,
            corner_radius_percent=self.corner_radius.GetValue(),
            knockout=self.knockout.GetValue(),
            knockout_margin_modules=margin,
            finder_radius_percent=self.finder_radius.GetValue(),
            knockout_corner_radius_percent=self.knockout_corner_radius.GetValue(),
        )

    def _refresh_preview(self) -> None:
        try:
            settings = self._read_settings().validated()
            encoded = encode_qr(settings)
            module_size = settings.size_mm / encoded.module_count
            footprint_size = settings.size_mm
            if settings.knockout:
                footprint_size *= (encoded.module_count + settings.knockout_margin_modules * 2) / encoded.module_count
            self.info.SetLabel(
                f"Version {encoded.version} · {encoded.module_count}×{encoded.module_count} modules · "
                f"{module_size:.3f} mm/module · {footprint_size:.2f} mm footprint"
            )
            self.warning_text.SetLabel(
                "Margins below 4 modules are non-standard; verify scanning on the finished board."
                if settings.knockout and settings.knockout_margin_modules < 4
                else ""
            )
            self.error_text.SetLabel("")
            self._settings = settings
            self._encoded = encoded
            self.preview.set_qr(
                encoded,
                self._layers[max(0, self.layer.GetSelection())].color,
                settings,
            )
            self.ok_button.Enable(True)
        except (QrSettingsError, RuntimeError, ValueError) as error:
            self.info.SetLabel("")
            self.warning_text.SetLabel("")
            self.error_text.SetLabel(str(error))
            self._settings = None
            self._encoded = None
            layer_index = max(0, self.layer.GetSelection())
            color = self._layers[layer_index].color if self._layers else (255, 255, 255)
            self.preview.set_qr(None, color, None)
            self.ok_button.Enable(False)
        self.Layout()

    def _on_ok(self, _event) -> None:
        self._refresh_preview()
        if self._settings is not None:
            self.EndModal(wx.ID_OK)

    def _on_style_change(self, event) -> None:
        self._update_style_controls()
        self._schedule_update(event)

    def _update_style_controls(self) -> None:
        self.corner_radius_value.SetLabel(f"{self.corner_radius.GetValue()}%")
        self.finder_radius_value.SetLabel(f"{self.finder_radius.GetValue()}%")
        self.knockout_corner_radius_value.SetLabel(f"{self.knockout_corner_radius.GetValue()}%")
        enabled = self.knockout.GetValue()
        custom = KNOCKOUT_CHOICES[max(0, self.knockout_margin.GetSelection())][1] is None
        self.knockout_margin.Enable(enabled)
        self.finder_radius.Enable(True)
        self.custom_margin.Show(enabled and custom)
        self.custom_margin_units.Show(enabled and custom)
        self.knockout_corner_radius.Enable(enabled)
        self.Layout()


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

import unittest

try:
    import pcbnew
except ImportError:
    pcbnew = None


@unittest.skipIf(pcbnew is None, "requires KiCad's Python runtime")
class GeometryTests(unittest.TestCase):
    def test_finder_rounding_includes_outer_gap_and_center(self):
        from better_qr_codes.geometry import _dark_geometry
        from better_qr_codes.model import QrSettings, encode_qr

        settings = QrSettings("finder", finder_radius_percent=100)
        geometry = _dark_geometry(settings, encode_qr(settings))

        self.assertFalse(geometry.Collide(pcbnew.VECTOR2I(1_000, 1_000)))
        self.assertTrue(geometry.Collide(pcbnew.VECTOR2I(35_000, 1_000)))
        self.assertTrue(geometry.Collide(pcbnew.VECTOR2I(11_000, 11_000)))
        self.assertFalse(geometry.Collide(pcbnew.VECTOR2I(35_000, 11_000)))
        self.assertTrue(geometry.Collide(pcbnew.VECTOR2I(35_000, 35_000)))

        half_rounded = QrSettings("finder", finder_radius_percent=50)
        half_geometry = _dark_geometry(half_rounded, encode_qr(half_rounded))
        self.assertFalse(half_geometry.Collide(pcbnew.VECTOR2I(12_000, 15_000)))

    def test_preview_scanlines_preserve_knockout_holes(self):
        from better_qr_codes.dialog import QrPreview
        from better_qr_codes.geometry import material_polygons
        from better_qr_codes.model import QrSettings, encode_qr

        settings = QrSettings(
            "preview",
            corner_radius_percent=80,
            knockout=True,
            knockout_margin_modules=2,
            finder_radius_percent=70,
        )
        encoded = encode_qr(settings)
        scale = 10
        total = encoded.module_count + settings.knockout_margin_modules * 2
        spans = tuple(QrPreview._scanline_spans(
            material_polygons(settings, encoded),
            settings.knockout_margin_modules * scale,
            settings.knockout_margin_modules * scale,
            scale,
            total * scale,
        ))
        filled_pixels = sum(end - start + 1 for _y, start, end in spans)

        self.assertGreater(filled_pixels, total * total * scale * scale * 0.35)
        self.assertLess(filled_pixels, total * total * scale * scale * 0.85)

    def test_knockout_polygons_remain_valid_after_native_scaling(self):
        from better_qr_codes.geometry import material_polygons
        from better_qr_codes.model import QrSettings, encode_qr

        settings = QrSettings(
            "scale",
            corner_radius_percent=80,
            knockout=True,
            knockout_margin_modules=2,
            finder_radius_percent=100,
            knockout_corner_radius_percent=100,
        )
        polygons = material_polygons(settings, encode_qr(settings))

        self.assertGreater(len(polygons), 0)
        for polygon in polygons:
            shape = pcbnew.PCB_SHAPE(None, pcbnew.SHAPE_T_POLY)
            shape.SetPolyPoints([
                pcbnew.VECTOR2I(round(x * 100_000), round(y * 100_000))
                for x, y in polygon
            ])
            shape.SetFilled(True)
            self.assertTrue(shape.IsPolyShapeValid())
            self.assertEqual(shape.GetPolyShape().OutlineCount(), 1)
            self.assertEqual(shape.GetPolyShape().HoleCount(0), 0)

            points_before = shape.GetPolyShape().Outline(0).PointCount()
            shape.Scale(1.75)

            self.assertTrue(shape.IsPolyShapeValid())
            self.assertEqual(shape.GetPolyShape().Outline(0).PointCount(), points_before)


if __name__ == "__main__":
    unittest.main()

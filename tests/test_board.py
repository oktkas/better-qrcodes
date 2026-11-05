import os
import tempfile
import unittest
from dataclasses import replace

try:
    import pcbnew
except ImportError:
    pcbnew = None


def _points(footprint):
    points = []
    for item in footprint.GraphicalItems():
        if item.GetShape() == pcbnew.SHAPE_T_RECT:
            corners = [item.GetStart(), item.GetEnd()]
        else:
            outline = item.GetPolyShape().Outline(0)
            corners = [outline.CPoint(i) for i in range(outline.PointCount())]
        points.extend((c.x, c.y) for c in corners)
    return sorted(points)


@unittest.skipIf(pcbnew is None, "requires KiCad's Python runtime")
class BoardTests(unittest.TestCase):
    def setUp(self):
        from better_qr_codes.model import QrSettings, encode_qr

        self.board = pcbnew.BOARD()
        self.position = pcbnew.VECTOR2I(pcbnew.FromMM(40), pcbnew.FromMM(30))
        self.settings = QrSettings("https://example.com", size_mm=12.0, corner_radius_percent=50)
        self.encoded = encode_qr(self.settings)

    def _add(self, settings=None):
        from better_qr_codes.board import add_qr
        from better_qr_codes.model import encode_qr

        settings = settings or self.settings
        return add_qr(self.board, settings, encode_qr(settings), self.position)

    def _edit(self, footprint, **changes):
        from better_qr_codes.board import editable_qr, update_qr
        from better_qr_codes.model import encode_qr

        editable = editable_qr(footprint, self.board)
        settings = replace(editable.settings, **changes).validated()
        return update_qr(self.board, editable, settings, encode_qr(settings))

    def test_new_code_is_a_hidden_board_only_footprint(self):
        from better_qr_codes.board import SETTINGS_FIELD, editable_qr

        footprint = self._add()

        self.assertEqual(footprint.GetReference(), "QR1")
        self.assertEqual(self._add().GetReference(), "QR2")
        self.assertEqual(footprint.GetPosition(), self.position)
        self.assertTrue(footprint.GetAttributes() & pcbnew.FP_BOARD_ONLY)
        self.assertTrue(footprint.GetAttributes() & pcbnew.FP_EXCLUDE_FROM_BOM)
        for field in footprint.GetFields():
            self.assertFalse(field.IsVisible(), field.GetName())
        self.assertTrue(footprint.HasField(SETTINGS_FIELD))
        self.assertEqual(editable_qr(footprint, self.board).settings, self.settings.validated())

    def test_native_rotation_is_read_back_and_kept_on_edit(self):
        from better_qr_codes.board import editable_qr

        footprint = self._add()
        footprint.SetOrientationDegrees(37)
        footprint.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(70), pcbnew.FromMM(10)))
        before = _points(footprint)

        self.assertEqual(editable_qr(footprint, self.board).settings.rotation_degrees, 37)
        self._edit(footprint)
        self.assertEqual(footprint.GetOrientationDegrees(), 37)
        self.assertEqual(footprint.GetPosition(), pcbnew.VECTOR2I(pcbnew.FromMM(70), pcbnew.FromMM(10)))
        self._assert_same_points(before, _points(footprint))

        self._edit(footprint, rotation_degrees=-120, size_mm=20.0)
        self.assertEqual(footprint.GetOrientationDegrees(), -120)
        self.assertEqual(editable_qr(footprint, self.board).settings.size_mm, 20.0)

    def test_native_flip_is_read_back_and_kept_on_edit(self):
        from better_qr_codes.board import editable_qr

        footprint = self._add()
        footprint.SetOrientationDegrees(30)
        footprint.Flip(footprint.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        before = _points(footprint)
        orientation = footprint.GetOrientationDegrees()

        settings = editable_qr(footprint, self.board).settings
        self.assertEqual(settings.layer_name, "B.Silkscreen")
        self.assertEqual(settings.rotation_degrees, orientation)
        self._edit(footprint)
        self.assertTrue(footprint.IsFlipped())
        self.assertEqual(footprint.GetOrientationDegrees(), orientation)
        self._assert_same_points(before, _points(footprint))

        self._edit(footprint, layer_name="F.Silkscreen")
        self.assertFalse(footprint.IsFlipped())
        self.assertEqual(
            {item.GetLayerName() for item in footprint.GraphicalItems()}, {"F.Silkscreen"}
        )

    def test_back_side_default_matches_native_flip_of_front_code(self):
        from better_qr_codes.model import flipped_rotation

        for degrees in (0, 30, -120):
            front = self._add(replace(self.settings, rotation_degrees=degrees))
            front.Flip(front.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
            back = self._add(replace(
                self.settings,
                layer_name="B.Silkscreen",
                rotation_degrees=flipped_rotation(degrees),
            ))
            self.assertEqual(back.GetOrientationDegrees(), front.GetOrientationDegrees())
            self._assert_same_points(_points(front), _points(back))

    def test_preview_placement_matches_board_geometry(self):
        from better_qr_codes.geometry import material_polygons
        from better_qr_codes.model import place_polygons

        for layer, degrees in (("F.Silkscreen", 25), ("B.Silkscreen", -70)):
            settings = replace(
                self.settings, layer_name=layer, rotation_degrees=degrees, knockout=True
            ).validated()
            footprint = self._add(settings)
            count = self.encoded.module_count
            scale = pcbnew.FromMM(settings.size_mm) / count
            preview = place_polygons(
                material_polygons(settings, self.encoded), count / 2, count / 2, degrees,
                layer.startswith("B."),
            )
            expected = sorted(
                (self.position.x + (x - count / 2) * scale, self.position.y + (y - count / 2) * scale)
                for polygon in preview
                for x, y in polygon
            )
            self._assert_same_points(expected, _points(footprint), tolerance=5)

    def test_save_and_reload_keeps_everything_editable(self):
        from better_qr_codes.board import editable_qr

        footprint = self._add(replace(self.settings, layer_name="B.Silkscreen", rotation_degrees=15))
        expected = editable_qr(footprint, self.board).settings
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "qr.kicad_pcb")
            pcbnew.SaveBoard(path, self.board)
            loaded = pcbnew.LoadBoard(path)
            reloaded = list(loaded.GetFootprints())[0]
            self.assertEqual(editable_qr(reloaded, loaded).settings, expected)

    def test_legacy_group_is_converted_to_a_footprint_on_edit(self):
        from better_qr_codes.board import editable_qr, update_qr
        from better_qr_codes.model import LEGACY_METADATA_PREFIX, METADATA_PREFIX, encode_metadata

        group = pcbnew.PCB_GROUP(self.board)
        group.SetName(LEGACY_METADATA_PREFIX + encode_metadata(self.settings)[len(METADATA_PREFIX):])
        self.board.Add(group)
        shape = pcbnew.PCB_SHAPE(self.board, pcbnew.SHAPE_T_RECT)
        shape.SetStart(pcbnew.VECTOR2I(0, 0))
        shape.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(10), pcbnew.FromMM(10)))
        shape.SetLayer(pcbnew.F_SilkS)
        shape.SetFilled(True)
        shape.SetWidth(0)
        self.board.Add(shape)
        group.AddItem(shape)

        editable = editable_qr(group, self.board)
        self.assertTrue(editable.legacy)
        self.assertAlmostEqual(editable.settings.size_mm, 10.0)
        footprint = update_qr(self.board, editable, editable.settings, self.encoded)

        self.assertEqual(len(self.board.Groups()), 0)
        self.assertEqual(len(self.board.GetDrawings()), 0)
        self.assertEqual(footprint.GetPosition(), pcbnew.VECTOR2I(pcbnew.FromMM(5), pcbnew.FromMM(5)))
        self.assertFalse(editable_qr(footprint, self.board).legacy)

    def _assert_same_points(self, expected, actual, tolerance=1):
        self.assertEqual(len(expected), len(actual))
        for (ex, ey), (ax, ay) in zip(sorted(expected), sorted(actual)):
            self.assertLessEqual(abs(ex - ax), tolerance)
            self.assertLessEqual(abs(ey - ay), tolerance)


if __name__ == "__main__":
    unittest.main()

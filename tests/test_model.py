import unittest

from better_qr_codes.model import (
    LEGACY_METADATA_PREFIX,
    METADATA_PREFIX,
    QrSettings,
    QrSettingsError,
    dark_runs,
    decode_metadata,
    encode_metadata,
    encode_qr,
    flipped_rotation,
    knockout_background_polygons,
    knockout_outline_polygon,
    knockout_modules,
    rounded_corner_wedges,
    place_polygons,
    rounded_module_polygons,
)


class QrModelTests(unittest.TestCase):
    def test_encodes_regular_qr(self):
        encoded = encode_qr(QrSettings("https://example.com", "M", 20.0, "F.Silkscreen"))

        self.assertGreaterEqual(encoded.version, 1)
        self.assertEqual(encoded.module_count, encoded.version * 4 + 17)
        self.assertEqual(len(encoded.modules), encoded.module_count)
        self.assertTrue(encoded.modules[0][0])

    def test_ecc_is_not_silently_boosted(self):
        low = encode_qr(QrSettings("A", "L", 20.0, "F.Silkscreen"))
        high = encode_qr(QrSettings("A", "H", 20.0, "F.Silkscreen"))

        self.assertEqual(low.version, 1)
        self.assertEqual(high.version, 1)
        self.assertNotEqual(low.modules, high.modules)

    def test_metadata_round_trip_preserves_unicode(self):
        settings = QrSettings("Příliš žluťoučký kůň", "Q", 17.5, "B.Silkscreen")
        encoded = encode_metadata(settings)
        decoded = decode_metadata(encoded, layer_name="F.Cu", rotation_degrees=45)

        self.assertTrue(encoded.startswith(METADATA_PREFIX))
        # Size travels in the metadata; layer and rotation come from the footprint.
        self.assertEqual(
            decoded, QrSettings(settings.data, "Q", 17.5, "F.Cu", rotation_degrees=45)
        )

    def test_metadata_round_trip_preserves_style(self):
        settings = QrSettings(
            "styled", "H", 18.0, "F.Silkscreen", 70, True, 2, 85, 60, -90,
        )
        decoded = decode_metadata(
            encode_metadata(settings),
            layer_name=settings.layer_name,
            rotation_degrees=-90,
        )

        self.assertEqual(decoded, settings)

    def test_legacy_group_metadata_needs_measured_size(self):
        legacy = LEGACY_METADATA_PREFIX + encode_metadata(QrSettings("old"))[len(METADATA_PREFIX):]

        self.assertIsNone(decode_metadata(legacy, layer_name="F.Cu"))
        decoded = decode_metadata(legacy, layer_name="F.Cu", size_mm=23.0)
        self.assertEqual(decoded, QrSettings("old", "L", 23.0, "F.Cu"))

    def test_rotation_matches_kicad_orientation_range(self):
        for given, expected in ((-30, -30.0), (330, -30.0), (180, 180.0), (-180, 180.0), (450, 90.0)):
            self.assertEqual(QrSettings("spin", rotation_degrees=given).validated().rotation_degrees, expected)

    def test_flipped_rotation_matches_kicad_flip(self):
        # Measured in KiCad 10.0.6: flipping at 30 degrees shows 150; at 0 shows 180.
        self.assertEqual(flipped_rotation(30), 150.0)
        self.assertEqual(flipped_rotation(0), 180.0)
        self.assertEqual(flipped_rotation(flipped_rotation(-70)), -70.0)

    def test_placement_matches_kicad_footprint_transform(self):
        # Measured in KiCad 10.0.6: local x axis (1, 0) and y axis (0, 2) about origin.
        axes = (((1.0, 0.0), (0.0, 2.0)),)
        cases = {
            (90, False): ((0.0, -1.0), (2.0, 0.0)),
            (0, True): ((1.0, 0.0), (0.0, -2.0)),
            (90, True): ((0.0, -1.0), (-2.0, 0.0)),
            (-30, True): ((0.866, 0.5), (1.0, -1.732)),
        }
        for (degrees, back), expected in cases.items():
            placed = place_polygons(axes, 0.0, 0.0, degrees, back)[0]
            for (x, y), (ex, ey) in zip(placed, expected):
                self.assertAlmostEqual(x, ex, places=3)
                self.assertAlmostEqual(y, ey, places=3)

    def test_unrelated_group_name_is_ignored(self):
        self.assertIsNone(decode_metadata("ordinary group", size_mm=20, layer_name="F.Cu"))

    def test_dark_runs_merge_adjacent_modules(self):
        modules = (
            (False, True, True, False, True),
            (True, False, False, False, False),
        )
        self.assertEqual(list(dark_runs(modules)), [(0, 1, 3), (0, 4, 5), (1, 0, 1)])

    def test_knockout_inverts_symbol_and_adds_module_margin(self):
        self.assertEqual(
            knockout_modules(((True,),), 1),
            (
                (True, True, True),
                (True, False, True),
                (True, True, True),
            ),
        )

    def test_knockout_corner_radius_is_relative_to_margin(self):
        square = knockout_background_polygons(21, 2, 0)
        rounded = knockout_background_polygons(21, 2, 100)

        self.assertEqual(len(square), 4)
        self.assertGreater(len(rounded[0]), len(square[0]))
        self.assertIn((-2.0, 0.0), rounded[0])

        outline = knockout_outline_polygon(21, 2, 100)
        self.assertGreater(len(outline), 4)
        self.assertTrue(all(-2 <= x <= 23 and -2 <= y <= 23 for x, y in outline))

    def test_rounding_only_affects_exposed_corners(self):
        modules = ((True, True),)

        polygons = list(rounded_module_polygons(modules, 100))
        wedges = list(rounded_corner_wedges(modules, 100))

        self.assertEqual(len(polygons), 2)
        self.assertEqual(len(wedges), 4)
        self.assertTrue(all(0 <= x <= 2 and 0 <= y <= 1 for polygon in polygons for x, y in polygon))

    def test_finder_rounding_is_independent_from_data_modules(self):
        modules = tuple(
            tuple((row, column) in {(0, 0), (10, 10)} for column in range(21))
            for row in range(21)
        )

        polygons = list(rounded_module_polygons(modules, 0, 100))

        self.assertGreater(len(polygons[0]), 4)
        self.assertEqual(len(polygons[1]), 4)

    def test_finder_outer_and_center_can_be_circular(self):
        modules = encode_qr(QrSettings("finder styles")).modules

        polygons = list(rounded_module_polygons(modules, 0, 0, "circle", "circle"))

        self.assertEqual(sum(len(polygon) == 32 for polygon in polygons), 3)
        self.assertGreaterEqual(sum(len(polygon) == 4 for polygon in polygons), 96)

    def test_rejects_empty_content(self):
        with self.assertRaises(QrSettingsError):
            encode_qr(QrSettings("  ", "M", 20.0, "F.Silkscreen"))

    def test_rejects_invalid_style_values(self):
        with self.assertRaises(QrSettingsError):
            QrSettings("data", corner_radius_percent=101).validated()
        with self.assertRaises(QrSettingsError):
            QrSettings("data", knockout_margin_modules=1.5).validated()

    def test_new_code_defaults_to_low_correction_and_15_mm(self):
        settings = QrSettings("data")

        self.assertEqual(settings.error_correction, "L")
        self.assertEqual(settings.size_mm, 15.0)


if __name__ == "__main__":
    unittest.main()

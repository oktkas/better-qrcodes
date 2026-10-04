import unittest

from better_qr_codes.model import (
    METADATA_PREFIX,
    QrSettings,
    QrSettingsError,
    dark_runs,
    decode_metadata,
    encode_metadata,
    encode_qr,
    knockout_background_polygons,
    knockout_outline_polygon,
    knockout_modules,
    rounded_corner_wedges,
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
        decoded = decode_metadata(encoded, size_mm=23.0, layer_name="F.Cu")

        self.assertTrue(encoded.startswith(METADATA_PREFIX))
        self.assertEqual(decoded, QrSettings(settings.data, "Q", 23.0, "F.Cu"))

    def test_metadata_round_trip_preserves_style(self):
        settings = QrSettings(
            "styled", "H", 18.0, "F.Silkscreen", 70, True, 2, 85, 60,
        )
        decoded = decode_metadata(
            encode_metadata(settings),
            size_mm=settings.size_mm,
            layer_name=settings.layer_name,
        )

        self.assertEqual(decoded, settings)

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

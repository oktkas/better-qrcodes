import unittest

from better_qr_codes.model import (
    METADATA_PREFIX,
    QrSettings,
    QrSettingsError,
    dark_runs,
    decode_metadata,
    encode_metadata,
    encode_qr,
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

    def test_unrelated_group_name_is_ignored(self):
        self.assertIsNone(decode_metadata("ordinary group", size_mm=20, layer_name="F.Cu"))

    def test_dark_runs_merge_adjacent_modules(self):
        modules = (
            (False, True, True, False, True),
            (True, False, False, False, False),
        )
        self.assertEqual(list(dark_runs(modules)), [(0, 1, 3), (0, 4, 5), (1, 0, 1)])

    def test_rejects_empty_content(self):
        with self.assertRaises(QrSettingsError):
            encode_qr(QrSettings("  ", "M", 20.0, "F.Silkscreen"))


if __name__ == "__main__":
    unittest.main()


"""alfabe modülü — Türkçe sıralama testleri."""

import unittest

from tokenizer.alfabe import ALFABE, alfabetik_anahtar


class AlfabeTest(unittest.TestCase):
    def test_29_harf(self):
        self.assertEqual(len(ALFABE), 29)
        self.assertEqual(len(set(ALFABE)), 29)

    def test_türkçe_sıra(self):
        kelimeler = ["zambak", "çam", "armut", "ıslak", "iyi", "öğe", "süt"]
        sıralı = sorted(kelimeler, key=alfabetik_anahtar)
        self.assertEqual(
            sıralı, ["armut", "çam", "ıslak", "iyi", "öğe", "süt", "zambak"]
        )

    def test_ç_d_arası(self):
        self.assertLess(alfabetik_anahtar("ç"), alfabetik_anahtar("d"))

    def test_ı_i_arası(self):
        self.assertLess(alfabetik_anahtar("ı"), alfabetik_anahtar("i"))

    def test_geçersiz_harf(self):
        with self.assertRaises(ValueError):
            alfabetik_anahtar("x")  # x Türkçe alfabede yok


if __name__ == "__main__":
    unittest.main()

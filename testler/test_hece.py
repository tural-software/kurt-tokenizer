"""hece modülü — kök heceleyici testleri."""

import unittest

from tokenizer.hece import hecele


class HeceTest(unittest.TestCase):
    def test_tek_hece(self):
        for k in ["git", "üst", "renk", "kurt", "kalp", "aş", "ay"]:
            self.assertEqual(hecele(k), [k], k)

    def test_çok_hece(self):
        durumlar = {
            "araba": ["a", "ra", "ba"],
            "kitap": ["ki", "tap"],
            "pencere": ["pen", "ce", "re"],
            "bilgisayar": ["bil", "gi", "sa", "yar"],
            "ayakkabı": ["a", "yak", "ka", "bı"],
            "oku": ["o", "ku"],
            "köprü": ["köp", "rü"],
        }
        for kelime, beklenen in durumlar.items():
            self.assertEqual(hecele(kelime), beklenen, kelime)

    def test_ünlü_bitişikliği(self):
        # VV → her ünlü kendi hecesinde
        self.assertEqual(hecele("saat"), ["sa", "at"])
        self.assertEqual(hecele("aile"), ["a", "i", "le"])

    def test_birleşim_kökü_verir(self):
        for k in ["araba", "kitap", "pencere", "bilgisayar", "şimdi", "ağaç"]:
            self.assertEqual("".join(hecele(k)), k)

    def test_hece_sayısı_ünlü_sayısına_eşit(self):
        self.assertEqual(len(hecele("araba")), 3)
        self.assertEqual(len(hecele("üst")), 1)


if __name__ == "__main__":
    unittest.main()

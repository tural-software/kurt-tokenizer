"""sema modülü — Kök şeması ve doğrulama testleri."""

import unittest

from tokenizer.sema import Kök, doğrula


def geçerli_kök() -> Kök:
    return Kök(tokens=["a", "ra", "ba"], tür="isim", son_ünlü="a",
               son_ses="ünlü", değişim=None)


class SemaTest(unittest.TestCase):
    def test_geçerli_kök_geçer(self):
        self.assertEqual(doğrula("araba", geçerli_kök()), [])

    def test_değişimli_kök_geçer(self):
        k = Kök(tokens=["git"], tür="fiil", son_ünlü="i", son_ses="ünsüz",
                değişim={"t→d": "ünlü_ile_başlayan_ek_gelince"})
        self.assertEqual(doğrula("git", k), [])

    def test_tokens_birleşimi_uyumsuz(self):
        k = Kök(tokens=["a", "ba"], tür="isim", son_ünlü="a", son_ses="ünlü")
        self.assertTrue(any("birleşimi" in h for h in doğrula("araba", k)))

    def test_boş_tokens(self):
        k = Kök(tokens=[], tür="isim", son_ünlü="a", son_ses="ünlü")
        self.assertTrue(any("tokens boş" in h for h in doğrula("araba", k)))

    def test_son_ünlü_uyumsuz(self):
        k = Kök(tokens=["git"], tür="fiil", son_ünlü="a", son_ses="ünsüz")
        self.assertTrue(any("son ünlüsü" in h for h in doğrula("git", k)))

    def test_son_ses_uyumsuz(self):
        k = Kök(tokens=["git"], tür="fiil", son_ünlü="i", son_ses="ünlü")
        self.assertTrue(any("son_ses" in h for h in doğrula("git", k)))

    def test_geçersiz_ünlü(self):
        k = Kök(tokens=["git"], tür="fiil", son_ünlü="x", son_ses="ünsüz")
        self.assertTrue(any("geçerli bir ünlü değil" in h for h in doğrula("git", k)))

    def test_geçersiz_tür(self):
        k = Kök(tokens=["git"], tür="kelime", son_ünlü="i", son_ses="ünsüz")
        self.assertTrue(any("izinli türlerden değil" in h for h in doğrula("git", k)))

    def test_geçersiz_değişim_tipi(self):
        k = Kök(tokens=["git"], tür="fiil", son_ünlü="i", son_ses="ünsüz",
                değişim=["t→d"])
        self.assertTrue(any("değişim" in h for h in doğrula("git", k)))

    def test_düşen_kök(self):
        # düşen-ünlü kök çok-heceli olmalı (geçerli) ; tek heceli reddedilir
        akıl = Kök(tokens=["a", "kıl"], tür="isim", son_ünlü="ı", son_ses="ünsüz",
                   düşen=True)
        self.assertEqual(doğrula("akıl", akıl), [])
        tek = Kök(tokens=["kıl"], tür="isim", son_ünlü="ı", son_ses="ünsüz", düşen=True)
        self.assertTrue(any("iki heceli" in h for h in doğrula("kıl", tek)))

    def test_vcc_cvcc_çok_heceli_geçer(self):
        # Yeni hece şekilleri (VCC / CVCC) ve çok-heceli kökler de doğrulamayı geçmeli.
        durumlar = [
            ("üst", Kök(tokens=["üst"], tür="isim", son_ünlü="ü", son_ses="ünsüz")),
            ("kurt", Kök(tokens=["kurt"], tür="isim", son_ünlü="u", son_ses="ünsüz",
                         değişim={"t→d": "ünlü_ile_başlayan_ek_gelince"})),
            ("pencere", Kök(tokens=["pen", "ce", "re"], tür="isim",
                            son_ünlü="e", son_ses="ünlü")),
        ]
        for ad, kök in durumlar:
            self.assertEqual(doğrula(ad, kök), [], ad)


if __name__ == "__main__":
    unittest.main()

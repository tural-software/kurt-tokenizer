"""ekler modülü — soyut ek çözümleyici ve yükleyici testleri."""

import json
import os
import tempfile
import unittest
from pathlib import Path

from tokenizer.ekler import ek_çöz, çöz_ünlü, çöz_ünsüz, yükle, EkŞemaHatası

EK_DOSYASI = Path(__file__).resolve().parent.parent / "veri" / "ekler.json"


class EkÇözTest(unittest.TestCase):
    def test_çoğul(self):
        for gövde, beklenen in [("ev", "ler"), ("araba", "lar"), ("göz", "ler"),
                                ("kuş", "lar"), ("kız", "lar")]:
            self.assertEqual(ek_çöz("lAr", gövde), beklenen, gövde)

    def test_belirtme(self):
        for gövde, beklenen in [("ev", "i"), ("araba", "yı"), ("göz", "ü"),
                                ("kuş", "u"), ("kız", "ı"), ("köprü", "yü"),
                                ("kapı", "yı")]:
            self.assertEqual(ek_çöz("(y)I", gövde), beklenen, gövde)

    def test_yönelme(self):
        for gövde, beklenen in [("ev", "e"), ("araba", "ya"), ("göz", "e"),
                                ("kuş", "a")]:
            self.assertEqual(ek_çöz("(y)A", gövde), beklenen, gövde)

    def test_bulunma_sertleşme(self):
        for gövde, beklenen in [("ev", "de"), ("araba", "da"), ("kitap", "ta"),
                                ("kuş", "ta"), ("ağaç", "ta"), ("göz", "de")]:
            self.assertEqual(ek_çöz("DA", gövde), beklenen, gövde)

    def test_ayrılma(self):
        for gövde, beklenen in [("ev", "den"), ("kitap", "tan"), ("araba", "dan")]:
            self.assertEqual(ek_çöz("DAn", gövde), beklenen, gövde)

    def test_tamlayan(self):
        for gövde, beklenen in [("ev", "in"), ("araba", "nın"), ("göz", "ün"),
                                ("kuş", "un")]:
            self.assertEqual(ek_çöz("(n)In", gövde), beklenen, gövde)

    def test_iyelik(self):
        self.assertEqual(ek_çöz("(I)m", "ev"), "im")
        self.assertEqual(ek_çöz("(I)m", "araba"), "m")
        self.assertEqual(ek_çöz("(I)m", "göz"), "üm")
        self.assertEqual(ek_çöz("(s)I", "araba"), "sı")
        self.assertEqual(ek_çöz("(s)I", "ev"), "i")
        self.assertEqual(ek_çöz("(s)I", "köprü"), "sü")
        self.assertEqual(ek_çöz("(I)mIz", "kuş"), "umuz")
        self.assertEqual(ek_çöz("lArI", "ev"), "leri")
        self.assertEqual(ek_çöz("lArI", "araba"), "ları")

    def test_çöz_ünlü(self):
        self.assertEqual(çöz_ünlü("A", "a"), "a")
        self.assertEqual(çöz_ünlü("A", "e"), "e")
        self.assertEqual(çöz_ünlü("I", "a"), "ı")
        self.assertEqual(çöz_ünlü("I", "o"), "u")
        self.assertEqual(çöz_ünlü("I", "ö"), "ü")
        self.assertEqual(çöz_ünlü("I", "i"), "i")

    def test_çöz_ünsüz(self):
        self.assertEqual(çöz_ünsüz("D", "p"), "t")   # sert → t
        self.assertEqual(çöz_ünsüz("D", "a"), "d")   # ötümlü → d
        self.assertEqual(çöz_ünsüz("C", "ş"), "ç")
        self.assertEqual(çöz_ünsüz("C", "n"), "c")


class FiilEkTest(unittest.TestCase):
    def test_zaman_kip(self):
        self.assertEqual(ek_çöz("(I)yor", "gel"), "iyor")
        self.assertEqual(ek_çöz("(I)yor", "oku"), "yor")
        self.assertEqual(ek_çöz("(I)yor", "kork"), "uyor")
        self.assertEqual(ek_çöz("(I)yor", "gör"), "üyor")
        self.assertEqual(ek_çöz("DI", "yaz"), "dı")
        self.assertEqual(ek_çöz("DI", "git"), "ti")
        self.assertEqual(ek_çöz("DI", "kork"), "tu")
        self.assertEqual(ek_çöz("mIş", "oku"), "muş")
        self.assertEqual(ek_çöz("(y)AcAk", "gel"), "ecek")
        self.assertEqual(ek_çöz("(y)AcAk", "oku"), "yacak")
        self.assertEqual(ek_çöz("mAlI", "gör"), "meli")
        self.assertEqual(ek_çöz("mAk", "yaz"), "mak")
        self.assertEqual(ek_çöz("(y)Iş", "oku"), "yuş")

    def test_şahıs(self):
        self.assertEqual(ek_çöz("m", "geldi"), "m")
        self.assertEqual(ek_çöz("nIz", "geldi"), "niz")
        self.assertEqual(ek_çöz("(y)Im", "geliyor"), "um")
        self.assertEqual(ek_çöz("sInIz", "geliyor"), "sunuz")


class EkYükleTest(unittest.TestCase):
    def test_yüklenir(self):
        e = yükle(EK_DOSYASI)
        self.assertGreaterEqual(len(e), 30)
        self.assertEqual(e["çoğul"].şablon, "lAr")
        self.assertEqual(e["şimdiki_zaman"].şablon, "(I)yor")
        self.assertEqual({x.öbek for x in e.values()}, {"isim", "fiil", "her"})
        self.assertEqual(e["çoğul"].yuva, 1)        # çoğul < iyelik < hâl
        self.assertEqual(e["belirtme"].yuva, 3)
        self.assertTrue(all(x.yuva >= 1 for x in e.values()))
        # nominalizer (sınıf-değiştiren) ekler: fiil → isim
        self.assertEqual(e["isim_fiil"].çıkış, "isim")
        self.assertEqual(e["fiil_isim_ma"].çıkış, "isim")
        self.assertEqual(e["çoğul"].çıkış, "")      # sıradan ek: geçiş yok

    def test_geçersiz_şablon_reddedilir(self):
        bozuk = {"x": {"şablon": "lQr", "tür": "test", "öbek": "isim"}}  # Q geçersiz
        p = tempfile.mktemp(suffix=".json")
        Path(p).write_text(json.dumps(bozuk, ensure_ascii=False), encoding="utf-8")
        try:
            with self.assertRaises(EkŞemaHatası):
                yükle(p)
        finally:
            os.unlink(p)


if __name__ == "__main__":
    unittest.main()

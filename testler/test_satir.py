"""Metin kipinde satır yapısı — satır sonu "\n" tokenı, boş satır = paragraf; tek satırlık metin değişmez."""
import unittest
from pathlib import Path

from tokenizer import ekler as ekler_mod, istisna, kokler
from tokenizer.pipeline import BOŞLUK, SATIR, decode, encode, metin_kanonik
from tokenizer.vocab import Vocab

V = Path(__file__).resolve().parents[1] / "veri"


class SatırTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.k = kokler.çalışma_sözlüğü(V / "kokler", V / "zamirler.json", V / "islev_kokleri.json")
        cls.e = ekler_mod.yükle(V / "ekler.json")
        cls.i = istisna.yükle(V / "istisnalar.json")
        cls.v = Vocab.yükle(V / "vocab.json")

    def gidip_gel(self, metin):
        return self.v.decode_ids(self.v.encode_ids(metin, self.k, self.e, self.i))

    def test_kanonik(self):
        self.assertEqual(metin_kanonik("\n\n  Başlık  \r\n\r\n  ilk   satır\t\nikinci \n\n\n"),
                         "Başlık\n\nilk satır\nikinci")
        self.assertEqual(metin_kanonik("tek  satır"), "tek satır")
        self.assertEqual(metin_kanonik(" \n \n "), "")

    def test_paragraf_ve_liste_gidip_gelir(self):
        metin = ("Kurt'un Özellikleri\n\nKurt, Türkçeyi birinci dil olarak bilir.\nŞunları yapar:\n"
                 "1. Soruları yanıtlar.\n2. Metin özetler.\n\n\nSON  SÖZ: TÜRK dili güzeldir.")
        self.assertEqual(self.gidip_gel(metin), metin_kanonik(metin))
        self.assertIn("\n\n", self.gidip_gel(metin))

    def test_harf_büyüklüğü_satırı_aşmaz(self):
        # HEP BÜYÜK işaretçisi satır sonunda biter: sonraki satırın kelimesi küçük kalır
        self.assertEqual(self.gidip_gel("TÜRK\nev"), "TÜRK\nev")
        self.assertEqual(self.gidip_gel("İstanbul'da\nıssız"), "İstanbul'da\nıssız")

    def test_bayt_ve_yabancı_satır_sınırında(self):
        metin = "日本\nŌsaka ▁ işareti\n\nqwx"
        self.assertEqual(self.gidip_gel(metin), metin_kanonik(metin))

    def test_tek_satır_değişmez(self):
        # satır sonu içermeyen metin eskisi gibi: yalnız kelime + ▁, hiç SATIR yok
        metin = "Bugün  hava\tçok güzel, değil mi?"
        t = encode(metin, self.k, self.e, self.i)
        self.assertNotIn(SATIR, t)
        self.assertEqual(t, encode(" ".join(metin.split()), self.k, self.e, self.i))
        self.assertEqual(decode(t), "Bugün hava çok güzel, değil mi?")

    def test_satır_sonu_boşluk_üretmez(self):
        t = encode("ev  \n  araba", self.k, self.e, self.i)
        self.assertEqual(t, ["ev", SATIR, "a", "ra", "ba"])
        self.assertNotIn(BOŞLUK, t)

    def test_metin_ve_kod_aynı_satır_tokenı(self):
        nid = self.v.tok2id[SATIR]
        self.assertIn(nid, self.v.encode_ids("a\nb", self.k, self.e, self.i))
        self.assertIn(nid, self.v.encode_ids("a\nb", self.k, self.e, self.i, kip="kod"))
        # sekme metin kipinde hâlâ boşluktur (kod tokenı üretmez)
        self.assertNotIn(self.v.tok2id["\t"], self.v.encode_ids("a\tb", self.k, self.e, self.i))


if __name__ == "__main__":
    unittest.main()

"""Kod kipi (K1) — boşluk, satır sonu ve girinti kayıpsız; metin kipi değişmez."""

import os
import random
import unittest
from pathlib import Path

from tokenizer.kokler import çalışma_sözlüğü
from tokenizer.ekler import yükle as ekleri_yükle
from tokenizer.istisna import yükle as istisna_yükle
from tokenizer.pipeline import encode, decode, boşluk_tokenları, BOŞLUK
from tokenizer.vocab import Vocab

KÖK = Path(__file__).resolve().parent.parent
VERİ = KÖK / "veri"


class KodKipiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.k = çalışma_sözlüğü(VERİ / "kokler", VERİ / "zamirler.json", VERİ / "islev_kokleri.json")
        cls.e = ekleri_yükle(VERİ / "ekler.json")
        cls.i = istisna_yükle(VERİ / "istisnalar.json")
        cls.v = Vocab.yükle(VERİ / "vocab.json")
        cls.bayt = {cls.v.tok2id[t] for t in cls.v.id2tok if t.startswith("<0x")}

    def gidip_gel(self, kod):
        ids = self.v.encode_ids(kod, self.k, self.e, self.i, kip="kod")
        return ids, self.v.decode_ids(ids, kip="kod")

    def test_boşluk_tokenları(self):
        self.assertEqual(boşluk_tokenları(" "), [BOŞLUK])
        self.assertEqual(boşluk_tokenları("\n    "), ["\n", BOŞLUK * 4])
        self.assertEqual(boşluk_tokenları(" " * 20), [BOŞLUK * 16, BOŞLUK * 4])
        self.assertEqual(boşluk_tokenları("\r\n\t\t"), ["\r", "\n", "\t", "\t"])

    def test_kenar_durumları(self):
        for kod in ["", " ", "\n", "  x = 1  \n", "\n\n\ndef f():\n\treturn 1\r\n",
                    "a" + " " * 40 + "b", "x\u00a0=\u00a01\x0c\x0b", "▁ ▁▁\n▁",
                    "    # Türkçe yorum: kökü bul\n    değer = İstanbul'da"]:
            ids, geri = self.gidip_gel(kod)
            self.assertEqual(geri, kod, repr(kod))
            self.assertNotIn(self.v.tok2id["<unk>"], ids)

    def test_sıradan_boşluk_bayta_düşmez(self):
        ids, _ = self.gidip_gel("def f(x):\n\tif x:\n        return [x,  x]\r\n")
        self.assertFalse(self.bayt & set(ids))

    def test_depo_kaynak_dosyaları(self):
        # bu deponun TÜM .py dosyaları kod kipinde birebir geri döner, bayt tokenı yok
        dosyalar = sorted(KÖK.glob("**/*.py"))
        self.assertGreater(len(dosyalar), 20)
        for yol in dosyalar:
            kod = yol.read_text(encoding="utf-8")
            ids, geri = self.gidip_gel(kod)
            self.assertEqual(geri, kod, str(yol))

    def test_stdlib_örneklem(self):
        # Python'un kendi kaynağından deterministik örneklem (bu makinedeki stdlib)
        lib = Path(os.__file__).parent
        dosyalar = sorted(p for p in lib.glob("*.py"))
        random.Random(11).shuffle(dosyalar)
        for yol in dosyalar[:25]:
            kod = yol.read_text(encoding="utf-8", errors="surrogateescape")
            _, geri = self.gidip_gel(kod)
            self.assertEqual(geri, kod, str(yol))

    def test_metin_kipi_değişmedi(self):
        # metin kipi boşluğu hâlâ tek ▁'ye indirir ve baş/son kırpar (kurt-veri uyumu)
        t = encode("  ev\n\n  araba  ", self.k, self.e, self.i)
        self.assertEqual(t, ["ev", BOŞLUK, "a", "ra", "ba"])
        self.assertEqual(decode(t), "ev araba")

    def test_bilinmeyen_kip(self):
        with self.assertRaises(ValueError):
            encode("x", self.k, self.e, self.i, kip="python")


if __name__ == "__main__":
    unittest.main()

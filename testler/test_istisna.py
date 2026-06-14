"""istisna modülü — istisna listesi yükleme ve sorgulama testleri."""

import json
import os
import tempfile
import unittest
from pathlib import Path

from tokenizer.istisna import yükle, istisna_bul, İstisnaHatası

İSTİSNA_DOSYASI = Path(__file__).resolve().parent.parent / "veri" / "istisnalar.json"


class İstisnaTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sözlük = yükle(İSTİSNA_DOSYASI)

    def test_yüklenir(self):
        self.assertGreaterEqual(len(self.sözlük), 9)
        for k in ("su", "ne", "bu", "şu", "o", "ve", "ile"):
            self.assertIn(k, self.sözlük)

    def test_gruplar(self):
        self.assertEqual(self.sözlük["su"].grup, "istisnalar")
        self.assertEqual(self.sözlük["internet"].grup, "yabancı")

    def test_tokens_ve_birleşim(self):
        for kelime, ist in self.sözlük.items():
            self.assertEqual("".join(ist.tokens), kelime, kelime)

    def test_bul(self):
        self.assertIsNotNone(istisna_bul(self.sözlük, "ve"))
        self.assertIsNotNone(istisna_bul(self.sözlük, "VE"))   # Türkçe küçültme
        self.assertIsNone(istisna_bul(self.sözlük, "araba"))

    def test_bozuk_reddedilir(self):
        bozuk = {"istisnalar": {"xy": {"tokens": ["x"], "not": "join != xy"}}}
        p = tempfile.mktemp(suffix=".json")
        Path(p).write_text(json.dumps(bozuk, ensure_ascii=False), encoding="utf-8")
        try:
            with self.assertRaises(İstisnaHatası):
                yükle(p)
        finally:
            os.unlink(p)


if __name__ == "__main__":
    unittest.main()

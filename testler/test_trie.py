"""trie modülü — kök öneki trie'si testleri (davranış-koruma + temel doğruluk)."""

import unittest
from pathlib import Path

from tokenizer.kokler import çalışma_sözlüğü
from tokenizer.trie import KökTrie, kök_önekleri

KÖK_DİZİN = Path(__file__).resolve().parent.parent / "veri" / "kokler"
ZAMİR_DOSYASI = Path(__file__).resolve().parent.parent / "veri" / "zamirler.json"
İŞLEV_DOSYASI = Path(__file__).resolve().parent.parent / "veri" / "islev_kokleri.json"


class TrieTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.k = çalışma_sözlüğü(KÖK_DİZİN, ZAMİR_DOSYASI, İŞLEV_DOSYASI)
        cls.trie = KökTrie(cls.k)

    def test_temel_bulma(self):
        # yumuşamış önek (kitap→kitab) ve ünlü-düşmüş önek (akıl→akl) bulunmalı
        self.assertIn("kitap", self.trie.bul("kitabı"))   # softened variant
        self.assertIn("akıl", self.trie.bul("aklı"))      # dropped variant
        self.assertIn("ev", self.trie.bul("evler"))       # düz önek
        self.assertIn("gel", self.trie.bul("geliyor"))

    def test_önek_olmayan_boş(self):
        # hiçbir kök öneki olmayan dizi → boş aday kümesi
        self.assertEqual(self.trie.bul("şçkptr"), set())

    def test_kaba_tarama_eşdeğer(self):
        # DAVRANIŞ KORUMA: trie.bul == eski O(kök) tarama (varyant-öneği hedefin öneki olan)
        def kaba(hedef):
            return {ad for ad, kök in self.k.items()
                    if any(hedef.startswith(p) for p in kök_önekleri(ad, kök))}
        for w in ["kitabı", "aklı", "geliyordu", "öğretmenlerimiz", "arabasında",
                  "gözlüğümü", "kalbine", "yapabilirdik", "evdekiler", "zürafa", "xyzqw"]:
            self.assertEqual(self.trie.bul(w), kaba(w), w)


if __name__ == "__main__":
    unittest.main()

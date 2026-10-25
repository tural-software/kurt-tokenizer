"""v2 kodlaması (V2-1): sözcük başı ▁ + Başlık işaretçisi + ilk token kaynaşması (tokenizer/v2.py).

Kapılar: decode(v2) == decode(v1) her dilin doğrulama metninde ve dil kipleri çapraz; v1 kipi v2 tokenı hiç
üretmez (v1 ID'leri birebir); kod kipinde v2 == v1; kaynaşma token sayısını düşürür.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from tokenizer import diller
from tokenizer.pipeline import encode
from tokenizer.v2 import kaynaştır, yüzey
from tokenizer.pipeline import BOŞLUK, BAŞ_BÜYÜK, ASCII_BAŞ
from tokenizer.vocab import Vocab

VERİ = Path(__file__).resolve().parent.parent / "veri"
DİLLER = (None, "az", "en", "fr", "de")


def _metin(dil):
    return (VERİ / ("korpus" if dil is None else f"{dil}/korpus") / "dogrulama.txt").read_text(encoding="utf-8")


class V2Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.v = Vocab.yükle(VERİ / "vocab.json")
        cls.veri = {d: diller.yükle(d) for d in DİLLER}

    def _ids(self, metin, dil, sürüm, kip="metin", kod_dil=None):
        d = self.veri[dil]
        return self.v.encode_ids(metin, d.kökler, d.ekler, d.istisnalar, kip=kip,
                                 dil=kod_dil if kip == "kod" else dil, sürüm=sürüm)

    def test_yüzey(self):
        self.assertEqual(yüzey(True, BAŞ_BÜYÜK, "istanbul"), "▁İstanbul")
        self.assertEqual(yüzey(True, ASCII_BAŞ, "in"), "▁In")
        self.assertEqual(yüzey(False, None, "gel"), "gel")

    def test_kaynaştır_sırası(self):
        izinli = {"gel", "i", "yor", "um", "haus", "ev", "ler", "in"}.__contains__
        düz, demet = {"▁gel", "Haus", "▁geliyor"}, {"lerin"}
        var = lambda t, d: t in düz if d else (t in demet or izinli(t))
        k = lambda tk: kaynaştır(tk, izinli, var)
        # en uzun eşleşme: ▁geliyor + um
        self.assertEqual(k([BOŞLUK, "gel", "i", "yor", "um"]), ["▁geliyor", "um"])
        # tam önekli dizi yoksa ▁ ayrı + Başlık kaynaşması
        self.assertEqual(k(["x", BOŞLUK, BAŞ_BÜYÜK, "haus"]), ["x", BOŞLUK, "Haus"])
        # iç demet; hiçbiri yoksa v1 dizisi
        self.assertEqual(k([BOŞLUK, "ev", "ler", "in"]), [BOŞLUK, "ev", "lerin"])
        self.assertEqual(k([BOŞLUK, BAŞ_BÜYÜK, "ev"]), [BOŞLUK, BAŞ_BÜYÜK, "ev"])
        # V2-6: ▁ + harf olmayan tek token, düz eşi varsa birleşir; yoksa ayrı kalır
        düz.add("▁(")
        self.assertEqual(k(["ev", BOŞLUK, "(", "ev", ")", BOŞLUK, "-"]), ["ev", "▁(", "ev", ")", BOŞLUK, "-"])

    def test_decode_eşit_ve_kısa(self):
        for dil in DİLLER:
            for metin_dili in DİLLER:                  # çapraz: Almanca metin Türkçe kipte de
                metin = _metin(metin_dili)
                with self.subTest(dil=dil, metin=metin_dili):
                    v1, v2 = self._ids(metin, dil, "v1"), self._ids(metin, dil, "v2")
                    self.assertEqual(self.v.decode_ids(v2), self.v.decode_ids(v1))
                    if dil == metin_dili:
                        self.assertLess(len(v2), 0.85 * len(v1))

    def test_v1_v2_tokenı_üretmez(self):
        for dil in DİLLER:
            ids = self._ids(_metin(dil), dil, "v1")
            self.assertFalse(set(ids) & self.v._v2_id, dil)

    def test_kod_kipi_değişmez(self):
        kod = 'def gel(x):\n    return "Merhaba dünya" + x  # Yorum burada\n'
        self.assertEqual(self._ids(kod, None, "v2", "kod", "python"), self._ids(kod, None, "v1", "kod", "python"))

    def test_kenar_durumları(self):
        for metin in ("İstanbul'da In der Stadt ( gel ) TÜRKİYE Haus", "a\n\nBir  iki", "▁ harfiyen ▁gel",
                      "EVLERİNDE Evlerinde evlerinde ARABALARININ Azərbaycanın", "geliyorum. Geliyorum, GELİYORUM!",
                      "uninsured NEMATODES Zwickau iPhone l’azote ArchWiki", "a ( 1 ) « b » 2,5 - c l'homme \"x\""):     # yedek parçaları birime girer (V2-4)
            for dil in DİLLER:
                with self.subTest(metin=metin, dil=dil):
                    self.assertEqual(self.v.decode_ids(self._ids(metin, dil, "v2")),
                                     self.v.decode_ids(self._ids(metin, dil, "v1")))

    def test_v2_dil_kapısı_yok(self):
        # v1'de Türkçe kip en-1 tokenını kullanamaz (the harf harf); v2'de vocab'daki her harf tokenı açık
        v1, v2 = self._ids("bir the yazısı", None, "v1"), self._ids("bir the yazısı", None, "v2")
        self.assertIn(self.v.tok2id["▁the"], v2)
        self.assertNotIn(self.v.tok2id["the"], v1)
        self.assertEqual(self.v.decode_ids(v2), self.v.decode_ids(v1))

    def test_özel_token_birime_girmez(self):
        # ▁ + HEP BÜYÜK işaretçisi / bayt tokenı düz v2 tokenı olamaz (harfiyen decode'da metne sızardı)
        from tokenizer.v2 import birimler
        izinli = self.v.v2_izinli("metin", None)
        for t in ("<|BB|>", "<|AA|>", "<0xE2>"):
            self.assertNotIn((True, [BOŞLUK, t]), list(birimler([BOŞLUK, t, "ev"], izinli)), t)
        self.assertFalse(any(t.startswith("▁<") and len(t) > 3 for t in self.v._düz))

    def test_boşluk_işaretçi(self):
        # V2-7: demetlenmeyen ▁ + casing işaretçisi tek token; decode v1 ile aynı. v1 bu tokenları üretmez
        m = "Dün TBMM ÜYESİ Kazancıoğulları ile NASA'ya gitti."
        v1, v2 = self._ids(m, None, "v1"), self._ids(m, None, "v2")
        self.assertIn(self.v.tok2id["▁<|BB|>"], v2)
        self.assertFalse(set(v1) & {self.v.tok2id[t] for t in self.v._işaret})
        self.assertEqual(self.v.decode_ids(v2), self.v.decode_ids(v1))
        self.assertEqual(len(self.v._işaret), 4)

    def test_tr1_yalnız_türkçe(self):
        # tr-1 (Türkçe kök heceleri: hakk) yalnız Türkçe metin kipinde
        tid = self.v.tok2id["hakk"]
        self.assertEqual(self.v._id("hakk", "metin", None), tid)
        for dil in ("az", "en", "fr", "de"):
            self.assertIsNone(self.v._id("hakk", "metin", dil), dil)
        self.assertIsNone(self.v._id("hakk", "kod", "python"))

    def test_geçersiz_sürüm(self):
        with self.assertRaises(ValueError):
            self._ids("ev", None, "v3")


if __name__ == "__main__":
    unittest.main()

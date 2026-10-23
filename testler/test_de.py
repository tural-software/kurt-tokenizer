"""Almanca (DE-1): çekim üreteçli çözümleyici + bileşik kuralı + hat entegrasyonu.

Kilitler:
  1. Veri: kokler.txt sıralı/tekil/geçerli; cekim.json örnek fiilleri; üretilen her ek ekler.json'da bildirilmiş.
  2. Altın liste (veri/de/korpus/altin.tsv) birebir.
  3. Kök bütünlüğü: her kök tek başına kendi yalın okumasıyla çözülür. Üret → çözümle: üretilen her biçim geri bulunur.
  4. Bileşik: Fugen ayrı token; belirsiz bileşik (en az parçalı birden çok okuma) BÜTÜN; kısa fiil gövdesi bileşen
     olmaz (Gehalt ≠ geh+alt).
  5. Ayrılmayan önekli fiil tek kök (verstehen), ge- almaz; ayrılabilir önek yalnız sözlükte kayıtlı fiilde.
  6. Casing kayıpsız (ß/ẞ dahil); Başlık biçimi özel ad öne alınmaz (Almancada her ad büyük).
  7. Türkçe kipi değişmez; yedek hece kayıpsız; seçim çözüm sırasından bağımsız (determinizm).
"""

from __future__ import annotations

import random
import tempfile
import unittest
from pathlib import Path

from tokenizer import de, diller
from tokenizer.dil import DE
from tokenizer.hece import hecele
from tokenizer.onay import OnayKuyruğu
from tokenizer.pipeline import ASCII_BAŞ, decode, encode, metin_kanonik
from tokenizer.vocab import Vocab

KÖK = Path(__file__).resolve().parent.parent
VERİ = KÖK / "veri" / "de"
V = diller.yükle("de")


def kodla(metin: str, kuyruk=None) -> list[str]:
    return encode(metin, V.kökler, V.ekler, V.istisnalar, kuyruk, dil="de")


def okuma(sözcük: str) -> list[str]:
    çs, _ = de.çözümle(sözcük, V.kökler, V.ekler, V.istisnalar)
    return de.en_iyi(çs, V.kökler).tokens if çs else []


class Veri(unittest.TestCase):
    def test_yüklenir(self):
        self.assertGreater(len(V.kökler), 500)
        self.assertIn("geben", V.ekler.sınıflar)
        self.assertEqual(V.istisnalar["der"].grup, "belirteç")

    def test_kök_doğrulaması(self):
        with tempfile.TemporaryDirectory() as d:
            yol = Path(d) / "k.txt"
            yol.write_text("verstehen|fiil|k=yok\nhaus|isim|ç=xx\nanfangen|fiil|ay=an\nabc|sıfat\n", encoding="utf-8")
            with self.assertRaises(de.DeVeriHatası) as h:
                de.kökleri_yükle(yol, V.ekler.sınıflar)
            metin = str(h.exception)
            self.assertIn("cekim.json'da yok", metin)    # bilinmeyen sınıf
            self.assertIn("ç=xx geçersiz", metin)
            self.assertIn("tabanı 'fangen' sözlükte yok", metin)
            self.assertIn("sıra", metin)

    def test_istisna_birleşimi(self):
        for k, ist in V.istisnalar.items():
            self.assertEqual("".join(ist.tokens), k)


class AltınListe(unittest.TestCase):
    def test_birebir(self):
        farklar = []
        for satır in (VERİ / "korpus" / "altin.tsv").read_text(encoding="utf-8").splitlines():
            if not satır or satır.startswith("#"):
                continue
            sözcük, beklenen = satır.split("\t")
            if kodla(sözcük) != beklenen.split():
                farklar.append((sözcük, kodla(sözcük), beklenen))
        self.assertEqual(farklar, [])


class SahteBölmeYok(unittest.TestCase):
    def test_kök_bütünlüğü(self):
        bölünen = []
        for ad, k in V.kökler.items():
            if ad in V.istisnalar:
                continue
            beklenen = list(de._kök_tokenları(ad, k))
            if okuma(ad) != beklenen:
                bölünen.append((ad, okuma(ad)))
        self.assertEqual(bölünen, [])

    def test_üret_çözümle_geri_kazanımı(self):
        kayıp = []
        for ad, kök in V.kökler.items():
            for tokenlar, ek in de.biçimler(ad, kök, V.ekler, V.kökler):
                yüzey = "".join(tokenlar)
                if yüzey in V.istisnalar:
                    continue
                çs, _ = de.çözümle(yüzey, V.kökler, V.ekler, V.istisnalar)
                if not any(ç.kök == ad and tuple(ç.tokens) == tokenlar for ç in çs):
                    kayıp.append((ad, tokenlar))
        self.assertEqual(kayıp, [])

    def test_bileşik(self):
        self.assertEqual(okuma("arbeitsplatz"), ["arbeit", "s", "platz"])
        self.assertEqual(okuma("schulbuch"), ["schul", "buch"])               # -e düşmesi
        self.assertEqual(okuma("energiesparlampen"), ["energie", "spar", "lampe", "n"])
        self.assertEqual(okuma("gehalt"), [])                                 # geh+alt değil: kısa fiil gövdesi
        self.assertEqual(okuma("kommentieren"), [])                           # komm+en+tier değil
        self.assertEqual(okuma("finden"), ["finden"])

    def test_belirsiz_bileşik_bütün(self):
        k = {**V.kökler, "stau": de.DeKök(tür="isim"), "staub": de.DeKök(tür="isim"),
             "becken": de.DeKök(tür="isim"), "ecke": de.DeKök(tür="isim", çoğul="n")}
        de._DİZİNLER.clear()
        try:
            çs, _ = de.çözümle("staubecken", k, V.ekler, V.istisnalar)
            self.assertEqual(çs, [])                                          # stau+becken / staub+ecke+n
        finally:
            de._DİZİNLER.clear()

    def test_önekli_fiil(self):
        self.assertEqual(okuma("verstanden"), ["verstand", "en"])           # tek kök, ge- yok
        self.assertEqual(okuma("besucht"), ["besuch", "t"])
        self.assertEqual(okuma("angefangen"), ["an", "ge", "fang", "en"])
        self.assertEqual(okuma("anzufangen"), ["an", "zu", "fangen"])


class CasingVeRoundTrip(unittest.TestCase):
    def test_round_trip(self):
        for m in ("Die Häuser der Kinder", "STRASSE und Straße und STRAßE", "Größte ẞ Probleme", "iPhone-Nutzer"):
            self.assertEqual(decode(kodla(m)), metin_kanonik(m))

    def test_doğrulama_metni(self):
        metin = (VERİ / "korpus" / "dogrulama.txt").read_text(encoding="utf-8")
        self.assertEqual(decode(kodla(metin)), metin_kanonik(metin))

    def test_ad_başlıkta_öne_alınmaz(self):
        self.assertFalse(DE.özel_ad_başlık)
        self.assertEqual(kodla("Häuser"), [ASCII_BAŞ, "häus", "er"])

    def test_bilinmeyen_kuyruğa(self):
        q = OnayKuyruğu()
        self.assertEqual(kodla("xylophon", q), ["xylophon"])
        self.assertEqual([b.kelime for b in q.bekleyenler()], ["xylophon"])

    def test_vocab_round_trip(self):
        v = Vocab.yükle(KÖK / "veri" / "vocab.json")
        metin = (VERİ / "korpus" / "dogrulama.txt").read_text(encoding="utf-8")
        ids = v.encode_ids(metin, V.kökler, V.ekler, V.istisnalar, dil="de")
        self.assertEqual(v.decode_ids(ids), metin_kanonik(metin))

    def test_türkçe_kipi_değişmez(self):
        tr = diller.yükle()
        self.assertEqual(encode("finden", tr.kökler, tr.ekler, tr.istisnalar), ["fin", "den"])


class Hece(unittest.TestCase):
    def test_örnekler(self):
        self.assertEqual(hecele("zucker", DE), ["zu", "cker"])
        self.assertEqual(hecele("arbeiten", DE), ["ar", "bei", "ten"])
        self.assertEqual(hecele("menschen", DE), ["men", "schen"])

    def test_kayıpsız(self):
        rng = random.Random(0)
        for _ in range(2000):
            s = "".join(rng.choice("abcdeäfghiklmnoöprsßtuüvwz") for _ in range(rng.randint(1, 14)))
            self.assertEqual("".join(hecele(s, DE)), s)


class Determinizm(unittest.TestCase):
    def test_sıradan_bağımsız(self):
        for w in ("kinder", "macht", "verstand", "gaben", "leben", "größte", "arbeitsplatz"):
            çs, _ = de.çözümle(w, V.kökler, V.ekler, V.istisnalar)
            beklenen = de.en_iyi(çs, V.kökler)
            for tohum in range(5):
                k = list(çs)
                random.Random(tohum).shuffle(k)
                self.assertEqual(de.en_iyi(k, V.kökler), beklenen)


if __name__ == "__main__":
    unittest.main()

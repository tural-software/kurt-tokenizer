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


def okuma(sözcük: str, ad: bool = False) -> list[str]:
    """ad: sözcük Başlık biçiminde yazılmış (Almanca adlar büyük yazılır → ad okuması öne)."""
    çs, _ = de.çözümle(sözcük, V.kökler, V.ekler, V.istisnalar)
    return de.en_iyi(çs, V.kökler, ad).tokens if çs else []


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
            # özel ad okuması bilerek SONDA (Sachsen = sachse+n da doğru); geri kök bilerek kaybeder (habe = hab+e)
            if ad in V.istisnalar or k.tür == "özel" or k.geri:
                continue
            beklenen = list(de._kök_tokenları(ad, k))
            yazım = "isim" in k.sınıflar()                    # ad kökü Başlık biçiminde yazılır (Strafe ≠ strafe)
            if okuma(ad, yazım) != beklenen:
                bölünen.append((ad, okuma(ad, yazım)))
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
        # kısa fiil gövdesi bileşen olmaz (sözlükten bağımsız: bölücü bu okumayı hiç üretmez)
        okumalar = lambda w: {a[0] for a in de._bileşik(w, V.kökler, V.ekler, V.istisnalar)}
        self.assertNotIn(("geh", "alt"), okumalar("gehalt"))
        self.assertFalse({o for o in okumalar("kommentieren") if o[:2] == ("komm", "en")})
        self.assertEqual(okuma("gehalt"), ["gehalt"])                         # Wikidata kökü: bütün
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


class Triyaj(unittest.TestCase):
    """DE-3: sık bilinmeyen triyajında eklenen kurallar."""

    def test_yazım_varyantı(self):
        self.assertEqual(okuma("grosse"), ["gross", "e"])                    # İsviçre yazımı ← groß
        self.assertEqual(okuma("mußte"), ["muß", "te"])                      # 1996 öncesi ← musste
        self.assertEqual(okuma("iſt"), ["iſt"])                              # uzun s ← ist
        self.assertEqual(okuma("zollstrasse"), [])                           # zoll+s+trasse / zoll+strasse: belirsiz

    def test_ad_çekimi(self):
        self.assertEqual(okuma("herrn", True), ["herr", "n"])                # zayıf tekil -n, çoğul -en
        self.assertEqual(okuma("ergebnisses", True), ["ergebniss", "es"])    # -nis ikizleşir
        self.assertEqual(okuma("instituts", True), ["institut", "s"])        # tamlayan (e)s
        self.assertEqual(okuma("leistungs", True), ["leistung", "s"])        # Fugen-s ön parça (Leistungs- und …)

    def test_fiil(self):
        self.assertEqual(okuma("bezeichnet"), ["bezeichn", "et"])            # ch + n: ek ünlüsü
        self.assertEqual(okuma("ausgestattet"), ["aus", "ge", "statt", "et"])   # bağlı taban (statten sözcük değil)
        self.assertEqual(okuma("geschaffen"), ["ge", "schaff", "en"])        # zayıf_da: schuf/geschaffen
        self.assertEqual(okuma("geschafft"), ["ge", "schaff", "t"])          # + schaffte/geschafft
        self.assertEqual(okuma("übersetzt"), ["übersetz", "t"])              # iki yönlü önek: korpus kanıtı
        self.assertEqual(okuma("geeignetsten"), ["geeignet", "st", "en"])    # vurgusuz -et en üstünlük

    def test_bileşik_kuralları(self):
        self.assertEqual(okuma("urheberrecht"), ["urheber", "recht"])        # baş çekimli fiil olamaz (rech+t)
        self.assertEqual(okuma("nichttragende"), ["nicht", "trag", "end", "e"])   # ortaç baş olur
        self.assertEqual(okuma("benutzeroberfläche"), ["benutzer", "ober", "fläche"])   # az fiil gövdesi
        self.assertEqual(okuma("bundesamt"), ["bund", "es", "amt"])          # Fugen bileşenin çekimine uyar
        okumalar = {a[0] for a in de._bileşik("frohnhauser", V.kökler, V.ekler, V.istisnalar)}
        self.assertFalse({o for o in okumalar if o[:2] == ("froh", "n")})    # sıfat bileşen Fugen almaz

    def test_istisna_grupları(self):
        self.assertEqual(kodla("dreiundzwanzig"), ["drei", "und", "zwanzig"])
        self.assertEqual(V.istisnalar["entweder"].grup, "bağlaç_ek")
        self.assertEqual(V.istisnalar["the"].grup, "yabancı")


class CasingVeRoundTrip(unittest.TestCase):
    def test_round_trip(self):
        for m in ("Die Häuser der Kinder", "STRASSE und Straße und STRAßE", "Größte ẞ Probleme", "iPhone-Nutzer"):
            self.assertEqual(decode(kodla(m)), metin_kanonik(m))

    def test_doğrulama_metni(self):
        metin = (VERİ / "korpus" / "dogrulama.txt").read_text(encoding="utf-8")
        q = OnayKuyruğu()
        self.assertEqual(decode(kodla(metin, q)), metin_kanonik(metin))
        self.assertEqual([b.kelime for b in q.bekleyenler()], [])      # DE-5 kapısı: 10 alan, bilinmeyen 0

    def test_ad_başlıkta_öne_alınmaz(self):
        self.assertFalse(DE.özel_ad_başlık)
        self.assertEqual(kodla("Häuser"), [ASCII_BAŞ, "häus", "er"])

    def test_bilinmeyen_kuyruğa(self):
        q = OnayKuyruğu()
        self.assertEqual(kodla("qxzwort", q), ["qxzwort"])
        self.assertEqual([b.kelime for b in q.bekleyenler()], ["qxzwort"])

    def test_vocab_round_trip(self):
        v = Vocab.yükle(KÖK / "veri" / "vocab.json")
        metin = (VERİ / "korpus" / "dogrulama.txt").read_text(encoding="utf-8")
        ids = v.encode_ids(metin, V.kökler, V.ekler, V.istisnalar, dil="de")
        self.assertEqual(v.decode_ids(ids), metin_kanonik(metin))

    def test_de1_bölümü_dil_kapısı(self):
        # de-1 tokenları YALNIZ dil="de" metin kipinde; önce eklenmiş ortak diller (EN, FR) de-1'i göremez.
        from tokenizer.vocab import EK_BÖLÜMLER
        v = Vocab.yükle(KÖK / "veri" / "vocab.json")
        de1 = {v.tok2id[t] for ad, b in EK_BÖLÜMLER if ad == "de-1" for t in b}
        self.assertEqual(len(de1), 3800)
        metin = (VERİ / "korpus" / "dogrulama.txt").read_text(encoding="utf-8") + " GROẞE Straße"
        ids = v.encode_ids(metin, V.kökler, V.ekler, V.istisnalar, dil="de")
        self.assertTrue(de1 & set(ids))
        self.assertEqual(v.decode_ids(ids), metin_kanonik(metin))
        self.assertIn(v.tok2id["ẞ"], v.encode_ids("ẞ", V.kökler, V.ekler, V.istisnalar, dil="de"))
        tr, az, en, fr = diller.yükle(), diller.yükle("az"), diller.yükle("en"), diller.yükle("fr")
        self.assertFalse(de1 & set(v.encode_ids(metin, tr.kökler, tr.ekler, tr.istisnalar)))
        self.assertFalse(de1 & set(v.encode_ids(metin, tr.kökler, tr.ekler, tr.istisnalar, kip="kod")))
        self.assertFalse(de1 & set(v.encode_ids(metin, az.kökler, az.ekler, az.istisnalar, dil="az")))
        self.assertFalse(de1 & set(v.encode_ids(metin, en.kökler, en.ekler, en.istisnalar, dil="en")))
        self.assertFalse(de1 & set(v.encode_ids(metin, fr.kökler, fr.ekler, fr.istisnalar, dil="fr")))

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

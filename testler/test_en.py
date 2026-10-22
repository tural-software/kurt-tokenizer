"""İngilizce (EN-1): yazım kurallı çözümleyici + hat entegrasyonu + vocab dil kapısı.

Kilitler:
  1. Veri: kokler.txt sıralı/tekil/geçerli; ekler.json ve istisnalar.json doğrulanır.
  2. Altın liste (veri/en/korpus/altin.tsv) birebir.
  3. Kök bütünlüğü: her kök tek başına BÜTÜN okunur (sahte bölme yok: since ≠ sinc+e, corner ≠ corn+er).
  4. Üret → çözümle geri kazanımı: üreteçle türetilen yüzeyin çözümleri o (kök, ekler) okumasını içerir.
  5. Casing (Unicode kuralı, ASCII işaretçisi): I → <|Ab|> i; klitikli HEP BÜYÜK bütün; round-trip kayıpsız.
  6. Türkçe kipi İngilizce eklendi diye değişmez; EN metin kipinde ASCII işaretçisi vocab'da açık.
  7. Yedek hece: birleşim = girdi; seçim çözüm sırasından bağımsız (determinizm).
"""

from __future__ import annotations

import random
import tempfile
import unittest
from pathlib import Path

from tokenizer import diller, en
from tokenizer.dil import EN
from tokenizer.hece import hecele
from tokenizer.pipeline import ASCII_BAŞ, ASCII_HEP, decode, encode, metin_kanonik
from tokenizer.vocab import Vocab

KÖK = Path(__file__).resolve().parent.parent
VERİ = KÖK / "veri" / "en"
V = diller.yükle("en")


def kodla(metin: str) -> list[str]:
    return encode(metin, V.kökler, V.ekler, V.istisnalar, dil="en")


class Veri(unittest.TestCase):
    def test_yüklenir(self):
        self.assertGreater(len(V.kökler), 500)
        self.assertIn("çoğul", V.ekler)
        self.assertIn("went", V.istisnalar)

    def test_kök_doğrulaması(self):
        with tempfile.TemporaryDirectory() as d:
            yol = Path(d) / "k.txt"
            yol.write_text("run|fiil|çift\nbig|sıfat\ngo|fiil|çift\nhero|isim\n", encoding="utf-8")
            with self.assertRaises(en.EnVeriHatası) as h:
                en.kökleri_yükle(yol)
            metin = str(h.exception)
            self.assertIn("sıra", metin)              # big < run
            self.assertIn("çift yalnız", metin)       # go ünlü-sonu

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
        # özel ad kökü Başlık biçiminde bütün (küçük harfte sıradan okuma yeğlenir: wells = well+s)
        bölünen = [ad for ad, k in V.kökler.items()
                   if (kodla(ad.capitalize()) != [ASCII_BAŞ, ad] if k.tür == "özel" else kodla(ad) != [ad])]
        self.assertEqual(bölünen, [])

    def test_üret_çözümle_geri_kazanımı(self):
        zincirler = {"isim": [["çoğul"]], "fiil": [["şimdiki_3tekil"], ["geçmiş"], ["ortaç_ing"], ["yapım_er"]],
                     "sıfat": [["karşılaştırma"], ["üstünlük"], ["yapım_ly"], ["yapım_ness"]]}
        kayıp = []
        for ad, kök in V.kökler.items():
            for sınıf in kök.sınıflar():
                for z in zincirler.get(sınıf, []):
                    if z[0] in kök.engel:              # düzensiz biçimli kök (see → saw): düzenli ek bilerek yok
                        continue
                    _, yüzey = en.üret(ad, kök, z, V.ekler)
                    if yüzey in V.istisnalar:          # düzensiz biçim (better, being) bütün tutulur
                        continue
                    çs, _ = en.çözümle(yüzey, V.kökler, V.ekler, V.istisnalar, EN.klitikler)
                    if not any(ç.kök == ad and ç.ekler == z for ç in çs):
                        kayıp.append((ad, z, yüzey))
        self.assertEqual(kayıp, [])

    def test_düzensiz_engeli(self):
        # see → saw, be → was: düzenli -ed yok (seed ≠ see+ed, bed ≠ be+ed); child → children: childs yok
        self.assertIn("geçmiş", V.kökler["see"].engel)
        for w in ("seed", "bed", "childs"):
            çs, _ = en.çözümle(w, V.kökler, V.ekler, V.istisnalar, EN.klitikler)
            self.assertFalse([ç for ç in çs if ç.kök in ("see", "be", "child")], w)

    def test_önek_kök_sınırı(self):
        self.assertEqual(kodla("univ"), ["univ"])              # un+iv değil (Roma rakamı lemması)
        self.assertEqual(kodla("unsubscribe"), ["un", "subscribe"])

    def test_geri_kök(self):
        self.assertTrue(V.kökler["doe"].geri)
        self.assertEqual(kodla("does"), ["do", "es"])          # doe+s değil
        self.assertEqual(kodla("doe"), ["doe"])                # tek okumada geri etkisiz

    def test_özel_ad(self):
        self.assertEqual(V.kökler["london"].tür, "özel")
        self.assertEqual(kodla("Londoners")[:1], [ASCII_BAŞ])
        self.assertEqual(kodla("Kennedys"), [ASCII_BAŞ, "kennedy", "s"])     # özel ad çoğulu -ys (Kennedies değil)
        self.assertEqual(kodla("Americans"), [ASCII_BAŞ, "american", "s"])
        self.assertEqual(kodla("Bayer"), [ASCII_BAŞ, "bayer"])               # Başlık: ad bütün
        self.assertEqual(kodla("bayer"), ["bay", "er"])                     # küçük harf: sıradan okuma
        self.assertEqual(kodla("mister"), ["mister"])                       # mist+er değil
        çs, _ = en.çözümle("londonly", V.kökler, V.ekler, V.istisnalar, EN.klitikler)
        self.assertEqual(çs, [])                                             # özel ad yalnız çoğul alır

    def test_istisna_grupları(self):
        for w, grup in (("x", "harf"), ("th", "kısaltma"), ("www", "web"), ("von", "yabancı"),
                        ("multi", "önek_parça"), ("gonna", "konuşma")):
            self.assertEqual(V.istisnalar[w].grup, grup)
        self.assertEqual(kodla("5th"), ["5", "th"])
        self.assertEqual(kodla("won't"), ["wo", "n't"])                     # klitik kalıp grubu korunur
        self.assertEqual(kodla("cannot"), ["can", "not"])
        self.assertEqual(kodla("dont"), ["do", "nt"])                       # kesmesiz klitik (kapalı liste)
        self.assertEqual(kodla("wont"), ["wont"])                           # gerçek sözcük: listeye girmez
        self.assertEqual(kodla("freshmen"), ["freshmen"])                    # -man → -men düzensiz
        self.assertEqual(kodla("penned"), ["pen", "n", "ed"])               # pent düzensizi düzenliyi engellemez
        self.assertEqual(kodla("ups"), ["up", "s"])                          # kapalı sınıf + ad okuması

    def test_ek_sınıf_kısıtı(self):
        self.assertEqual(kodla("corner"), ["corner"])         # corn (isim) + -er (sıfat/fiil eki) yok
        çs, _ = en.çözümle("newer", V.kökler, V.ekler, V.istisnalar, EN.klitikler)
        self.assertEqual([ç.ekler for ç in çs], [["karşılaştırma"]])


class CasingVeRoundTrip(unittest.TestCase):
    def test_i_ve_başlık(self):
        self.assertEqual(kodla("I"), [ASCII_BAŞ, "i"])
        self.assertEqual(kodla("THE"), [ASCII_HEP, "the"])
        self.assertEqual(kodla("Don't"), [ASCII_BAŞ, "do", "n't"])
        self.assertEqual(kodla("DON'T"), ["DON'T"])           # klitikli HEP BÜYÜK bütün (kayıpsız)

    def test_kesme_eki_yok(self):
        # Türkçedeki kesme sonrası ek kuralı EN'de kapalı: O'Brien iki sözcük, Brien Başlık işaretli
        self.assertEqual(kodla("O'Brien"), [ASCII_BAŞ, "o", "'", ASCII_BAŞ, "brien"])

    def test_doğrulama_metni(self):
        metin = (VERİ / "korpus" / "dogrulama.txt").read_text(encoding="utf-8")
        self.assertEqual(decode(kodla(metin)), metin_kanonik(metin))
        vocab = Vocab.yükle(KÖK / "veri" / "vocab.json")
        ids = vocab.encode_ids(metin, V.kökler, V.ekler, V.istisnalar, dil="en")
        self.assertEqual(vocab.decode_ids(ids), metin_kanonik(metin))

    def test_vocab_ascii_işaretçisi_yalnız_en_metin(self):
        vocab = Vocab.yükle(KÖK / "veri" / "vocab.json")
        ab = vocab.tok2id[ASCII_BAŞ]
        self.assertIn(ab, vocab.encode_ids("The end", V.kökler, V.ekler, V.istisnalar, dil="en"))
        tr = diller.yükle()
        self.assertNotIn(ab, vocab.encode_ids("The end", tr.kökler, tr.ekler, tr.istisnalar))
        self.assertIsNone(vocab._id(ASCII_BAŞ, "metin", None))
        self.assertIsNone(vocab._id(ASCII_BAŞ, "metin", "az"))

    def test_türkçe_kipi_değişmez(self):
        tr = diller.yükle()
        self.assertEqual(encode("I don't", tr.kökler, tr.ekler, tr.istisnalar)[:2], ["<|Bb|>", "ı"])


class Hece(unittest.TestCase):
    def test_örnekler(self):
        self.assertEqual(hecele("information", EN), ["in", "for", "ma", "tion"])
        self.assertEqual(hecele("happy", EN), ["hap", "py"])
        self.assertEqual(hecele("strength", EN), ["strength"])
        self.assertEqual(hecele("player", EN), ["pla", "yer"])

    def test_kayıpsız(self):
        rng = random.Random(0)
        for _ in range(2000):
            s = "".join(rng.choice("abcdefghijklmnopqrstuvwxyz'") for _ in range(rng.randint(1, 14)))
            self.assertEqual("".join(hecele(s, EN)), s)


class Determinizm(unittest.TestCase):
    def test_sıradan_bağımsız(self):
        for w in ("leaves", "lies", "studies", "unhappiness", "buildings"):
            çs, _ = en.çözümle(w, V.kökler, V.ekler, V.istisnalar, EN.klitikler)
            beklenen = en.en_iyi(çs)
            for tohum in range(5):
                k = list(çs)
                random.Random(tohum).shuffle(k)
                self.assertEqual(en.en_iyi(k), beklenen)


if __name__ == "__main__":
    unittest.main()

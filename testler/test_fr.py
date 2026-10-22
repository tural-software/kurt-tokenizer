"""Fransızca (FR-1): çekim üreteçli çözümleyici + elizyon + hat entegrasyonu + vocab dil kapısı.

Kilitler:
  1. Veri: kokler.txt sıralı/tekil/geçerli; cekim.json sınıfları; üretilen her ek ekler.json'da bildirilmiş.
  2. Altın liste (veri/fr/korpus/altin.tsv) birebir.
  3. Kök bütünlüğü: her kök tek başına BÜTÜN okunur. Üret → çözümle: üretilen her biçimin okumaları kendini içerir.
  4. Seçim: gövdesi değişmemiş ad okuması (portes = porte+s), düzensiz tek token (suis), seyrek kip sonda (dis = di+s).
  5. Elizyon solda ayrı token, kesme biçimi korunur; kesmeli bütün sözcük (aujourd'hui) tek token; casing kayıpsız.
  6. Türkçe/AZ/EN kipi Fransızca eklendi diye değişmez (regresyon kapıları ayrıca); FR metin kipi ASCII işaretçisini kullanır.
  7. Yedek hece: birleşim = girdi; seçim çözüm sırasından bağımsız (determinizm).
"""

from __future__ import annotations

import random
import tempfile
import unittest
from pathlib import Path

from tokenizer import diller, fr
from tokenizer.dil import FR
from tokenizer.hece import hecele
from tokenizer.onay import OnayKuyruğu
from tokenizer.pipeline import ASCII_BAŞ, ASCII_HEP, decode, encode, metin_kanonik
from tokenizer.vocab import Vocab

KÖK = Path(__file__).resolve().parent.parent
VERİ = KÖK / "veri" / "fr"
V = diller.yükle("fr")


def kodla(metin: str, kuyruk=None) -> list[str]:
    return encode(metin, V.kökler, V.ekler, V.istisnalar, kuyruk, dil="fr")


def okuma(sözcük: str) -> list[str]:
    çs, _ = fr.çözümle(sözcük, V.kökler, V.ekler, V.istisnalar)
    return fr.en_iyi(çs, V.kökler).tokens if çs else []


class Veri(unittest.TestCase):
    def test_yüklenir(self):
        self.assertGreater(len(V.kökler), 700)
        self.assertIn("ons", V.ekler.ekler)
        self.assertIn("l'", V.istisnalar)
        self.assertEqual(V.istisnalar["l'"].grup, "elizyon")

    def test_kök_doğrulaması(self):
        with tempfile.TemporaryDirectory() as d:
            yol = Path(d) / "k.txt"
            yol.write_text("vendre|fiil\nparler|fiil|k=yok\nchat|isim|aux\nabc|sıfat\n", encoding="utf-8")
            with self.assertRaises(fr.FrVeriHatası) as h:
                fr.kökleri_yükle(yol, V.ekler.sınıflar)
            metin = str(h.exception)
            self.assertIn("k=) ister", metin)            # -re fiili sınıfsız
            self.assertIn("cekim.json'da yok", metin)    # bilinmeyen sınıf
            self.assertIn("aux yalnız", metin)           # chat -al değil
            self.assertIn("sıra", metin)                 # abc < chat

    def test_ekler_bildirilmiş(self):
        # veri_yükle bildirilmemiş eki reddeder; burada tüm biçimlerin ekleri kümede
        for ad, kök in V.kökler.items():
            for tokenlar, _ in fr.biçimler(ad, kök, V.ekler):
                self.assertTrue(set(tokenlar[1:]) <= V.ekler.ekler, (ad, tokenlar))

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
        bölünen = [ad for ad, k in V.kökler.items()
                   if (kodla(ad.capitalize()) != [ASCII_BAŞ, ad] if k.tür == "özel" else kodla(ad) != [ad])]
        self.assertEqual(bölünen, [])

    def test_üret_çözümle_geri_kazanımı(self):
        kayıp = []
        for ad, kök in V.kökler.items():
            for tokenlar, ek in fr.biçimler(ad, kök, V.ekler):
                yüzey = "".join(tokenlar)
                if yüzey in V.istisnalar:
                    continue
                çs, _ = fr.çözümle(yüzey, V.kökler, V.ekler, V.istisnalar)
                if not any(ç.kök == ad and tuple(ç.tokens) == tokenlar for ç in çs):
                    kayıp.append((ad, tokenlar))
        self.assertEqual(kayıp, [])

    def test_önek_sınırı(self):
        self.assertEqual(okuma("présent"), [])              # pré+sent (sentir) değil: pré- önek değil
        self.assertEqual(okuma("désert"), [])               # dé+sert (servir) değil: kalan yüzey < 5
        self.assertEqual(okuma("redire"), ["redire"])       # kök bütün
        self.assertEqual(okuma("antisocial"), ["anti", "social"])
        self.assertEqual(okuma("refermons"), ["re", "ferm", "ons"])   # refermer kök değil: re + fermer
        self.assertEqual(okuma("relevons"), ["relev", "ons"])         # relever kök: önek okunmaz

    def test_seçim(self):
        self.assertEqual(okuma("portes"), ["porte", "s"])          # ad çoğulu (port+es fiil değil)
        self.assertEqual(okuma("avions"), ["avion", "s"])
        self.assertEqual(okuma("suis"), ["suis"])                  # être (sui+s suivre değil)
        self.assertEqual(okuma("dis"), ["di", "s"])                # şimdiki (d+is basit geçmiş değil)
        self.assertEqual(okuma("été"), ["été"])                    # bütün kök (ét+é ortaç değil)

    def test_1990_yazımı(self):
        self.assertEqual(okuma("connaît"), ["connaî", "t"])
        self.assertEqual(okuma("connait"), ["connai", "t"])
        self.assertEqual(okuma("ognon"), ["ognon"])
        self.assertEqual(okuma("cèderai"), ["cèder", "ai"])
        self.assertEqual(okuma("céderai"), ["céder", "ai"])


class Elizyon(unittest.TestCase):
    def test_elizyon_solda_ayrı(self):
        self.assertEqual(kodla("l'homme"), ["l'", "homme"])
        self.assertEqual(kodla("l’homme"), ["l’", "homme"])            # kesme biçimi korunur
        self.assertEqual(kodla("qu'il"), ["qu'", "il"])
        self.assertEqual(kodla("jusqu'à"), ["jusqu'", "à"])
        self.assertEqual(kodla("L'État"), [ASCII_BAŞ, "l'", ASCII_BAŞ, "état"])

    def test_kesmeli_bütün(self):
        self.assertEqual(kodla("aujourd'hui"), ["aujourd'hui"])
        self.assertEqual(kodla("aujourd’hui"), ["aujourd’hui"])
        self.assertEqual(kodla("Aujourd'hui"), [ASCII_BAŞ, "aujourd'hui"])

    def test_elizyon_olmayan_kesme(self):
        # kesmeden önceki parça elizyon değilse dokunulmaz (O'Neill: o, ', neill)
        self.assertEqual(kodla("O'Neill")[:3], [ASCII_BAŞ, "o", "'"])

    def test_hep_büyük_elizyon(self):
        t = kodla("QU'IL")
        self.assertEqual(t, [ASCII_HEP, "qu'", ASCII_HEP, "il"])
        self.assertEqual(decode(t), "QU'IL")


class CasingVeRoundTrip(unittest.TestCase):
    def test_round_trip(self):
        for m in ("L'homme qu'il a vu n'est pas venu aujourd’hui.", "Œuvre du cœur, ÇA VA ? a-t-il dit.",
                  "Les États-Unis et l'Union européenne."):
            self.assertEqual(decode(kodla(m)), metin_kanonik(m))

    def test_doğrulama_metni(self):
        metin = (VERİ / "korpus" / "dogrulama.txt").read_text(encoding="utf-8")
        self.assertEqual(decode(kodla(metin)), metin_kanonik(metin))

    def test_bilinmeyen_kuyruğa(self):
        q = OnayKuyruğu()
        self.assertEqual(kodla("xylophone", q), ["xylophone"])
        self.assertEqual([b.kelime for b in q.bekleyenler()], ["xylophone"])

    def test_vocab_round_trip_ve_dil_kapısı(self):
        v = Vocab.yükle(KÖK / "veri" / "vocab.json")
        metin = (VERİ / "korpus" / "dogrulama.txt").read_text(encoding="utf-8")
        ids = v.encode_ids(metin, V.kökler, V.ekler, V.istisnalar, dil="fr")
        self.assertEqual(v.decode_ids(ids), metin_kanonik(metin))
        self.assertIn(v.tok2id[ASCII_BAŞ], ids)                  # FR metin kipi ASCII işaretçisini kullanır
        en_bölümü = {v.tok2id[t] for t in __import__("json").loads(
            (KÖK / "veri" / "en" / "vocab_en1.json").read_text(encoding="utf-8"))["tokenlar"] if t in v.tok2id}
        self.assertTrue(en_bölümü & set(ids))                     # ortak dizgi (EN bölümü) FR'de açık

    def test_türkçe_kipi_değişmez(self):
        tr = diller.yükle()
        self.assertEqual(encode("l'homme", tr.kökler, tr.ekler, tr.istisnalar)[:2], ["l", "'"])


class Hece(unittest.TestCase):
    def test_örnekler(self):
        self.assertEqual(hecele("information", FR), ["in", "for", "ma", "tion"])
        self.assertEqual(hecele("château", FR), ["châ", "teau"])
        self.assertEqual(hecele("problème", FR), ["pro", "blè", "me"])
        self.assertEqual(hecele("oiseau", FR), ["oi", "seau"])

    def test_kayıpsız(self):
        rng = random.Random(0)
        for _ in range(2000):
            s = "".join(rng.choice("abcdeéèfghiîjlmnoôœpqrstuûvyz'") for _ in range(rng.randint(1, 14)))
            self.assertEqual("".join(hecele(s, FR)), s)


class Determinizm(unittest.TestCase):
    def test_sıradan_bağımsız(self):
        for w in ("avions", "suis", "complète", "dis", "vins", "causes"):
            çs, _ = fr.çözümle(w, V.kökler, V.ekler, V.istisnalar)
            beklenen = fr.en_iyi(çs, V.kökler)
            for tohum in range(5):
                k = list(çs)
                random.Random(tohum).shuffle(k)
                self.assertEqual(fr.en_iyi(k, V.kökler), beklenen)


if __name__ == "__main__":
    unittest.main()

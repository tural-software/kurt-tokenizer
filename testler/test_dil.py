"""Dil profili altyapısı (AZ-1): Türkçe yol birebir aynı + profil parametresi gerçekten işler.

Kilitler:
  1. TR profili = sesler/alfabe/ekler/birlestir sabitlerinin KENDİSİ.
  2. Açık profil=TR ile varsayılan (None) çıktısı birebir (çözümle, hecele, ek_çöz, encode).
  3. AZ ses kuralları: ə ince-düz, A→a/ə, Q→q/k, D/C şablonda yazılmaz, 32 harf sıralama.
  4. encode(dil="az"): o dilin sözlüğüyle çözümler, dil anahtarlı önbellek, geçersiz dil hata.
  5. Vocab dil kapısı: az-* bölümü tokenı yalnız dil="az" metin kipinde açık.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from tokenizer import alfabe, sesler
from tokenizer.birlestir import _ince_çevir, birleştir
from tokenizer.cozumle import çözümle
from tokenizer.dil import AZ, TR, DOĞAL_DİLLER, PROFİLLER
from tokenizer.ekler import SERT, Ek, ek_çöz
from tokenizer.ekler import yükle as ekleri_yükle
from tokenizer.hece import hecele
from tokenizer.istisna import yükle as istisna_yükle
from tokenizer.kokler import çalışma_sözlüğü
from tokenizer.onay import OnayKuyruğu
from tokenizer.pipeline import BAŞ_BÜYÜK, BOŞLUK, decode, encode, metin_kanonik, _altbirimler
from tokenizer.sema import Kök, doğrula
from tokenizer.vocab import EK_BÖLÜMLER, Vocab, dil_bölümü

KÖK = Path(__file__).resolve().parent.parent
VERİ = KÖK / "veri"


def _kök(ad: str, tür: str, profil, **alanlar) -> Kök:
    son_ü = profil.son_ünlü_bul(ad)
    return Kök(tokens=hecele(ad, profil), tür=tür, son_ünlü=son_ü,
               son_ses="ünlü" if ad[-1] in profil.ünlüler else "ünsüz", **alanlar)


# AZ-1 için küçük bir deneme sözlüğü (gerçek AZ verisi AZ-2/3'te veri/az/ altında gelir).
AZ_KÖKLER = {ad: _kök(ad, tür, AZ, **x) for ad, tür, x in [
    ("ev", "isim", {}), ("kitab", "isim", {}), ("gəl", "fiil", {}), ("al", "fiil", {}),
    ("işlə", "fiil", {}), ("oxu", "fiil", {}),
    ("uşaq", "isim", {"değişim": {"q→ğ": "ünlü_ile_başlayan_ek_gelince"}}),
    ("çörək", "isim", {"değişim": {"k→y": "ünlü_ile_başlayan_ek_gelince"}}),
]}
AZ_EKLER = {
    "çoğul": Ek(şablon="lAr", tür="çoğul", öbek="isim", yuva=1),
    "belirtme": Ek(şablon="(n)I", tür="belirtme", öbek="isim", yuva=3),
    "bulunma": Ek(şablon="dA", tür="bulunma", öbek="isim", yuva=3),
    "görülen_geçmiş": Ek(şablon="dI", tür="görülen_geçmiş", öbek="fiil", yuva=2),
    "olumsuz": Ek(şablon="mA", tür="olumsuz", öbek="fiil", yuva=1),
    "şimdiki_zaman": Ek(şablon="(y)Ir", tür="şimdiki_zaman", öbek="fiil", yuva=2, daraltır=True),
    "gelecek_zaman": Ek(şablon="(y)AcAQ", tür="gelecek_zaman", öbek="fiil", yuva=2,
                        değişim={"q→ğ": "x", "k→y": "x"}),
}


class TürkçeProfilEşitliği(unittest.TestCase):
    def test_sabitler(self):
        self.assertEqual(TR.alfabe, alfabe.ALFABE)
        self.assertIs(TR.ünlüler, sesler.ÜNLÜLER)
        self.assertEqual((TR.kalın, TR.ince, TR.düz, TR.yuvarlak),
                         (sesler.KALIN, sesler.İNCE, sesler.DÜZ, sesler.YUVARLAK))
        self.assertEqual(TR.sert, SERT)
        self.assertEqual(TR.geniş_ince, "e")
        for ü in sesler.ÜNLÜLER:
            self.assertEqual(TR.ince_çevir(ü), _ince_çevir(ü), ü)
            self.assertEqual(TR.artlık(ü), sesler.artlık(ü))
            self.assertEqual(TR.yuvarlaklık(ü), sesler.yuvarlaklık(ü))
        for s in ("İstanbul", "ISPARTA", "ılık", "çağ"):
            self.assertEqual(TR.küçült(s), sesler.türkçe_küçült(s))
            self.assertEqual(TR.büyült(s), sesler.türkçe_büyült(s))
        for s in ("çağ", "kâr", "ılık", "zürafa"):
            self.assertEqual(TR.alfabetik_anahtar(s), alfabe.alfabetik_anahtar(s))

    def test_profil_listesi(self):
        self.assertEqual(PROFİLLER["tr"], TR)
        self.assertEqual(DOĞAL_DİLLER, frozenset({"az"}))   # Türkçe dil=None ile seçilir


class AçıkTürkçeProfilBirebir(unittest.TestCase):
    """profil=TR ile profil=None aynı çıktıyı vermeli (gerçek sözlük, doğrulama korpusu)."""

    @classmethod
    def setUpClass(cls):
        cls.k = çalışma_sözlüğü(VERİ / "kokler", VERİ / "zamirler.json", VERİ / "islev_kokleri.json")
        cls.e = ekleri_yükle(VERİ / "ekler.json")
        cls.i = istisna_yükle(VERİ / "istisnalar.json")
        metin = (VERİ / "korpus" / "dogrulama.txt").read_text(encoding="utf-8")
        cls.kelimeler = sorted({sesler.türkçe_küçült(a) for p in metin.split()
                                for a, harf in _altbirimler(p) if harf})

    def test_çözümle_birebir(self):
        for w in self.kelimeler:
            self.assertEqual(çözümle(w, self.k, self.e, self.i),
                             çözümle(w, self.k, self.e, self.i, profil=TR), w)

    def test_hecele_birebir(self):
        for w in self.kelimeler:
            self.assertEqual(hecele(w), hecele(w, TR), w)

    def test_birleştir_ve_ek_çöz_birebir(self):
        for ad in ("kitap", "oyna", "akıl", "kalp", "git", "ye", "gel", "oku"):
            kök = self.k[ad]
            sınıf = "fiil" if kök.tür == "fiil" else "isim"
            for ek_ad, ek in self.e.items():
                if ek.öbek not in (sınıf, "her"):
                    continue
                try:
                    a = birleştir(ad, kök, [ek_ad], self.e)
                except Exception as hata:          # üretilemeyen bileşim: iki yolda da aynı hata
                    with self.assertRaises(type(hata)):
                        birleştir(ad, kök, [ek_ad], self.e, TR)
                    continue
                self.assertEqual(a, birleştir(ad, kök, [ek_ad], self.e, TR), (ad, ek_ad))
        for şablon in ("lAr", "(y)I", "DA", "CI", "(I)yor", "(y)AcAk"):
            for gövde in ("kitap", "ev", "araba", "göz", "kuş"):
                self.assertEqual(ek_çöz(şablon, gövde), ek_çöz(şablon, gövde, profil=TR))

    def test_doğrula_birebir(self):
        for ad in ("kitap", "akıl", "kâr", "hikâye"):
            self.assertEqual(doğrula(ad, self.k[ad]), doğrula(ad, self.k[ad], TR))


class AzSes(unittest.TestCase):
    def test_hecele(self):
        self.assertEqual(hecele("gələcək", AZ), ["gə", "lə", "cək"])
        self.assertEqual(hecele("azərbaycan", AZ), ["a", "zər", "bay", "can"])
        self.assertEqual(hecele("gələcək"), ["gələcək"])         # Türkçe ə'yi ünlü saymaz → bütün

    def test_geniş_ünlü(self):
        self.assertEqual(ek_çöz("lAr", "ev", profil=AZ), "lər")
        self.assertEqual(ek_çöz("lAr", "qız", profil=AZ), "lar")
        self.assertEqual(ek_çöz("lAr", "ev"), "ler")              # Türkçe değişmez
        self.assertEqual(ek_çöz("dA", "göz", profil=AZ), "də")
        self.assertEqual(ek_çöz("dA", "kitab", profil=AZ), "da")  # AZ'de sertleşme yazılmaz

    def test_dar_ünlü(self):
        for gövde, beklenen in (("gəl", "ir"), ("al", "ır"), ("gör", "ür"), ("qur", "ur")):
            self.assertEqual(ek_çöz("(y)Ir", gövde, profil=AZ), beklenen)
        self.assertEqual(ek_çöz("(y)Ir", "oxu", profil=AZ), "yur")

    def test_q_morfofonemi(self):
        self.assertEqual(ek_çöz("(y)AcAQ", "al", profil=AZ), "acaq")
        self.assertEqual(ek_çöz("(y)AcAQ", "gəl", profil=AZ), "əcək")
        self.assertEqual(ek_çöz("(y)AcAQ", "oxu", profil=AZ), "yacaq")
        self.assertEqual(ek_çöz("(y)IQ", "gəlir", profil=AZ), "ik")
        self.assertEqual(ek_çöz("(y)IQ", "alır", profil=AZ), "ıq")
        self.assertEqual(ek_çöz("(y)IQ", "tələbə", profil=AZ), "yik")

    def test_sıralama(self):
        sözcükler = ["xalq", "hava", "ilk", "ıslaq", "qara", "kənd", "əl", "ev", "zəng"]
        self.assertEqual(sorted(sözcükler, key=AZ.alfabetik_anahtar),
                         ["ev", "əl", "hava", "xalq", "ıslaq", "ilk", "kənd", "qara", "zəng"])

    def test_şema(self):
        self.assertEqual(doğrula("gəl", AZ_KÖKLER["gəl"], AZ), [])
        self.assertTrue(doğrula("gəl", AZ_KÖKLER["gəl"]))         # Türkçe şema ə'yi tanımaz


class AzUçtanUca(unittest.TestCase):
    def az(self, metin, **kw):
        return encode(metin, AZ_KÖKLER, AZ_EKLER, None, dil="az", **kw)

    def test_çözümleme(self):
        self.assertEqual(self.az("evlərdə"), ["ev", "lər", "də"])
        self.assertEqual(self.az("kitabda"), ["ki", "tab", "da"])
        self.assertEqual(self.az("gəldi"), ["gəl", "di"])
        self.assertEqual(self.az("uşağı"), ["u", "şağ", "ı"])                 # q→ğ (kök)
        self.assertEqual(self.az("çörəyi"), ["çö", "rəy", "i"])               # k→y (kök)
        self.assertEqual(self.az("alacaq"), ["al", "acaq"])

    def test_daralma_yalnız_olumsuzda(self):
        # AZ: -(y)Ir önünde yalnız olumsuz -mA'nın ünlüsü düşer; gövde ünlüsü düşmez (TR'den farkı)
        self.assertEqual(self.az("gəlmir"), ["gəl", "m", "ir"])
        self.assertEqual(self.az("işləyir"), ["iş", "lə", "y", "ir"])
        self.assertEqual(self.az("oxuyur"), ["o", "xu", "y", "ur"])
        self.assertEqual(self.az("işləmir"), ["iş", "lə", "m", "ir"])

    def test_casing_ve_round_trip(self):
        metin = "Evlərdə ÇÖRƏYİ gəldi.\nUşağı kitabda"
        tk = self.az(metin)
        self.assertEqual(tk[:4], [BAŞ_BÜYÜK, "ev", "lər", "də"])
        self.assertEqual(decode(tk), metin_kanonik(metin))

    def test_bilinmeyen_bütün_ve_kuyruk(self):
        kuyruk = OnayKuyruğu()
        self.assertEqual(self.az("dəniz", kuyruk=kuyruk), ["dəniz"])
        self.assertEqual([g.kelime for g in kuyruk.bekleyenler()], ["dəniz"])

    def test_önbellek_dil_ayrımı(self):
        k = çalışma_sözlüğü(VERİ / "kokler", VERİ / "zamirler.json", VERİ / "islev_kokleri.json")
        e = ekleri_yükle(VERİ / "ekler.json")
        önbellek: dict = {}
        tr = encode("evde", k, e, None, önbellek=önbellek)
        az = encode("evde", AZ_KÖKLER, AZ_EKLER, None, önbellek=önbellek, dil="az")
        self.assertEqual(tr, ["ev", "de"])
        self.assertEqual(az, ["evde"])           # AZ'de 'evde' yok → bütün (TR sonucu SIZMAZ)
        self.assertEqual(encode("evde", k, e, None, önbellek=önbellek), tr)

    def test_geçersiz_dil(self):
        with self.assertRaises(ValueError):
            encode("x", AZ_KÖKLER, AZ_EKLER, dil="xx")
        with self.assertRaises(ValueError):
            encode("x", AZ_KÖKLER, AZ_EKLER, kip="kod", dil="az")     # kod kipinde doğal dil yok
        with self.assertRaises(ValueError):
            encode("x", AZ_KÖKLER, AZ_EKLER, dil="tr")               # Türkçe: dil verilmez


class VocabDilKapısı(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        taban = Vocab.yükle(VERİ / "vocab.json").id2tok
        cls.yeni = ["gə", "lər", "çö"]
        cls.v = Vocab(taban + cls.yeni, bölümler=EK_BÖLÜMLER + [("az-deneme", cls.yeni)])
        cls.v_tr = Vocab(taban)

    def test_bölüm_adı(self):
        self.assertEqual(dil_bölümü("az-1"), "az")
        self.assertIsNone(dil_bölümü("kod-python"))
        self.assertIsNone(dil_bölümü("harf-genis"))
        self.assertIsNone(dil_bölümü("arap"))

    def test_kapı(self):
        for t in self.yeni:
            tid = self.v.tok2id[t]
            self.assertIsNone(self.v._id(t, "metin"))              # Türkçe metin kipi: kapalı
            self.assertIsNone(self.v._id(t, "kod"))                # kod kipi: kapalı
            self.assertEqual(self.v._id(t, "metin", "az"), tid)    # AZ metin kipi: açık
        self.assertEqual(self.v._id("ev", "metin", "az"), self.v.tok2id["ev"])   # ortak token

    def test_türkçe_kodlama_değişmez(self):
        k = çalışma_sözlüğü(VERİ / "kokler", VERİ / "zamirler.json", VERİ / "islev_kokleri.json")
        e = ekleri_yükle(VERİ / "ekler.json")
        metin = "Gələrlər çörək dedi; evlerde gələcək."
        self.assertEqual(self.v.encode_ids(metin, k, e), self.v_tr.encode_ids(metin, k, e))

    def test_az_yedek_hece(self):
        ids = self.v.encode_ids("gələr", AZ_KÖKLER, AZ_EKLER, dil="az")
        self.assertEqual([self.v.id2tok[i] for i in ids], ["gə", "lər"])   # bilinmeyen → AZ hecesi
        self.assertEqual(self.v.decode_ids(ids), "gələr")


if __name__ == "__main__":
    unittest.main()

"""Azerbaycan Türkçesi (AZ-2 motor, AZ-3 tam sözlük) kapıları.

  1. Altın liste (veri/az/korpus/altin.tsv): en iyi çözümün tokenları birebir + beklenen çözümleme
     çözüm kümesinde. Elle yazıldı (orfoqrafiya/orfoepiya normaları + gerçek yazım).
  2. Sahte bölme taraması (TÜM kökler): her AZ kökü tek başına BÜTÜN okunur; yalnız bilinçli türemiş
     başlıklar (türemiş hep/çıplak: olan = ol+an, artır = art+ır) bileşik okunur — birleşimi köke eşit.
  3. Üret → çözümle (deterministik örneklem): dilbilgisel zincirlerle üretilen biçimin çözümlemesi
     geri kazanılır.
  4. Kaynak ↔ çıktı: veri/az/kokler, araclar/kaynak/az'dan birebir yeniden üretilir.
  5. Hat: dil="az" round-trip kayıpsız, rakam-tire eki (2024-cü), casing (Ə/İ), Türkçe izolasyon.
  6. Korpus (veri/az/korpus/dogrulama.txt, AZ-6: çok alanlı elle yazılmış metin): küçük harfli bilinmeyen YOK —
     yalnız özel ad (Bakı, Gəncə) bilinmeyen kalır; yeni bir çekim boşluğu açılırsa kapı düşer.
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from araclar.uret import dizinler, kaynak_oku, sözlük_üret
from tokenizer import diller
from tokenizer.birlestir import birleştir
from tokenizer.cozumle import çözümle
from tokenizer.dil import AZ
from tokenizer.onay import OnayKuyruğu
from tokenizer.pipeline import BAŞ_BÜYÜK, HEP_BÜYÜK, decode, en_iyi_çözüm, encode, metin_kanonik
from tokenizer.vocab import EK_BÖLÜMLER, Vocab

KÖK = Path(__file__).resolve().parent.parent
ÖRNEKLEM_ADIM = 200   # 65k kök × ~100 zincir tam koşu dakikalar sürer; deterministik eşit aralıklı örneklem
AZ_VERİ = KÖK / "veri" / "az"

# Dilbilgisel zincirler (üret → çözümle geri kazanım): ad ve fiil tabanı için.
İSİM_ZİNCİR = [[], ["çoğul"], ["belirtme"], ["yönelme"], ["bulunma"], ["ayrılma"], ["tamlayan"],
               ["araç"], ["iyelik_1tekil"], ["iyelik_3tekil"], ["iyelik_1çoğul"],
               ["çoğul", "iyelik_1çoğul", "bulunma"], ["iyelik_3tekil", "ayrılma"],
               ["çoğul", "tamlayan"], ["bulunma", "aitlik"], ["koşaç_1tekil_t1"],
               ["ek_fiil_dir"], ["bulunma", "ek_fiil_idi"], ["yapım_lı"], ["yapım_sız"],
               ["yapım_lıq", "iyelik_3tekil"], ["yönelme", "edat_dək"]]
_ZAMAN_KİŞİ = {
    "şimdiki_zaman": ("şahıs_1tekil_t1", "şahıs_2tekil_t1", "şahıs_1çoğul_t1", "şahıs_2çoğul_t1",
                      "şahıs_3çoğul", "ek_fiil_idi"),
    "gelecek_zaman": ("şahıs_1tekil_t1", "şahıs_1çoğul_t1", "şahıs_2tekil_t1", "şahıs_3çoğul"),
    "geniş_zaman": ("şahıs_1tekil_t1", "şahıs_2tekil_t1", "şahıs_1çoğul_t1", "ek_fiil_ken"),
    "duyulan_geçmiş": ("şahıs_1tekil_t1", "şahıs_2tekil_t1", "şahıs_2çoğul_t1", "ek_fiil_idi"),
    "geçmiş_ib": ("şahıs_2tekil_t1", "şahıs_3çoğul", "ek_fiil_dir"),
    "görülen_geçmiş": ("şahıs_1tekil_t2", "şahıs_2tekil_t2", "şahıs_1çoğul_t2", "şahıs_2çoğul_t2",
                       "şahıs_3çoğul"),
    "şart": ("şahıs_1tekil_t2", "şahıs_1çoğul_t2", "ek_fiil_idi"),
    "gereklilik": ("şahıs_1tekil_t1", "ek_fiil_dir"),
}
FİİL_ZİNCİR = ([[]] + [[z] for z in _ZAMAN_KİŞİ]
               + [[z, k] for z, kişiler in _ZAMAN_KİŞİ.items() for k in kişiler]
               + [["olumsuz", z] for z in _ZAMAN_KİŞİ]
               + [["olumsuz", "geniş_zaman", "şahıs_1tekil_t1"], ["mastar"], ["mastar", "yönelme"],
                  ["ortaç_an"], ["ortaç_dik", "iyelik_1tekil"], ["ortaç_acak", "iyelik_3tekil"],
                  ["ulaç_arak"], ["ulaç_anda"], ["ulaç_madan"], ["istek_1çoğul"], ["emir_3tekil"],
                  ["ettirgen", "görülen_geçmiş"], ["edilgen", "görülen_geçmiş"]])


def _altın():
    for satır in (AZ_VERİ / "korpus" / "altin.tsv").read_text(encoding="utf-8").splitlines():
        if satır.strip() and not satır.startswith("#"):
            yüzey, tokenlar, çözümleme = satır.split("\t")
            kök, *ekler = çözümleme.split("+")
            yield yüzey, tokenlar.split(), kök, ekler


class AzMotor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.v = diller.yükle("az")

    def en_iyi(self, w, ad_okuma=False):
        çs = çözümle(w, self.v.kökler, self.v.ekler, self.v.istisnalar, AZ)
        return çs, (en_iyi_çözüm(çs, self.v.kökler, self.v.ekler, AZ, ad_okuma) if çs else None)

    def test_altın_liste(self):
        satır = 0
        for yüzey, tokenlar, kök, ekler in _altın():
            satır += 1
            with self.subTest(yüzey=yüzey):
                çs, b = self.en_iyi(yüzey)
                self.assertIsNotNone(b, "bilinmeyen")
                self.assertEqual(b.tokens, tokenlar)
                self.assertTrue(any(c.kök == kök and c.ekler == ekler for c in çs),
                                f"beklenen çözümleme yok: {kök}+{'+'.join(ekler)}")
        self.assertGreaterEqual(satır, 350)

    def test_kök_bütün_okunur(self):
        # İlke #1: hiçbir kök kendi başına bölünmez; türemiş (hep/çıplak) başlık bilinçli olarak bileşik okunur
        # (sözlükte üretken fiil biçimi olan başlık: olan = ol+an) — o zaman da tokenlar köke birleşir. Özel ad
        # (AZ-7) Başlık biçiminde bütün okunur (Gəncə); küçük harfte sıradan okuma bilinçli (gəncə = gənc+ə).
        bileşik = 0
        for ad, kök in self.v.kökler.items():
            with self.subTest(kök=ad):
                _, b = self.en_iyi(ad, ad_okuma=kök.tür == "özel")
                self.assertEqual("".join(b.tokens), ad)
                if kök.türemiş in ("hep", "çıplak"):
                    bileşik += bool(b.ekler)
                else:
                    self.assertEqual(b.ekler, [], (b.tokens, b.ekler))
        self.assertGreater(bileşik, 300)

    def test_üret_çözümle_geri_kazanım(self):
        eksik, gölge = [], set()
        örneklem = sorted(self.v.kökler, key=AZ.alfabetik_anahtar)[::ÖRNEKLEM_ADIM]
        for ad in örneklem:
            kök = self.v.kökler[ad]
            zincirler = FİİL_ZİNCİR if kök.tür == "fiil" else İSİM_ZİNCİR
            for z in zincirler:
                if getattr(kök, "sadece_koşaç", False) and z and self.v.ekler[z[0]].öbek != "her":
                    continue
                _, yüzey = birleştir(ad, kök, z, self.v.ekler, AZ)
                if yüzey in self.v.istisnalar:   # işlev sözcüğü eşseslisi (ilə/üçün/kimi/təki): istisna
                    gölge.add(yüzey)             # önce gelir, bütün token (kayıpsız, belgeli seçim)
                    continue
                çs, _ = self.en_iyi(yüzey)
                if not any(c.kök == ad and c.ekler == z for c in çs):
                    eksik.append((ad, "+".join(z), yüzey))
        self.assertEqual(eksik, [])
        self.assertGreaterEqual(len(örneklem), 300)
        self.assertTrue(gölge <= set(self.v.istisnalar))

    def test_kaynak_çıktı_eşleşir(self):
        kaynak, çıktı = dizinler("az")
        for txt in kaynak.glob("*.txt"):
            with self.subTest(harf=txt.stem):
                beklenen = sözlük_üret(kaynak_oku(txt), AZ)
                mevcut = json.loads((çıktı / f"{txt.stem}.json").read_text(encoding="utf-8"))
                self.assertEqual(mevcut, beklenen)


class AzHat(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.v = diller.yükle("az")
        cls.vocab = Vocab.yükle(KÖK / "veri" / "vocab.json")
        cls.metin = (AZ_VERİ / "korpus" / "dogrulama.txt").read_text(encoding="utf-8")

    def az(self, metin, **kw):
        return encode(metin, self.v.kökler, self.v.ekler, self.v.istisnalar, dil="az", **kw)

    def test_round_trip_token(self):
        self.assertEqual(decode(self.az(self.metin)), metin_kanonik(self.metin))

    def test_round_trip_id(self):
        ids = self.vocab.encode_ids(self.metin, self.v.kökler, self.v.ekler, self.v.istisnalar, dil="az")
        self.assertEqual(self.vocab.decode_ids(ids), metin_kanonik(self.metin))
        self.assertNotIn(self.vocab.tok2id["<unk>"], ids)

    def test_küçük_harfli_bilinmeyen_yok(self):
        kuyruk = OnayKuyruğu()
        self.az(self.metin, kuyruk=kuyruk)
        küçük = {w for w in re.findall(r"[^\W\d_]+", self.metin) if w == AZ.küçült(w)}
        bilinmeyen = {g.kelime for g in kuyruk.bekleyenler()}
        self.assertEqual(bilinmeyen & küçük, set())
        self.assertLessEqual(len(bilinmeyen), 6, bilinmeyen)        # yalnız özel adlar (Bakı, Gəncə, Yupiter)

    def test_rakam_tire_eki(self):
        # normalar 5.4: rakama ek tireyle; tireden sonrası ek (hecelenir, bilinmeyene gitmez)
        kuyruk = OnayKuyruğu()
        self.assertEqual(self.az("2024-cü", kuyruk=kuyruk), ["2", "0", "2", "4", "-", "cü"])
        self.assertEqual(self.az("5-də"), ["5", "-", "də"])
        self.assertEqual(len(kuyruk), 0)
        # rakamsız tire eki tetiklemez (sözcük-tire-sözcük): ikinci parça normal çözülür
        self.assertEqual(self.az("ev-ev")[-1:], ["ev"])

    def test_casing(self):
        self.assertEqual(self.az("ÜRƏYİMDƏ")[:2], [HEP_BÜYÜK, "ü"])
        self.assertEqual(self.az("Əlimdə")[:2], [BAŞ_BÜYÜK, "əl"])
        for s in ("ÜRƏYİMDƏ", "Əlimdə", "İşçilər", "IŞIQ"):
            self.assertEqual(decode(self.az(s)), s)

    def test_az1_bölümü_dil_kapısı(self):
        # az-1 tokenları YALNIZ dil="az" metin kipinde: AZ metni Türkçe kipte ve kod kipinde onları üretmez,
        # Türkçe metin hiç üretmez; AZ kipte üretir ve ID round-trip kayıpsız kalır.
        az1 = {self.vocab.tok2id[t] for ad, b in EK_BÖLÜMLER if ad.startswith("az-") for t in b}   # az-1 + az-2
        self.assertGreater(len(az1), 1850)
        az2 = {self.vocab.tok2id[t] for ad, b in EK_BÖLÜMLER if ad == "az-2" for t in b}
        self.assertTrue(az2 & set(self.vocab.encode_ids("Məmmədova gedəcəm, Əliyeva görüləsi işi edəcək.",
                                                         self.v.kökler, self.v.ekler, self.v.istisnalar, dil="az")))
        az = self.vocab.encode_ids(self.metin, self.v.kökler, self.v.ekler, self.v.istisnalar, dil="az")
        self.assertTrue(az1 & set(az))
        self.assertEqual(self.vocab.decode_ids(az), metin_kanonik(self.metin))
        tr = diller.yükle()
        for metin in (self.metin, (KÖK / "veri" / "korpus" / "dogrulama.txt").read_text(encoding="utf-8")):
            self.assertFalse(az1 & set(self.vocab.encode_ids(metin, tr.kökler, tr.ekler, tr.istisnalar)))
            self.assertFalse(az1 & set(self.vocab.encode_ids(metin, tr.kökler, tr.ekler, tr.istisnalar,
                                                             kip="kod")))

    def test_türkçe_hat_etkilenmez(self):
        tr = diller.yükle()
        önce = encode("Evlerimizde 2024-cü yıl", tr.kökler, tr.ekler, tr.istisnalar)
        self.assertEqual(önce[:4], [BAŞ_BÜYÜK, "ev", "ler", "i"])
        self.assertIn("cü", önce)                    # Türkçe kipte rakam-tire kuralı yok


class AzDanışıqVeÖzelAd(unittest.TestCase):
    """AZ-7: danışıq (konuşma) yazımı, özel ad listesi, soyad eki, -(y)AsI ortacı."""

    @classmethod
    def setUpClass(cls):
        cls.v = diller.yükle("az")

    def az(self, metin):
        return encode(metin, self.v.kökler, self.v.ekler, self.v.istisnalar, dil="az")

    def test_danışıq_biçimleri(self):
        for metin, beklenen in (("burda", ["bur", "da"]), ("hardansa", ["har", "dan", "sa"]),
                                ("burdayam", ["bur", "da", "y", "am"]), ("biraz", ["bir", "az"]),
                                ("bugün", ["bu", "gün"]), ("bilərsiz", ["bil", "ər", "siz"]),
                                ("edəcəm", ["ed", "əcəm"]), ("bilməyəcəm", ["bil", "mə", "y", "əcəm"]),
                                ("şəkili", ["şə", "kil", "i"]), ("şəkli", ["şə", "kl", "i"])):
            self.assertEqual(self.az(metin), beklenen, metin)

    def test_seyrek_danışıq_ve_ortaç_normatife_yenilir(self):
        # normatif okuma varsa danışıq/seyrek okuma seçilmez: alına bilər (al+ın+a, 'alına' alın+a değil),
        # atası = ata+sı (at + -(y)AsI değil), şəkərsiz = şəkər+siz (2.çoğul -sIz değil)
        self.assertEqual(self.az("alına"), ["al", "ı", "n", "a"])
        self.assertEqual(self.az("atası"), ["a", "ta", "s", "ı"])
        self.assertEqual(self.az("şəkərsiz"), ["şə", "kər", "siz"])
        self.assertEqual(self.az("görüləsi"), ["gör", "ü", "l", "əsi"])

    def test_özel_ad_harf_büyüklüğüne_göre(self):
        # Başlık biçimi → ad okuması; küçük harf → sıradan kök (kayıpsız her iki yönde)
        self.assertEqual(self.az("Gəncə"), [BAŞ_BÜYÜK, "gən", "cə"])
        self.assertEqual(self.az("gəncə"), ["gənc", "ə"])
        self.assertEqual(self.az("Quranın"), [BAŞ_BÜYÜK, "qu", "ran", "ın"])
        self.assertEqual(self.az("Amerikanın"), [BAŞ_BÜYÜK, "a", "me", "ri", "ka", "n", "ın"])
        self.assertEqual(self.az("Azəri"), [BAŞ_BÜYÜK, "a", "zə", "ri"])            # bütün kök korunur
        self.assertEqual(self.az("Əlimdə"), [BAŞ_BÜYÜK, "əl", "i", "m", "də"])      # 1.kişi iyelikli ad okuması yok
        self.assertEqual(self.az("əli"), ["əl", "i"])
        self.assertEqual(self.az("şəkili"), ["şə", "kil", "i"])                       # Şəki+li değil
        self.assertEqual(self.az("türkiyəli"), ["tür", "ki", "yə", "li"])
        for metin in ("Bakıda", "Bakının", "Qarabağımız", "Tanrıya", "Ərdoğanın"):
            kuyruk = OnayKuyruğu()
            t = encode(metin, self.v.kökler, self.v.ekler, self.v.istisnalar, kuyruk, dil="az")
            self.assertEqual(decode(t), metin)
            self.assertEqual(len(kuyruk), 0, metin)

    def test_soyad_eki(self):
        for metin, son in (("Əliyev", ["ə", "li", "yev"]), ("Məmmədova", ["məm", "məd", "ova"]),
                           ("Rəsulzadə", ["rə", "sul", "zadə"]), ("Qurbanovun", ["qur", "ban", "ov", "un"]),
                           ("Əliyevanın", ["ə", "li", "yeva", "n", "ın"])):
            self.assertEqual(self.az(metin)[1:], son, metin)


if __name__ == "__main__":
    unittest.main()

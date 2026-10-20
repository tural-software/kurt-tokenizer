"""Azerbaycan Türkçesi (AZ-2): ek motoru + tohum sözlük kapıları.

  1. Altın liste (veri/az/korpus/altin.tsv): en iyi çözümün tokenları birebir + beklenen çözümleme
     çözüm kümesinde. Elle yazıldı (orfoqrafiya/orfoepiya normaları + gerçek yazım).
  2. Sahte bölme taraması: her AZ kökü tek başına BÜTÜN okunur.
  3. Üret → çözümle: dilbilgisel zincirlerle üretilen her biçimin çözümlemesi geri kazanılır.
  4. Kaynak ↔ çıktı: veri/az/kokler, araclar/kaynak/az'dan birebir yeniden üretilir.
  5. Hat: dil="az" round-trip kayıpsız, rakam-tire eki (2024-cü), casing (Ə/İ), Türkçe izolasyon.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from araclar.uret import dizinler, kaynak_oku, sözlük_üret
from tokenizer import diller
from tokenizer.birlestir import birleştir
from tokenizer.cozumle import çözümle
from tokenizer.dil import AZ
from tokenizer.onay import OnayKuyruğu
from tokenizer.pipeline import BAŞ_BÜYÜK, HEP_BÜYÜK, decode, en_iyi_çözüm, encode, metin_kanonik
from tokenizer.vocab import Vocab

KÖK = Path(__file__).resolve().parent.parent
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

    def en_iyi(self, w):
        çs = çözümle(w, self.v.kökler, self.v.ekler, self.v.istisnalar, AZ)
        return çs, (en_iyi_çözüm(çs, self.v.kökler, self.v.ekler, AZ) if çs else None)

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
        # İlke #1: hiçbir kök kendi başına bölünmez (bütün-kök önceliği AZ politikasında da ilk sırada)
        for ad in self.v.kökler:
            with self.subTest(kök=ad):
                _, b = self.en_iyi(ad)
                self.assertEqual(b.ekler, [], (b.tokens, b.ekler))

    def test_üret_çözümle_geri_kazanım(self):
        eksik, gölge = [], set()
        for ad, kök in self.v.kökler.items():
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
        self.assertEqual(gölge, {"ilə", "üçün", "kimi", "təki", "ay"})   # ay: nida = kök, aynı token

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

    def test_türkçe_hat_etkilenmez(self):
        tr = diller.yükle()
        önce = encode("Evlerimizde 2024-cü yıl", tr.kökler, tr.ekler, tr.istisnalar)
        self.assertEqual(önce[:4], [BAŞ_BÜYÜK, "ev", "ler", "i"])
        self.assertIn("cü", önce)                    # Türkçe kipte rakam-tire kuralı yok


if __name__ == "__main__":
    unittest.main()

"""kokler modülü — dizin yükleme, kapsam, tutarlılık ve dosya-yapısı testleri."""

import json
import tempfile
import unittest
from pathlib import Path

from tokenizer import sesler
from tokenizer.hece import hecele
from tokenizer.kokler import yükle, yükle_dizin, çalışma_sözlüğü, kök_bul, ŞemaHatası
from tokenizer.sema import doğrula
from araclar.uret import sıra_anahtarı

VERİ_DİZİN = Path(__file__).resolve().parent.parent / "veri" / "kokler"
ZAMİR_DOSYASI = Path(__file__).resolve().parent.parent / "veri" / "zamirler.json"
İZİNLİ_DEĞİŞİM = {"t→d", "p→b", "ç→c", "k→ğ", "k→g"}
# tamamlanan fazlar: harf -> asgari kök sayısı (seyrek harfler gerçekte var olan kadar)
TAMAMLANAN = {"a": 50, "b": 50, "c": 40, "ç": 40, "d": 50, "e": 50,
              "f": 35, "g": 50, "h": 50, "ı": 12,
              "i": 45, "j": 12, "k": 50, "l": 25,
              "m": 50, "n": 25, "o": 25, "ö": 25,
              "p": 40, "r": 22, "s": 50, "ş": 35,
              "t": 50, "u": 18, "ü": 18, "v": 20, "y": 50, "z": 20}


class KöklerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sözlük = yükle_dizin(VERİ_DİZİN)

    # --- temel ---
    def test_dizin_yüklenir(self):
        self.assertGreaterEqual(len(self.sözlük), 100)
        self.assertEqual(self.sözlük["git"].son_ünlü, "i")

    def test_kök_bul(self):
        self.assertIsNotNone(kök_bul(self.sözlük, "araba"))
        self.assertIsNotNone(kök_bul(self.sözlük, "ARABA"))  # Türkçe küçültme
        self.assertIsNone(kök_bul(self.sözlük, "yokböylekök"))

    # --- tüm küme tutarlı (dar kümedeki davranış geniş kümede de geçerli) ---
    def test_her_kök_geçerli(self):
        for ad, kök in self.sözlük.items():
            self.assertEqual(doğrula(ad, kök), [], ad)

    def test_tutarlılık(self):
        for ad, kök in self.sözlük.items():
            self.assertEqual(sesler.son_ünlü_bul(ad), kök.son_ünlü, ad)
            self.assertEqual(ad[-1] in sesler.ÜNLÜLER, kök.son_ses == "ünlü", ad)
            self.assertEqual("".join(kök.tokens), ad, ad)
            self.assertEqual(hecele(ad), kök.tokens, ad)   # motor ↔ veri çapraz kontrol

    # --- kapsam ---
    def test_sekiz_ünlü_kapsanır(self):
        # 8 fonemik ünlünün tümü sözlükte temsil edilmeli (düzeltme imli â/î/û opsiyonel)
        görülen = {k.son_ünlü for k in self.sözlük.values()}
        self.assertTrue(sesler.STANDART_ÜNLÜLER <= görülen,
                        f"kapsanmayan: {sesler.STANDART_ÜNLÜLER - görülen}")
        self.assertTrue(görülen <= set(sesler.ÜNLÜLER))   # tümü geçerli ünlü

    def test_hece_şekli_varlığı(self):
        for ad in ("üst", "alt", "renk", "kurt", "genç"):  # VCC / CVCC
            self.assertIn(ad, self.sözlük)

    def test_değişim_anahtarları_geçerli(self):
        for ad, kök in self.sözlük.items():
            if kök.değişim:
                for anahtar in kök.değişim:
                    self.assertIn(anahtar, İZİNLİ_DEĞİŞİM, f"{ad}: {anahtar}")

    def test_fiil_hedefi(self):
        fiil = sum(1 for k in self.sözlük.values() if k.tür == "fiil")
        self.assertGreaterEqual(fiil, 500, f"fiil sayısı {fiil} < 500")

    def test_fiil_yumuşaması_yok(self):
        # Fiil köklerinde ötümsüz son ünsüz yumuşamaz; yalnızca t→d olabilir.
        for ad, kök in self.sözlük.items():
            if kök.tür == "fiil" and kök.değişim:
                self.assertEqual(set(kök.değişim), {"t→d"},
                                 f"{ad}: fiilde beklenmeyen değişim {kök.değişim}")

    def test_faz_hedefleri(self):
        for harf, hedef in TAMAMLANAN.items():
            say = sum(1 for ad in self.sözlük if ad.startswith(harf))
            self.assertGreaterEqual(say, hedef, harf)

    # --- zamir gövdeleri (ayrı dosya, fazlara karışmaz; aynı şema+hece değişmezi) ---
    def test_zamir_gövdeleri_geçerli(self):
        zamirler = yükle(ZAMİR_DOSYASI)
        self.assertEqual(set(zamirler), {"ben", "biz", "bun", "kim", "on", "sen", "siz",
                                         "şun", "nere", "kimse", "herkes", "kendi"})
        for ad, kök in zamirler.items():
            self.assertEqual(doğrula(ad, kök), [], ad)
            self.assertEqual(hecele(ad), kök.tokens, ad)
            self.assertEqual(kök.tür, "zamir", ad)

    def test_zamir_içerik_köküyle_çakışmaz(self):
        # çalışma sözlüğü harf fazları + zamir köklerini çakışmadan birleştirir
        birleşik = çalışma_sözlüğü(VERİ_DİZİN, ZAMİR_DOSYASI)
        self.assertEqual(len(birleşik), len(self.sözlük) + 12)

    # --- dosya yapısı (her harf dosyası, otomatik) ---
    def test_dosya_harf_tutarlı(self):
        for dosya in VERİ_DİZİN.glob("*.json"):
            harf = dosya.stem
            ham = json.loads(dosya.read_text(encoding="utf-8"))
            for ad in ham:
                self.assertTrue(ad.startswith(harf), f"{dosya.name}: {ad}")

    def test_dosya_sıralı(self):
        # önce hece sayısı, sonra Türkçe alfabetik
        for dosya in VERİ_DİZİN.glob("*.json"):
            anahtarlar = [
                k for k, _ in json.loads(
                    dosya.read_text(encoding="utf-8"),
                    object_pairs_hook=lambda p: p,
                )
            ]
            self.assertEqual(
                anahtarlar, sorted(anahtarlar, key=sıra_anahtarı), dosya.name
            )

    # --- bozuk giriş (tek dosya yolu korunur) ---
    def test_bozuk_giriş_reddedilir(self):
        bozuk = {"araba": {"tokens": ["a", "ba"], "tür": "isim",
                           "son_ünlü": "a", "son_ses": "ünlü"}}
        with tempfile.NamedTemporaryFile(
            "w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(bozuk, f, ensure_ascii=False)
            yol = f.name
        try:
            with self.assertRaises(ŞemaHatası) as ctx:
                yükle(yol)
            self.assertTrue(any("araba" in h for h in ctx.exception.hatalar))
        finally:
            Path(yol).unlink()


if __name__ == "__main__":
    unittest.main()

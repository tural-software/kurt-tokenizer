"""Veri büyütme guard'ı — sözlük büyürken her kökün motorla TUTARLI kaldığını doğrular.

Amaç: 10 fazlık veri genişlemesinde (1.9k → ~8k kök) bir kök yanlış etiketlenir ya da
yeni bir bayrak kombinasyonu önek-kapsamını aşarsa ANINDA yakalamak. Mevcut testlerin
üstüne iki güvence ekler:

  1. ÜRETİM bütünlüğü (TÜM kökler): her kökün bir örnek çekimi üretilir; tokenların
     birleşimi yüzey biçmine eşit olmalı (değişim/düşen/ince/pronominal-n hepsi devrede).
  2. ÇÖZÜMLEME geri-kazanımı (TÜM kökler): üretilen çekim geri çözümlendiğinde köke
     ulaşılmalı (kök == ad bir çözümde bulunmalı) — yoksa o kök, metinde çekimli geçtiğinde
     motorca bulunamaz (önek-kapsama açığı / gölgelenme). Round-trip de kayıpsız olmalı.

Bu test köke özel değil, kök-AGNOSTİK bir değişmezdir: yeni veri yalnızca beslemedir.
"""

import unittest
from pathlib import Path

from tokenizer.kokler import çalışma_sözlüğü
from tokenizer.ekler import yükle as ekleri_yükle
from tokenizer.istisna import yükle as istisna_yükle
from tokenizer.birlestir import birleştir
from tokenizer.cozumle import çözümle
from tokenizer.istisna import istisna_bul
from tokenizer.pipeline import encode, decode

ÖRNEKLEM = 600   # pahalı (çözümle O(kök)) testler için deterministik örneklem üst sınırı

KÖK_DİZİN = Path(__file__).resolve().parent.parent / "veri" / "kokler"
EK_DOSYASI = Path(__file__).resolve().parent.parent / "veri" / "ekler.json"
İST_DOSYASI = Path(__file__).resolve().parent.parent / "veri" / "istisnalar.json"
ZAMİR_DOSYASI = Path(__file__).resolve().parent.parent / "veri" / "zamirler.json"
İŞLEV_DOSYASI = Path(__file__).resolve().parent.parent / "veri" / "islev_kokleri.json"


def _örnek_ek(kök) -> str:
    """Kökü en iyi sınayan çekim eki adı: sadece-koşaç (mı/değil) → ek-fiil idi; fiil →
    görülen geçmiş; ad-soyu → belirtme (ünlü-başlı: yumuşama/düşme/ince uyumu tetikler)."""
    if getattr(kök, "sadece_koşaç", False):
        return "ek_fiil_idi"
    türler = {kök.tür, *(kök.ek_tür or [])}
    return "görülen_geçmiş" if "fiil" in türler else "belirtme"


class BüyümeGuardTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.k = çalışma_sözlüğü(KÖK_DİZİN, ZAMİR_DOSYASI, İŞLEV_DOSYASI)
        cls.e = ekleri_yükle(EK_DOSYASI)
        cls.i = istisna_yükle(İST_DOSYASI)

    def test_üretim_bütünlüğü(self):
        # her kök için örnek çekim: tokenların birleşimi yüzeye eşit olmalı
        for ad, kök in self.k.items():
            ek = _örnek_ek(kök)
            tokenlar, yüzey = birleştir(ad, kök, [ek], self.e)
            self.assertEqual("".join(tokenlar), yüzey, f"{ad}+{ek}: token≠yüzey")
            self.assertTrue(all(tokenlar), f"{ad}+{ek}: boş token")

    def _örneklem(self):
        """Deterministik, eşit aralıklı kök örneklemi (büyük veride sabit-zaman kalır)."""
        adlar = sorted(self.k)
        adım = max(1, len(adlar) // ÖRNEKLEM)
        return adlar[::adım]

    def test_çözümleme_geri_kazanımı(self):
        # üretilen çekim geri çözümlenince köke ulaşılmalı + round-trip kayıpsız (örneklem)
        eksik = []
        for ad in self._örneklem():
            kök = self.k[ad]
            ek = _örnek_ek(kök)
            _, yüzey = birleştir(ad, kök, [ek], self.e)
            if istisna_bul(self.i, yüzey):
                continue                      # probe yüzeyi bir istisna sahipleniyor (pek→peki)
            çözümler = çözümle(yüzey, self.k, self.e, self.i)
            if not any(ç.kök == ad for ç in çözümler):
                eksik.append(f"{ad} ({yüzey})")
            if decode(encode(yüzey, self.k, self.e, self.i)) != yüzey:
                eksik.append(f"{ad}: round-trip bozuk ({yüzey})")
        self.assertEqual(eksik, [], f"{len(eksik)} kök geri-kazanılamadı: {eksik[:20]}")

    def test_citation_round_trip(self):
        # her kökün yalın biçimi kayıpsız (küçük-harf bağlamında) — örneklem
        for ad in self._örneklem():
            self.assertEqual(decode(encode(ad, self.k, self.e, self.i)), ad, ad)


if __name__ == "__main__":
    unittest.main()

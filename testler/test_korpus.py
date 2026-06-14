"""Korpus doğrulama — gerçek koşan metinde round-trip kayıpsızlığı ve bilinmeyen tavanı.

Aşama 0 bitiş ölçütünü test paketine bağlar: çok-alanlı doğal Türkçe korpus üzerinde
HER satır round-trip kayıpsız OLMALI (kırmızı çizgi) + bilinmeyen oranı bir tavanın
altında kalmalı (regresyon kapısı). Bilinmeyen ≠ hata (özel ad/bileşik beklenir), ama
oran yükselirse bir çekim boşluğu açılmıştır → kapı düşürür.
"""

import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from araclar.dogrula_korpus import doğrula

KORPUS = Path(__file__).resolve().parent.parent / "veri" / "korpus" / "dogrulama.txt"


class KorpusTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with redirect_stdout(io.StringIO()):           # rapor çıktısını sustur
            cls.sonuç = doğrula(KORPUS)

    def test_round_trip_kayıpsız(self):
        # KIRMIZI ÇİZGİ: tek bir satır bile bozulmamalı
        self.assertEqual(self.sonuç["round_trip_kırık"], [],
                         f"round-trip kırık: {self.sonuç['round_trip_kırık']}")

    def test_bilinmeyen_tavanı(self):
        # Regresyon kapısı: bilinmeyen oranı %4'ün altında (şu an ~%2.6; özel ad+belgeli sınır)
        self.assertLess(self.sonuç["bilinmeyen_oran"], 0.04,
                        f"bilinmeyen oran çok yüksek: %{100*self.sonuç['bilinmeyen_oran']:.1f}")

    def test_küçük_bilinmeyen_yok(self):
        # Korpusta küçük-harfli (sözlük boşluğu) bilinmeyen KALMADI — yalnız özel ad/bileşik
        # (büyük-harfli) bilinmeyen beklenir. Yeni bir çekim boşluğu açılırsa bu kapı düşer.
        self.assertEqual(self.sonuç["küçük_bilinmeyen"], set(),
                         f"küçük-harfli bilinmeyen (boşluk): {self.sonuç['küçük_bilinmeyen']}")


if __name__ == "__main__":
    unittest.main()

"""araclar.uret — üretilen json'ların kaynak .txt'lerle eşleştiğini doğrular.

veri/kokler/<harf>.json daima araclar/kaynak/<harf>.txt'ten yeniden üretilebilir
olmalı (kaynak ↔ çıktı senkron; elle düzenleme kaçağı yakalanır).
"""

import json
import unittest

from araclar.uret import KAYNAK_DİZİN, ÇIKTI_DİZİN, kaynak_oku, sözlük_üret


class UretTest(unittest.TestCase):
    def test_json_kaynakla_eşleşir(self):
        for txt in KAYNAK_DİZİN.glob("*.txt"):
            harf = txt.stem
            json_yol = ÇIKTI_DİZİN / f"{harf}.json"
            self.assertTrue(json_yol.exists(), f"{harf}.json yok")
            beklenen = sözlük_üret(kaynak_oku(txt))
            mevcut = json.loads(json_yol.read_text(encoding="utf-8"))
            self.assertEqual(mevcut, beklenen, harf)


if __name__ == "__main__":
    unittest.main()

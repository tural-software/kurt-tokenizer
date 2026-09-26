"""Determinizm kapısı (ilke #5): çıktı PYTHONHASHSEED'e (set/dict yineleme sırasına) bağlı olamaz.

Her Python süreci kendi rastgele hash tohumunu alır; paralel veri hattında (multiprocessing) aynı
kelime farklı işçilerde kodlanır → çıktı süreçten sürece değişirse korpus tutarsızlaşır. Test aynı
metni farklı tohumlu ALT SÜREÇLERDE kodlar ve birebir aynılık ister.
"""

import os
import subprocess
import sys
import unittest
from pathlib import Path

KÖK = Path(__file__).resolve().parent.parent

# resmin: resim+tamlayan [re,sm,in] ile resmi+iyelik_2tekil [res,mi,n] seçim politikasının
# tüm ölçütlerinde berabere → son kırıcı olmadan çıktı çözüm SIRASINA bağlıydı.
_BETİK = """
import json, sys
from pathlib import Path
from tokenizer.kokler import çalışma_sözlüğü
from tokenizer.ekler import yükle as ekleri_yükle
from tokenizer.istisna import yükle as istisna_yükle
from tokenizer.pipeline import encode
V = Path("veri")
k = çalışma_sözlüğü(V / "kokler", V / "zamirler.json", V / "islev_kokleri.json")
e, i = ekleri_yükle(V / "ekler.json"), istisna_yükle(V / "istisnalar.json")
metin = "resmin Resmin resmi resim " + (V / "korpus" / "dogrulama.txt").read_text(encoding="utf-8")
print(json.dumps(encode(metin, k, e, i), ensure_ascii=False))
"""


class DeterminizmTest(unittest.TestCase):
    def test_hash_tohumundan_bağımsız(self):
        süreçler = {
            tohum: subprocess.Popen([sys.executable, "-c", _BETİK], cwd=KÖK,
                                    env=dict(os.environ, PYTHONHASHSEED=str(tohum), PYTHONUTF8="1"),
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    text=True, encoding="utf-8")
            for tohum in range(6)}                     # eşzamanlı: süre ≈ tek süreç
        çıktılar = {}
        for tohum, s in süreçler.items():
            out, err = s.communicate()
            self.assertEqual(s.returncode, 0, err)
            çıktılar.setdefault(out, []).append(tohum)
        self.assertEqual(len(çıktılar), 1, f"çıktı hash tohumuna bağlı: {list(çıktılar.values())}")


if __name__ == "__main__":
    unittest.main()

"""onay modülü — onay kuyruğu testleri."""

import os
import tempfile
import unittest
from pathlib import Path

from tokenizer.onay import OnayKuyruğu, BEKLİYOR


class OnayKuyruğuTest(unittest.TestCase):
    def test_ekle_ve_tekilleştir(self):
        q = OnayKuyruğu()
        self.assertTrue(q.ekle("filanca", "bir cümlede filanca geçti"))
        self.assertFalse(q.ekle("filanca"))          # aynı kelime → bir daha sorulmaz
        self.assertFalse(q.ekle("FİLANCA"))          # Türkçe-duyarlı tekilleştirme
        self.assertEqual(len(q), 1)

    def test_bekleyenler(self):
        q = OnayKuyruğu()
        q.ekle("zzz"); q.ekle("yyy")
        bek = q.bekleyenler()
        self.assertEqual(len(bek), 2)
        self.assertTrue(all(g.durum == BEKLİYOR for g in bek))

    def test_yükle_kaydet_round_trip(self):
        q = OnayKuyruğu()
        q.ekle("abuk", "bağlam-1")
        q.ekle("sabuk", "bağlam-2")
        p = tempfile.mktemp(suffix=".json")
        try:
            q.kaydet(p)
            q2 = OnayKuyruğu.yükle(p)
            self.assertEqual(len(q2), 2)
            self.assertEqual(q2.girdiler[0].kelime, "abuk")
            self.assertEqual(q2.girdiler[0].bağlam, "bağlam-1")
            self.assertFalse(q2.ekle("abuk"))        # yüklemeden sonra da tekil
        finally:
            os.unlink(p)

    def test_yükle_yok_boş(self):
        q = OnayKuyruğu.yükle(Path(tempfile.gettempdir()) / "yok_böyle_kuyruk_12345.json")
        self.assertEqual(len(q), 0)


if __name__ == "__main__":
    unittest.main()

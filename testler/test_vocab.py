"""vocab modülü — token↔ID, ID-düzeyi round-trip, kapsama ve fallback testleri."""

import random
import unittest
from pathlib import Path

from tokenizer.kokler import çalışma_sözlüğü, yükle_dizin
from tokenizer.ekler import yükle as ekleri_yükle
from tokenizer.istisna import yükle as istisna_yükle
from tokenizer.birlestir import birleştir
from tokenizer.vocab import vocab_kur, Vocab, ÖZEL_TOKENLAR

KÖK_DİZİN = Path(__file__).resolve().parent.parent / "veri" / "kokler"
EK = Path(__file__).resolve().parent.parent / "veri" / "ekler.json"
İST = Path(__file__).resolve().parent.parent / "veri" / "istisnalar.json"
ZAMİR = Path(__file__).resolve().parent.parent / "veri" / "zamirler.json"
İŞLEV = Path(__file__).resolve().parent.parent / "veri" / "islev_kokleri.json"
VOCAB = Path(__file__).resolve().parent.parent / "veri" / "vocab.json"


class VocabTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.k = çalışma_sözlüğü(KÖK_DİZİN, ZAMİR, İŞLEV)
        cls.e = ekleri_yükle(EK)
        cls.i = istisna_yükle(İST)
        cls.v = Vocab.yükle(VOCAB)

    def test_özel_tokenlar_sabit_id(self):
        # <pad>=0, <unk>=1, <s>=2, </s>=3 … model bağımlılığı için KALICI önek
        self.assertEqual(self.v.id2tok[:len(ÖZEL_TOKENLAR)], ÖZEL_TOKENLAR)
        self.assertEqual(self.v.tok2id["<pad>"], 0)
        self.assertEqual(self.v.tok2id["<unk>"], 1)

    def test_benzersiz_ve_makul_boyut(self):
        self.assertEqual(len(self.v.id2tok), len(set(self.v.id2tok)))
        self.assertTrue(2000 <= len(self.v) <= 30000, len(self.v))

    def test_id_round_trip(self):
        for metin in ["Bugün İstanbul'da öğrencilerin hazırladığı projeler sergilendi.",
                      "Çocuklar bahçede oynayıp eğlendiler; 2024 yılında %50 arttı.",
                      "Bilim insanları geliştirilen yöntemle verileri analiz ettiler.",
                      "TBMM'de görüşülen kanun teklifi oy çokluğuyla kabul edildi."]:
            ids = self.v.encode_ids(metin, self.k, self.e, self.i)
            self.assertTrue(all(isinstance(x, int) for x in ids))
            self.assertEqual(self.v.decode_ids(ids), metin, metin)

    def test_çözülen_token_kapsama(self):
        # RESOLVED kelimelerin ürettiği her morfem token vocab'da olmalı (fallback YOK)
        s = yükle_dizin(KÖK_DİZİN)
        random.seed(7)
        çek = [["belirtme"], ["iyelik_3tekil"], ["iyelik_3tekil", "bulunma"]]
        fçek = [["şimdiki_zaman"], ["görülen_geçmiş"], ["edilgen", "görülen_geçmiş"]]
        kaçan = set()
        for ad in random.sample(list(s), 3000):
            kök = s[ad]
            for z in (fçek if kök.tür == "fiil" else çek):
                try:
                    tk, _ = birleştir(ad, kök, z, self.e)
                    kaçan |= {t for t in tk if t not in self.v.tok2id}
                except Exception:
                    pass
        self.assertEqual(kaçan, set(), f"vocab'da olmayan morfem tokenlar: {sorted(kaçan)[:20]}")

    def test_bilinmeyen_fallback(self):
        # bilinmeyen kelime hece→harf fallback ile kayıpsız temsil edilir
        ids = self.v.encode_ids("zürümpülat geldi", self.k, self.e, self.i)
        self.assertEqual(self.v.decode_ids(ids), "zürümpülat geldi")

    def test_yeniden_üretilebilir(self):
        # vocab.json deterministik: kaynak'tan yeniden üretim birebir aynı
        yeniden = vocab_kur(self.k, self.e, self.i)
        self.assertEqual(yeniden, self.v.id2tok)


if __name__ == "__main__":
    unittest.main()

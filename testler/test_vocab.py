"""vocab modülü — token↔ID, ID-düzeyi round-trip, kapsama ve fallback testleri."""

import random
import unittest
from pathlib import Path

from tokenizer.kokler import çalışma_sözlüğü, yükle_dizin
from tokenizer.ekler import yükle as ekleri_yükle
from tokenizer.istisna import yükle as istisna_yükle
from tokenizer.birlestir import birleştir
from tokenizer.vocab import (vocab_kur, Vocab, ÖZEL_TOKENLAR, EK_BÖLÜMLER, DONMUŞ_BÖLÜMLER,
                             bölüm_özeti, bölümleri_ekle)

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

    def test_qwx_kayıpsız(self):
        # Faz 1: q/w/x atomik (önceden <unk> → metinden siliniyordu)
        unk = self.v.tok2id["<unk>"]
        for metin in ["Windows'ta x ve y", "max_index(xs) QWERTY", "XIV. yüzyılda Quebec"]:
            ids = self.v.encode_ids(metin, self.k, self.e, self.i)
            self.assertNotIn(unk, ids, metin)
            self.assertEqual(self.v.decode_ids(ids), metin, metin)

    def test_bayt_tüm_unicode(self):
        # Faz 2: boşluk dışındaki HER Unicode karakteri kayıpsız ve <unk>'sız — BMP'nin tamamı +
        # ek düzlemlerden her 11. kod noktası. (Boşluk korunumu kod kipinin işi: encode split.)
        unk = self.v.tok2id["<unk>"]
        kaçan = []
        for n in [*range(0x10000), *range(0x10000, 0x110000, 11)]:
            c = chr(n)
            if 0xD800 <= n <= 0xDFFF or c.isspace():
                continue
            ids = self.v.encode_ids(c, self.k, self.e, self.i)
            if unk in ids or self.v.decode_ids(ids) != c:
                kaçan.append(f"U+{n:04X}")
        self.assertEqual(kaçan, [], f"{len(kaçan)} kayıplı karakter, örn. {kaçan[:10]}")

    def test_bayt_vekil_ve_geçersiz_dizi(self):
        # tek başına vekil (surrogate) çökmez ve geri döner; geçersiz bayt dizisi (ör. model
        # çıktısı) çökmez → U+FFFD
        for metin in ["\ud800", "a\udfffb"]:
            ids = self.v.encode_ids(metin, self.k, self.e, self.i)
            self.assertEqual(self.v.decode_ids(ids), metin)
        t = self.v.tok2id
        self.assertEqual(self.v.decode_ids([t["<0xFF>"]]), "�")
        self.assertEqual(self.v.decode_ids([t["a"], t["<0xE2>"]]), "a�")   # yarım karakter

    def test_bayt_karışık_metin(self):
        # harf-sınıfı içi/dışı, çok baytlı, birleşen işaret, casing sınırı karışık rastgele metin
        unk = self.v.tok2id["<unk>"]
        havuz = "aAğĞıIiİxXāÑéΩω𝑖€₺±−≤☃😀中عĢ▁́'.,1"
        rnd = random.Random(11)
        for _ in range(500):
            metin = " ".join("".join(rnd.choice(havuz) for _ in range(rnd.randint(1, 7)))
                             for _ in range(rnd.randint(1, 4)))
            ids = self.v.encode_ids(metin, self.k, self.e, self.i)
            self.assertNotIn(unk, ids, metin)
            self.assertEqual(self.v.decode_ids(ids), metin, metin)

    def test_faz3_tek_token(self):
        # Faz 3: onaylı 350 karakterin her biri TEK token (bayt değil), kayıpsız
        from tokenizer.vocab import EK_BÖLÜMLER
        faz3 = [c for ad, t in EK_BÖLÜMLER if ad in ("harf-genis", "sembol", "arap", "kiril")
                for c in t]
        self.assertEqual(len(faz3), 350)
        for c in faz3:
            ids = self.v.encode_ids(c, self.k, self.e, self.i)
            self.assertEqual([self.v.id2tok[x] for x in ids], [c], f"U+{ord(c):04X}")
            self.assertEqual(self.v.decode_ids(ids), c)

    def test_faz3_metin_baytsız(self):
        # gerçek karışık metin: Osmanlıca, Türk dilleri, bilim, Arap/Kiril yazısı → bayt yok
        bayt = {self.v.tok2id[t] for t in self.v.id2tok if t.startswith("<0x")}
        for metin in ["Kitâbü'l-ʿİber ve ṣaġīr", "Azərbaycan dili, Türkmençe ýaş",
                      "H₂SO₄ ve Ca²⁺ için ΔH ≈ −40 kJ ± 2", "fiyat 12 € / 450 ₺ ✓",
                      "دولت عليه عثمانیه", "Қазақстан және Москва", "├── kök │ └── ek"]:
            ids = self.v.encode_ids(metin, self.k, self.e, self.i)
            self.assertFalse(bayt & set(ids), metin)
            self.assertEqual(self.v.decode_ids(ids), metin, metin)

    def test_faz3b_bilim_ve_büyük_harf(self):
        # bilim sembolleri tek token; karışık yazımlı kelimede büyük harf bayta düşmez (kΩ)
        from tokenizer.vocab import EK_BÖLÜMLER
        b = dict(EK_BÖLÜMLER)
        self.assertEqual((len(b["sembol-bilim"]), len(b["harf-buyuk"])), (50, 118))
        for c in b["sembol-bilim"]:
            ids = self.v.encode_ids(c, self.k, self.e, self.i)
            self.assertEqual([self.v.id2tok[x] for x in ids], [c], f"U+{ord(c):04X}")
        bayt = {self.v.tok2id[t] for t in self.v.id2tok if t.startswith("<0x")}
        for c in b["harf-buyuk"]:                       # karışık biçim: küçük + BÜYÜK
            metin = "k" + c
            ids = self.v.encode_ids(metin, self.k, self.e, self.i)
            self.assertFalse(bayt & set(ids), metin)
            self.assertEqual(self.v.decode_ids(ids), metin, metin)
        for metin in ["10 kΩ direnç", "∀x ∈ ℝ, ⌊x⌋ ≤ x ∴ ispat ∎", "N₂ + 3H₂ ⇌ 2NH₃",
                      "E = ℏω ve 𝔼[X]", "BAKI ŞƏHƏRİ ve ŞəHəR", "Москва ҚАЗАҚ"]:
            ids = self.v.encode_ids(metin, self.k, self.e, self.i)
            self.assertFalse(bayt & set(ids), metin)
            self.assertEqual(self.v.decode_ids(ids), metin, metin)

    def test_harfiyen_boşluk_işareti(self):
        # metindeki HARFİYEN '▁' (U+2581) boşluk tokenıyla karışmaz → bayt kaçışı, geri '▁'
        for metin in ["▁", "a▁b", "SentencePiece ▁ işareti"]:
            ids = self.v.encode_ids(metin, self.k, self.e, self.i)
            self.assertEqual(self.v.decode_ids(ids), metin, metin)
        self.assertNotIn(self.v.tok2id["▁"], self.v.encode_ids("▁", self.k, self.e, self.i))

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

    def test_önek_değişmezliği(self):
        # SONA-EKLEME kapısı: her donmuş bölüm yerinde ve birebir (hiçbir ID kaymaz), ve
        # vocab'da dondurulmamış token kalmaz (faz bitince DONMUŞ_BÖLÜMLER'e işlenir).
        baş = 0
        for ad, boy, özet in DONMUŞ_BÖLÜMLER:
            self.assertEqual(bölüm_özeti(self.v.id2tok[baş:baş + boy]), özet,
                             f"'{ad}' bölümü değişti ya da kaydı (ID {baş}..{baş + boy - 1})")
            baş += boy
        self.assertEqual(baş, len(self.v), "dondurulmamış bölüm var")

    def test_bölüm_kaydı_tutarlı(self):
        # DONMUŞ_BÖLÜMLER = v1 + EK_BÖLÜMLER, aynı sıra ve aynı boy
        self.assertEqual([ad for ad, _, _ in DONMUŞ_BÖLÜMLER],
                         ["v1"] + [ad for ad, _ in EK_BÖLÜMLER])
        for (ad, boy, _), (_, bölüm) in zip(DONMUŞ_BÖLÜMLER[1:], EK_BÖLÜMLER):
            self.assertEqual(boy, len(bölüm), ad)

    def test_bölüm_tekrar_reddi(self):
        # var olan token ya da bölüm-içi tekrar sessizce yutulmaz → ValueError
        self.assertEqual(bölümleri_ekle(["a", "b"], [("y", ["c"])]), ["a", "b", "c"])
        with self.assertRaises(ValueError):
            bölümleri_ekle(["a", "b"], [("y", ["b"])])
        with self.assertRaises(ValueError):
            bölümleri_ekle(["a"], [("y", ["c", "c"])])


if __name__ == "__main__":
    unittest.main()

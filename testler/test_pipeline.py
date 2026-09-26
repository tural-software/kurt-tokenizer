"""pipeline modülü — encode/decode ve ilk gerçek metin testleri."""

import unittest
from pathlib import Path

from tokenizer.kokler import çalışma_sözlüğü
from tokenizer.ekler import yükle as ekleri_yükle
from tokenizer.istisna import yükle as istisna_yükle
from tokenizer.onay import OnayKuyruğu
from tokenizer.pipeline import encode, decode, BOŞLUK

KÖK_DİZİN = Path(__file__).resolve().parent.parent / "veri" / "kokler"
EK_DOSYASI = Path(__file__).resolve().parent.parent / "veri" / "ekler.json"
İST_DOSYASI = Path(__file__).resolve().parent.parent / "veri" / "istisnalar.json"
ZAMİR_DOSYASI = Path(__file__).resolve().parent.parent / "veri" / "zamirler.json"
İŞLEV_DOSYASI = Path(__file__).resolve().parent.parent / "veri" / "islev_kokleri.json"


class PipelineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.k = çalışma_sözlüğü(KÖK_DİZİN, ZAMİR_DOSYASI, İŞLEV_DOSYASI)
        cls.e = ekleri_yükle(EK_DOSYASI)
        cls.i = istisna_yükle(İST_DOSYASI)

    def enc(self, metin, kuyruk=None):
        return encode(metin, self.k, self.e, self.i, kuyruk)

    def test_seçim_deterministik(self):
        self.assertEqual(self.enc("evler"), ["ev", "ler"])
        self.assertEqual(self.enc("kitabı"), ["ki", "tab", "ı"])

    def test_boşluk_tokenı(self):
        t = self.enc("ev araba")
        self.assertIn(BOŞLUK, t)
        self.assertEqual(t, ["ev", BOŞLUK, "a", "ra", "ba"])

    def test_noktalama(self):
        self.assertEqual(self.enc("ev, araba"), ["ev", ",", BOŞLUK, "a", "ra", "ba"])

    def test_bilinmeyen_kuyruğa(self):
        q = OnayKuyruğu()
        t = self.enc("şçkptr geldi", q)          # ünlüsüz → çözülemez (kalıcı bilinmeyen)
        self.assertIn("şçkptr", t)               # BÜTÜN tutuldu
        self.assertEqual(len(q.bekleyenler()), 1)
        self.assertFalse(q.ekle("şçkptr"))       # kuyruğa girmiş

    def test_decode_özel_atla(self):
        self.assertEqual(decode(["<s>", "ev", "ler", "</s>"]), "evler")

    def test_round_trip(self):
        for metin in ["evler arabaya", "ev, araba geldi", "kitabı gözümüz"]:
            self.assertEqual(decode(self.enc(metin)), metin, metin)

    def test_harf_büyüklüğü_round_trip(self):
        # casing işaretçisi ile büyük harf KAYIPSIZ (Türkçe İ↔i, I↔ı duyarlı)
        for metin in ["Bugün hava güzeldi", "Ben İstanbul'a gittim", "TÜRK kahvesi",
                      "Çocuklar bahçede", "iPhone aldı", "ışık ve IŞIK"]:
            self.assertEqual(decode(self.enc(metin)), metin, metin)
        from tokenizer.pipeline import BAŞ_BÜYÜK, HEP_BÜYÜK
        self.assertEqual(self.enc("Bugün")[0], BAŞ_BÜYÜK)
        self.assertEqual(self.enc("TÜRK")[0], HEP_BÜYÜK)
        self.assertEqual(self.enc("iPhone"), ["iPhone"])    # karışık → bütün-token

    def test_qwx_harf(self):
        # q/w/x harf sayılır (kelimeyi bölmez); kök/ek/istisnada yok → bilinmeyen-BÜTÜN kalır
        from tokenizer.pipeline import BAŞ_BÜYÜK, HEP_BÜYÜK
        self.assertEqual(self.enc("taxi"), ["taxi"])
        self.assertEqual(self.enc("index"), ["index"])       # eskiden inde + x (x siliniyordu)
        self.assertEqual(self.enc("max_index"), ["max", "_", "index"])
        self.assertEqual(self.enc("Windows"), [BAŞ_BÜYÜK, "windows"])
        self.assertEqual(self.enc("XIV"), [HEP_BÜYÜK, "xıv"])
        for metin in ["Windows ve WhatsApp'ta", "x=5 ise QWERTY", "XIV. yüzyıl",
                      "max_index(xs)", "Quebec'e gitti"]:
            self.assertEqual(decode(self.enc(metin)), metin, metin)

    def test_casing_koşu_sınırı(self):
        # koşu sınırı encode'un harf sınıfıyla aynı (_harf_mi): karışık biçim bütün korunur,
        # harf-dışı karakter (±, kesme) koşuyu bitirir → "AĞé" "AĞÉ" olmaz
        for metin in ["AĞé", "TÜRKΩ", "Ağaçé", "é ÇOK", "AĞ±ÇOK", "ÉCOLE", "Αθήνα", "МОСКВА"]:
            self.assertEqual(decode(self.enc(metin)), metin, metin)

    def test_yabancı_harfli_kelime_bütün(self):
        # Faz 3: tüm Unicode harfleri harf sınıfı → yabancı kelime parçalanıp Türkçe çözülmez
        # (eskiden Ōsaka → Ō + 'saka' [sakacı], güneĢ → 'güne' + Ģ)
        from tokenizer.pipeline import BAŞ_BÜYÜK
        self.assertEqual(self.enc("Ōsaka"), [BAŞ_BÜYÜK, "ōsaka"])
        self.assertEqual(self.enc("español"), ["español"])
        self.assertEqual(self.enc("güneĢ"), ["güneĢ"])            # karışık biçim → bütün
        self.assertEqual(self.enc("Москва"), [BAŞ_BÜYÜK, "москва"])
        for metin in ["Ōsaka'da", "ṣadı̇̄ḳ", "x̅ = 5", "Muṣliḥ ve Αθήνα", "Москва'ya gitti"]:
            self.assertEqual(decode(self.enc(metin)), metin, metin)

    def test_değiştirici_kesme(self):
        # ʼ ʹ kesme olarak kullanılır (harf sınıfı dışı): sonrası EK → hecelenir, kuyruğa girmez
        q = OnayKuyruğu()
        self.assertEqual(self.enc("Cumhuriyetʼi", q)[-2:], ["ʼ", "i"])
        self.assertEqual(self.enc("Kemalʹin", q)[-2:], ["ʹ", "in"])
        self.assertNotIn("in", [x.kelime for x in q.bekleyenler()])
        for metin in ["Cumhuriyetʼi", "Kemalʹin", "Batıʼda kaldı"]:
            self.assertEqual(decode(self.enc(metin)), metin, metin)

    def test_bayt_tokenı(self):
        from tokenizer.pipeline import bayt_tokenları
        self.assertEqual(bayt_tokenları("ā"), ["<0xC4>", "<0x81>"])
        self.assertEqual(decode(["ev", *bayt_tokenları("ā"), "ler"]), "evāler")
        self.assertEqual(decode(self.enc("a▁b")), "a▁b")          # harfiyen ▁ ≠ boşluk tokenı

    def test_zamir_round_trip(self):
        # zamir hibrit: gövde+ek çekimleri ve suppletif istisna uçtan uca kayıpsız
        for metin in ["ben seni gördüm", "bana bunu verdi", "onlar bizden geldi"]:
            self.assertEqual(decode(self.enc(metin)), metin, metin)
        # token paylaşımı: ben gövdesi + belirtme/ayrılma ekleri
        self.assertEqual(self.enc("beni"), ["ben", "i"])
        self.assertEqual(self.enc("bana"), ["ban", "a"])      # suppletif istisna

    def test_kesme_eki(self):
        # özel ad/akronim/sayı + kesme + EK: ek tanınır (kuyruğa atılmaz), round-trip kayıpsız
        for metin in ["İstanbul'da", "Ahmet'in", "2024'te", "TBMM'de", "İzmir'den"]:
            self.assertEqual(decode(self.enc(metin)), metin, metin)
        # kesme sonrası 'da' hecelenir, BİLİNMEYEN değil
        q = OnayKuyruğu()
        self.enc("Ankara'da", q)
        self.assertNotIn("da", [x.kelime for x in q.bekleyenler()])

    def test_ilk_gerçek_metin(self):
        # Aşama 0 bitiş sınaması: gerçek bir Türkçe cümle uçtan uca
        metin = "çocuklar bahçede oynuyor"
        tokenlar = self.enc(metin)
        self.assertEqual(decode(tokenlar), metin)
        self.assertTrue(all(isinstance(t, str) and t for t in tokenlar))


if __name__ == "__main__":
    unittest.main()

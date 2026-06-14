"""birlestir modülü — üretim motoru (isim zincirleri) testleri."""

import unittest
from pathlib import Path

from tokenizer.kokler import yükle_dizin
from tokenizer.ekler import yükle as ekleri_yükle
from tokenizer.birlestir import birleştir

KÖK_DİZİN = Path(__file__).resolve().parent.parent / "veri" / "kokler"
EK_DOSYASI = Path(__file__).resolve().parent.parent / "veri" / "ekler.json"


class BirleştirTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kökler = yükle_dizin(KÖK_DİZİN)
        cls.ekler = ekleri_yükle(EK_DOSYASI)

    def b(self, ad, *ek_adları):
        return birleştir(ad, self.kökler[ad], list(ek_adları), self.ekler)

    def test_yüzey_biçimleri(self):
        durumlar = [
            ("ev", ("çoğul",), "evler"),
            ("araba", ("yönelme",), "arabaya"),
            ("araba", ("belirtme",), "arabayı"),
            ("araba", ("tamlayan",), "arabanın"),
            ("araba", ("iyelik_3tekil",), "arabası"),
            ("kitap", ("belirtme",), "kitabı"),        # p→b
            ("kitap", ("bulunma",), "kitapta"),        # sertleşme, yumuşama yok
            ("kitap", ("çoğul",), "kitaplar"),         # l ünsüz, yumuşama yok
            ("renk", ("belirtme",), "rengi"),          # k→g
            ("ağaç", ("belirtme",), "ağacı"),          # ç→c
            ("ev", ("iyelik_1tekil",), "evim"),
            ("araba", ("iyelik_1tekil",), "arabam"),
            ("göz", ("iyelik_1çoğul",), "gözümüz"),
            ("ev", ("çoğul", "iyelik_1tekil"), "evlerim"),
            ("kitap", ("çoğul", "belirtme"), "kitapları"),
        ]
        for ad, ekler, beklenen in durumlar:
            _, yüzey = self.b(ad, *ekler)
            self.assertEqual(yüzey, beklenen, f"{ad}+{ekler}")

    def test_araç_durumu(self):
        # instrumental -(y)lA: ünsüz-sonu → -le/-la, ünlü-sonu → -y+la (tampon ayrı token)
        self.assertEqual(self.b("ev", "araç"), (["ev", "le"], "evle"))
        self.assertEqual(self.b("araba", "araç"), (["a", "ra", "ba", "y", "la"], "arabayla"))
        self.assertEqual(self.b("göz", "araç")[1], "gözle")
        # iyelik + araç zinciri (zamir araç biçimlerinin temeli): ev+im+le
        self.assertEqual(self.b("ev", "iyelik_1tekil", "araç"), (["ev", "i", "m", "le"], "evimle"))

    def test_token_dizileri(self):
        # Parantezli tampon (ünlü/ünsüz) her zaman ayrı token (CLAUDE.md modeli)
        self.assertEqual(self.b("araba", "yönelme")[0], ["a", "ra", "ba", "y", "a"])
        self.assertEqual(self.b("kitap", "belirtme")[0], ["ki", "tab", "ı"])
        self.assertEqual(self.b("araba", "tamlayan")[0], ["a", "ra", "ba", "n", "ın"])
        self.assertEqual(self.b("ev", "iyelik_1tekil")[0], ["ev", "i", "m"])
        self.assertEqual(self.b("ev", "çoğul", "iyelik_1tekil")[0], ["ev", "ler", "i", "m"])
        self.assertEqual(self.b("renk", "belirtme")[0], ["reng", "i"])

    def test_istisnai_uyum(self):
        # ince kök: art ünlü ama ince ek (kalp→kalbi, rol→rolü); yuvarlaklık korunur
        self.assertEqual(self.b("kalp", "iyelik_3tekil"), (["kalb", "i"], "kalbi"))  # +p→b
        self.assertEqual(self.b("rol", "iyelik_3tekil"), (["rol", "ü"], "rolü"))
        self.assertEqual(self.b("saat", "yönelme")[1], "saate")
        self.assertEqual(self.b("kalp", "çoğul")[1], "kalpler")   # ünsüz ek de ince

    def test_ünlü_düşmesi(self):
        # düşen-ünlü kök: ünlü-başlı ek → son ünlü düşer; ünsüz-başlıda düşmez
        self.assertEqual(self.b("akıl", "iyelik_1tekil"), (["a", "kl", "ı", "m"], "aklım"))
        self.assertEqual(self.b("ağız", "belirtme"), (["a", "ğz", "ı"], "ağzı"))
        self.assertEqual(self.b("şehir", "yönelme")[1], "şehre")
        self.assertEqual(self.b("akıl", "çoğul"), (["a", "kıl", "lar"], "akıllar"))  # düşmez
        # düşen + yumuşama birlikte: kayıp → kayb → kaybı
        self.assertEqual(self.b("kayıp", "belirtme"), (["ka", "yb", "ı"], "kaybı"))

    def test_pronominal_n(self):
        # 3.tekil/çoğul iyelik + hâl → araya -n- (ayrı token)
        self.assertEqual(self.b("araba", "iyelik_3tekil", "bulunma"),
                         (["a", "ra", "ba", "s", "ı", "n", "da"], "arabasında"))
        self.assertEqual(self.b("ev", "iyelik_3çoğul", "yönelme")[1], "evlerine")
        self.assertEqual(self.b("kitap", "iyelik_3tekil", "ayrılma")[1], "kitabından")

    def test_token_birleşimi_yüzeye_eşit(self):
        # değişmez: tokenların birleşimi yüzey biçmini verir
        for ad, ekler in [("kitap", ("belirtme",)), ("araba", ("iyelik_3tekil",)),
                          ("ağaç", ("çoğul", "belirtme")), ("göz", ("iyelik_1çoğul",)),
                          ("araba", ("iyelik_3tekil", "bulunma"))]:
            tokenlar, yüzey = self.b(ad, *ekler)
            self.assertEqual("".join(tokenlar), yüzey, f"{ad}+{ekler}")


class FiilZincirTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kökler = yükle_dizin(KÖK_DİZİN)
        cls.ekler = ekleri_yükle(EK_DOSYASI)

    def b(self, ad, *ek_adları):
        return birleştir(ad, self.kökler[ad], list(ek_adları), self.ekler)

    def test_zaman_zincirleri(self):
        durumlar = [
            ("gel", ("şimdiki_zaman",), "geliyor"),
            ("oku", ("şimdiki_zaman",), "okuyor"),
            ("git", ("şimdiki_zaman",), "gidiyor"),        # t→d (ünlü öncesi)
            ("yaz", ("görülen_geçmiş",), "yazdı"),
            ("git", ("görülen_geçmiş",), "gitti"),          # ünsüz öncesi: yumuşama yok
            ("gör", ("gereklilik",), "görmeli"),
            ("oku", ("gelecek_zaman", "şahıs_2tekil_t1"), "okuyacaksın"),
            ("gel", ("görülen_geçmiş", "şahıs_1tekil_t2"), "geldim"),
            ("gel", ("şimdiki_zaman", "şahıs_1tekil_t1"), "geliyorum"),
            # -Iyor ünlü daralması (a/e-sonu çok-heceli köklerde)
            ("oyna", ("şimdiki_zaman",), "oynuyor"),
            ("başla", ("şimdiki_zaman",), "başlıyor"),
            ("anla", ("şimdiki_zaman",), "anlıyor"),
            ("oku", ("şimdiki_zaman",), "okuyor"),     # dar ünlü → daralmaz
            ("gel", ("olumsuz", "şimdiki_zaman"), "gelmiyor"),  # -mA daralır
            # geniş zaman -Ar/-Ir (kök-koşullu)
            ("gel", ("geniş_zaman",), "gelir"),     # istisna küme → -Ir
            ("yaz", ("geniş_zaman",), "yazar"),     # tek-heceli → -Ar
            ("oku", ("geniş_zaman",), "okur"),      # ünlü-sonu → -r
            ("getir", ("geniş_zaman",), "getirir"), # çok-heceli ünsüz → -Ir
            ("git", ("geniş_zaman",), "gider"),     # -Ar + t→d yumuşaması
            ("gör", ("geniş_zaman",), "görür"),     # istisna küme → -Ir
            ("gel", ("olumsuz", "geniş_zaman"), "gelmez"),  # olumsuz geniş → -z
            ("yaz", ("olumsuz", "geniş_zaman"), "yazmaz"),
            ("oku", ("olumsuz", "geniş_zaman"), "okumaz"),
        ]
        for ad, ekler, beklenen in durumlar:
            _, yüzey = self.b(ad, *ekler)
            self.assertEqual(yüzey, beklenen, f"{ad}+{ekler}")

    def test_gelecek_yumuşaması(self):
        # ek-sonu yumuşaması: -AcAk + ünlü-başlı kişi eki → k→ğ (geleceğim, gideceğiz)
        durumlar = [
            ("gel", ("gelecek_zaman", "şahıs_1tekil_t1"), "geleceğim"),
            ("git", ("gelecek_zaman", "şahıs_1çoğul_t1"), "gideceğiz"),
            ("yap", ("gelecek_zaman", "şahıs_1çoğul_t1"), "yapacağız"),
            ("gel", ("gelecek_zaman", "şahıs_2tekil_t1"), "geleceksin"),  # ünsüz: yumuşamaz
            ("gel", ("gelecek_zaman", "ek_fiil_idi"), "gelecekti"),       # ünsüz: yumuşamaz
        ]
        for ad, ekler, beklenen in durumlar:
            _, yüzey = self.b(ad, *ekler)
            self.assertEqual(yüzey, beklenen, f"{ad}+{ekler}")
        self.assertEqual(self.b("gel", "gelecek_zaman", "şahıs_1tekil_t1")[0],
                         ["gel", "eceğ", "im"])

    def test_iyor_daralma_token(self):
        self.assertEqual(self.b("oyna", "şimdiki_zaman")[0], ["oy", "n", "u", "yor"])
        self.assertEqual(self.b("başla", "şimdiki_zaman")[0], ["baş", "l", "ı", "yor"])

    def test_iyor_token(self):
        self.assertEqual(self.b("gel", "şimdiki_zaman")[0], ["gel", "i", "yor"])
        self.assertEqual(self.b("oku", "şimdiki_zaman")[0], ["o", "ku", "yor"])
        self.assertEqual(self.b("git", "şimdiki_zaman")[0], ["gid", "i", "yor"])

    def test_token_birleşimi_yüzeye_eşit(self):
        for ad, ekler in [("gel", ("şimdiki_zaman", "şahıs_1tekil_t1")),
                          ("oku", ("gelecek_zaman", "şahıs_2tekil_t1")),
                          ("git", ("görülen_geçmiş", "şahıs_1tekil_t2"))]:
            tokenlar, yüzey = self.b(ad, *ekler)
            self.assertEqual("".join(tokenlar), yüzey, f"{ad}+{ekler}")


class EkFiilTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kökler = yükle_dizin(KÖK_DİZİN)
        cls.ekler = ekleri_yükle(EK_DOSYASI)

    def b(self, ad, *ek_adları):
        return birleştir(ad, self.kökler[ad], list(ek_adları), self.ekler)

    def test_koşaç(self):
        durumlar = [
            ("öğretmen", ("ek_fiil_idi",), "öğretmendi"),
            ("hasta", ("ek_fiil_idi",), "hastaydı"),       # ünlü-sonu → y tamponu
            ("güzel", ("ek_fiil_imiş",), "güzelmiş"),
            ("güzel", ("ek_fiil_dir",), "güzeldir"),
            ("ev", ("bulunma", "ek_fiil_ise"), "evdeyse"), # hâl(3) + koşaç(4)
        ]
        for ad, ekler, beklenen in durumlar:
            _, yüzey = self.b(ad, *ekler)
            self.assertEqual(yüzey, beklenen, f"{ad}+{ekler}")
        self.assertEqual(self.b("ev", "bulunma", "ek_fiil_ise")[0],
                         ["ev", "de", "y", "se"])

    def test_nominalizer(self):
        # fiil → isim öbek geçişi: -mA/-Iş isimleştirir, isim ekleri ardından gelir
        durumlar = [
            ("gel", ("fiil_isim_ma", "iyelik_3tekil"), "gelmesi"),
            ("oku", ("fiil_isim_ma", "çoğul"), "okumalar"),
            ("gel", ("fiil_isim_ma", "belirtme"), "gelmeyi"),
            ("yürü", ("isim_fiil", "iyelik_3tekil"), "yürüyüşü"),
        ]
        for ad, ekler, beklenen in durumlar:
            _, yüzey = self.b(ad, *ekler)
            self.assertEqual(yüzey, beklenen, f"{ad}+{ekler}")
        self.assertEqual(self.b("gel", "fiil_isim_ma", "iyelik_3tekil")[0],
                         ["gel", "me", "s", "i"])
        self.assertEqual(self.b("yürü", "isim_fiil", "iyelik_3tekil")[0],
                         ["yü", "rü", "y", "üş", "ü"])

    def test_koşaç_kişi_ve_bileşik(self):
        durumlar = [
            ("öğretmen", ("koşaç_1tekil_t1",), "öğretmenim"),        # present copula+kişi
            ("hasta", ("koşaç_1tekil_t1",), "hastayım"),
            ("öğretmen", ("ek_fiil_idi", "koşaç_1tekil_t2"), "öğretmendim"),
            ("gel", ("şimdiki_zaman", "ek_fiil_idi"), "geliyordu"),  # bileşik zaman
            ("gel", ("gelecek_zaman", "ek_fiil_idi"), "gelecekti"),
            ("gel", ("geniş_zaman", "ek_fiil_idi"), "gelirdi"),
            ("gel", ("şimdiki_zaman", "ek_fiil_idi", "koşaç_1tekil_t2"), "geliyordum"),
        ]
        for ad, ekler, beklenen in durumlar:
            _, yüzey = self.b(ad, *ekler)
            self.assertEqual(yüzey, beklenen, f"{ad}+{ekler}")


if __name__ == "__main__":
    unittest.main()

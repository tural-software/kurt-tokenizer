"""cozumle modülü — çözümleme (segmentasyon) motoru testleri."""

import unittest
from pathlib import Path

from tokenizer.kokler import çalışma_sözlüğü
from tokenizer.ekler import yükle as ekleri_yükle
from tokenizer.istisna import yükle as istisna_yükle
from tokenizer.cozumle import çözümle
from tokenizer.pipeline import en_iyi_çözüm

KÖK_DİZİN = Path(__file__).resolve().parent.parent / "veri" / "kokler"
EK_DOSYASI = Path(__file__).resolve().parent.parent / "veri" / "ekler.json"
İST_DOSYASI = Path(__file__).resolve().parent.parent / "veri" / "istisnalar.json"
ZAMİR_DOSYASI = Path(__file__).resolve().parent.parent / "veri" / "zamirler.json"
İŞLEV_DOSYASI = Path(__file__).resolve().parent.parent / "veri" / "islev_kokleri.json"


class ÇözümleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.k = çalışma_sözlüğü(KÖK_DİZİN, ZAMİR_DOSYASI, İŞLEV_DOSYASI)
        cls.e = ekleri_yükle(EK_DOSYASI)
        cls.i = istisna_yükle(İST_DOSYASI)

    def çöz(self, kelime):
        return çözümle(kelime, self.k, self.e, self.i)

    def _var_mı(self, kelime, tokens, kök, ekler):
        return any(ç.tokens == tokens and ç.kök == kök and ç.ekler == ekler
                   for ç in self.çöz(kelime))

    def test_beklenen_çözüm_var(self):
        self.assertTrue(self._var_mı("evler", ["ev", "ler"], "ev", ["çoğul"]))
        self.assertTrue(self._var_mı("kitabı", ["ki", "tab", "ı"], "kitap", ["belirtme"]))
        self.assertTrue(self._var_mı("arabaya", ["a", "ra", "ba", "y", "a"], "araba", ["yönelme"]))
        self.assertTrue(self._var_mı("geliyor", ["gel", "i", "yor"], "gel", ["şimdiki_zaman"]))
        self.assertTrue(self._var_mı("kitapları", ["ki", "tap", "lar", "ı"], "kitap",
                                     ["çoğul", "belirtme"]))

    def test_çıplak_kök(self):
        self.assertTrue(self._var_mı("araba", ["a", "ra", "ba"], "araba", []))

    def test_bütün_kök_önceliği(self):
        # Kelime ZATEN sözlükte bir kök ise (ek yok) bütün-okuma, nadir kök+ek parçalanmasına
        # yeğlenir (deneyim/deneme/açacak/gelecek leksik). Bileşimsel biçim (kök DEĞİL) etkilenmez.
        def en(w):
            return en_iyi_çözüm(self.çöz(w), self.k, self.e)
        for w in ["deneyim", "deneme", "açacak", "gelecek", "düşünce"]:
            ç = en(w)
            self.assertEqual((ç.kök, ç.ekler), (w, []), w)      # bütün-okuma kazanır
        # bileşimsel (kök değil): geleceğim = gel+gelecek_zaman+şahıs (bonus etkilemez)
        ç = en("geleceğim")
        self.assertEqual(ç.kök, "gel")
        self.assertIn("gelecek_zaman", ç.ekler)

    def test_istisna(self):
        ç = self.çöz("ve")
        self.assertEqual(ç[0].tokens, ["ve"])

    def test_bilinmeyen_boş(self):
        # ünlüsüz dizi: şema gereği (son_ünlü zorunlu) ASLA kök olamaz → kalıcı bilinmeyen
        self.assertEqual(self.çöz("şçkptr"), [])       # çözülemez → bilinmeyen

    def test_morfotaktik_sahte_eler(self):
        # Her çözüm: ekler kök sınıfıyla öbek-uyumlu + yuvalar kesin artan olmalı
        for kelime in ["evlerim", "kitapları", "evler", "geliyorum", "kitabı"]:
            for ç in self.çöz(kelime):
                kk = self.k[ç.kök]
                sınıflar = {"fiil" if t == "fiil" else "isim"
                            for t in [kk.tür, *(kk.ek_tür or [])]}
                self.assertTrue(
                    all(self.e[a].öbek == "her" or self.e[a].öbek in sınıflar
                        for a in ç.ekler), f"{kelime}: öbek uyumsuz {ç}")
                yuvalar = [self.e[a].yuva for a in ç.ekler]
                self.assertEqual(yuvalar, sorted(set(yuvalar)),
                                 f"{kelime}: yuva artan değil {ç}")

    def test_sahte_azaldı(self):
        # morfotaktik + kişi-bağlamı ile sahteler kökten elendi (14 → 2)
        self.assertLessEqual(len(self.çöz("evlerim")), 2)   # my houses / I-am-houses
        # isim kökü + fiil eki sahtesi (öbek ihlali) yok
        for ç in self.çöz("oynuyor"):
            self.assertNotEqual(self.k[ç.kök].tür, "isim")
        # kişi-bağlamı: kanonik (en az token) çözüm öğretmen-tabanlı
        # (öğret+me+n+im "senin öğretmen-im" gerçek bir belirsizlik → korunur ama uzun)
        en_az = min(self.çöz("öğretmenim"), key=lambda c: len(c.tokens))
        self.assertEqual(en_az.kök, "öğretmen")
        # tip-2 kişi (-m) yalnız -DI/-sA sonrası: geldim var, "gelim" yok
        self.assertTrue(any(c.ekler == ["görülen_geçmiş", "şahıs_1tekil_t2"]
                            for c in self.çöz("geldim")))

    def test_nominalizer_çözümlenir(self):
        # fiil→isim öbek geçişi: nominalizer + isim ekleri
        self.assertTrue(self._var_mı("gelmesi", ["gel", "me", "s", "i"], "gel",
                                     ["fiil_isim_ma", "iyelik_3tekil"]))
        self.assertTrue(self._var_mı("okumalar", ["o", "ku", "ma", "lar"], "oku",
                                     ["fiil_isim_ma", "çoğul"]))
        self.assertTrue(self._var_mı("yürüyüşü", ["yü", "rü", "y", "üş", "ü"], "yürü",
                                     ["isim_fiil", "iyelik_3tekil"]))
        self.assertTrue(self._var_mı("gelmeyi", ["gel", "me", "y", "i"], "gel",
                                     ["fiil_isim_ma", "belirtme"]))

    def test_iyor_daralma_çözümlenir(self):
        self.assertTrue(self._var_mı("oynuyor", ["oy", "n", "u", "yor"], "oyna",
                                     ["şimdiki_zaman"]))
        self.assertTrue(self._var_mı("başlıyor", ["baş", "l", "ı", "yor"], "başla",
                                     ["şimdiki_zaman"]))
        # olumsuz+şimdiki: -mA daralır → gelmiyor (aynı daraltır kuralı)
        self.assertTrue(self._var_mı("gelmiyor", ["gel", "m", "i", "yor"], "gel",
                                     ["olumsuz", "şimdiki_zaman"]))

    def test_eşsesli_çift_okuma(self):
        # yaz: isim (yazları) + fiil (yazdı) — her iki okuma da çözülmeli
        self.assertTrue(self._var_mı("yazları", ["yaz", "lar", "ı"], "yaz",
                                     ["çoğul", "belirtme"]))
        self.assertTrue(self._var_mı("yazdı", ["yaz", "dı"], "yaz", ["görülen_geçmiş"]))
        # göç: isim + fiil
        self.assertTrue(any(ç.kök == "göç" for ç in self.çöz("göçtü")))
        # yüz: isim (yüzü) + fiil (yüzdü)
        self.assertTrue(any(ç.kök == "yüz" for ç in self.çöz("yüzdü")))

    def test_geniş_zaman(self):
        self.assertTrue(self._var_mı("gelir", ["gel", "ir"], "gel", ["geniş_zaman"]))
        self.assertTrue(self._var_mı("yazar", ["yaz", "ar"], "yaz", ["geniş_zaman"]))
        self.assertTrue(self._var_mı("okur", ["o", "ku", "r"], "oku", ["geniş_zaman"]))
        self.assertTrue(self._var_mı("getirir", ["ge", "tir", "ir"], "getir",
                                     ["geniş_zaman"]))
        # olumsuz geniş → -z (gelmez)
        self.assertTrue(self._var_mı("gelmez", ["gel", "me", "z"], "gel",
                                     ["olumsuz", "geniş_zaman"]))

    def test_ek_fiil(self):
        self.assertTrue(self._var_mı("öğretmendi", ["öğ", "ret", "men", "di"],
                                     "öğretmen", ["ek_fiil_idi"]))
        self.assertTrue(self._var_mı("evdeyse", ["ev", "de", "y", "se"], "ev",
                                     ["bulunma", "ek_fiil_ise"]))
        self.assertTrue(any(ç.kök == "güzel" for ç in self.çöz("güzelmiş")))

    def test_ortaç_çözümlenir(self):
        # -An sıfat-fiil (ortaç): isimleşir, isim eki alır (çıkış mekanizması)
        self.assertTrue(self._var_mı("geçen", ["geç", "en"], "geç", ["ortaç_an"]))
        self.assertTrue(self._var_mı("okuyan", ["o", "ku", "y", "an"], "oku", ["ortaç_an"]))
        self.assertTrue(self._var_mı("gelenler", ["gel", "en", "ler"], "gel",
                                     ["ortaç_an", "çoğul"]))
        self.assertTrue(self._var_mı("gelmeyen", ["gel", "me", "y", "en"], "gel",
                                     ["olumsuz", "ortaç_an"]))

    def test_düzeltme_imli_ünlü(self):
        # â/î/û artık ünlü → hikâye/kâğıt/kâr kökleri çözülür (â interior ya da son)
        self.assertTrue(self._var_mı("hikâyeyi", ["hi", "kâ", "ye", "y", "i"], "hikâye",
                                     ["belirtme"]))
        self.assertTrue(self._var_mı("kâğıdı", ["kâ", "ğıd", "ı"], "kâğıt",
                                     ["iyelik_3tekil"]))   # â interior + t→d
        self.assertTrue(self._var_mı("kârı", ["kâr", "ı"], "kâr", ["iyelik_3tekil"]))

    def test_çatı_ekleri(self):
        # edilgen (pasif): ünsüz→(I)l, l-sonu→(I)n, ünlü-sonu→n
        self.assertTrue(self._var_mı("yapıldı", ["yap", "ı", "l", "dı"], "yap",
                                     ["edilgen", "görülen_geçmiş"]))
        self.assertTrue(self._var_mı("görülen", ["gör", "ü", "l", "en"], "gör",
                                     ["edilgen", "ortaç_an"]))
        self.assertTrue(any(c.ekler == ["edilgen", "görülen_geçmiş"]
                            for c in self.çöz("bulundu")))   # bul+un+du (l-sonu)
        # dönüşlü: giyin
        self.assertTrue(self._var_mı("giyindi", ["giy", "i", "n", "di"], "giy",
                                     ["dönüşlü", "görülen_geçmiş"]))
        # ettirgen + edilgen YIĞILMASI (çıkış-reset ile): yaptırıldı
        self.assertTrue(self._var_mı("yaptırıldı", ["yap", "tır", "ı", "l", "dı"], "yap",
                                     ["ettirgen", "edilgen", "görülen_geçmiş"]))
        # çatı + olumsuz + zaman: yazılmadı
        self.assertTrue(self._var_mı("yazılmadı", ["yaz", "ı", "l", "ma", "dı"], "yaz",
                                     ["edilgen", "olumsuz", "görülen_geçmiş"]))

    def test_yapım_ekleri(self):
        # üretken yapım ekleri: -lI/-sIz/-CI/-lIk → yeni gövde (çıkış isim), çekim alır
        self.assertTrue(self._var_mı("evli", ["ev", "li"], "ev", ["yapım_lı"]))
        self.assertTrue(self._var_mı("evsiz", ["ev", "siz"], "ev", ["yapım_sız"]))
        self.assertTrue(self._var_mı("kapıcı", ["ka", "pı", "cı"], "kapı", ["yapım_cı"]))  # C→c
        self.assertTrue(self._var_mı("simitçi", ["si", "mit", "çi"], "simit", ["yapım_cı"]))  # C→ç
        self.assertTrue(self._var_mı("kitapçı", ["ki", "tap", "çı"], "kitap", ["yapım_cı"]))  # p SABİT (C ünsüz)
        self.assertTrue(self._var_mı("güzellik", ["gü", "zel", "lik"], "güzel", ["yapım_lık"]))
        # türetilmiş gövde çekim alır: yapım + çoğul (çıkış-reset ile)
        self.assertTrue(self._var_mı("evliler", ["ev", "li", "ler"], "ev",
                                     ["yapım_lı", "çoğul"]))
        # -lIk k→ğ ünlü-başlı ek öncesi: gözlüğü
        self.assertTrue(self._var_mı("gözlüğü", ["göz", "lüğ", "ü"], "göz",
                                     ["yapım_lık", "iyelik_3tekil"]))
        # yapım YIĞILMASI: gözlük+çü (çıkış-reset)
        self.assertTrue(self._var_mı("gözlükçü", ["göz", "lük", "çü"], "göz",
                                     ["yapım_lık", "yapım_cı"]))
        # yapım eki ÇEKİMDEN önce gelir: çekimli gövdeden türetilemez (evlerli YOK)
        for ç in self.çöz("evlerli"):
            self.assertNotEqual(ç.ekler, ["çoğul", "yapım_lı"])
        # -sAl türetim: kişisel/toplumsal/bilimsel → isimleşir, çekim alır
        self.assertTrue(self._var_mı("kişisel", ["ki", "şi", "sel"], "kişi", ["yapım_sal"]))
        self.assertTrue(self._var_mı("toplumsal", ["top", "lum", "sal"], "toplum", ["yapım_sal"]))
        self.assertTrue(self._var_mı("kişiseldi", ["ki", "şi", "sel", "di"], "kişi",
                                     ["yapım_sal", "ek_fiil_idi"]))

    def test_istek_kipi(self):
        # -(y)AlIm istek 1.çoğul (yuva 2 kip): gidelim/yapalım/hazırlayalım
        self.assertTrue(self._var_mı("gidelim", ["gid", "elim"], "git", ["istek_1çoğul"]))
        self.assertTrue(self._var_mı("yapalım", ["yap", "alım"], "yap", ["istek_1çoğul"]))
        self.assertTrue(self._var_mı("hazırlayalım", ["ha", "zır", "la", "y", "alım"],
                                     "hazırla", ["istek_1çoğul"]))

    def test_ye_de_düzensiz(self):
        # ye/de düzensizi: y-glide'lı ek (ünlü-başlı veya -Iyor) öncesi çekirdek e→i
        self.assertTrue(self._var_mı("yiyor", ["yi", "yor"], "ye", ["şimdiki_zaman"]))
        self.assertTrue(self._var_mı("yiyelim", ["yi", "y", "elim"], "ye", ["istek_1çoğul"]))
        self.assertTrue(self._var_mı("diyor", ["di", "yor"], "de", ["şimdiki_zaman"]))
        self.assertTrue(self._var_mı("diyecek", ["di", "y", "ecek"], "de", ["gelecek_zaman"]))
        self.assertTrue(self._var_mı("diyen", ["di", "y", "en"], "de", ["ortaç_an"]))
        # ünsüz-başlı ekte DEĞİŞMEZ (yedi/dedi/dese = ye/de+ek, e korunur)
        self.assertTrue(self._var_mı("dedi", ["de", "di"], "de", ["görülen_geçmiş"]))
        self.assertTrue(self._var_mı("dese", ["de", "se"], "de", ["şart"]))
        self.assertTrue(any(c.kök == "ye" and c.ekler == ["şart"] for c in self.çöz("yese")))

    def test_istek_emir_kipleri(self):
        # -(y)AyIm istek 1.tekil (düşüneyim/gideyim) + -sIn emir 3.kişi (gelsin/okusun)
        self.assertTrue(self._var_mı("düşüneyim", ["dü", "şün", "eyim"], "düşün",
                                     ["istek_1tekil"]))
        self.assertTrue(self._var_mı("gideyim", ["gid", "eyim"], "git", ["istek_1tekil"]))
        self.assertTrue(self._var_mı("gelsin", ["gel", "sin"], "gel", ["emir_3tekil"]))
        self.assertTrue(self._var_mı("okusun", ["o", "ku", "sun"], "oku", ["emir_3tekil"]))

    def test_emir_paradigması(self):
        # emir 2çoğul -(y)In / kibar -(y)InIz / 3çoğul -sInlAr (öbek fiil → iyelik ile çakışmaz)
        self.assertTrue(self._var_mı("geliniz", ["gel", "iniz"], "gel", ["emir_2çoğul_kibar"]))
        self.assertTrue(self._var_mı("okuyunuz", ["o", "ku", "y", "unuz"], "oku",
                                     ["emir_2çoğul_kibar"]))
        self.assertTrue(self._var_mı("gelsinler", ["gel", "sinler"], "gel", ["emir_3çoğul"]))
        self.assertTrue(self._var_mı("oturun", ["o", "tur", "un"], "otur", ["emir_2çoğul"]))
        # ye→yi daralan emirde de: yiyiniz
        self.assertTrue(self._var_mı("yiyiniz", ["yi", "y", "iniz"], "ye", ["emir_2çoğul_kibar"]))
        # iyelik (öbek isim) bozulmadı: kitabınız = kitap + iyelik_2çoğul
        self.assertTrue(self._var_mı("kitabınız", ["ki", "tab", "ı", "nız"], "kitap",
                                     ["iyelik_2çoğul"]))

    def test_sıra_sayısı(self):
        # -(I)ncI sıra sayısı: üç→üçüncü, beş→beşinci, yirmi→yirminci; isimleşir, çekim alır
        self.assertTrue(self._var_mı("üçüncü", ["üç", "ü", "ncü"], "üç", ["sıra"]))
        self.assertTrue(self._var_mı("beşinci", ["beş", "i", "nci"], "beş", ["sıra"]))
        self.assertTrue(self._var_mı("yirminci", ["yir", "mi", "nci"], "yirmi", ["sıra"]))
        self.assertTrue(self._var_mı("üçüncüsü", ["üç", "ü", "ncü", "s", "ü"], "üç",
                                     ["sıra", "iyelik_3tekil"]))

    def test_kendi_dönüşlü_zamir(self):
        # kendi: dönüşlü zamir gövdesi → iyelik+hâl motorla çözülür, token paylaşır
        self.assertTrue(self._var_mı("kendimi", ["ken", "di", "m", "i"], "kendi",
                                     ["iyelik_1tekil", "belirtme"]))
        self.assertTrue(self._var_mı("kendisi", ["ken", "di", "s", "i"], "kendi",
                                     ["iyelik_3tekil"]))

    def test_ara_eşsesli_fiil(self):
        # ara: isim (mola) + fiil (aramak) → arar/ararken/arıyor çözülür
        self.assertTrue(self._var_mı("ararken", ["a", "ra", "r", "ken"], "ara",
                                     ["geniş_zaman", "ek_fiil_ken"]))
        self.assertTrue(any(c.kök == "ara" and c.ekler == ["şimdiki_zaman"]
                            for c in self.çöz("arıyor")))

    def test_sınıf_farkındalıklı_yumuşama(self):
        # Eşsesli gerek: İSİM olarak k→ğ (gereği) ama FİİL olarak k SABİT (gerekiyor) — kural #7.
        self.assertTrue(self._var_mı("gerekiyor", ["ge", "rek", "i", "yor"], "gerek",
                                     ["şimdiki_zaman"]))               # fiil: k yumuşamaz
        self.assertTrue(any(c.ekler == ["iyelik_3tekil"] and c.tokens == ["ge", "reğ", "i"]
                            for c in self.çöz("gereği")))              # isim: k→ğ yumuşar
        # gerekmektedir = gerek(fiil)+mek+te+dir (kök k sabit; ünsüz-sonu bulunma)
        self.assertTrue(self._var_mı("gerekmektedir", ["ge", "rek", "mek", "te", "dir"], "gerek",
                                     ["mastar", "bulunma", "ek_fiil_dir"]))
        # regresyon: t→d fiil yumuşaması SÜRER (git→gidiyor)
        self.assertTrue(self._var_mı("gidiyor", ["gid", "i", "yor"], "git", ["şimdiki_zaman"]))

    def test_okumaya_göre_yumuşama(self):
        # Yumuşama kökün BİRİNCİL sınıfına aittir; ikincil okumada uygulanmaz.
        # art (isim t→d / fiil sabit): ardı(isim) yumuşar, artıyor(fiil) sabit
        self.assertTrue(self._var_mı("ardı", ["ard", "ı"], "art", ["iyelik_3tekil"]))
        self.assertTrue(self._var_mı("artıyor", ["art", "ı", "yor"], "art", ["şimdiki_zaman"]))
        # et (fiil t→d / isim sabit): ediyor(fiil) yumuşar, eti(isim) sabit
        self.assertTrue(self._var_mı("ediyor", ["ed", "i", "yor"], "et", ["şimdiki_zaman"]))
        self.assertTrue(self._var_mı("eti", ["et", "i"], "et", ["iyelik_3tekil"]))
        # öğüt (isim t→d / fiil sabit): öğüdü(isim) yumuşar, öğütüyor(fiil) sabit
        self.assertTrue(self._var_mı("öğüdü", ["ö", "ğüd", "ü"], "öğüt", ["iyelik_3tekil"]))
        self.assertTrue(self._var_mı("öğütüyor", ["ö", "ğüt", "ü", "yor"], "öğüt",
                                     ["şimdiki_zaman"]))

    def test_her_iki_yön_yumuşama(self):
        # tat: HER İKİ okumada da t→d (ek_değişim ile) — tadı(isim) VE tadıyor/tadar(fiil)
        self.assertTrue(self._var_mı("tadı", ["tad", "ı"], "tat", ["iyelik_3tekil"]))
        self.assertTrue(self._var_mı("tadıyor", ["tad", "ı", "yor"], "tat", ["şimdiki_zaman"]))
        self.assertTrue(self._var_mı("tadar", ["tad", "ar"], "tat", ["geniş_zaman"]))
        # ünsüz-başlı ekte yumuşamaz (mastar/koşaç): tatmak
        self.assertTrue(self._var_mı("tatmak", ["tat", "mak"], "tat", ["mastar"]))

    def test_araç_pronominal_n_yok(self):
        # araç -(y)lA 3.tekil iyelikten sonra -n- ALMAZ (arabasıyla, arabasınla DEĞİL)
        self.assertTrue(self._var_mı("arabasıyla", ["a", "ra", "ba", "s", "ı", "y", "la"],
                                     "araba", ["iyelik_3tekil", "araç"]))
        # ama bulunma -n- ALIR (arabasında)
        self.assertTrue(self._var_mı("arabasında", ["a", "ra", "ba", "s", "ı", "n", "da"],
                                     "araba", ["iyelik_3tekil", "bulunma"]))

    def test_yetersizlik(self):
        # -(y)AmA yetersizlik + geniş(-z): gelemez/gelemezler
        self.assertTrue(self._var_mı("gelemez", ["gel", "eme", "z"], "gel",
                                     ["yetersizlik", "geniş_zaman"]))
        self.assertTrue(self._var_mı("yapamaz", ["yap", "ama", "z"], "yap",
                                     ["yetersizlik", "geniş_zaman"]))
        self.assertTrue(any(c.ekler == ["yetersizlik", "geniş_zaman", "şahıs_3çoğul"]
                            for c in self.çöz("gelemezler")))

    def test_soru_kişi(self):
        # soru edatı kökü (mı/mi/mu/mü) koşaç/ek-fiil alır: misin/miyim/miydi
        self.assertTrue(self._var_mı("misin", ["mi", "sin"], "mi", ["koşaç_2tekil_t1"]))
        self.assertTrue(self._var_mı("miyim", ["mi", "y", "im"], "mi", ["koşaç_1tekil_t1"]))
        self.assertTrue(self._var_mı("miydi", ["mi", "y", "di"], "mi", ["ek_fiil_idi"]))

    def test_sadece_koşaç_kirletmez(self):
        # mı/mi kökü isim eki ALMAZ → "mide" yanlışlıkla mi+bulunma diye bölünmez
        for ç in self.çöz("mide"):
            self.assertNotEqual(ç.kök, "mi", f"mide yanlış bölündü: {ç}")

    def test_mastar_iyelik(self):
        # -mAk + iyelik: k→ğ ek-yumuşaması (gelmek+i → gelmeği)
        self.assertTrue(self._var_mı("gelmeği", ["gel", "meğ", "i"], "gel",
                                     ["mastar", "iyelik_3tekil"]))

    def test_yeterlilik(self):
        # -(y)Abil yeterlilik + zaman (yuva 1 → zaman yuva 2)
        self.assertTrue(self._var_mı("olabilir", ["ol", "abil", "ir"], "ol",
                                     ["yeterlilik", "geniş_zaman"]))
        self.assertTrue(self._var_mı("gidebilir", ["gid", "ebil", "ir"], "git",
                                     ["yeterlilik", "geniş_zaman"]))
        self.assertTrue(self._var_mı("görebilirim", ["gör", "ebil", "ir", "im"], "gör",
                                     ["yeterlilik", "geniş_zaman", "şahıs_1tekil_t1"]))

    def test_istisnai_uyum(self):
        # ince kök çözümlenir
        self.assertTrue(self._var_mı("kalbi", ["kalb", "i"], "kalp", ["iyelik_3tekil"]))
        self.assertTrue(self._var_mı("rolü", ["rol", "ü"], "rol", ["iyelik_3tekil"]))
        self.assertTrue(self._var_mı("saate", ["sa", "at", "e"], "saat", ["yönelme"]))

    def test_ünlü_düşmesi(self):
        # düşen-ünlü kök çözümlenir (düşmüş önek adayı eklenir)
        self.assertTrue(self._var_mı("aklı", ["a", "kl", "ı"], "akıl", ["iyelik_3tekil"]))
        self.assertTrue(self._var_mı("şehri", ["şe", "hr", "i"], "şehir", ["iyelik_3tekil"]))
        self.assertTrue(self._var_mı("ağzı", ["a", "ğz", "ı"], "ağız", ["iyelik_3tekil"]))
        self.assertTrue(self._var_mı("kaybı", ["ka", "yb", "ı"], "kayıp", ["iyelik_3tekil"]))
        # ünsüz-başlı ekte düşmez
        self.assertTrue(self._var_mı("akıllar", ["a", "kıl", "lar"], "akıl", ["çoğul"]))

    def test_pronominal_n(self):
        # 3.tekil iyelik + hâl → araya -n- (arabası+n+da); sı-tipi yalnız 3.tekil
        self.assertTrue(self._var_mı("arabasında", ["a", "ra", "ba", "s", "ı", "n", "da"],
                                     "araba", ["iyelik_3tekil", "bulunma"]))
        self.assertTrue(self._var_mı("arabasını", ["a", "ra", "ba", "s", "ı", "n", "ı"],
                                     "araba", ["iyelik_3tekil", "belirtme"]))

    def test_dik_ortaç(self):
        # -DIk ortacı (k→ğ) + iyelik; çıplak 'geldik' 1.çoğul kalır (iyelik gerektiren)
        self.assertTrue(self._var_mı("yaptığı", ["yap", "tığ", "ı"], "yap",
                                     ["ortaç_dik", "iyelik_3tekil"]))
        self.assertTrue(self._var_mı("geldiği", ["gel", "diğ", "i"], "gel",
                                     ["ortaç_dik", "iyelik_3tekil"]))
        for ç in self.çöz("geldik"):          # bare: yalnız 1.çoğul görülen, ortaç YOK
            self.assertNotIn("ortaç_dik", ç.ekler)
        # -AcAk ortacı (k→ğ) + iyelik; çıplak 'gelecek' zaman kalır
        self.assertTrue(self._var_mı("geleceği", ["gel", "eceğ", "i"], "gel",
                                     ["ortaç_acak", "iyelik_3tekil"]))
        self.assertTrue(any(c.ekler == ["gelecek_zaman"] for c in self.çöz("gelecek")))
        for ç in self.çöz("gelecek"):
            self.assertNotIn("ortaç_acak", ç.ekler)

    def test_eşitlik_ca(self):
        # -CA eşitlik/görelik: güzelce, bence (zamir), çocukça (k sonrası ç)
        self.assertTrue(self._var_mı("güzelce", ["gü", "zel", "ce"], "güzel", ["eşitlik"]))
        self.assertTrue(self._var_mı("bence", ["ben", "ce"], "ben", ["eşitlik"]))
        self.assertTrue(self._var_mı("çocukça", ["ço", "cuk", "ça"], "çocuk", ["eşitlik"]))

    def test_soru_edatı(self):
        for w in ["mı", "mi", "mu", "mü"]:
            self.assertEqual(self.çöz(w)[0].tokens, [w], w)

    def test_aitlik_çözümlenir(self):
        # -ki aitlik: hâl/iyelik sonrası ilgi sıfatı; isimleşir (evdekiler)
        self.assertTrue(self._var_mı("evdeki", ["ev", "de", "ki"], "ev",
                                     ["bulunma", "aitlik"]))
        self.assertTrue(self._var_mı("kenarındaki", ["ke", "nar", "ı", "n", "da", "ki"],
                                     "kenar", ["iyelik_2tekil", "bulunma", "aitlik"]))
        self.assertTrue(self._var_mı("benimki", ["ben", "i", "m", "ki"], "ben",
                                     ["iyelik_1tekil", "aitlik"]))

    def test_ulaç_çözümlenir(self):
        # zarf-fiil (ulaç): -Ip / -ArAk / -IncA / -mAdAn
        self.assertTrue(self._var_mı("alıp", ["al", "ıp"], "al", ["ulaç_ip"]))
        self.assertTrue(self._var_mı("olunca", ["ol", "unca"], "ol", ["ulaç_inca"]))
        self.assertTrue(self._var_mı("gelerek", ["gel", "erek"], "gel", ["ulaç_arak"]))
        self.assertTrue(self._var_mı("okuyarak", ["o", "ku", "y", "arak"], "oku",
                                     ["ulaç_arak"]))
        self.assertTrue(self._var_mı("gelmeden", ["gel", "meden"], "gel", ["ulaç_madan"]))

    def test_gelecek_yumuşaması_çözümlenir(self):
        # ek-sonu yumuşaması ÇÖZÜMLENİR (ara biçim gelecek→geleceğ önek budamasını geçer)
        self.assertTrue(self._var_mı("geleceğim", ["gel", "eceğ", "im"], "gel",
                                     ["gelecek_zaman", "şahıs_1tekil_t1"]))
        self.assertTrue(self._var_mı("gideceğiz", ["gid", "eceğ", "iz"], "git",
                                     ["gelecek_zaman", "şahıs_1çoğul_t1"]))
        self.assertTrue(self._var_mı("yapacağız", ["yap", "acağ", "ız"], "yap",
                                     ["gelecek_zaman", "şahıs_1çoğul_t1"]))

    def test_koşaç_bağlanma(self):
        # koşaç/ek-fiil çıplak fiile bağlanmaz + kişi kaynağı (V↔fiil, K↔koşaç) eşleşir
        gd = self.çöz("geldim")
        self.assertEqual(len(gd), 1)                       # görülen+koşaç ve gel+idi elendi
        self.assertEqual(gd[0].ekler, ["görülen_geçmiş", "şahıs_1tekil_t2"])
        # bileşik zaman (zamanlı fiil + koşaç) korunur
        self.assertTrue(any(c.ekler == ["şimdiki_zaman", "ek_fiil_idi", "koşaç_1tekil_t2"]
                            for c in self.çöz("geliyordum")))
        # ad-yüklem koşaç (present-zero) korunur
        self.assertTrue(any(c.ekler == ["koşaç_1tekil_t1"] for c in self.çöz("öğretmenim")))

    def test_zamir_çözümlenir(self):
        # hibrit: zamir gövdesi (ben/sen/biz/on/bun…) düzenli çekimleri motorla çözer
        self.assertTrue(self._var_mı("beni", ["ben", "i"], "ben", ["belirtme"]))
        self.assertTrue(self._var_mı("benden", ["ben", "den"], "ben", ["ayrılma"]))
        self.assertTrue(self._var_mı("senin", ["sen", "in"], "sen", ["tamlayan"]))
        self.assertTrue(self._var_mı("onu", ["on", "u"], "on", ["belirtme"]))
        self.assertTrue(self._var_mı("ona", ["on", "a"], "on", ["yönelme"]))
        self.assertTrue(self._var_mı("onlar", ["on", "lar"], "on", ["çoğul"]))
        self.assertTrue(self._var_mı("bunu", ["bun", "u"], "bun", ["belirtme"]))
        # bare zamir = çıplak kök
        self.assertTrue(self._var_mı("ben", ["ben"], "ben", []))

    def test_işlev_sözcükleri(self):
        # çekimlenen zamir-sınıfı: motorla çözülür ve token paylaşır
        self.assertTrue(self._var_mı("herkese", ["her", "kes", "e"], "herkes", ["yönelme"]))
        self.assertTrue(self._var_mı("kimi", ["kim", "i"], "kim", ["iyelik_3tekil"]))
        self.assertTrue(self._var_mı("nereye", ["ne", "re", "y", "e"], "nere", ["yönelme"]))
        # değişmez işlev sözcükleri: istisna, bütün-token
        for w in ["gibi", "için", "çünkü", "ama", "her"]:
            self.assertEqual(self.çöz(w)[0].tokens, [w], w)

    def test_copula_zone(self):
        # çekimlenen işlev kökü değil/yok: copula ekleriyle çözülür, token paylaşır
        self.assertTrue(self._var_mı("değilim", ["de", "ğil", "im"], "değil",
                                     ["koşaç_1tekil_t1"]))
        self.assertTrue(self._var_mı("değildi", ["de", "ğil", "di"], "değil",
                                     ["ek_fiil_idi"]))
        self.assertTrue(self._var_mı("yoktu", ["yok", "tu"], "yok", ["ek_fiil_idi"]))
        self.assertTrue(self._var_mı("yoksa", ["yok", "sa"], "yok", ["ek_fiil_ise"]))
        # -ken ulacı: zamanlı fiile (gelirken) ve ad-yükleme (çocukken/evdeyken)
        self.assertTrue(any(c.ekler == ["geniş_zaman", "ek_fiil_ken"]
                            for c in self.çöz("gelirken")))
        self.assertTrue(self._var_mı("çocukken", ["ço", "cuk", "ken"], "çocuk",
                                     ["ek_fiil_ken"]))
        self.assertTrue(self._var_mı("evdeyken", ["ev", "de", "y", "ken"], "ev",
                                     ["bulunma", "ek_fiil_ken"]))

    def test_araç_durumu_çözümlenir(self):
        # araç durumu: isimde doğrudan, zamirde iyelik+araç zinciriyle (benimle=ben+im+le)
        self.assertTrue(self._var_mı("evle", ["ev", "le"], "ev", ["araç"]))
        self.assertTrue(self._var_mı("arabayla", ["a", "ra", "ba", "y", "la"], "araba",
                                     ["araç"]))
        self.assertTrue(self._var_mı("benimle", ["ben", "i", "m", "le"], "ben",
                                     ["iyelik_1tekil", "araç"]))
        self.assertTrue(self._var_mı("onunla", ["on", "u", "n", "la"], "on",
                                     ["iyelik_2tekil", "araç"]))

    def test_zamir_suppletif_istisna(self):
        # gerçek suppletion (bana/sana) istisna; engine "bene" üretir, kullanıcı "bana" yazar
        self.assertEqual(self.çöz("bana")[0].tokens, ["ban", "a"])
        self.assertEqual(self.çöz("sana")[0].tokens, ["san", "a"])

    def test_token_birleşimi_kelimeye_eşit(self):
        for kelime in ["evler", "kitabı", "arabaya", "geliyor", "kitapları",
                       "gözümüz", "rengi"]:
            for ç in self.çöz(kelime):
                self.assertEqual("".join(ç.tokens), kelime, kelime)


if __name__ == "__main__":
    unittest.main()

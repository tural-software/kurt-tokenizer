"""Kod kipi (K1) — boşluk, satır sonu ve girinti kayıpsız; metin kipi değişmez."""

import os
import random
import unittest
from pathlib import Path

from tokenizer.kokler import çalışma_sözlüğü
from tokenizer.ekler import yükle as ekleri_yükle
from tokenizer.istisna import yükle as istisna_yükle
from tokenizer.pipeline import encode, decode, boşluk_tokenları, BOŞLUK
from tokenizer.vocab import Vocab

KÖK = Path(__file__).resolve().parent.parent
VERİ = KÖK / "veri"


class KodKipiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.k = çalışma_sözlüğü(VERİ / "kokler", VERİ / "zamirler.json", VERİ / "islev_kokleri.json")
        cls.e = ekleri_yükle(VERİ / "ekler.json")
        cls.i = istisna_yükle(VERİ / "istisnalar.json")
        cls.v = Vocab.yükle(VERİ / "vocab.json")
        cls.bayt = {cls.v.tok2id[t] for t in cls.v.id2tok if t.startswith("<0x")}

    def gidip_gel(self, kod):
        ids = self.v.encode_ids(kod, self.k, self.e, self.i, kip="kod")
        return ids, self.v.decode_ids(ids, kip="kod")

    def test_boşluk_tokenları(self):
        self.assertEqual(boşluk_tokenları(" "), [BOŞLUK])
        self.assertEqual(boşluk_tokenları("\n    "), ["\n", BOŞLUK * 4])
        self.assertEqual(boşluk_tokenları(" " * 20), [BOŞLUK * 16, BOŞLUK * 4])
        self.assertEqual(boşluk_tokenları("\r\n\t\t"), ["\r", "\n", "\t", "\t"])

    def test_kenar_durumları(self):
        for kod in ["", " ", "\n", "  x = 1  \n", "\n\n\ndef f():\n\treturn 1\r\n",
                    "a" + " " * 40 + "b", "x\u00a0=\u00a01\x0c\x0b", "▁ ▁▁\n▁",
                    "    # Türkçe yorum: kökü bul\n    değer = İstanbul'da"]:
            ids, geri = self.gidip_gel(kod)
            self.assertEqual(geri, kod, repr(kod))
            self.assertNotIn(self.v.tok2id["<unk>"], ids)

    def test_sıradan_boşluk_bayta_düşmez(self):
        ids, _ = self.gidip_gel("def f(x):\n\tif x:\n        return [x,  x]\r\n")
        self.assertFalse(self.bayt & set(ids))

    def test_depo_kaynak_dosyaları(self):
        # bu deponun TÜM .py dosyaları kod kipinde birebir geri döner, bayt tokenı yok
        dosyalar = sorted(KÖK.glob("**/*.py"))
        self.assertGreater(len(dosyalar), 20)
        for yol in dosyalar:
            kod = yol.read_text(encoding="utf-8")
            ids, geri = self.gidip_gel(kod)
            self.assertEqual(geri, kod, str(yol))

    def test_stdlib_örneklem(self):
        # Python'un kendi kaynağından deterministik örneklem (bu makinedeki stdlib)
        lib = Path(os.__file__).parent
        dosyalar = sorted(p for p in lib.glob("*.py"))
        random.Random(11).shuffle(dosyalar)
        for yol in dosyalar[:25]:
            kod = yol.read_text(encoding="utf-8", errors="surrogateescape")
            _, geri = self.gidip_gel(kod)
            self.assertEqual(geri, kod, str(yol))

    def test_metin_kipi_değişmedi(self):
        # metin kipi boşluğu hâlâ tek ▁'ye indirir ve baş/son kırpar (kurt-veri uyumu)
        t = encode("  ev\n\n  araba  ", self.k, self.e, self.i)
        self.assertEqual(t, ["ev", BOŞLUK, "a", "ra", "ba"])
        self.assertEqual(decode(t), "ev araba")

    def test_bilinmeyen_kip(self):
        with self.assertRaises(ValueError):
            encode("x", self.k, self.e, self.i, kip="python")
        with self.assertRaises(ValueError):                  # dil yalnız kod kipinde
            encode("x", self.k, self.e, self.i, dil="python")
        with self.assertRaises(ValueError):
            encode("x", self.k, self.e, self.i, kip="kod", dil="cobol")


class PythonK2Test(unittest.TestCase):
    """K2 — Python lexer: anahtar sözcük/operatör bütün token, yorum/string Türkçe hat."""

    @classmethod
    def setUpClass(cls):
        KodKipiTest.setUpClass.__func__(cls)

    def py(self, kod, kuyruk=None):
        return encode(kod, self.k, self.e, self.i, kuyruk, kip="kod", dil="python")

    def py_gidip_gel(self, kod):
        ids = self.v.encode_ids(kod, self.k, self.e, self.i, kip="kod", dil="python")
        return ids, self.v.decode_ids(ids, kip="kod")

    def test_lexer_tüm_stdlib_kayıpsız(self):
        # lexer parçalarının birleşimi = girdi: stdlib'in TAMAMI (yapısal kayıpsızlık)
        from tokenizer.kod import python_parçala
        dosyalar = sorted(Path(os.__file__).parent.glob("**/*.py"))
        self.assertGreater(len(dosyalar), 500)
        for yol in dosyalar:
            kod = yol.read_text(encoding="utf-8", errors="surrogateescape")
            self.assertEqual("".join(s for _, s in python_parçala(kod)), kod, str(yol))

    def test_anahtar_ve_işlem_bütün(self):
        t = self.py("def f(x) -> None:\n    return x ** 2 if x != 0 else ...")
        for bütün in ["def", "->", "None", "return", "**", "if", "!=", "else", "..."]:
            self.assertIn(bütün, t)
        self.assertIn(BOŞLUK * 4, t)
        # anahtar sözcük yalnız TAM tanımlayıcı olarak sınıflanır ('import_x', 'classes' → ad)
        from tokenizer.kod import python_parçala
        türler = dict((s, t) for t, s in python_parçala("import_x = classes; import y"))
        self.assertEqual((türler["import_x"], türler["classes"], türler["import"]),
                         ("ad", "ad", "anahtar"))
        self.assertNotIn("class", self.py("classes"))

    def test_yorum_ve_string_türkçe(self):
        t = self.py('# kökleri bul\nx = "evlerimizde"')
        self.assertIn("kök", t)
        self.assertIn("ev", t)
        self.assertEqual(t[-1], '"')

    def test_kapanmamış_ve_özel_stringler(self):
        for kod in ['x = "kapanmadı\ny = 1', "s = '''üçlü\nsatır", 'f"{a!r:>10}"',
                    "rb'\\x00' + Rb\"\\\\\"", 'x = "a\\"b"', "'''a'' '", "#", "\"\"\"",
                    "değer = kök_bul(İstanbul)  # Türkçe tanımlayıcı"]:
            ids, geri = self.py_gidip_gel(kod)
            self.assertEqual(geri, kod, repr(kod))

    def test_depo_ve_stdlib_python_kipi(self):
        dosyalar = sorted(KÖK.glob("**/*.py"))
        lib = sorted(Path(os.__file__).parent.glob("*.py"))
        random.Random(11).shuffle(lib)
        for yol in dosyalar + lib[:25]:
            kod = yol.read_text(encoding="utf-8", errors="surrogateescape")
            _, geri = self.py_gidip_gel(kod)
            self.assertEqual(geri, kod, str(yol))

    def test_kod_tokenı_yalnız_kod_kipinde(self):
        # 'from' kodda anahtar sözcük (tek token), Türkçe metinde İngilizce kelime (harf harf)
        kid = self.v.tok2id["from"]
        metin = self.v.encode_ids("Veriler from ve class ile", self.k, self.e, self.i)
        self.assertNotIn(kid, metin)
        self.assertNotIn(self.v.tok2id["class"], metin)
        self.assertEqual(self.v.decode_ids(metin), "Veriler from ve class ile")
        kod = self.v.encode_ids("from x import y", self.k, self.e, self.i, kip="kod", dil="python")
        self.assertIn(kid, kod)
        # v1'deki ortak heceler (if/in/def) metin kipinde eskisi gibi kullanılır
        self.assertIn(self.v.tok2id["if"], self.v.encode_ids("if", self.k, self.e, self.i))

    def test_tanımlayıcı_böl(self):
        from tokenizer.kod import tanımlayıcı_böl
        for ad, beklenen in [("get_item", ["get", "_", "item"]), ("getItem", ["get", "Item"]),
                             ("HTTPServer", ["HTTP", "Server"]), ("__init__", ["__", "init", "__"]),
                             ("utf8_decode", ["utf", "8", "_", "decode"]), ("kökBul", ["kök", "Bul"]),
                             ("MAX_LEN", ["MAX", "_", "LEN"]), ("x", ["x"]), ("_", ["_"]),
                             ("IOError", ["IO", "Error"]),
                             ("HTTPserver", ["HTT", "Pserver"])]:   # standart camel kuralı, kayıpsız
            self.assertEqual(tanımlayıcı_böl(ad), beklenen, ad)
            self.assertEqual("".join(tanımlayıcı_böl(ad)), ad)

    def test_tanımlayıcı_ascii_casing(self):
        # ASCII kuralı: Item → <|Ab|> item ('ıtem' DEĞİL); HEP koşusu sonrası küçük parça kapatılır
        from tokenizer.pipeline import ASCII_BAŞ, ASCII_HEP
        t = self.py("getItem")
        self.assertIn(ASCII_BAŞ, t)
        self.assertNotIn("ı", "".join(t))                   # Türkçe küçültme uygulanmadı
        self.assertIn(ASCII_HEP, self.py("MAX_LEN"))
        for kod in ["getItem", "HTTPServer", "MAX_LEN = 1", "IOError", "ÇokDeğer", "ÇOKdeğer",
                    "xIn", "I", "İ", "ı", "HTTPsDEĞER", "self.__init__()", "Iğdır_İl",
                    "resp.getHeaderValue('X')", "classes = __all__"]:
            ids, geri = self.py_gidip_gel(kod)
            self.assertEqual(geri, kod, kod)
        # ASCII işaretçileri metin kipinde asla üretilmez
        metin = encode("getItem HTTPServer İstanbul", self.k, self.e, self.i)
        self.assertFalse(set(metin) & {ASCII_BAŞ, ASCII_HEP})

    def test_sayı_ve_t_string_sınırları(self):
        # K4 bulgusu: .05 / 1e-6 bölünüyordu; t-string öneki (3.14) tanınmıyordu
        from tokenizer.kod import python_parçala
        for kod, sayılar in [("x = .05 + 1e-6 - 3.14j", [".05", "1e-6", "3.14j"]),
                             ("y = 0xFF_FF | 0b1010 | 1_000.5e+10", ["0xFF_FF", "0b1010", "1_000.5e+10"])]:
            self.assertEqual([s for t, s in python_parçala(kod) if t == "sayı"], sayılar, kod)
        self.assertEqual([t for t, _ in python_parçala('t"{0}"')][:2], ["önek", "tırnak"])

    def test_tokenize_sınır_örneklem(self):
        # stdlib örnekleminde lexer sınırları tokenize ile birebir (tam koşu: araclar.kod_dogrula)
        from araclar.kod_dogrula import sınır_karşılaştır
        lib = sorted(Path(os.__file__).parent.glob("*.py"))
        random.Random(3).shuffle(lib)
        for yol in lib[:40]:
            r = sınır_karşılaştır(yol.read_text(encoding="utf-8", errors="surrogateescape"))
            if r is not None:
                self.assertEqual(r[0], [], str(yol))

    def test_kod_sözlüğü(self):
        # sözlük kelimesi kodda TEK token; metinde eskisi gibi (kod-* tokenı metne sızmaz)
        from tokenizer.kod import KOD_SÖZLÜĞÜ, KOD_SÖZLÜK_YENİ
        self.assertGreater(len(KOD_SÖZLÜĞÜ), 1000)
        for w in KOD_SÖZLÜĞÜ:
            self.assertTrue(w.isascii() and w.isalpha() and w == w.lower(), w)
            self.assertIn(w, self.v.tok2id, w)
        t = self.py("def get_value(self, request): return self.dataFrame")
        for w in ["value", "self", "request", "data", "frame"]:
            self.assertIn(w, t)
        yalnız = {self.v.tok2id[w] for w in KOD_SÖZLÜK_YENİ}
        metin = self.v.encode_ids("Bu value ve request değerleri path üzerinden gelir.",
                                  self.k, self.e, self.i)
        self.assertFalse(yalnız & set(metin))

    def test_tanımlayıcı_rastgele(self):
        # decode değişmezi: rastgele karışık-büyüklüklü tanımlayıcılar birebir geri döner
        rnd = random.Random(5)
        alfabe = "aeiIıİxXqQzZçÇğĞöÖşŞüÜ_09ÅåΩωß"
        for _ in range(1500):
            ad = rnd.choice("aAçÇ_ΩI") + "".join(rnd.choice(alfabe) for _ in range(rnd.randint(0, 12)))
            kod = f"{ad} = {ad}.{ad}()"
            _, geri = self.py_gidip_gel(kod)
            self.assertEqual(geri, kod, repr(kod))

    def test_tanımlayıcı_kuyruğa_girmez(self):
        from tokenizer.onay import OnayKuyruğu
        q = OnayKuyruğu()
        self.py("zyxwqk = 1  # qwzyk", q)
        kelimeler = {x.kelime for x in q.bekleyenler()}
        self.assertIn("qwzyk", kelimeler)                   # yorumdaki bilinmeyen sorulur
        self.assertNotIn("zyxwqk", kelimeler)               # tanımlayıcı sorulmaz


if __name__ == "__main__":
    unittest.main()

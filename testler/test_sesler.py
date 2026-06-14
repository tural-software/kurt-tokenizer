"""sesler modülü — ünlü sistemi testleri."""

import unittest

from tokenizer import sesler


class SeslerTest(unittest.TestCase):
    def test_artlık(self):
        for ü in "aıou":
            self.assertEqual(sesler.artlık(ü), "kalın", ü)
        for ü in "eiöü":
            self.assertEqual(sesler.artlık(ü), "ince", ü)

    def test_yuvarlaklık(self):
        for ü in "aeıi":
            self.assertEqual(sesler.yuvarlaklık(ü), "düz", ü)
        for ü in "ouöü":
            self.assertEqual(sesler.yuvarlaklık(ü), "yuvarlak", ü)

    def test_artlık_geçersiz(self):
        with self.assertRaises(ValueError):
            sesler.artlık("k")

    def test_yuvarlaklık_geçersiz(self):
        with self.assertRaises(ValueError):
            sesler.yuvarlaklık("t")

    def test_ünlü_mü(self):
        self.assertTrue(sesler.ünlü_mü("a"))
        self.assertFalse(sesler.ünlü_mü("k"))

    def test_ünlü_kümesi_tam(self):
        # 8 fonemik ünlü + 3 düzeltme imli (â/î/û) = 11; artlık/yuvarlaklık tam+ayrık böler.
        self.assertEqual(len(sesler.STANDART_ÜNLÜLER), 8)
        self.assertEqual(len(sesler.ÜNLÜLER), 11)
        self.assertTrue(sesler.STANDART_ÜNLÜLER <= sesler.ÜNLÜLER)
        self.assertEqual(sesler.KALIN | sesler.İNCE, sesler.ÜNLÜLER)
        self.assertEqual(sesler.KALIN & sesler.İNCE, frozenset())
        self.assertEqual(sesler.DÜZ | sesler.YUVARLAK, sesler.ÜNLÜLER)
        self.assertEqual(sesler.DÜZ & sesler.YUVARLAK, frozenset())

    def test_son_ünlü_bul(self):
        self.assertEqual(sesler.son_ünlü_bul("araba"), "a")
        self.assertEqual(sesler.son_ünlü_bul("git"), "i")
        self.assertEqual(sesler.son_ünlü_bul("renk"), "e")
        self.assertEqual(sesler.son_ünlü_bul("oku"), "u")
        self.assertIsNone(sesler.son_ünlü_bul("şt"))

    def test_türkçe_küçült(self):
        self.assertEqual(sesler.türkçe_küçült("GİT"), "git")
        self.assertEqual(sesler.türkçe_küçült("IŞIK"), "ışık")
        self.assertEqual(sesler.türkçe_küçült("ARABA"), "araba")


if __name__ == "__main__":
    unittest.main()

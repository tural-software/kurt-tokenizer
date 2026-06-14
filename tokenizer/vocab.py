"""Token vocabulary: token ↔ ID eşlemesi ve ID-düzeyi encode/decode.

Tokenizer'ın asıl çıktısı: bir modelin tüketebileceği SABİT vocab + ID dizisi. Bu modül
motorun ürettiği token kümesini DETERMİNİSTİK toplayıp dondurur (BPE gibi corpus'tan
öğrenmez — kurallarımızdan türer):

  1. ÖZEL tokenlar      <pad>/<unk>/<s>/</s>/<|...|>/<|Bb|>/<|BB|>/▁   (sabit ID önek)
  2. ATOMİK taban       tüm harf (iki büyüklük) + â/î/û + rakam + noktalama  (fallback zemini)
  3. HECE/MORFEM        46k kökün tüm heceleri + ek yüzeyleri + tamponlar + istisna tokenları

Bilinmeyen kelime (sabit vocab'da bütün-token OLAMAZ): HECE→HARF fallback ile atomik
tabana iner (kayıpsız); "bütün tut" felsefesi onay kuyruğunda korunur (kelime yine
insana sorulur). Truly-novel karakter (emoji vb.) → <unk> (Aşama 0 sınırı, byte-fallback
sonraki bir madde).
"""

from __future__ import annotations

import json
from pathlib import Path

from tokenizer import sesler
from tokenizer.alfabe import ALFABE, alfabetik_anahtar
from tokenizer.hece import hecele
from tokenizer.birlestir import birleştir
from tokenizer.pipeline import encode, decode, BOŞLUK, BAŞ_BÜYÜK, HEP_BÜYÜK, ÖZEL

# Sabit önek: özel tokenlar (ID 0..) — sıra KALICI olmalı (model bağımlılığı).
ÖZEL_TOKENLAR = ["<pad>", "<unk>", "<s>", "</s>", "<|sistem|>", "<|kullanici|>",
                 "<|asistan|>", "<|bitis|>", BAŞ_BÜYÜK, HEP_BÜYÜK, BOŞLUK]

NOKTALAMA = list(".,;:!?'\"`()[]{}<>-–—/\\|@#$%&*+=~^_°²³…’‘“”«»·•")
RAKAM = list("0123456789")


def _atomik_taban() -> list[str]:
    """Her dizinin temsil edilebilmesi için zemin: harf (iki büyüklük) + rakam + noktalama."""
    küçük = set(ALFABE) | set("âîû")
    büyük = {sesler.türkçe_büyült(c) for c in küçük}
    return sorted(küçük | büyük | set(RAKAM) | set(NOKTALAMA))


def _ek_yüzeyleri(kökler, ekler) -> set[str]:
    """Ek yüzey + tampon tokenlarını, çeşitli kökler üzerinde çekim üreterek toplar.

    Her ekin yüzeyi gövdenin son ünlüsüne/sesine bağlı → tüm son_ünlü sınıflarını +
    ünsüz/ünlü/l/r-sonu + yumuşama/düşen/ince köklerini kapsayan bir prob kümesi seçilir.
    """
    # Çeşitli prob kökleri: her son_ünlü + özel sınıflar, isim ve fiil ayrı.
    isim_prob, fiil_prob = {}, {}
    for ad, k in kökler.items():
        hedef = isim_prob if k.tür != "fiil" else fiil_prob
        anahtar = (k.son_ünlü, ad[-1] in sesler.ÜNLÜLER, ad[-1] in "lr",
                   bool(k.değişim), getattr(k, "düşen", False), getattr(k, "ince", False))
        hedef.setdefault(anahtar, ad)
    isimler, fiiller = list(isim_prob.values()), list(fiil_prob.values())

    isim_zinc = [[e] for e, x in ekler.items() if x.öbek == "isim"]
    isim_zinc += [["çoğul", "iyelik_1tekil"], ["iyelik_3tekil", "bulunma"],
                  ["iyelik_3tekil", "araç"], ["iyelik_2tekil", "bulunma", "aitlik"]]
    fiil_zinc = [[e] for e, x in ekler.items() if x.öbek == "fiil"]
    fiil_zinc += [["şimdiki_zaman", "şahıs_1tekil_t1"], ["görülen_geçmiş", "şahıs_1tekil_t2"],
                  ["gelecek_zaman", "şahıs_1çoğul_t1"], ["olumsuz", "geniş_zaman"],
                  ["edilgen", "görülen_geçmiş"], ["ettirgen", "edilgen", "görülen_geçmiş"],
                  ["ortaç_dik", "iyelik_3tekil"], ["şimdiki_zaman", "ek_fiil_idi"]]
    her_zinc = [["ek_fiil_idi"], ["ek_fiil_imiş"], ["koşaç_1tekil_t1"]]

    tokens: set[str] = set()
    for kökler_l, zincirler in ((isimler, isim_zinc), (fiiller, fiil_zinc),
                                (isimler + fiiller, her_zinc)):
        for ad in kökler_l:
            kök = kökler[ad]
            for zinc in zincirler:
                try:
                    tk, _ = birleştir(ad, kök, zinc, ekler)
                    tokens.update(tk)
                except Exception:
                    pass

    # Yumuşama/düşme TÜM köklerde kök-son heceyi değiştirir (kitap→tab, böcek→böceğ,
    # affet→fed, akıl→akl). Bu yüzden değişim/düşen köklerin ünlü-başlı çekimini üret.
    for ad, kök in kökler.items():
        if not (kök.değişim or getattr(kök, "düşen", False)):
            continue
        z = ([["şimdiki_zaman"], ["gelecek_zaman", "şahıs_1tekil_t1"]]
             if kök.tür == "fiil" else [["belirtme"], ["iyelik_3tekil"]])
        for zinc in z:
            try:
                tk, _ = birleştir(ad, kök, zinc, ekler)
                tokens.update(tk)
            except Exception:
                pass
    return tokens


def vocab_kur(kökler, ekler, istisnalar) -> list[str]:
    """Deterministik vocab: özel + atomik taban + hece/morfem/ek/istisna tokenları."""
    morfem: set[str] = set()
    for kök in kökler.values():                 # kök heceleri
        morfem.update(kök.tokens)
    for ist in istisnalar.values():             # istisna bütün-tokenları
        morfem.update(ist.tokens)
    morfem |= _ek_yüzeyleri(kökler, ekler)      # ek yüzeyleri + tamponlar

    atom = _atomik_taban()
    morfem -= set(ÖZEL_TOKENLAR) | set(atom)    # önce-gelenleri çıkar (tekrar yok)
    # Sıra: önce hece sayısı/uzunluk, sonra Türkçe alfabetik, son TAM kırıcı ham token
    # (â/î/û temel ünlüye eşlendiğinden 'di'/'dî' aynı anahtara düşer → kararlılık için ham).
    _harfli = set(ALFABE) | set("âîû")
    sıralı_morfem = sorted(morfem, key=lambda t: (
        len(t), alfabetik_anahtar("".join(c for c in t if c in _harfli) or "a"), t))
    return ÖZEL_TOKENLAR + atom + sıralı_morfem


class Vocab:
    """Token ↔ ID; ID-düzeyi encode/decode (mevcut pipeline'ı sarar)."""

    def __init__(self, id2tok: list[str]):
        self.id2tok = id2tok
        self.tok2id = {t: i for i, t in enumerate(id2tok)}
        self._unk = self.tok2id["<unk>"]

    def __len__(self):
        return len(self.id2tok)

    def _fallback(self, kelime: str) -> list[int]:
        """Bilinmeyen bütün-token → hece, vocab'da yoksa harf, o da yoksa <unk>."""
        ids: list[int] = []
        for hece in hecele(kelime):
            if hece in self.tok2id:
                ids.append(self.tok2id[hece])
            else:
                ids.extend(self.tok2id.get(ch, self._unk) for ch in hece)
        return ids

    def encode_ids(self, metin, kökler, ekler, istisnalar=None, kuyruk=None,
                   önbellek=None) -> list[int]:
        """Metin → ID dizisi. Bilinen token doğrudan; bilinmeyen bütün-token fallback'lenir.
        önbellek: büyük korpus için kelime-memoization (encode'a iletilir)."""
        ids: list[int] = []
        for t in encode(metin, kökler, ekler, istisnalar, kuyruk, önbellek):
            tid = self.tok2id.get(t)
            ids.append(tid) if tid is not None else ids.extend(self._fallback(t))
        return ids

    def decode_ids(self, ids) -> str:
        """ID dizisi → metin (casing/▁/özel tokenlar pipeline.decode ile çözülür)."""
        return decode([self.id2tok[i] for i in ids])

    def kaydet(self, yol: str | Path) -> None:
        Path(yol).write_text(json.dumps({"id2tok": self.id2tok}, ensure_ascii=False),
                             encoding="utf-8")

    @classmethod
    def yükle(cls, yol: str | Path) -> "Vocab":
        ham = json.loads(Path(yol).read_text(encoding="utf-8"))
        return cls(ham["id2tok"])

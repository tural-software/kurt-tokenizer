"""Kod kipi dil lexer'ları (K2). Şimdilik Python.

Kendi lexer'ımız (stdlib tokenize DEĞİL): tokenize hatalı/yarım kodda (sohbetteki kod parçası)
hata verir; tokenizer hiçbir girdide çökmemeli. Doğruluk K4'te tokenize ile karşılaştırılır.

KAYIPSIZLIK YAPISAL: python_parçala() girdiyi ardışık, örtüşmesiz (tür, metin) parçalarına böler;
parçaların birleşimi HER ZAMAN girdinin kendisidir (kapanmamış string, tanınmayan karakter dahil).

Türler:
  boşluk    boşluk koşusu (satır sonu/girinti)
  metin     yorum (# dahil) ve string İÇERİĞİ → Türkçe metin hattı
  tırnak    string sınırı: ' " ''' \"\"\"
  önek      string öneki: r b u f t rb br fr rf tr rt (büyük/küçük)
  anahtar   anahtar sözcük (PY_ANAHTAR)
  işlem     operatör/noktalama (çok karakterli PY_İŞLEM en uzun eşleşme; yoksa tek karakter)
  ad        tanımlayıcı (Unicode dahil: değer, kök_bul)
  sayı      sayı sabiti (1_000, 0x1F, 3.14, 1e5)
"""

from __future__ import annotations

import json
import re
from pathlib import Path

# 35 anahtar sözcük (keyword.kwlist) + sık yumuşak anahtar sözcükler (match/case/type; '_' hariç).
PY_ANAHTAR = ("False", "None", "True", "and", "as", "assert", "async", "await", "break",
              "class", "continue", "def", "del", "elif", "else", "except", "finally", "for",
              "from", "global", "if", "import", "in", "is", "lambda", "nonlocal", "not", "or",
              "pass", "raise", "return", "try", "while", "with", "yield",
              "match", "case", "type")
_ANAHTAR = frozenset(PY_ANAHTAR)

# Çok karakterli operatörler — en uzundan kısaya denenir (en uzun eşleşme: **= önce, ** sonra).
PY_İŞLEM = ("**=", "//=", ">>=", "<<=", "...",
            "->", ":=", "==", "!=", "<=", ">=", "**", "//", "<<", ">>",
            "+=", "-=", "*=", "/=", "%=", "&=", "|=", "^=", "@=")
PY_TIRNAK = ('"""', "'''")                      # tek tırnaklar (' ") atomik tabanda

_BOŞLUK = re.compile(r"\s+")
# Önekler: bytes/raw/unicode/f-string + Python 3.14 t-string (şablon: t, tr, rt).
_DİZE_BAŞI = re.compile(r"""(?i)(rb|br|fr|rf|tr|rt|b|r|u|f|t)?('''|\"\"\"|'|")""")
_AD = re.compile(r"[^\W\d]\w*")
# Python sayı dilbilgisi (K4: tokenize ile karşılaştırmada .05 ve 1e-6 bölünüyordu): hex/oct/bin,
# ondalık (baştaki nokta dahil: .5), üs (işaretli: 1e-6), sanal (3j), alt çizgi (1_000).
_SAYI = re.compile(r"0[xX][\da-fA-F_]+|0[oO][0-7_]+|0[bB][01_]+"
                   r"|(?:\d[\d_]*(?:\.[\d_]*)?|\.\d[\d_]*)(?:[eE][+-]?\d[\d_]*)?[jJ]?")
_İŞLEM_UZUNLUK = sorted({len(o) for o in PY_İŞLEM}, reverse=True)
_İŞLEM = frozenset(PY_İŞLEM)


def _dize_sonu(kod: str, i: int, tırnak: str) -> int:
    """String içeriğinin bittiği indeks (kapanış tırnağının başı) ya da kapanmamışsa sınır:
    tek satırlıkta satır sonu, üçlüde metin sonu. Ters bölü sonraki karakteri kaçırır."""
    üçlü = len(tırnak) == 3
    n = len(kod)
    while i < n:
        c = kod[i]
        if c == "\\":
            i += 2
            continue
        if kod.startswith(tırnak, i):
            return i
        if c == "\n" and not üçlü:
            return i
        i += 1
    return n


def python_parçala(kod: str):
    """Python kaynağını (tür, metin) parçalarına böler; birleşim == kod (kayıpsız)."""
    i, n = 0, len(kod)
    while i < n:
        c = kod[i]
        m = _BOŞLUK.match(kod, i)
        if m:
            yield "boşluk", m.group()
            i = m.end()
            continue
        if c == "#":                              # yorum: satır sonuna kadar (dahil değil)
            j = kod.find("\n", i)
            j = n if j < 0 else j
            yield "metin", kod[i:j]
            i = j
            continue
        m = _DİZE_BAŞI.match(kod, i)
        if m:
            önek, tırnak = m.group(1), m.group(2)
            if önek:
                yield "önek", önek
            yield "tırnak", tırnak
            baş = m.end()
            son = min(_dize_sonu(kod, baş, tırnak), n)
            if son > baş:
                yield "metin", kod[baş:son]
            i = son
            if kod.startswith(tırnak, i):
                yield "tırnak", tırnak
                i += len(tırnak)
            continue
        m = _AD.match(kod, i)
        if m:
            s = m.group()
            yield ("anahtar" if s in _ANAHTAR else "ad"), s
            i = m.end()
            continue
        m = _SAYI.match(kod, i)
        if m:
            yield "sayı", m.group()
            i = m.end()
            continue
        for u in _İŞLEM_UZUNLUK:
            if kod[i:i + u] in _İŞLEM:
                yield "işlem", kod[i:i + u]
                i += u
                break
        else:
            yield "işlem", c
            i += 1


DİLLER = {"python": python_parçala}

# Kod sözlüğü (K3b): tanımlayıcı parçası olarak TEK token olan küçük harfli İngilizce kelime ve
# yerleşik kısaltmalar (veri/kod_sozlugu.json: stdlib taraması + elle alan listeleri; kullanıcı
# onaylı). 'yeni' alanı vocab'ın kod-sozluk bölümüdür; geri kalanlar v1 tokenını paylaşır.
KOD_SÖZLÜK_DOSYASI = Path(__file__).resolve().parent.parent / "veri" / "kod_sozlugu.json"
_SÖZLÜK = json.loads(KOD_SÖZLÜK_DOSYASI.read_text(encoding="utf-8"))
KOD_SÖZLÜĞÜ: frozenset[str] = frozenset(w for g in _SÖZLÜK["gruplar"].values() for w in g)
KOD_SÖZLÜK_YENİ: list[str] = list(_SÖZLÜK["yeni"])


def _büyük(c: str) -> bool:
    return c.isupper() or c.istitle()


def tanımlayıcı_böl(ad: str) -> list[str]:
    """Tanımlayıcıyı parçalar (K3); birleşim == ad. '_' koşuları, rakam koşuları ve harf
    koşularının camelCase parçaları ayrı:
      get_item → get _ item      getItem → get Item      HTTPServer → HTTP Server
      __init__ → __ init __      utf8_decode → utf 8 _ decode      kökBul → kök Bul
    camelCase sınırı: küçük→Büyük (getItem) ve BÜYÜK→Büyük+küçük (HTTPServer: P|S)."""
    parçalar: list[str] = []
    i, n = 0, len(ad)
    while i < n:
        c = ad[i]
        j = i + 1
        if c == "_":
            while j < n and ad[j] == "_":
                j += 1
        elif c.isdigit():
            while j < n and ad[j].isdigit():
                j += 1
        else:
            while j < n and ad[j] != "_" and not ad[j].isdigit():
                ö, s = ad[j - 1], ad[j]
                if _büyük(s) and not _büyük(ö):                      # getItem: t|I
                    break
                if (_büyük(ö) and _büyük(s) and j + 1 < n and ad[j + 1].islower()):
                    break                                            # HTTPServer: P|S
                j += 1
        parçalar.append(ad[i:j])
        i = j
    return parçalar

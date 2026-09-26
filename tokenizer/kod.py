"""Kod kipi dil lexer'ları (K2). Şimdilik Python.

Kendi lexer'ımız (stdlib tokenize DEĞİL): tokenize hatalı/yarım kodda (sohbetteki kod parçası)
hata verir; tokenizer hiçbir girdide çökmemeli. Doğruluk K4'te tokenize ile karşılaştırılır.

KAYIPSIZLIK YAPISAL: python_parçala() girdiyi ardışık, örtüşmesiz (tür, metin) parçalarına böler;
parçaların birleşimi HER ZAMAN girdinin kendisidir (kapanmamış string, tanınmayan karakter dahil).

Türler:
  boşluk    boşluk koşusu (satır sonu/girinti)
  metin     yorum (# dahil) ve string İÇERİĞİ → Türkçe metin hattı
  tırnak    string sınırı: ' " ''' \"\"\"
  önek      string öneki: r b u f rb br fr rf (büyük/küçük)
  anahtar   anahtar sözcük (PY_ANAHTAR)
  işlem     operatör/noktalama (çok karakterli PY_İŞLEM en uzun eşleşme; yoksa tek karakter)
  ad        tanımlayıcı (Unicode dahil: değer, kök_bul)
  sayı      sayı sabiti (1_000, 0x1F, 3.14, 1e5)
"""

from __future__ import annotations

import re

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
_DİZE_BAŞI = re.compile(r"""(?i)(rb|br|fr|rf|b|r|u|f)?('''|\"\"\"|'|")""")
_AD = re.compile(r"[^\W\d]\w*")
_SAYI = re.compile(r"\d\w*(?:\.\d*\w*)?")
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

"""v2 kodlaması (büyük modeller için): v1 token dizisi üzerinde DETERMİNİSTİK kaynaşma ve demetleme.

v1 dizisinde bir sözcük BİRİMİ: varsa ▁ (boşluk), varsa Başlık işaretçisi (<|Bb|> / <|Ab|>), ardından harf tokenları
(morfem/hece); ya da ▁ + harf olmayan tek token (▁( ▁1 ▁l’ — yalnız düz eşi vocab'daysa birleşir). v2 her birimi soldan sağa EN UZUN eşleşmeyle böler: birimin ardışık tokenlarının birleşimi vocab'da
(v2 bölümleri ya da var olan token) varsa tek token olur. Yalnız var olan token sınırları kalkar → yeni sınır,
dolayısıyla yanlış bölme yapısal olarak imkânsız; çözüm aynı, kodlama kabalaşır.

İki tür v2 tokenı:
  düz (yüzey)  ▁ ya da Başlık işaretçisiyle başlayan dizi: ▁ <|Bb|> haus → "▁Haus", ▁ gel i yor um → "▁geliyorum".
               decode harfiyen yazar (▁ → boşluk) — Başlık kuralı yüzeyde uygulanmış olarak saklanır.
  demet        yalnız harf tokenları: ler in → "lerin". decode sıradan token gibi (casing koşusu uygulanır;
               HEP BÜYÜK sözcükte de doğru büyür).
→ decode(v2) == decode(v1). HEP BÜYÜK işaretçisi (<|BB|>) birime girmez (koşu boyunca sürer); kod kipi değişmez.
"""

from __future__ import annotations

from tokenizer import sesler
from tokenizer.pipeline import BOŞLUK, BAŞ_BÜYÜK, ASCII_BAŞ, BOŞLUK_İŞARET, _harf_mi

SÜRÜMLER = ("v1", "v2")
_BAŞLIK = (BAŞ_BÜYÜK, ASCII_BAŞ)
EN_UZUN = 16                     # birimde en uzun demet (token)


def yüzey(boşluk: bool, işaret: str | None, t: str) -> str:
    """Önekli dizinin decode'daki metni (▁ boşluğu temsil eder). Başlık kuralı decode'unkiyle aynı."""
    if işaret == BAŞ_BÜYÜK:
        t = sesler.türkçe_başlık(t)
    elif işaret == ASCII_BAŞ:
        t = t[:1].upper() + t[1:]
    return BOŞLUK + t if boşluk else t


def _özel(t: str) -> bool:
    """Özel/işaretçi/bayt tokenı (<…>): düz v2 tokenına giremez."""
    return len(t) > 2 and t[0] == "<" and t[-1] == ">"


def harf_tokenı(t: str) -> bool:
    """Birime girebilen token: tümü harf (noktalama decode'da casing koşusunu bitirir; özel/boşluk/satır değil)."""
    return bool(t) and all(_harf_mi(c) for c in t)


def dizi(birim, i: int, j: int) -> tuple[str, bool] | None:
    """birim[i:j]'nin v2 tokenı ve düz mü; yalnız önek (▁/işaretçi) kalıyorsa None."""
    b = birim[i] == BOŞLUK
    k = i + b
    m = birim[k] if k < j and birim[k] in _BAŞLIK else None
    k += m is not None
    if k >= j:
        return None
    return yüzey(b, m, "".join(birim[k:j])), bool(b or m)


def birimler(tokenlar, izinli):
    """Dizi → (birim mi, tokenlar) parçaları. izinli(t): t bu kipte/dilde vocab'da açık bir harf tokenı mı."""
    k: list[str] = []
    for t in tokenlar:
        if izinli(t):
            k.append(t)
            continue
        if t in _BAŞLIK and k == [BOŞLUK]:
            k.append(t)
            continue
        if k == [BOŞLUK] and t != BOŞLUK and not _özel(t):
            # ▁ + harf olmayan tek token (noktalama, rakam, elizyon l’): böl ▁( ▁1 ▁l’ düz eşini dener (V2-6). Özel token
            # (HEP BÜYÜK işaretçisi <|BB|> <|AA|>, bayt <0xE2>, <s>) giremez: harfiyen decode'da metne sızardı
            yield True, [BOŞLUK, t]
            k = []
            continue
        if k:
            yield harf_tokenı(k[-1]) and len(k) > 1, k
        k = [t] if t == BOŞLUK or t in _BAŞLIK else []
        if not k:
            yield False, [t]
    if k:
        yield harf_tokenı(k[-1]) and len(k) > 1, k


def böl(birim, var) -> list[str]:
    """Birimi soldan sağa en uzun eşleşmeyle böler. var(token, düz) → bu token kullanılabilir mi."""
    çıktı, i, n = [], 0, len(birim)
    while i < n:
        j = i + 1
        for jj in range(min(n, i + EN_UZUN), i + 1, -1):
            d = dizi(birim, i, jj)
            if d and var(*d):
                çıktı.append(d[0])
                j = jj
                break
        else:
            çıktı.append(birim[i])
        i = j
    return çıktı


def kaynaştır(tokenlar: list[str], izinli, var, işaret=frozenset()) -> list[str]:
    """v1 token dizisi → v2 dizisi (birimler en uzun eşleşmeyle demetlenir). işaret: vocab'daki ▁+işaretçi tokenları
    (V2-7) — demetlemeden sonra kalan ▁ + casing işaretçisi çifti tek token olur (▁<|Bb|> ▁<|AA|>)."""
    çıktı: list[str] = []
    for birim_mi, k in birimler(tokenlar, izinli):
        for t in (böl(k, var) if birim_mi else k):
            if çıktı and çıktı[-1] == BOŞLUK and BOŞLUK + t in işaret:
                çıktı[-1] = BOŞLUK + t
            else:
                çıktı.append(t)
    return çıktı

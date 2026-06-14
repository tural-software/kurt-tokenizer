"""Türkçe ünlü sistemi — tokenizer'ın tek ses (fonoloji) kaynağı.

Kök kaydı yalnızca `son_ünlü`yü saklar. Artlık (kalın/ince) ve yuvarlaklık
(düz/yuvarlak) buradan *türetilir*, ayrıca saklanmaz. Bkz. .claude/CLAUDE.md
"son_ünlü neden tek kaynak" bölümü.

    son_ünlü   artlık   yuvarlaklık
    a          kalın    düz
    ı          kalın    düz
    o, u       kalın    yuvarlak
    e, i       ince     düz
    ö, ü       ince     yuvarlak
"""

from __future__ import annotations

# Sekiz Türkçe ünlü + düzeltme imli ünlüler (â/î/û): uyumda temel karşılıkları gibi
# davranır (â≈a kalın-düz, î≈i ince-düz, û≈u kalın-yuvarlak). â çoğu alıntıda art uyumlu
# (kâr→kârı); ince-uyumlu â'lar (hâl→hâli) kök kaydındaki 'ince' bayrağıyla işaretlenir.
STANDART_ÜNLÜLER: frozenset[str] = frozenset("aeıioöuü")   # 8 fonemik ünlü (kapsam ölçütü)
ÜNLÜLER: frozenset[str] = frozenset("aeıioöuüâîû")

# Artlık (backness)
KALIN: frozenset[str] = frozenset("aıouâû")   # art ünlüler (â, û dahil)
İNCE: frozenset[str] = frozenset("eiöüî")     # ön ünlüler (î dahil)

# Yuvarlaklık (roundedness)
DÜZ: frozenset[str] = frozenset("aeıiâî")        # düz ünlüler (â, î dahil)
YUVARLAK: frozenset[str] = frozenset("ouöüû")    # yuvarlak ünlüler (û dahil)


def ünlü_mü(harf: str) -> bool:
    """Tek bir harfin Türkçe ünlü olup olmadığını döndürür."""
    return harf in ÜNLÜLER


def artlık(ünlü: str) -> str:
    """Ünlünün artlığını döndürür: 'kalın' | 'ince'."""
    if ünlü in KALIN:
        return "kalın"
    if ünlü in İNCE:
        return "ince"
    raise ValueError(f"Ünlü değil: {ünlü!r}")


def yuvarlaklık(ünlü: str) -> str:
    """Ünlünün yuvarlaklığını döndürür: 'düz' | 'yuvarlak'."""
    if ünlü in DÜZ:
        return "düz"
    if ünlü in YUVARLAK:
        return "yuvarlak"
    raise ValueError(f"Ünlü değil: {ünlü!r}")


def son_ünlü_bul(kelime: str) -> str | None:
    """Kelimedeki son ünlüyü döndürür; hiç ünlü yoksa None."""
    for harf in reversed(kelime):
        if harf in ÜNLÜLER:
            return harf
    return None


def türkçe_küçült(s: str) -> str:
    """Türkçe-duyarlı küçük harfe çevirme.

    Standart str.lower() 'I' → 'i' ve 'İ' → 'i̇' (birleşik nokta) verdiği için
    Türkçe'de yanlıştır. Önce 'I'→'ı' ve 'İ'→'i' eşlenir, sonra lower() çağrılır.
    """
    return s.replace("I", "ı").replace("İ", "i").lower()


def türkçe_büyült(s: str) -> str:
    """Türkçe-duyarlı büyük harfe çevirme (küçültmenin tersi).

    Standart str.upper() 'i' → 'I' verdiği için Türkçe'de yanlıştır (i→İ olmalı).
    Önce 'i'→'İ' ve 'ı'→'I' eşlenir, sonra upper() çağrılır.
    """
    return s.replace("i", "İ").replace("ı", "I").upper()


def türkçe_başlık(s: str) -> str:
    """İlk harfi Türkçe-duyarlı büyük, gerisi olduğu gibi (Title-case ilk harf)."""
    return türkçe_büyült(s[:1]) + s[1:] if s else s

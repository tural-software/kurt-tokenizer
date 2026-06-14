"""Türkçe alfabe ve sıralama.

Python'un varsayılan sıralaması Unicode kod-noktasına dayanır ve Türkçe için
yanlıştır (ör. 'ç' (U+00E7) > 'z'; 'ı'/'i' sırası bozuk). Bu modül 29 harflik
Türkçe alfabe sırasını tek kaynak olarak tutar.
"""

from __future__ import annotations

# 29 harflik Türkçe alfabe (küçük harf)
ALFABE: str = "abcçdefgğhıijklmnoöprsştuüvyz"

_SIRA: dict[str, int] = {harf: i for i, harf in enumerate(ALFABE)}
# Düzeltme imli ünlüler ayrı harf değildir; sıralamada temel ünlülerinin yanında durur.
_SIRA.update({"â": _SIRA["a"], "î": _SIRA["i"], "û": _SIRA["u"]})


def alfabetik_anahtar(s: str) -> list[int]:
    """Türkçe alfabe sırasına göre sıralama anahtarı döndürür.

    sorted(kelimeler, key=alfabetik_anahtar) Türkçe doğru sırayı verir.
    """
    try:
        return [_SIRA[harf] for harf in s]
    except KeyError as e:
        raise ValueError(f"Alfabede olmayan harf: {e.args[0]!r} ({s!r})")

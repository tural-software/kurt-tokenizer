"""v2 kodlaması (büyük modeller için): v1 token dizisi üzerinde DETERMİNİSTİK kaynaşma.

v1 dizisinde sözcük başı üç tokendır: ▁ (boşluk), varsa Başlık işaretçisi (<|Bb|> / <|Ab|>), ilk token.
v2 bu üçlüyü, yüzeyi vocab'ın v2 bölümünde varsa TEK tokena kaynaştırır: ▁ <|Bb|> haus → "▁Haus",
▁ gel → "▁gel", <|Bb|> gel → "Gel". Kaynaşık token YÜZEY metnidir: decode onu harfiyen yazar (▁ → boşluk)
→ decode(v2) == decode(v1) yapısal olarak; morfem sınırı değişmez (kaynaşan yalnız boşluk ve harf
büyüklüğü). HEP BÜYÜK (<|BB|>) kaynaşmaz: o işaretçi koşu boyunca sürer.

Seçim sırası: önce tam üçlü (▁Haus), yoksa ▁ ayrı + Başlık kaynaşması (Haus), yoksa ▁ + ilk token (▁haus
yalnız işaretçisiz sözcükte; işaretçi araya girdiğinden ▁ ile ilk token bitişik değildir).
"""

from __future__ import annotations

from tokenizer import sesler
from tokenizer.pipeline import BOŞLUK, BAŞ_BÜYÜK, ASCII_BAŞ, _harf_mi

SÜRÜMLER = ("v1", "v2")
_BAŞLIK = (BAŞ_BÜYÜK, ASCII_BAŞ)


def yüzey(boşluk: bool, işaret: str | None, t: str) -> str:
    """Üçlünün decode'daki metni (▁ boşluğu temsil eder). Başlık kuralı decode'unkiyle aynı."""
    if işaret == BAŞ_BÜYÜK:
        t = sesler.türkçe_başlık(t)
    elif işaret == ASCII_BAŞ:
        t = t[:1].upper() + t[1:]
    return BOŞLUK + t if boşluk else t


def kaynaşabilir(t: str, işaret: str | None) -> bool:
    """İlk token kaynaşabilir mi: özel/satır/boşluk tokenı değil; Başlık işaretçisiyle yalnız tümü harf
    (noktalama decode'da casing koşusunu bitirir, kaynaşık yüzeyde bu ayrım kaybolurdu)."""
    if not t or t.startswith("<") or t == "\n" or t[0] == BOŞLUK:
        return False
    return işaret is None or all(_harf_mi(c) for c in t)


def üçlüler(tokenlar):
    """(başlangıç, bitiş, boşluk, işaret, ilk_token) — kaynaşma adayı her sözcük başı (sayım için)."""
    i, n = 0, len(tokenlar)
    while i < n:
        b = tokenlar[i] == BOŞLUK
        j = i + b
        m = tokenlar[j] if j < n and tokenlar[j] in _BAŞLIK else None
        j += m is not None
        if (b or m) and j < n and kaynaşabilir(tokenlar[j], m):
            yield i, j + 1, b, m, tokenlar[j]
            i = j + 1
        else:
            i += 1


def kaynaştır(tokenlar: list[str], var) -> list[str]:
    """v1 token dizisi → v2 dizisi. var(yüzey, ilk_token) → bu kipte/dilde kaynaşık token kullanılabilir mi."""
    çıktı: list[str] = []
    k = 0
    for i, j, b, m, t in üçlüler(tokenlar):
        çıktı.extend(tokenlar[k:i])
        if var(y := yüzey(b, m, t), t):
            çıktı.append(y)
        elif b and m and var(y := yüzey(False, m, t), t):
            çıktı += [BOŞLUK, y]
        else:
            çıktı.extend(tokenlar[i:j])
        k = j
    çıktı.extend(tokenlar[k:])
    return çıktı

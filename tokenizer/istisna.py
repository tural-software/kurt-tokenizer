"""İstisna listesi: kök sistemine girmeyen özel sözcükler (su, ne, bu, ve, ile…)
ve bütün tutulan yabancı sözcükler (internet, smartphone).

Tokenizasyon akışında ilk basamak: kelime istisna listesindeyse doğrudan onun
tokenları kullanılır (bkz. CLAUDE.md "Tokenizasyon Akışı").
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from tokenizer import sesler


@dataclass(frozen=True)
class İstisna:
    tokens: list[str]
    notu: str
    grup: str   # "istisnalar" | "yabancı"


class İstisnaHatası(Exception):
    def __init__(self, hatalar: list[str]):
        self.hatalar = hatalar
        super().__init__(
            f"İstisna listesinde {len(hatalar)} hata:\n  " + "\n  ".join(hatalar)
        )


def yükle(yol: str | Path) -> dict[str, İstisna]:
    """İstisna listesini JSON'dan yükler, doğrular ve {kelime: İstisna} döndürür."""
    ham = json.loads(Path(yol).read_text(encoding="utf-8"))
    sözlük: dict[str, İstisna] = {}
    hatalar: list[str] = []
    for grup, girdiler in ham.items():
        for kelime, g in girdiler.items():
            tokens = g.get("tokens")
            if not tokens or not all(isinstance(t, str) and t for t in tokens):
                hatalar.append(f"{kelime!r}: tokens boş olmayan metin listesi olmalı")
            elif "".join(tokens) != kelime:
                hatalar.append(
                    f"{kelime!r}: tokens birleşimi {''.join(tokens)!r} kelimeye eşit değil"
                )
            else:
                sözlük[kelime] = İstisna(tokens=tokens, notu=g.get("not", ""), grup=grup)
    if hatalar:
        raise İstisnaHatası(hatalar)
    return sözlük


def istisna_bul(sözlük: dict[str, İstisna], kelime: str) -> İstisna | None:
    """Kelimeyi istisna listesinde arar (Türkçe-duyarlı küçültme). Yoksa None."""
    return sözlük.get(sesler.türkçe_küçült(kelime))

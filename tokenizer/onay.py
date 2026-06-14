"""Onay kuyruğu: çözümlenemeyen (bilinmeyen) kelimeler buraya alınır; karar bize aittir.

CLAUDE.md "Bilinmeyen Kelime — bize sorulur": kelime BÜTÜN tutulur, kuyruğa
{kelime, bağlam, durum: onay_bekliyor} eklenir, biz karar veririz, bir daha sorulmaz.

Sözlüklerin aksine bu DEĞİŞTİRİLEBİLİR bir durumdur; JSON'a kalıcılaştırılır.
Aynı kelime (Türkçe-duyarlı) ikinci kez sorulmaz — tekilleştirme garanti.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from tokenizer import sesler

BEKLİYOR = "onay_bekliyor"
ONAYLANDI = "onaylandı"
REDDEDİLDİ = "reddedildi"


@dataclass
class OnayGirdisi:
    kelime: str
    bağlam: str = ""
    durum: str = BEKLİYOR


class OnayKuyruğu:
    def __init__(self, girdiler=None):
        self.girdiler: list[OnayGirdisi] = list(girdiler or [])
        self._görülen = {sesler.türkçe_küçült(g.kelime) for g in self.girdiler}

    def ekle(self, kelime: str, bağlam: str = "") -> bool:
        """Bilinmeyen kelimeyi kuyruğa ekler. Zaten varsa (bir daha sorulmaz) False."""
        küç = sesler.türkçe_küçült(kelime)
        if küç in self._görülen:
            return False
        self.girdiler.append(OnayGirdisi(kelime=kelime, bağlam=bağlam, durum=BEKLİYOR))
        self._görülen.add(küç)
        return True

    def bekleyenler(self) -> list[OnayGirdisi]:
        return [g for g in self.girdiler if g.durum == BEKLİYOR]

    def __len__(self) -> int:
        return len(self.girdiler)

    @classmethod
    def yükle(cls, yol) -> "OnayKuyruğu":
        yol = Path(yol)
        if not yol.exists():
            return cls()
        ham = json.loads(yol.read_text(encoding="utf-8"))
        return cls(OnayGirdisi(**g) for g in ham)

    def kaydet(self, yol) -> None:
        Path(yol).write_text(
            json.dumps([asdict(g) for g in self.girdiler], ensure_ascii=False, indent=2)
            + "\n",
            encoding="utf-8",
        )

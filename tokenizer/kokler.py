"""Kök sözlüğünü JSON'dan yükler, doğrular ve sorgular.

İki yükleme yolu:
  - yükle(dosya)        tek JSON dosyası
  - yükle_dizin(dizin)  veri/kokler/<harf>.json dosyalarını birleştirir (çalışma
                        zamanı API'si); dosyalar arası yinelenen kökleri yakalar
"""

from __future__ import annotations

import json
from pathlib import Path

from tokenizer import sesler
from tokenizer.sema import Kök, doğrula

_ALANLAR = {"tokens", "tür", "son_ünlü", "son_ses", "değişim", "ek_tür", "düşen", "ince",
            "sadece_koşaç", "daralan", "ek_değişim"}


class ŞemaHatası(Exception):
    """Kök sözlüğünde bir veya daha fazla geçersiz giriş bulunduğunda fırlatılır.

    `hatalar` tüm ihlal mesajlarını taşır (tek geçişte hepsi raporlanır).
    """

    def __init__(self, hatalar: list[str]):
        self.hatalar = hatalar
        super().__init__(
            f"Kök sözlüğünde {len(hatalar)} doğrulama hatası:\n  "
            + "\n  ".join(hatalar)
        )


def _girdi_işle(ad, girdi, sözlük, hatalar, görülen, kaynak):
    """Tek bir kök girdisini işler; geçerliyse sözlüğe ekler, değilse hata toplar."""
    if ad in görülen:
        hatalar.append(
            f"{ad!r}: hem {kaynak} hem {görülen[ad]} dosyasında tanımlı (yinelenen)"
        )
        return
    görülen[ad] = kaynak

    if not isinstance(girdi, dict):
        hatalar.append(f"{ad!r}: girdi bir nesne olmalı")
        return

    bilinmeyen = set(girdi) - _ALANLAR
    if bilinmeyen:
        hatalar.append(f"{ad!r}: bilinmeyen alan(lar): {sorted(bilinmeyen)}")

    kök = Kök(
        tokens=girdi.get("tokens"),
        tür=girdi.get("tür"),
        son_ünlü=girdi.get("son_ünlü"),
        son_ses=girdi.get("son_ses"),
        değişim=girdi.get("değişim"),
        ek_tür=girdi.get("ek_tür", []),
        düşen=girdi.get("düşen", False),
        ince=girdi.get("ince", False),
        sadece_koşaç=girdi.get("sadece_koşaç", False),
        daralan=girdi.get("daralan", False),
        ek_değişim=girdi.get("ek_değişim"),
    )

    girdi_hataları = doğrula(ad, kök)
    if girdi_hataları:
        hatalar.extend(girdi_hataları)
    else:
        sözlük[ad] = kök


def yükle(yol: str | Path) -> dict[str, Kök]:
    """Tek bir JSON kök dosyasını okur, doğrular ve {ad: Kök} döndürür.

    Herhangi bir giriş geçersizse tüm hataları toplayıp ŞemaHatası fırlatır.
    """
    yol = Path(yol)
    ham = json.loads(yol.read_text(encoding="utf-8"))
    if not isinstance(ham, dict):
        raise ŞemaHatası([f"{yol.name}: en dış yapı bir nesne (sözlük) olmalı"])

    sözlük: dict[str, Kök] = {}
    hatalar: list[str] = []
    görülen: dict[str, str] = {}
    for ad, girdi in ham.items():
        _girdi_işle(ad, girdi, sözlük, hatalar, görülen, yol.name)

    if hatalar:
        raise ŞemaHatası(hatalar)
    return sözlük


def yükle_dizin(dizin: str | Path) -> dict[str, Kök]:
    """Dizindeki tüm <harf>.json kök dosyalarını birleştirir ve doğrular.

    Dosyalar arası yinelenen kök anahtarlarını da yakalar. Çalışma zamanı API'si.
    """
    dizin = Path(dizin)
    dosyalar = sorted(dizin.glob("*.json"))
    if not dosyalar:
        raise ŞemaHatası([f"{dizin}: hiç .json kök dosyası bulunamadı"])

    sözlük: dict[str, Kök] = {}
    hatalar: list[str] = []
    görülen: dict[str, str] = {}
    for dosya in dosyalar:
        ham = json.loads(dosya.read_text(encoding="utf-8"))
        if not isinstance(ham, dict):
            hatalar.append(f"{dosya.name}: en dış yapı bir nesne (sözlük) olmalı")
            continue
        for ad, girdi in ham.items():
            _girdi_işle(ad, girdi, sözlük, hatalar, görülen, dosya.name)

    if hatalar:
        raise ŞemaHatası(hatalar)
    return sözlük


def çalışma_sözlüğü(dizin: str | Path, *ek_dosyalar: str | Path) -> dict[str, Kök]:
    """Çalışma-zamanı kök sözlüğü: harf-fazı içerik kökleri + ek kök dosyaları.

    Zamir gövdeleri (ben/sen/on/bun…) işlev sözcüğüdür → harf fazlarına girmez
    (Veri Düzeni #5); ayrı dosyadan (veri/zamirler.json) gelir ve burada birleşir.
    Motor (çözümle/pipeline) bu birleşik sözlüğü kullanır. İçerik köküyle çakışan
    ek kök ŞemaHatası verir.
    """
    sözlük = yükle_dizin(dizin)
    hatalar: list[str] = []
    for dosya in ek_dosyalar:
        for ad, kök in yükle(dosya).items():
            if ad in sözlük:
                hatalar.append(f"{ad!r}: ek kök ({Path(dosya).name}) içerik köküyle çakışıyor")
            else:
                sözlük[ad] = kök
    if hatalar:
        raise ŞemaHatası(hatalar)
    return sözlük


def kök_bul(sözlük: dict[str, Kök], kelime: str) -> Kök | None:
    """Sözlükte kökü arar; Türkçe-duyarlı küçültme uygular. Yoksa None."""
    return sözlük.get(sesler.türkçe_küçült(kelime))

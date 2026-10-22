"""Dil verisi yükleyici: dil kodu → o dilin kökleri, ekleri, istisnaları.

Türkçe (dil None) veri/ altından, diğer diller veri/<dil>/ altından (aynı dosya düzeni):
  kokler/<harf>.json   harf fazları (araclar/kaynak[/<dil>]/<harf>.txt'ten üretilir)
  zamirler.json        zamir gövdeleri (varsa)
  islev_kokleri.json   çekimlenen işlev kökleri (varsa)
  ekler.json           ek listesi
  istisnalar.json      istisna/işlev sözcükleri (varsa)

    v = diller.yükle("az")
    encode(metin, v.kökler, v.ekler, v.istisnalar, dil="az")

Sonuç önbelleklidir: aynı dil için aynı nesneler döner (çözümle'nin trie önbelleği kimlikle
eşleşir → trie bir kez kurulur).
"""

from __future__ import annotations

from functools import cache
from pathlib import Path
from typing import NamedTuple

from tokenizer.dil import PROFİLLER
from tokenizer.ekler import yükle as ekleri_yükle
from tokenizer.istisna import yükle as istisna_yükle
from tokenizer.kokler import çalışma_sözlüğü

VERİ = Path(__file__).resolve().parent.parent / "veri"


class DilVerisi(NamedTuple):
    kökler: dict
    ekler: dict
    istisnalar: dict


def veri_dizini(dil: str | None = None) -> Path:
    return VERİ if dil is None else VERİ / dil


@cache
def yükle(dil: str | None = None) -> DilVerisi:
    """Dilin kök/ek/istisna verisini yükler ve doğrular (dil None = Türkçe)."""
    if dil is not None and (dil not in PROFİLLER or dil == "tr"):
        raise ValueError(f"bilinmeyen dil: {dil!r} (Türkçe için dil verilmez)")
    profil = None if dil is None else PROFİLLER[dil]
    dizin = veri_dizini(dil)
    ek_dosyalar = [dizin / ad for ad in ("zamirler.json", "islev_kokleri.json", "ozel_adlar.json")
                   if (dizin / ad).exists()]
    kökler = çalışma_sözlüğü(dizin / "kokler", *ek_dosyalar, profil=profil)
    ekler = ekleri_yükle(dizin / "ekler.json", profil)
    ist_yol = dizin / "istisnalar.json"
    istisnalar = istisna_yükle(ist_yol) if ist_yol.exists() else {}
    return DilVerisi(kökler, ekler, istisnalar)

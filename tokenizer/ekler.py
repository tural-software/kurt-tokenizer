"""Ek (sonek) listesi: soyut morfofonem + çözümleyici.

Ekler soyut yazılır; yüzey biçimi kökün (ya da gövdenin) son ünlüsü ve son sesinden
DETERMİNİSTİK türetilir — kök tasarımındaki "son_ünlü tek kaynak" ilkesiyle birebir.

Şablon mini-dili:
  A      geniş ünlü morfofonemi   → a/e        (artlığa göre)
  I      dar ünlü morfofonemi     → ı/i/u/ü    (artlık+yuvarlaklık)
  D      ünsüz morfofonemi        → d/t        (önceki ses ötümsüzse t)
  C      ünsüz morfofonemi        → c/ç        (önceki ses ötümsüzse ç)
  (X)    tampon:
           X ünlü (A/I) ise  → yalnızca ÜNSÜZ-sonu gövdeye eklenir   (iyelik -(I)m)
           X ünsüz (y/n/s) ise → yalnızca ÜNLÜ-sonu gövdeye eklenir  (-(y)I, -(s)I)
  diğer  düz harf (olduğu gibi)

Not: kökün ünsüz yumuşaması (kitap→kitab) EK tarafında değil, birleştirme motorunda
KÖK tarafında uygulanır. Bu modül yalnızca ekin yüzey biçimini üretir.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from tokenizer import sesler
from tokenizer.alfabe import ALFABE

# Ötümsüz (sert) ünsüzler — "fıstıkçışahap"
SERT: frozenset[str] = frozenset("çfhkpsşt")

İZİNLİ_ÖBEK: frozenset[str] = frozenset({"isim", "fiil", "her"})  # her = ad+fiil (koşaç)
_ŞABLON_SİMGE = set(ALFABE) | set("AIDC()")


def çöz_ünlü(simge: str, son_ünlü: str) -> str:
    """A/I morfofonemini kökün son ünlüsüne göre yüzeye indirger."""
    art = sesler.artlık(son_ünlü)
    if simge == "A":
        return "a" if art == "kalın" else "e"
    if simge == "I":
        yuv = sesler.yuvarlaklık(son_ünlü)
        return {
            ("kalın", "düz"): "ı", ("ince", "düz"): "i",
            ("kalın", "yuvarlak"): "u", ("ince", "yuvarlak"): "ü",
        }[(art, yuv)]
    raise ValueError(f"Ünlü morfofonemi değil: {simge!r}")


def çöz_ünsüz(simge: str, önceki: str) -> str:
    """D/C morfofonemini önceki sesin ötümlülüğüne göre yüzeye indirger."""
    sert = önceki in SERT
    if simge == "D":
        return "t" if sert else "d"
    if simge == "C":
        return "ç" if sert else "c"
    raise ValueError(f"Ünsüz morfofonemi değil: {simge!r}")


def ek_çöz(şablon: str, gövde: str, son_ü: str | None = None) -> str:
    """Soyut ek şablonunu, eklendiği gövdeye göre yüzey biçimine indirger.

    Örn: ek_çöz("(y)I", "araba") -> "yı";  ek_çöz("DA", "kitap") -> "ta".
    `son_ü` verilirse ilk uyum çapası olarak kullanılır (istisnai uyum: kalp→kalbi için
    art ünlü 'a' yerine ince karşılığı 'e' geçirilir); verilmezse gövdeden türetilir.
    """
    if son_ü is None:
        son_ü = sesler.son_ünlü_bul(gövde)   # ilerleyici uyum için "o anki son ünlü"
    if son_ü is None:
        raise ValueError(f"Gövdede ünlü yok: {gövde!r}")
    ünlü_sonu = gövde[-1] in sesler.ÜNLÜLER
    önceki = gövde[-1]
    sonuç: list[str] = []
    i = 0
    while i < len(şablon):
        c = şablon[i]
        if c == "(":
            simge = şablon[i + 1]
            i += 3  # "(X)" atla
            if simge in "AI":              # tampon ünlü → ünsüz-sonu gövdeye
                if not ünlü_sonu:
                    h = çöz_ünlü(simge, son_ü)
                    sonuç.append(h); önceki = h; son_ü = h
            else:                          # tampon ünsüz (y/n/s) → ünlü-sonu gövdeye
                if ünlü_sonu:
                    sonuç.append(simge); önceki = simge
            continue
        if c in "AI":
            h = çöz_ünlü(c, son_ü)         # önceki ÜNLÜ ile uyumla (ilerleyici)
            son_ü = h
        elif c in "DC":
            h = çöz_ünsüz(c, önceki)
        else:
            h = c
            if c in sesler.ÜNLÜLER:        # düz ünlü de uyumu ilerletir (ör. -Iyor'daki o)
                son_ü = c
        sonuç.append(h); önceki = h
        i += 1
    return "".join(sonuç)


@dataclass(frozen=True)
class Ek:
    """Tek bir ek kaydı (soyut şablon + işlev + paradigma öbeği + yuva/sıra)."""

    şablon: str
    tür: str
    öbek: str   # "isim" | "fiil" | "her"
    yuva: int   # morfotaktik sıra: isim çoğul1<iyelik2<hâl3; fiil olumsuz1<zaman2<şahıs3<soru4
    daraltır: bool = False     # ünlü-sonu köke gelince kök-son geniş ünlüyü düşürür (-Iyor)
    kök_koşullu: str = ""      # şablon gövdeye göre çözülür: "geniş"|"edilgen"|"ettirgen"
    çıkış: str = ""            # sınıf-değiştiren ek (nominalizer -mA/-Iş): gövdenin yeni öbeği
    değişim: dict | None = None  # ek-sonu yumuşaması: ünlü-başlı ek gelince (gelecek→geleceğiz)


class EkŞemaHatası(Exception):
    def __init__(self, hatalar: list[str]):
        self.hatalar = hatalar
        super().__init__(
            f"Ek listesinde {len(hatalar)} doğrulama hatası:\n  " + "\n  ".join(hatalar)
        )


def doğrula(ad: str, ek: Ek) -> list[str]:
    hatalar: list[str] = []
    if not ek.şablon:
        hatalar.append(f"{ad!r}: şablon boş olamaz")
    else:
        bilinmeyen = set(ek.şablon) - _ŞABLON_SİMGE
        if bilinmeyen:
            hatalar.append(f"{ad!r}: şablonda geçersiz simge(ler): {sorted(bilinmeyen)}")
    if ek.öbek not in İZİNLİ_ÖBEK:
        hatalar.append(f"{ad!r}: öbek {ek.öbek!r} geçersiz (isim|fiil)")
    if not ek.tür:
        hatalar.append(f"{ad!r}: tür boş olamaz")
    if not isinstance(ek.yuva, int) or ek.yuva < 1:
        hatalar.append(f"{ad!r}: yuva pozitif tam sayı olmalı, bulundu {ek.yuva!r}")
    if ek.çıkış and ek.çıkış not in ("isim", "fiil"):
        hatalar.append(f"{ad!r}: çıkış {ek.çıkış!r} geçersiz (isim|fiil|boş)")
    return hatalar


def yükle(yol: str | Path) -> dict[str, Ek]:
    """Ek listesini JSON'dan yükler ve doğrular."""
    ham = json.loads(Path(yol).read_text(encoding="utf-8"))
    sözlük: dict[str, Ek] = {}
    hatalar: list[str] = []
    for ad, girdi in ham.items():
        ek = Ek(şablon=girdi.get("şablon"), tür=girdi.get("tür"),
                öbek=girdi.get("öbek"), yuva=girdi.get("yuva"),
                daraltır=girdi.get("daraltır", False),
                kök_koşullu=("geniş" if girdi.get("kök_koşullu") is True
                             else (girdi.get("kök_koşullu") or "")),
                çıkış=girdi.get("çıkış", ""),
                değişim=girdi.get("değişim"))
        g = doğrula(ad, ek)
        hatalar.extend(g) if g else sözlük.update({ad: ek})
    if hatalar:
        raise EkŞemaHatası(hatalar)
    return sözlük

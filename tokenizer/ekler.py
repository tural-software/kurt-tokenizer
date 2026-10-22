"""Ek (sonek) listesi: soyut morfofonem + çözümleyici.

Ekler soyut yazılır; yüzey biçimi kökün (ya da gövdenin) son ünlüsü ve son sesinden
DETERMİNİSTİK türetilir — kök tasarımındaki "son_ünlü tek kaynak" ilkesiyle birebir.

Şablon mini-dili:
  A      geniş ünlü morfofonemi   → a/e        (artlığa göre)
  I      dar ünlü morfofonemi     → ı/i/u/ü    (artlık+yuvarlaklık)
  D      ünsüz morfofonemi        → d/t        (önceki ses ötümsüzse t)
  C      ünsüz morfofonemi        → c/ç        (önceki ses ötümsüzse ç)
  Q      ünsüz morfofonemi        → q/k        (artlığa göre; AZ -AcAQ: alacaq/gələcək)
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
_MORFOFONEM = "AIDCQ()"
_ŞABLON_SİMGE = set(ALFABE) | set(_MORFOFONEM)


def çöz_ünlü(simge: str, son_ünlü: str, profil=None) -> str:
    """A/I morfofonemini kökün son ünlüsüne göre yüzeye indirger (profil: dil, None = Türkçe)."""
    art = sesler.artlık(son_ünlü) if profil is None else profil.artlık(son_ünlü)
    if simge == "A":
        return "a" if art == "kalın" else ("e" if profil is None else profil.geniş_ince)
    if simge == "I":
        yuv = sesler.yuvarlaklık(son_ünlü) if profil is None else profil.yuvarlaklık(son_ünlü)
        return {
            ("kalın", "düz"): "ı", ("ince", "düz"): "i",
            ("kalın", "yuvarlak"): "u", ("ince", "yuvarlak"): "ü",
        }[(art, yuv)]
    raise ValueError(f"Ünlü morfofonemi değil: {simge!r}")


def çöz_ünsüz(simge: str, önceki: str, profil=None) -> str:
    """D/C morfofonemini önceki sesin ötümlülüğüne göre yüzeye indirger."""
    sert = önceki in (SERT if profil is None else profil.sert)
    if simge == "D":
        return "t" if sert else "d"
    if simge == "C":
        return "ç" if sert else "c"
    raise ValueError(f"Ünsüz morfofonemi değil: {simge!r}")


def ek_çöz(şablon: str, gövde: str, son_ü: str | None = None, profil=None) -> str:
    """Soyut ek şablonunu, eklendiği gövdeye göre yüzey biçimine indirger.

    Örn: ek_çöz("(y)I", "araba") -> "yı";  ek_çöz("DA", "kitap") -> "ta".
    `son_ü` verilirse ilk uyum çapası olarak kullanılır (istisnai uyum: kalp→kalbi için
    art ünlü 'a' yerine ince karşılığı 'e' geçirilir); verilmezse gövdeden türetilir.
    """
    ünlüler = sesler.ÜNLÜLER if profil is None else profil.ünlüler
    if son_ü is None:                       # ilerleyici uyum için "o anki son ünlü"
        son_ü = (sesler.son_ünlü_bul(gövde) if profil is None else profil.son_ünlü_bul(gövde))
    if son_ü is None:
        raise ValueError(f"Gövdede ünlü yok: {gövde!r}")
    ünlü_sonu = gövde[-1] in ünlüler
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
                    h = çöz_ünlü(simge, son_ü, profil)
                    sonuç.append(h); önceki = h; son_ü = h
            else:                          # tampon ünsüz (y/n/s) → ünlü-sonu gövdeye
                if ünlü_sonu:
                    sonuç.append(simge); önceki = simge
            continue
        if c in "AI":
            h = çöz_ünlü(c, son_ü, profil)  # önceki ÜNLÜ ile uyumla (ilerleyici)
            son_ü = h
        elif c in "DCQ":
            if c == "Q":                   # artlığa göre q/k (AZ); Türkçe şablonlarda yok
                h = "q" if (sesler.artlık(son_ü) if profil is None
                            else profil.artlık(son_ü)) == "kalın" else "k"
            else:
                h = çöz_ünsüz(c, önceki, profil)
        else:
            h = c
            if c in ünlüler:               # düz ünlü de uyumu ilerletir (ör. -Iyor'daki o)
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
    son_düşer: str = ""        # ekin son ünsüzü, bu harfle başlayan ek önünde düşer (AZ -mIş + sAn
    #                            → gəlmisən: ş, s önünde yazılmaz)
    önce_olamaz: tuple = ()    # bu eklerden HEMEN sonra gelemez (AZ yapım_lı ← fiil_isim_ma: -mAlI
    #                            gereklilik ekidir, -mA + -lI diye bölünmez)
    yalnız_kökler: frozenset = frozenset()  # boş değilse ek YALNIZ bu köklerin zincirinde bulunur (AZ sıra
    #                            sayısı -(I)ncI: sayılar, altıncı = altı+ncı; belirsizlik -sA: zamirler, nəyisə)
    yalnız_sonra: frozenset = frozenset()   # boş değilse ek YALNIZ bu eklerden HEMEN sonra gelir (AZ kişi
    #                            eki + -sA: deyilsinizsə, oldularsa)
    ünlü_sonra: bool = False   # ek yalnız ÜNLÜYLE biten gövdeye gelir (AZ y'siz ek-fiil -dI: yaxşıdı; ünsüzden
    #                            sonra zaten ek_fiil_idi aynı yüzeyi verir — hədd+i 'həddi' gölgelenmesin)


class EkŞemaHatası(Exception):
    def __init__(self, hatalar: list[str]):
        self.hatalar = hatalar
        super().__init__(
            f"Ek listesinde {len(hatalar)} doğrulama hatası:\n  " + "\n  ".join(hatalar)
        )


def doğrula(ad: str, ek: Ek, profil=None) -> list[str]:
    hatalar: list[str] = []
    simgeler = _ŞABLON_SİMGE if profil is None else set(profil.alfabe) | set(_MORFOFONEM)
    if not ek.şablon:
        hatalar.append(f"{ad!r}: şablon boş olamaz")
    else:
        bilinmeyen = set(ek.şablon) - simgeler
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


def yükle(yol: str | Path, profil=None) -> dict[str, Ek]:
    """Ek listesini JSON'dan yükler ve doğrular (profil: şablon alfabesi; None = Türkçe)."""
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
                değişim=girdi.get("değişim"),
                son_düşer=girdi.get("son_düşer", ""),
                önce_olamaz=tuple(girdi.get("önce_olamaz", ())),
                yalnız_kökler=frozenset(girdi.get("yalnız_kökler", ())),
                yalnız_sonra=frozenset(girdi.get("yalnız_sonra", ())),
                ünlü_sonra=girdi.get("ünlü_sonra", False))
        g = doğrula(ad, ek, profil)
        hatalar.extend(g) if g else sözlük.update({ad: ek})
    if hatalar:
        raise EkŞemaHatası(hatalar)
    return sözlük

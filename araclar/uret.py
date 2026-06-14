"""Kök kaynaklarından (.txt) sözlük JSON'u üretir.

Kaynak (insan-yazımı, dilbilimsel içerik): araclar/kaynak/<harf>.txt
  - satır başına:  kelime|tür|değişim
  - değişim boş → null;  ör.  git|fiil|t→d   ;  çoklu için virgül: x→y,z→w
  - '#' ile başlayan ve boş satırlar yok sayılır

Üretici tokens / son_ünlü / son_ses alanlarını otomatik türetir (yükleyici zaten
join==ad ve son_ünlü tutarlılığını denetler), doğrular, (hece sayısı, alfabetik)
sıralar ve veri/kokler/<harf>.json'a yazar.

Kullanım:
  python -X utf8 -m araclar.uret a         # tek harf
  python -X utf8 -m araclar.uret --hepsi   # tüm kaynaklar
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from tokenizer import sesler
from tokenizer.alfabe import alfabetik_anahtar
from tokenizer.hece import hecele
from tokenizer.sema import Kök, doğrula

KÖK_DİZİN = Path(__file__).resolve().parent.parent
KAYNAK_DİZİN = KÖK_DİZİN / "araclar" / "kaynak"
ÇIKTI_DİZİN = KÖK_DİZİN / "veri" / "kokler"
DEĞİŞİM_KOŞULU = "ünlü_ile_başlayan_ek_gelince"


def kaynak_oku(txt_yol: str | Path) -> list[tuple]:
    """Bir <harf>.txt kaynağını (kelime, tür, değişim, ek_tür, düşen) kayıtlarına ayrıştırır.

    Satır biçimi: kelime|tür|değişim|ek_tür  (değişim ve ek_tür virgülle çoklu, boş olabilir)
    Ünlü düşmesi: değişim sütununda 'düşen' özel değeri (tek başına ya da 'p→b,düşen' gibi).
    """
    kayıtlar = []
    for ham_satır in Path(txt_yol).read_text(encoding="utf-8").splitlines():
        satır = ham_satır.strip()
        if not satır or satır.startswith("#"):
            continue
        parçalar = [p.strip() for p in satır.split("|")]
        kelime = parçalar[0]
        tür = parçalar[1] if len(parçalar) > 1 else ""
        değişim_ham = parçalar[2] if len(parçalar) > 2 else ""
        ek_tür_ham = parçalar[3] if len(parçalar) > 3 else ""
        ek_değişim_ham = parçalar[4] if len(parçalar) > 4 else ""
        düşen = ince = daralan = False
        kurallar = []
        for m in (p.strip() for p in değişim_ham.split(",") if p.strip()):
            if m == "düşen":
                düşen = True
            elif m == "ince":
                ince = True
            elif m == "daralan":
                daralan = True
            else:
                kurallar.append(m)
        değişim = {m: DEĞİŞİM_KOŞULU for m in kurallar} if kurallar else None
        ek_tür = [t.strip() for t in ek_tür_ham.split(",")] if ek_tür_ham else []
        ek_kurallar = [m.strip() for m in ek_değişim_ham.split(",") if m.strip()]
        ek_değişim = {m: DEĞİŞİM_KOŞULU for m in ek_kurallar} if ek_kurallar else None
        kayıtlar.append((kelime, tür, değişim, ek_tür, düşen, ince, daralan, ek_değişim))
    return kayıtlar


def kök_üret(kelime: str, tür: str, değişim: dict | None, ek_tür=None,
             düşen: bool = False, ince: bool = False, daralan: bool = False,
             ek_değişim: dict | None = None) -> dict:
    """Mekanik alanları (tokens, son_ünlü, son_ses) türeterek tam kök girdisi üretir."""
    giriş = {
        "tokens": hecele(kelime),
        "tür": tür,
        "son_ünlü": sesler.son_ünlü_bul(kelime),
        "son_ses": "ünlü" if kelime and kelime[-1] in sesler.ÜNLÜLER else "ünsüz",
        "değişim": değişim,
    }
    if ek_tür:                                   # yalnız eşseslilerde ek alan
        giriş["ek_tür"] = list(ek_tür)
    if düşen:                                    # yalnız ünlü düşmesi köklerinde
        giriş["düşen"] = True
    if ince:                                     # yalnız istisnai uyum köklerinde
        giriş["ince"] = True
    if daralan:                                  # yalnız ye/de düzensiz fiillerinde
        giriş["daralan"] = True
    if ek_değişim:                               # yalnız her-iki-yön yumuşayan eşseslide (tat)
        giriş["ek_değişim"] = ek_değişim
    return giriş


def sıra_anahtarı(ad: str) -> tuple[int, list[int]]:
    """Sıralama anahtarı: önce hece sayısı, eşitlikte Türkçe alfabetik."""
    return (len(hecele(ad)), alfabetik_anahtar(ad))


def sözlük_üret(kayıtlar) -> dict[str, dict]:
    """Kayıtları doğrulanmış, sıralı bir {ad: girdi} sözlüğüne dönüştürür."""
    girişler: dict[str, dict] = {}
    hatalar: list[str] = []
    for kelime, tür, değişim, ek_tür, düşen, ince, daralan, ek_değişim in kayıtlar:
        if kelime in girişler:
            hatalar.append(f"{kelime!r}: kaynakta yinelenmiş")
            continue
        giriş = kök_üret(kelime, tür, değişim, ek_tür, düşen, ince, daralan, ek_değişim)
        hatalar.extend(doğrula(kelime, Kök(**giriş)))
        girişler[kelime] = giriş
    if hatalar:
        raise ValueError("Üretim doğrulama hatası:\n  " + "\n  ".join(hatalar))
    return {ad: girişler[ad] for ad in sorted(girişler, key=sıra_anahtarı)}


def biçimlendir(sözlük: dict[str, dict]) -> str:
    """Kök başına tek satır, okunabilir ve diff dostu JSON metni üretir."""
    if not sözlük:
        return "{}\n"
    satırlar = [
        "  "
        + json.dumps(ad, ensure_ascii=False)
        + ": "
        + json.dumps(sözlük[ad], ensure_ascii=False)
        for ad in sözlük
    ]
    return "{\n" + ",\n".join(satırlar) + "\n}\n"


def üret_ve_yaz(harf: str) -> int:
    """Bir harfin kaynağını okuyup veri/kokler/<harf>.json'a yazar; kök sayısını döndürür."""
    sözlük = sözlük_üret(kaynak_oku(KAYNAK_DİZİN / f"{harf}.txt"))
    ÇIKTI_DİZİN.mkdir(parents=True, exist_ok=True)
    (ÇIKTI_DİZİN / f"{harf}.json").write_text(biçimlendir(sözlük), encoding="utf-8")
    return len(sözlük)


def main(argv: list[str]) -> None:
    if not argv or argv[0] == "--hepsi":
        harfler = sorted(p.stem for p in KAYNAK_DİZİN.glob("*.txt"))
    else:
        harfler = argv
    for harf in harfler:
        print(f"{harf}.json  ←  {üret_ve_yaz(harf)} kök")


if __name__ == "__main__":
    main(sys.argv[1:])

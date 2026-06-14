"""Korpus doğrulama: gerçek koşan metin üzerinde tokenizer'ı ölçer.

Ölçülen (Aşama 0 bitiş ölçütleri):
  1. ROUND-TRIP kayıpsızlığı   — decode(encode(satır)) == satır  (HER satır)
  2. BİLİNMEYEN oranı          — çözülemeyen (onay kuyruğuna düşen) kelime / tüm kelime
  3. ÜRETKENLİK (fertility)    — token / kelime ortalaması
  4. Bilinmeyenlerin DÖKÜMÜ    — büyük-harfli (muhtemel özel ad) vs küçük (sözlük boşluğu)

Bilinmeyen ≠ hata: felsefe gereği bilinmeyen kelime BÜTÜN tutulur + kuyruğa alınır
("bilmiyorum, sana soruyorum"). Özel ad / alıntı / solid bileşik beklenen bilinmeyendir.
Asıl kırmızı çizgi ROUND-TRIP: tek bir satır bile bozulursa kayıp var demektir.

Çalıştırma:
    python -X utf8 -m araclar.dogrula_korpus [korpus_dosyası]
    (varsayılan: veri/korpus/dogrulama.txt)
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

from tokenizer.kokler import çalışma_sözlüğü
from tokenizer.ekler import yükle as ekleri_yükle
from tokenizer.istisna import yükle as istisna_yükle
from tokenizer.onay import OnayKuyruğu
from tokenizer.pipeline import encode, decode, BOŞLUK, BÜYÜK, ÖZEL

KÖK = Path("veri/kokler")
EK = Path("veri/ekler.json")
İST = Path("veri/istisnalar.json")
ZAMİR = Path("veri/zamirler.json")
İŞLEV = Path("veri/islev_kokleri.json")

# Sayılmayan tokenlar: boşluk, casing işaretçileri, özel, saf-noktalama.
_SAYMA = {BOŞLUK} | BÜYÜK | ÖZEL


def _kelime_mi(parça: str) -> bool:
    return any(c.isalpha() for c in parça)


def _içerik_token(tokenlar) -> int:
    """Üretkenlik için anlamlı token sayısı (boşluk/casing/noktalama hariç)."""
    return sum(1 for t in tokenlar
               if t not in _SAYMA and any(c.isalnum() for c in t))


def doğrula(korpus: Path):
    kökler = çalışma_sözlüğü(KÖK, ZAMİR, İŞLEV)
    ekler = ekleri_yükle(EK)
    istisnalar = istisna_yükle(İST)

    satırlar = [s.strip() for s in korpus.read_text(encoding="utf-8").splitlines()]
    satırlar = [s for s in satırlar if s and not s.startswith("#")]

    rt_kırık = []                         # round-trip bozulan satırlar
    kelime_sayısı = içerik_token = 0
    bilinmeyen_tip = Counter()            # surface → görülme
    büyük_bilinmeyen = set()              # ilk harfi büyük (muhtemel özel ad)
    tüm_kelimeler = set()

    for satır in satırlar:
        if decode(encode(satır, kökler, ekler, istisnalar)) != satır:
            rt_kırık.append(satır)
        for parça in satır.split():
            if not _kelime_mi(parça):
                continue
            kelime_sayısı += 1
            tüm_kelimeler.add(parça)
            q = OnayKuyruğu()
            tok = encode(parça, kökler, ekler, istisnalar, q)
            içerik_token += _içerik_token(tok)
            bekleyen = q.bekleyenler()
            if bekleyen:                  # bu kelime (veya özel-ad tabanı) çözülemedi
                for x in bekleyen:
                    bilinmeyen_tip[x.kelime] += 1
                    if parça[:1].isupper():
                        büyük_bilinmeyen.add(x.kelime)

    bilinmeyen_token = sum(bilinmeyen_tip.values())
    print(f"Korpus            : {korpus}")
    print(f"Cümle             : {len(satırlar)}")
    print(f"Kelime (token)    : {kelime_sayısı}   |   benzersiz: {len(tüm_kelimeler)}")
    print(f"Round-trip        : {len(satırlar) - len(rt_kırık)}/{len(satırlar)} "
          f"{'✓ KAYIPSIZ' if not rt_kırık else '✗ KIRIK VAR'}")
    print(f"Üretkenlik        : {içerik_token / kelime_sayısı:.3f} token/kelime")
    print(f"Bilinmeyen        : {bilinmeyen_token}/{kelime_sayısı} token "
          f"(%{100 * bilinmeyen_token / kelime_sayısı:.1f})   |   "
          f"benzersiz tür: {len(bilinmeyen_tip)}")
    küçük = {b for b in bilinmeyen_tip if b not in büyük_bilinmeyen}
    print(f"  • büyük-harfli (muhtemel özel ad): {len(büyük_bilinmeyen)} tür")
    print(f"  • küçük-harfli (sözlük boşluğu)  : {len(küçük)} tür")

    if rt_kırık:
        print("\n!!! ROUND-TRIP KIRIK satırlar:")
        for s in rt_kırık[:20]:
            print("   ", s)
    if küçük:
        print("\nKüçük-harfli bilinmeyenler (sözlük boşluğu — incele):")
        for b, n in sorted(((b, bilinmeyen_tip[b]) for b in küçük), key=lambda x: -x[1]):
            print(f"   {b}  ×{n}")
    if büyük_bilinmeyen:
        print("\nBüyük-harfli bilinmeyenler (özel ad — beklenen):")
        print("   " + ", ".join(sorted(büyük_bilinmeyen)))

    return {
        "cümle": len(satırlar),
        "kelime": kelime_sayısı,
        "round_trip_kırık": rt_kırık,
        "üretkenlik": içerik_token / kelime_sayısı,
        "bilinmeyen_token": bilinmeyen_token,
        "bilinmeyen_oran": bilinmeyen_token / kelime_sayısı,
        "küçük_bilinmeyen": {b for b in bilinmeyen_tip if b not in büyük_bilinmeyen},
        "büyük_bilinmeyen": büyük_bilinmeyen,
    }


if __name__ == "__main__":
    yol = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("veri/korpus/dogrulama.txt")
    sonuç = doğrula(yol)
    sys.exit(0 if not sonuç["round_trip_kırık"] else 1)

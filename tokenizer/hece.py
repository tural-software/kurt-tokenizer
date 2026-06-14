"""Deterministik kök heceleyici.

Bu, yol haritasındaki "Hece motoru"nun kök düzeyinde (ek/morfem yok) öne çekilmiş
hâlidir. Yalnızca fonolojik kurala dayanır; istatistik veya dış araç yoktur.

Kural (her hecede tam bir ünlü vardır → hece sayısı = ünlü sayısı):
İki ünlü arasındaki ünsüzler:
  0 ünsüz (VV)   → sınır ilk ünlüden hemen sonra        (sa-at, a-i-le)
  1 ünsüz (VCV)  → ünsüz sağ heceye                     (a-ra-ba, o-ku)
  ≥2 ünsüz       → son ünsüz hariç hepsi sola, son sağa (ki-tap, pen-ce-re)
Baştaki ünsüzler ilk heceye, sondaki ünsüzler son heceye bağlanır.

Kısıt: alıntı sözcüklerdeki *iç* 3'lü ünsüz öbekleri (kontrol → kon-trol yerine
kont-rol) bu kuralla TDK'dan sapar. Native Türkçe köklerin tamamında doğrudur.
"""

from __future__ import annotations

from tokenizer import sesler


def hecele(kelime: str) -> list[str]:
    """Bir kökü (ek almamış kelimeyi) hecelere böler."""
    ünlü_yerleri = [i for i, harf in enumerate(kelime) if harf in sesler.ÜNLÜLER]
    if not ünlü_yerleri:
        return [kelime] if kelime else []

    sınırlar = [0]
    for a, b in zip(ünlü_yerleri, ünlü_yerleri[1:]):
        ünsüz_sayısı = b - a - 1
        if ünsüz_sayısı <= 0:
            sınırlar.append(a + 1)   # VV: ilk ünlüden sonra böl
        else:
            sınırlar.append(b - 1)   # yalnızca son ünsüz sonraki heceye

    parçalar = []
    for i, baş in enumerate(sınırlar):
        son = sınırlar[i + 1] if i + 1 < len(sınırlar) else len(kelime)
        parçalar.append(kelime[baş:son])
    return parçalar

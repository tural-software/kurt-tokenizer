"""Kök öneki trie'si (prefix ağacı) — çözümleme aday-kök taramasını hızlandırır.

Sorun: çözümle, bir kelimenin köklerini bulmak için TÜM sözlüğü (46k+) tarayıp her kökün
yüzey-varyantlarının kelimenin öneki olup olmadığına bakıyordu → O(kök), kelime başına ~29ms.

Çözüm: kök varyant-öneklerini bir karakter-trie'sine indeksle. `bul(hedef)`, hedefi
karakterlerce yürüyerek yalnız varyantı hedefin ÖNEKİ olan kökleri döndürür → O(kelime
uzunluğu). Sonuç kümesi, eski `any(hedef.startswith(önek))` taramasıyla BİREBİR aynıdır;
yani davranış değişmez, yalnız aday bulma hızlanır.

Varyant önekleri (çözümle'nin eski 'önekler' kümesiyle aynı):
  - citation (ad)
  - yumuşamış (kitap→kitab)              değişim varsa
  - a/e-düşmüş (oyna→oyn)                -Iyor daralması adayı
  - ünlü-düşmüş (akıl→akl) [+yumuşamış]  düşen kök
"""

from __future__ import annotations

from tokenizer.birlestir import _yumuşat_son, _ünlü_düşür, _e_i


def kök_önekleri(ad: str, kök) -> set[str]:
    """Bir kökün, çözümleme adaylığı için tüm yüzey-varyant öneklerini döndürür."""
    ön = {ad}
    if kök.değişim:
        ön.add(_yumuşat_son(ad, kök.değişim))
    if ad and ad[-1] in "ae":
        ön.add(ad[:-1])
    if getattr(kök, "düşen", False):
        düş = _ünlü_düşür(ad)
        ön.add(düş)
        if kök.değişim:
            ön.add(_yumuşat_son(düş, kök.değişim))
    if getattr(kök, "daralan", False):           # ye→yi / de→di (yiyor için 'ye' adayı)
        ön.add(_e_i(ad))
    if getattr(kök, "ek_değişim", None):         # ikincil-sınıf yumuşaması (tat→tad: tadıyor)
        ön.add(_yumuşat_son(ad, kök.ek_değişim))
    return ön


class _Düğüm:
    __slots__ = ("çocuk", "kökler")

    def __init__(self):
        self.çocuk: dict[str, _Düğüm] = {}
        self.kökler: set[str] | None = None   # bu önekte BİTEN kök adları


class KökTrie:
    """Kök varyant-öneklerinden kurulu karakter-trie'si."""

    def __init__(self, kökler: dict):
        self.kök = _Düğüm()
        for ad, k in kökler.items():
            for önek in kök_önekleri(ad, k):
                düğüm = self.kök
                for ch in önek:
                    düğüm = düğüm.çocuk.setdefault(ch, _Düğüm())
                if düğüm.kökler is None:
                    düğüm.kökler = set()
                düğüm.kökler.add(ad)

    def bul(self, hedef: str) -> set[str]:
        """Varyantı `hedef`in öneki olan tüm kök adlarını döndürür (O(len(hedef)))."""
        sonuç: set[str] = set()
        düğüm = self.kök
        for ch in hedef:
            düğüm = düğüm.çocuk.get(ch)
            if düğüm is None:
                break
            if düğüm.kökler:
                sonuç |= düğüm.kökler
        return sonuç

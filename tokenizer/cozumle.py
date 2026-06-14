"""Çözümleme (segmentasyon) motoru: yüzey kelime → token(lar). Tokenizer'ın encode yönü.

Strateji (kullanıcı kararı): EK SOYMA + ÜRETEÇLE DOĞRULA.
  Aday (kök, ek dizisi) DFS ile aranır; her aday birleştir() ile üretilir ve üretilen
  yüzey hedefe eşitse çözüm kabul edilir. Harmony/tampon/yumuşama TERSİNE kodlanmaz —
  üreteç (tokenizer/birlestir.py) tek doğruluk kaynağıdır; bu modül onu doğrulayıcı
  olarak kullanır.

Belirsizlik (kullanıcı kararı): tüm geçerli çözümler döndürülür (gizlenmez).
  0 çözüm → bilinmeyen (üst katman onay kuyruğuna alır).
  İstisna listesindeki kelime doğrudan çözülür (akışta ilk basamak).

Budama: aday kök, kelimenin önekidir (yumuşama son ünsüzü değiştirebildiğinden
yumuşamış biçim de denenir). DFS'te yalnızca üretilen yüzey hedefin öneki olan
dallara inilir. Derinlik sınırı MAX_EK.

v1 sınırları (sonraki turlar): ek SIRASI ve ÖBEK (isim/fiil) zorlanmaz — üreteç+
doğrulama yüzeyi tutmayan dizileri eler ama yüzeyi tutan kural-dışı dizileri de
döndürebilir; düzensizler (geniş zaman, gelmiyor, ek-fiil) kapsam dışı.
"""

from __future__ import annotations

from dataclasses import dataclass

from tokenizer import sesler
from tokenizer.birlestir import birleştir
from tokenizer.istisna import istisna_bul
from tokenizer.trie import KökTrie

MAX_EK = 6   # koşaç zinciri için: kök+çoğul+iyelik+hâl+koşaç+kişi

# Trie önbelleği: aynı kökler sözlüğü için trie bir kez kurulur (kimlikle eşleştirilir).
_son_kökler = None
_son_trie: KökTrie | None = None


def _trie_al(kökler) -> KökTrie:
    """Verilen kökler sözlüğü için (gerekirse kurup) trie'yi döndürür — önbellekli."""
    global _son_kökler, _son_trie
    if kökler is not _son_kökler:
        _son_trie = KökTrie(kökler)
        _son_kökler = kökler
    return _son_trie

# Kişi-bağlamı (ince morfotaktik): kişi eki, kendini lisanslayan bir işaretçiye bağlı.
# İşaretçi (tip, kaynak): tip 1↔present-tarz / tip 2↔geçmiş-koşul; kaynak V↔fiil-zamanı,
# K↔koşaç(ek-fiil). Kişi eki hem TİP hem KAYNAK eşleşmesi ister: şahıs (-m/-n/-k…) fiil
# zamanına (V) bağlı; koşaç (-(y)Im…) ek-fiil işaretine (K) ya da ad-yüklem present-zero'ya.
# (Düzensiz değil, kapalı dilbilgisel olgu → kod-içi sabit.)
KİŞİ_LİSANS = {
    "şimdiki_zaman": (1, "V"), "gelecek_zaman": (1, "V"),
    "duyulan_geçmiş": (1, "V"), "geniş_zaman": (1, "V"),
    "görülen_geçmiş": (2, "V"), "şart": (2, "V"),
    "ek_fiil_imiş": (1, "K"), "ek_fiil_dir": (1, "K"),
    "ek_fiil_idi": (2, "K"), "ek_fiil_ise": (2, "K"),
}
KİŞİ_TİP = {
    "şahıs_1tekil_t1": (1, "V"), "şahıs_2tekil_t1": (1, "V"),
    "şahıs_1çoğul_t1": (1, "V"), "şahıs_2çoğul_t1": (1, "V"),
    "şahıs_3çoğul": ("T", "V"),
    "şahıs_1tekil_t2": (2, "V"), "şahıs_2tekil_t2": (2, "V"),
    "şahıs_1çoğul_t2": (2, "V"), "şahıs_2çoğul_t2": (2, "V"),
    "koşaç_1tekil_t1": (1, "K"), "koşaç_2tekil_t1": (1, "K"),
    "koşaç_1çoğul_t1": (1, "K"), "koşaç_2çoğul_t1": (1, "K"),
    "koşaç_3çoğul": ("T", "K"),
    "koşaç_1tekil_t2": (2, "K"), "koşaç_2tekil_t2": (2, "K"),
    "koşaç_1çoğul_t2": (2, "K"), "koşaç_2çoğul_t2": (2, "K"),
}
# tip "T" = 3. çoğul (-lAr): aynı KAYNAKtan bir işaretçi ister (geldiler V / güzellermiş K)
#   VEYA ad-yüklem present-zero (güzeller K); çıplak fiilden sonra gelmez.
# Koşaç/ek-fiil işaretçisi çıplak fiile bağlanmaz (önce fiil zamanı gerekir):
KOŞAÇ_İŞARET = frozenset({"ek_fiil_idi", "ek_fiil_imiş", "ek_fiil_ise", "ek_fiil_dir",
                          "ek_fiil_ken"})
# Yüklem olamayan hâller: present-koşaç (işaretçisiz) bunlardan sonra gelmez
# (bulunma HARİÇ: "evdeyim" geçerli ad-yüklem; araç/belirtme/yönelme/ayrılma/tamlayan değil)
TAHMİN_DIŞI_HAL = {"belirtme", "yönelme", "ayrılma", "tamlayan", "araç"}
# İyelik gerektiren ortaç: -DIk sıfat-fiili çıplak gelmez (bare 'geldik' = 1.çoğul görülen);
# yalnız iyelikli kullanılır (geldiğim, gördüğü). Çıplak ortaç_dik çözümü reddedilir.
İYELİK_GEREKTİREN = {"ortaç_dik", "ortaç_acak"}


def _present_zero_ok(ek_dizi, sınıf):
    """İşaretçisiz (present-zero) ad-yüklem koşacı bağlamı uygun mu?"""
    return sınıf == "isim" and not (ek_dizi and ek_dizi[-1] in TAHMİN_DIŞI_HAL)


def _kişi_uygun(ek_ad, ek_dizi, sınıf):
    """Kişi eki ek_ad, mevcut zincir bağlamında geçerli mi? (tip+kaynak lisanslama)"""
    beklenen = KİŞİ_TİP.get(ek_ad)
    if beklenen is None:
        return True                              # kişi eki değil → kısıt yok
    tip, kaynak = beklenen
    lisanslar = [KİŞİ_LİSANS[a] for a in ek_dizi if a in KİŞİ_LİSANS]
    son = lisanslar[-1] if lisanslar else None   # (tip, kaynak) | None
    if tip == "T":                                # 3. çoğul (-lAr)
        if son is not None and son[1] == kaynak:
            return True
        return kaynak == "K" and _present_zero_ok(ek_dizi, sınıf)
    if son == (tip, kaynak):                       # uygun tip+kaynak işaretçisi var
        return True
    if kaynak == "K" and tip == 1 and son is None:  # present-zero koşaç (ad yüklem)
        return _present_zero_ok(ek_dizi, sınıf)
    return False


def _koşaç_bağlanır(ek_ad, ek_dizi, sınıf, ekler):
    """Koşaç/ek-fiil işaretçisi bu tabana bağlanabilir mi? Çıplak fiile bağlanmaz:
    fiil tabanda önce bir zaman (yuva 2) gerekir; ad tabanda serbest (present-zero)."""
    if ek_ad not in KOŞAÇ_İŞARET or sınıf != "fiil":
        return True
    return any(ekler[a].öbek == "fiil" and ekler[a].yuva == 2 for a in ek_dizi)


@dataclass(frozen=True)
class Çözüm:
    tokens: list[str]
    kök: str
    ekler: list[str]


def _ara(kök_ad, kök, ek_dizi, son_yuva, sınıf, hedef, ekler, çıktı):
    tokenlar, yüzey = birleştir(kök_ad, kök, ek_dizi, ekler)
    if yüzey == hedef:
        # iyelik-gerektiren ortaç (-DIk) çıplak kabul edilmez (geldik=1.çoğul kalsın)
        if not (ek_dizi and ek_dizi[-1] in İYELİK_GEREKTİREN):
            çıktı.append(Çözüm(tokens=tokenlar, kök=kök_ad, ekler=list(ek_dizi)))
        return                                   # tam eşleşme; daha derini taşar
    if len(ek_dizi) >= MAX_EK:
        return
    for ek_ad, ek in ekler.items():
        # MORFOTAKTİK: ek öbeği gövde sınıfıyla uyumlu (koşaç 'her' her sınıfa) +
        # yuva kesin artan olmalı
        if (ek.öbek not in ("her", sınıf)) or ek.yuva <= son_yuva:
            continue
        # sadece-koşaç kökler (mı/değil) isim eki almaz; yalnız koşaç/ek-fiil ('her')
        # → "mide" yanlışlıkla mi+bulunma diye bölünmez
        if getattr(kök, "sadece_koşaç", False) and ek.öbek != "her":
            continue
        if not _kişi_uygun(ek_ad, ek_dizi, sınıf):    # kişi-bağlamı (tip+kaynak)
            continue
        if not _koşaç_bağlanır(ek_ad, ek_dizi, sınıf, ekler):  # koşaç çıplak fiile bağlanmaz
            continue
        _, ç_yüzey = birleştir(kök_ad, kök, ek_dizi + [ek_ad], ekler)
        # öneki tutan dala in; ara gövdenin SON sesi sonraki ünlü-başlı ek ile değişebilir:
        #   a/e → düşer (daraltır: gelme→gelmiyor)  |  k/p/ç/t → yumuşar (gelecek→geleceğiz).
        # Bu yüzden son ses "değişken" ise öneki son-ses-hariç de kabul et.
        if (hedef.startswith(ç_yüzey)
                or (ç_yüzey and ç_yüzey[-1] in "aekpçt" and hedef.startswith(ç_yüzey[:-1]))):
            # nominalizer (çıkış): gövde sınıfı değişir, yuva zonu sıfırlanır
            # (fiil → isim: gelme+si, yürüyüş+ü); aksi halde aynı zonda artan yuva
            if ek.çıkış:
                _ara(kök_ad, kök, ek_dizi + [ek_ad], 0, ek.çıkış, hedef, ekler, çıktı)
            else:
                _ara(kök_ad, kök, ek_dizi + [ek_ad], ek.yuva, sınıf, hedef, ekler, çıktı)


def çözümle(kelime, kökler, ekler, istisnalar=None) -> list[Çözüm]:
    """Yüzey kelimeyi tüm geçerli (kök + ek dizisi) çözümlerine ayırır."""
    hedef = sesler.türkçe_küçült(kelime)

    if istisnalar:
        ist = istisna_bul(istisnalar, hedef)
        if ist:
            return [Çözüm(tokens=list(ist.tokens), kök=hedef, ekler=[])]

    çözümler: list[Çözüm] = []
    # Aday kökler: varyant-öneki (kök / yumuşamış / a-e-düşmüş / ünlü-düşmüş) hedefin öneki
    # olanlar. Trie ile O(len(hedef)) bulunur (eski O(kök) tarama ile birebir aynı küme).
    for kök_ad in _trie_al(kökler).bul(hedef):
        kök = kökler[kök_ad]
        # eşsesli kök birden çok sınıfa ait olabilir (yaz: fiil + isim)
        türler = [kök.tür, *(kök.ek_tür or [])]
        sınıflar = {"fiil" if t == "fiil" else "isim" for t in türler}
        for sınıf in sınıflar:
            _ara(kök_ad, kök, [], 0, sınıf, hedef, ekler, çözümler)

    # aynı (token, kök, ek) çözümünü tekilleştir (eşseslide çıplak kök yinelenebilir)
    görülen, benzersiz = set(), []
    for ç in çözümler:
        anahtar = (tuple(ç.tokens), ç.kök, tuple(ç.ekler))
        if anahtar not in görülen:
            görülen.add(anahtar)
            benzersiz.append(ç)
    return benzersiz

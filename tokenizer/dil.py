"""Dil profili: motorun DİLE BAĞLI ses ve yazım bilgisi tek yerde.

Motor (hece, ek çözümleyici, birleştirme, çözümleme, trie, pipeline) tek; dile göre değişen her
şey bir DilProfili'nde toplanır ve fonksiyonlara `profil` olarak geçer (varsayılan TR). Türkçe
profilin değerleri sesler.py / alfabe.py / ekler.py'deki sabitlerin KENDİSİDİR → Türkçe yol bayt
bayt aynı kalır (test_dil kilitler, regresyon kapısı kanıtlar).

Dil eklemek = yeni profil + o dilin kendi verisi (veri/<dil>/: kökler, ekler, istisnalar). Kök
sözlükleri dillere göre AYRIDIR (AZ kipi Türkçe sözlüğü hiç görmez); token dizgisi aynıysa vocab
ID'si paylaşılır (ev, lar, da).
"""

from __future__ import annotations

from dataclasses import dataclass

from tokenizer import alfabe, sesler

SERT_TR: frozenset[str] = frozenset("çfhkpsşt")     # ötümsüz ünsüzler — "fıstıkçışahap"


@dataclass(frozen=True)
class DilProfili:
    """Bir dilin motor için gereken ses/yazım bilgisi. Alanlar donmuş (hashable: önbellek anahtarı)."""

    kod: str                    # "tr" | "az" …
    alfabe: str                 # küçük harf alfabe, sıralama düzeninde
    ünlüler: frozenset[str]     # tüm ünlüler (imli dahil)
    kalın: frozenset[str]       # art ünlüler
    ince: frozenset[str]        # ön ünlüler
    düz: frozenset[str]
    yuvarlak: frozenset[str]
    sert: frozenset[str]        # ötümsüz ünsüzler (D/C morfofonemi)
    geniş_ince: str             # A morfofoneminin ince karşılığı: TR 'e', AZ 'ə'
    ince_karşılık: tuple        # istisnai uyum (ince bayrağı): art ünlü → ön karşılığı, (eski, yeni) çiftleri
    değişken_son: str           # çözümle budaması: sonraki ek gelince değişebilen gövde son sesleri
    daralan_son: str            # 'daraltır' ek önünde düşebilen gövde son ünlüleri
    daraltma: str               # "gövde": her çok heceli a/e-sonu gövde (TR oyna→oynuyor)
    #                             "olumsuz": yalnız olumsuz -mA'nın ünlüsü (AZ gəl+mə+ir→gəlmir)
    sıra_eş: tuple = ()         # sıralamada temel harfine eşlenen harfler (â→a), (harf, temel) çiftleri
    geniş: str = "tr"           # geniş zaman kuralı: "tr" (-Ar/-Ir + GENİŞ_IR, olumsuz -z) |
    #                             "az" (-(y)Ar; olumsuz 1. kişide -r: gəlmərəm, diğerinde -z: gəlməz)
    ettirgen_ünsüz: str = "DIr" # ünsüz-sonu gövdede ettirgen şablonu (AZ: sertleşme yazılmaz → dIr)
    rakam_tire_eki: bool = False  # rakamdan sonra tire + harf = ek (AZ 2024-cü, 5-də; kesme gibi)
    kişi_lisansı: tuple = ()    # ortak KİŞİ_LİSANS'a dile özgü ek: (ek_adı, tip, kaynak) üçlüleri
    # Seçim politikası eklentileri (pipeline.en_iyi_çözüm; Türkçe politika değişmez):
    son_çare_ekler: frozenset = frozenset()  # bu ekleri içeren çözüm yalnız başka çözüm yoksa
    #                                          (AZ bitişik soru -mI: özümü = öz+ü+m+ü, öz+ü+mü değil)
    az_ek_önce: bool = False    # token sayısı eşitse daha az ekli çözüm (gəl+məli+y+əm, gəl+mə+liy+əm değil)
    birincil_önce: bool = False # eşsesli kök birincil sınıfıyla okunabiliyorsa o okuma (yazsan = yaz+sa+n
    #                             'yazarsan', yaz [mevsim]+san değil)
    yeğlenmeyen_ekler: frozenset = frozenset()  # aynı token sayısında bu ekleri içermeyen çözüm
    #                             yeğlenir (AZ 2. kişi iyelik: altından = alt+ı+n+dan, altı+n+dan değil)

    # ── ses ──────────────────────────────────────────────────────────────────────────────────
    def artlık(self, ünlü: str) -> str:
        if ünlü in self.kalın:
            return "kalın"
        if ünlü in self.ince:
            return "ince"
        raise ValueError(f"Ünlü değil: {ünlü!r}")

    def yuvarlaklık(self, ünlü: str) -> str:
        if ünlü in self.düz:
            return "düz"
        if ünlü in self.yuvarlak:
            return "yuvarlak"
        raise ValueError(f"Ünlü değil: {ünlü!r}")

    def son_ünlü_bul(self, kelime: str) -> str | None:
        for harf in reversed(kelime):
            if harf in self.ünlüler:
                return harf
        return None

    def ince_çevir(self, ünlü: str) -> str:
        return dict(self.ince_karşılık).get(ünlü, ünlü)

    # ── yazım (casing: Türk dilleri İ/i, I/ı) ───────────────────────────────────────────────
    def küçült(self, s: str) -> str:
        return sesler.türkçe_küçült(s)

    def büyült(self, s: str) -> str:
        return sesler.türkçe_büyült(s)

    def başlık(self, s: str) -> str:
        return sesler.türkçe_başlık(s)

    # ── sıralama ─────────────────────────────────────────────────────────────────────────────
    def alfabetik_anahtar(self, s: str) -> list[int]:
        sıra = {h: i for i, h in enumerate(self.alfabe)}
        sıra.update({h: sıra[t] for h, t in self.sıra_eş})
        try:
            return [sıra[h] for h in s]
        except KeyError as e:
            raise ValueError(f"{self.kod} alfabesinde olmayan harf: {e.args[0]!r} ({s!r})")


# Türkçe: sesler.py / alfabe.py / ekler.py sabitlerinin KENDİSİ (test_dil eşitliği kilitler).
TR = DilProfili(
    kod="tr",
    alfabe=alfabe.ALFABE,
    ünlüler=sesler.ÜNLÜLER,
    kalın=sesler.KALIN,
    ince=sesler.İNCE,
    düz=sesler.DÜZ,
    yuvarlak=sesler.YUVARLAK,
    sert=SERT_TR,
    geniş_ince="e",
    ince_karşılık=(("a", "e"), ("ı", "i"), ("o", "ö"), ("u", "ü"), ("â", "e"), ("û", "ü")),
    değişken_son="aekpçt",
    daralan_son="ae",
    daraltma="gövde",
    sıra_eş=(("â", "a"), ("î", "i"), ("û", "u")),
)

# Azerbaycan Türkçesi (32 harf; ə ince-düz ünlü; x/q ünsüz; w yok). Kaynak: Azərbaycan dilinin
# orfoqrafiya normaları (NK 16.04.2019 №174) ve orfoepiya normaları (NK 18.06.2021 №175).
AZ = DilProfili(
    kod="az",
    alfabe="abcçdeəfgğhxıijkqlmnoöprsştuüvyz",
    ünlüler=frozenset("aeəıioöuü"),
    kalın=frozenset("aıou"),
    ince=frozenset("eəiöü"),
    düz=frozenset("aeəıi"),
    yuvarlak=frozenset("ouöü"),
    sert=frozenset("çfhxkpsşt"),
    geniş_ince="ə",
    ince_karşılık=(("a", "ə"), ("ı", "i"), ("o", "ö"), ("u", "ü")),
    değişken_son="aəkqşz",         # ş: -mIş + sAn → gəlmisən (son_düşer); z: -mAz → -mAr (gəlmərəm)
    daralan_son="aə",
    daraltma="olumsuz",
    geniş="az",
    ettirgen_ünsüz="dIr",
    rakam_tire_eki=True,
    # -(y)Ib geçmişi (gəlibsən, gəliblər) ve gereklilik (gəlməliyəm, gəlməliyik) kişi eki alır.
    kişi_lisansı=(("geçmiş_ib", 1, "V"), ("gereklilik", 1, "V")),
    son_çare_ekler=frozenset({"soru"}),
    az_ek_önce=True,
    birincil_önce=True,
    yeğlenmeyen_ekler=frozenset({"iyelik_2tekil", "iyelik_2çoğul"}),
)

PROFİLLER: dict[str, DilProfili] = {"tr": TR, "az": AZ}
# Metin kipinde seçilebilen doğal diller (None = Türkçe). Kod kipindeki 'dil' programlama dilidir.
DOĞAL_DİLLER = frozenset(k for k in PROFİLLER if k != "tr")

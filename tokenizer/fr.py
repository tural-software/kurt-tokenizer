"""Fransızca sözcük çözümleyicisi (FR-1): kök sözlüğü + çekim kuralı + ÜRET-DOĞRULA.

İlke Türkçe/AZ/İngilizce ile aynıdır: her kökün yüzey biçimleri KENDİ kurallarımızla üretilir (üret), sözcük ancak
üretilen bir biçime birebir eşitse çözülür; kural tersine kodlanmaz. Fransızca çekim kapalı ve sonludur (fiil başına
~50 biçim), bu yüzden üreteç tüm biçimleri bir kez dizine yazar; çözümleme dizin araması + önektir. Hat (pipeline),
casing (Unicode, <|Ab|>/<|AA|>), vocab, dil kapısı ve onay kuyruğu ortaktır.

Token kuralları (plan docs/arastirma/fr_plan.md §2):
  - Kök/gövde tek token; yazım değişimi ve ikizleşme GÖVDE TOKENINDA: commenç+ons, mange+ons, lèv+e, appell+e,
    pai+e, bonn+e, heureus+e, journ+aux.
  - Çekim eki tek token: parl+ons, parl+aient, fin+iss+ons, parler+ai (gelecek = mastar gövdesi + ek), vend+u,
    parl+ées (ortaç uyumu tek token).
  - 3. grup fiil: gövde varyantı (veri/fr/cekim.json sınıfları): vien+s, ven+ons, vienn+ent, viendr+ai.
  - Elizyon SOLDA ayrı token: l'homme = [l', homme] (kesme biçimi korunur: l’homme = [l’, homme]); elizyon birimi
    hatta birleştirilir (pipeline._elizyon_birleştir), burada istisna olarak okunur.
  - Önek ayrı token: re+faire, in+égal (kalan gövde sözlükte ve ≥ 4 harf).
  - Tamamen düzensiz biçim bütün (istisnalar.json 'düzensiz': est, sont, ont, va, fut).

Seçim (deterministik, EN ile aynı düzen): (küçük harfte özel ad sonda) → BÜTÜN kök → en az ek/önek → öneksiz → geri
kök → en uzun kök → en az token → tam kırıcı.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from tokenizer.cozumle import Çözüm
from tokenizer.istisna import yükle as istisna_yükle

ALFABE = "aàâæbcçdeéèêëfghiîïjklmnoôœpqrstuùûüvwxyÿz"
HARFLER = frozenset(ALFABE)
ÜNLÜ = frozenset("aàâæeéèêëiîïoôœuùûüyÿ")
SINIFLAR = frozenset({"isim", "fiil", "sıfat", "zarf", "özel"})
KAPALI = frozenset({"zamir", "belirteç", "edat", "bağlaç", "ünlem", "sayı"})
TÜRLER = SINIFLAR | KAPALI
# Bayraklar (kokler.txt 3. sütun; değerli olanlar 'ad=değer'):
#   ad/sıfat çoğulu: x (bijou → bijoux; -eau/-au/-eu kendiliğinden), s (pneu → pneus, festival → festivals),
#                    aux (travail → travaux; -al kendiliğinden)
#   sıfat dişili:    çift (gros → grosse, sot → sotte), è (complet → complète), f=<dişil> (beau → belle)
#   fiil:            k=<sınıf> (cekim.json; -er 1. grup, -ir 2. grup kendiliğinden), çift (appeler → appelle;
#                    yoksa -eler/-eter → è), çift2 (iki yazım da: renouvelle / renouvèle)
#   geri:            eşsesli çakışmada geri çekilir (EN gibi)
BAYRAKLAR = frozenset({"x", "s", "aux", "çift", "çift2", "è", "geri"})
DEĞERLİ = frozenset({"f", "k"})
ÖNEK_KÖK_EN_KISA = 4
ÖNEK_YÜZEY_EN_KISA = 5      # önekten sonra kalan yüzey (présent ≠ pré+sent: sentir çekimi 4 harf)
KESMELER = ("'", "’")

# Çekim eki kümeleri (gövde + ek; ek tek token). Kişi sırası: 1t 2t 3t 1ç 2ç 3ç.
SÜREKLİ = ("ais", "ais", "ait", "ions", "iez", "aient")
GELECEK = ("ai", "as", "a", "ons", "ez", "ont")
KOŞUL = SÜREKLİ
DİLEK = ("e", "es", "e", "ions", "iez", "ent")
ŞİMDİKİ = {"s": ("s", "s", "t", "ons", "ez", "ent"), "x": ("x", "x", "t", "ons", "ez", "ent"),
           "e": ("e", "es", "e", "ons", "ez", "ent"), "d": ("s", "s", "", "ons", "ez", "ent")}
# Basit geçmiş (passé simple) + dilek geçmiş (subj. imparfait): ünlü türüne göre
BASİT = {"a": ("ai", "as", "a", "âmes", "âtes", "èrent"), "i": ("is", "is", "it", "îmes", "îtes", "irent"),
         "u": ("us", "us", "ut", "ûmes", "ûtes", "urent")}
DİLEK_GEÇMİŞ = {"a": ("asse", "asses", "ât", "assions", "assiez", "assent"),
                "i": ("isse", "isses", "ît", "issions", "issiez", "issent"),
                "u": ("usse", "usses", "ût", "ussions", "ussiez", "ussent")}
# -in türü (vins, tins): gövde 'in'/'în' + kişi eki
BASİT_İN = (("in", "s"), ("in", "s"), ("in", "t"), ("în", "mes"), ("în", "tes"), ("in", "rent"))
DİLEK_GEÇMİŞ_İN = (("in", "sse"), ("in", "sses"), ("în", "t"), ("in", "ssions"), ("in", "ssiez"), ("in", "ssent"))
SESSİZ_SON = frozenset({"e", "es", "ent"})        # sessiz e'li ekler: è / ikizleşme / y → i önünde
# Yazı dilinde seyrek kipler: aynı yüzeyin sık okuması varsa o seçilir (dis = di+s şimdiki, d+is basit geçmiş değil)
SEYREK = frozenset({"basit", "dilek_geçmiş"})
_ÇEKİM_SINIFLARI = ("g1", "g2")


@dataclass(frozen=True)
class FrKök:
    tür: str
    ek_tür: tuple = ()
    çoğul: str = ""         # "" kural | "x" | "s" | "aux"
    dişil: str = ""         # sıfat dişili açıkça (beau → belle); "" kural
    çift: bool = False
    çift2: bool = False
    è: bool = False
    sınıf: str = ""         # fiil çekim sınıfı: g1 | g2 | cekim.json adı
    geri: bool = False

    def sınıflar(self) -> list[str]:
        sonuç = []
        for s in (self.tür, *self.ek_tür):
            if s in SINIFLAR and s not in sonuç:
                sonuç.append(s)
        return sonuç


class FrVeriHatası(Exception):
    def __init__(self, hatalar: list[str]):
        self.hatalar = hatalar
        super().__init__(f"FR verisinde {len(hatalar)} hata:\n  " + "\n  ".join(hatalar))


def sıra_anahtarı(s: str) -> tuple:
    """Fransız sözlük sırası: önce imsiz harfler (é = e), eşitlikte kod noktası (deterministik)."""
    taban = unicodedata.normalize("NFD", s.replace("œ", "oe").replace("æ", "ae"))
    return ("".join(c for c in taban if not unicodedata.combining(c)), s)


# ── veri ────────────────────────────────────────────────────────────────────────────────────

def kökleri_yükle(yol: str | Path, sınıflar: dict) -> dict[str, FrKök]:
    """kokler.txt: 'sözcük|tür[,ek_tür…]|bayrak[,bayrak…]' satırları, # yorum. Sözcük küçük FR harfleri, sıralı."""
    sözlük: dict[str, FrKök] = {}
    hatalar: list[str] = []
    önceki = None
    for no, satır in enumerate(Path(yol).read_text(encoding="utf-8").splitlines(), 1):
        satır = satır.strip()
        if not satır or satır.startswith("#"):
            continue
        alanlar = satır.split("|")
        while len(alanlar) < 3:
            alanlar.append("")
        ad, türler = alanlar[0], alanlar[1].split(",")
        bayraklar = [b for b in alanlar[2].split(",") if b]
        yer = f"{no}: {ad!r}"
        if not ad or not all(c in HARFLER for c in ad):
            hatalar.append(f"{yer}: sözcük küçük FR harfleri olmalı")
            continue
        if önceki is not None and sıra_anahtarı(ad) <= sıra_anahtarı(önceki):
            hatalar.append(f"{yer}: sıra/tekillik bozuk (önceki {önceki!r})")
        önceki = ad
        if any(t not in TÜRLER for t in türler) or len(set(türler)) != len(türler):
            hatalar.append(f"{yer}: tür {türler} geçersiz ({sorted(TÜRLER)})")
            continue
        değer = {}
        düz = set()
        for b in bayraklar:
            if "=" in b:
                a, d = b.split("=", 1)
                if a not in DEĞERLİ or not d:
                    hatalar.append(f"{yer}: bayrak {b!r} geçersiz")
                değer[a] = d
            elif b in BAYRAKLAR:
                düz.add(b)
            else:
                hatalar.append(f"{yer}: bayrak {b!r} geçersiz ({sorted(BAYRAKLAR)}, f=, k=)")
        sınıf = ""
        if "fiil" in türler:
            sınıf = değer.get("k") or ("g1" if ad.endswith("er") else "g2" if ad.endswith("ir") else "")
            if not sınıf:
                hatalar.append(f"{yer}: -re/-oir fiili çekim sınıfı (k=) ister")
            elif sınıf not in _ÇEKİM_SINIFLARI and sınıf not in sınıflar:
                hatalar.append(f"{yer}: çekim sınıfı {sınıf!r} cekim.json'da yok")
            elif sınıf in sınıflar and not ad.endswith(sınıflar[sınıf]["son"]):
                hatalar.append(f"{yer}: {sınıf} sınıfı -{sınıflar[sınıf]['son']} ister")
            elif sınıf == "g1" and not ad.endswith("er") or sınıf == "g2" and not ad.endswith("ir"):
                hatalar.append(f"{yer}: {sınıf} sınıfı uyumsuz")
        elif "k" in değer:
            hatalar.append(f"{yer}: k= yalnız fiilde")
        if "f" in değer and not ("sıfat" in türler or "isim" in türler):
            hatalar.append(f"{yer}: f= yalnız sıfat/isimde")
        çoğul = next((b for b in ("x", "s", "aux") if b in düz), "")
        if çoğul == "aux" and not ad.endswith(("al", "ail")):
            hatalar.append(f"{yer}: aux yalnız -al/-ail sonunda")
        sözlük[ad] = FrKök(tür=türler[0], ek_tür=tuple(türler[1:]), çoğul=çoğul, dişil=değer.get("f", ""),
                           çift="çift" in düz, çift2="çift2" in düz, è="è" in düz, sınıf=sınıf, geri="geri" in düz)
    if hatalar:
        raise FrVeriHatası(hatalar)
    return sözlük


def sınıfları_yükle(yol: str | Path) -> dict:
    """cekim.json: 3. grup (ve düzensiz) fiil çekim sınıfları. Her sınıf: son (mastardan atılan; kalan TABAN), gövdeler
    tabana EKLENEN dizgiler. Alanlar: şimdiki {tür, gövdeler[tekil, 1-2 çoğul, 3 çoğul]} ya da 6'lı [gövde, ek] listesi,
    sürekli, dilek [tekil+3ç, 1-2ç] ya da 6'lı liste, basit [gövde, tür a|i|u|in], gelecek, ortaç [[gövde, ek(, uyum)]],
    ulaç."""
    ham = json.loads(Path(yol).read_text(encoding="utf-8"))
    hatalar = []
    for ad, s in ham.items():
        for alan in ("son", "şimdiki", "sürekli", "dilek", "basit", "gelecek", "ortaç", "ulaç"):
            if alan not in s:
                hatalar.append(f"{ad!r}: {alan} eksik")
        şim = s.get("şimdiki")
        if isinstance(şim, dict) and (şim.get("tür") not in ŞİMDİKİ or len(şim.get("gövdeler", ())) != 3):
            hatalar.append(f"{ad!r}: şimdiki {{tür ∈ {sorted(ŞİMDİKİ)}, 3 gövde}}")
        if isinstance(şim, list) and len(şim) != 6:
            hatalar.append(f"{ad!r}: şimdiki listesi 6 kişi")
        if s.get("basit", [None, None])[1] not in (*BASİT, "in"):
            hatalar.append(f"{ad!r}: basit türü a|i|u|in")
    if hatalar:
        raise FrVeriHatası(hatalar)
    return ham


@dataclass(frozen=True)
class FrEkler:
    """FR ek verisi: ek tokenları (doğrulama + vocab kaynağı), önekler, çekim sınıfları."""
    ekler: frozenset
    önekler: tuple             # (önek, izinli sınıflar) — uzun önek önce
    sınıflar: dict

    def __hash__(self):
        return id(self)


def ekleri_yükle(yol: str | Path, sınıflar: dict) -> FrEkler:
    ham = json.loads(Path(yol).read_text(encoding="utf-8"))
    ekler = frozenset(t for grup in ham["ekler"].values() for t in grup)
    önekler = tuple(sorted(((ö, frozenset(s)) for ö, s in ham["önekler"].items()), key=lambda x: (-len(x[0]), x[0])))
    return FrEkler(ekler=ekler, önekler=önekler, sınıflar=sınıflar)


@cache
def veri_yükle(dizin: Path):
    """veri/fr/: kokler.txt, ekler.json, cekim.json, istisnalar.json → (kökler, ekler, istisnalar). Üretilen her ek
    tokenı ekler.json'da bildirilmiş olmalı (bildirilmemiş ek = veri hatası)."""
    sınıflar = sınıfları_yükle(dizin / "cekim.json")
    kökler = kökleri_yükle(dizin / "kokler.txt", sınıflar)
    ekler = ekleri_yükle(dizin / "ekler.json", sınıflar)
    istisnalar = istisna_yükle(dizin / "istisnalar.json")
    hatalar = []
    for ad in sorted(kökler, key=sıra_anahtarı):
        for tokenlar, _ in biçimler(ad, kökler[ad], ekler):
            for t in tokenlar[1:]:
                if t not in ekler.ekler:
                    hatalar.append(f"{ad!r}: ek {t!r} ekler.json'da yok ({'+'.join(tokenlar)})")
            if "".join(tokenlar) == "" or any(not t for t in tokenlar):
                hatalar.append(f"{ad!r}: boş token ({tokenlar})")
    if hatalar:
        raise FrVeriHatası(sorted(set(hatalar))[:50])
    return kökler, ekler, istisnalar


# ── üretim: ad ve sıfat ───────────────────────────────────────────────────────────────────────

def _çoğul(ad: str, kök: FrKök) -> list[tuple[tuple, str]]:
    if ad.endswith(("s", "x", "z")):
        return []                                        # değişmez (bras, prix, nez)
    if kök.çoğul == "aux" or (not kök.çoğul and ad.endswith("al")):
        return [((ad[:-3] if ad.endswith("ail") else ad[:-2], "aux"), "çoğul")]
    if kök.çoğul == "x" or (not kök.çoğul and ad.endswith(("eau", "au", "eu"))):
        return [((ad, "x"), "çoğul")]
    return [((ad, "s"), "çoğul")]


def dişil(ad: str, kök: FrKök) -> str | None:
    """Sıfatın dişil tekil biçimi (kural + bayrak); masc = dişil ise None."""
    if kök.dişil:
        return kök.dişil
    if ad.endswith("e"):
        return None
    if kök.è and ad.endswith(("et", "er")):
        return ad[:-2] + "è" + ad[-1] + "e"              # complet → complète
    if kök.çift or ad.endswith(("el", "eil", "en", "on", "et")):
        return ad + ad[-1] + "e"                         # gros → grosse, cruel → cruelle, bon → bonne, net → nette
    if ad.endswith("eux"):
        return ad[:-1] + "se"                            # heureux → heureuse
    if ad.endswith("if"):
        return ad[:-1] + "ve"                            # actif → active
    if ad.endswith("er"):
        return ad[:-2] + "ère"                           # premier → première
    if ad.endswith("g"):
        return ad + "ue"                                 # long → longue
    return ad + "e"


def _sıfat(ad: str, kök: FrKök) -> list[tuple[tuple, str]]:
    sonuç = _çoğul(ad, kök)
    d = dişil(ad, kök)
    if d is not None:
        g = d[:-1]
        sonuç += [((g, "e"), "dişil"), ((g, "es"), "dişil_çoğul")]
    zarf = _zarf(ad, d)
    if zarf:
        sonuç.append((zarf, "zarf"))
    return sonuç


def _zarf(ad: str, d: str | None) -> tuple | None:
    """-ment zarfı: ünlü sonu eril + ment (vrai+ment), -ant/-ent → amment/emment, diğer dişil gövde + ement."""
    if ad.endswith("ant"):
        return (ad[:-3], "amment")
    if ad.endswith("ent"):
        return (ad[:-3], "emment")
    if d is None:                                        # -e sonu: rapide → rapid+ement
        return (ad[:-1], "ement")
    if ad[-1] in "iéu":
        return (ad, "ment")
    return (d[:-1], "ement")


# ── üretim: fiil ─────────────────────────────────────────────────────────────────────────────

def _ortaç(gövde: str, ek: str, uyum: bool = True) -> list[tuple[tuple, str]]:
    sonuç = [((gövde, ek), "ortaç")]
    if uyum:
        sonuç.append(((gövde, ek + "e"), "ortaç"))
        sonuç.append(((gövde, ek + "es"), "ortaç"))
        if not ek.endswith(("s", "x")):
            sonuç.append(((gövde, ek + "s"), "ortaç"))
    return sonuç


def _g1(ad: str, kök: FrKök) -> list[tuple[tuple, str]]:
    """1. grup -er: yazım değişimleri gövde tokenında. ç/ge (a/o önü), è ya da ikizleşme (sessiz e önü ve gelecek),
    y → i (sessiz e önü)."""
    taban = ad[:-2]
    sert = taban                                          # a/o önü
    if taban.endswith("c"):
        sert = taban[:-1] + "ç"
    elif taban.endswith("g"):
        sert = taban + "e"
    sessiz: list[str] = [taban]                           # sessiz e önü (bir ya da iki yazım)
    gelecek: list[str] = [ad]
    # son hecede e/é + tek ünsüz (x hariç), patlamalı + akıcı (sevr, célébr), ch, gn ya da qu/gu
    m = re.search(r"([eé])([bcdfgjklmnpqrstvz]|[bcdfgptv][rl]|ch|gn|qu|gu)$", taban)
    if taban.endswith(("oy", "uy")):
        sessiz = [taban[:-1] + "i"]
        gelecek = [taban[:-1] + "ier"]
    elif taban.endswith("ay"):
        sessiz = [taban, taban[:-1] + "i"]
        gelecek = [ad, taban[:-1] + "ier"]
    elif m:
        ön, ünlü, ünsüz = taban[:m.start()], m.group(1), m.group(2)
        è_gövde = ön + "è" + ünsüz
        if ünlü == "e" and (kök.çift or kök.çift2) and ünsüz in ("l", "t"):
            ikiz = ön + "e" + ünsüz + ünsüz               # appeler → appell, jeter → jett
            sessiz = [ikiz] + ([è_gövde] if kök.çift2 else [])
            gelecek = [ikiz + "er"] + ([è_gövde + "er"] if kök.çift2 else [])
        elif ünlü == "e":
            sessiz, gelecek = [è_gövde], [è_gövde + "er"]  # lever → lèv, lèver+ai
        else:
            sessiz, gelecek = [è_gövde], [ad, è_gövde + "er"]   # céder → cèd; céder+ai / cèder+ai (1990)
    sonuç: list[tuple[tuple, str]] = []

    def gv(ek):
        return sert if ek[:1] in ("a", "o", "â") else taban

    for i, ek in enumerate(ŞİMDİKİ["e"]):
        for g in (sessiz if ek in SESSİZ_SON else [gv(ek)]):
            sonuç.append(((g, ek), "şimdiki"))
    for ek in SÜREKLİ:
        sonuç.append(((gv(ek), ek), "sürekli"))
    for ek in DİLEK:
        for g in (sessiz if ek in SESSİZ_SON else [taban]):
            sonuç.append(((g, ek), "dilek"))
    for ek in BASİT["a"]:
        sonuç.append(((taban if ek == "èrent" else gv(ek), ek), "basit"))
    for ek in DİLEK_GEÇMİŞ["a"]:
        sonuç.append(((gv(ek), ek), "dilek_geçmiş"))
    for g in gelecek:
        sonuç += [((g, ek), "gelecek") for ek in GELECEK] + [((g, ek), "koşul") for ek in KOŞUL]
    sonuç += _ortaç(taban, "é")
    sonuç.append(((sert, "ant"), "ulaç"))
    return sonuç


def _g2(ad: str) -> list[tuple[tuple, str]]:
    """2. grup -ir (-iss-): fin+is, fin+iss+ons, finir+ai, fin+i."""
    taban = ad[:-2]
    sonuç = [((taban, ek), "şimdiki") for ek in ("is", "it")]
    sonuç += [((taban, "iss", ek), "şimdiki") for ek in ("ons", "ez", "ent")]
    sonuç += [((taban, "iss", ek), "sürekli") for ek in SÜREKLİ]
    sonuç += [((taban, "iss", ek), "dilek") for ek in DİLEK]
    sonuç += [((taban, ek), "basit") for ek in BASİT["i"]]
    sonuç += [((taban, "ît"), "dilek_geçmiş")]
    sonuç += [((ad, ek), "gelecek") for ek in GELECEK] + [((ad, ek), "koşul") for ek in KOŞUL]
    sonuç += _ortaç(taban, "i")
    sonuç.append(((taban, "iss", "ant"), "ulaç"))
    return sonuç


def _kişi_listesi(alan, taban: str, ekler6) -> list[tuple]:
    """Sınıf alanı: [tekil, 1-2 çoğul, 3 çoğul] gövdeleri (ekler6 ile) ya da 6'lı [gövde, ek] listesi → (gövde, ek)."""
    if isinstance(alan, list) and alan and isinstance(alan[0], list):
        return [(taban + g, e) for g, e in alan]
    if isinstance(alan, str):
        alan = [alan, alan]
    if len(alan) == 2:                                     # dilek: [tekil + 3 çoğul, 1-2 çoğul]
        gövdeler = [alan[0], alan[0], alan[0], alan[1], alan[1], alan[0]]
    else:
        gövdeler = [alan[0], alan[0], alan[0], alan[1], alan[1], alan[2]]
    return [(taban + g, e) for g, e in zip(gövdeler, ekler6)]


def _sınıf_biçimleri(ad: str, s: dict) -> list[tuple[tuple, str]]:
    taban = ad[:-len(s["son"])]
    sonuç: list[tuple[tuple, str]] = []
    şim = s["şimdiki"]
    çiftler = (_kişi_listesi(şim["gövdeler"], taban, ŞİMDİKİ[şim["tür"]]) if isinstance(şim, dict)
               else _kişi_listesi(şim, taban, ()))
    sonuç += [((g, e) if e else (g,), "şimdiki") for g, e in çiftler]
    sonuç += [((taban + s["sürekli"], e), "sürekli") for e in SÜREKLİ]
    sonuç += [((g, e), "dilek") for g, e in _kişi_listesi(s["dilek"], taban, DİLEK)]
    bg, bt = s["basit"]
    if bt == "in":
        sonuç += [((taban + bg + g, e), "basit") for g, e in BASİT_İN]          # v+in+s → vin+s
        sonuç += [((taban + bg + g, e), "dilek_geçmiş") for g, e in DİLEK_GEÇMİŞ_İN]
    else:
        sonuç += [((taban + bg, e), "basit") for e in BASİT[bt]]
        sonuç += [((taban + bg, e), "dilek_geçmiş") for e in DİLEK_GEÇMİŞ[bt]]
    g = taban + s["gelecek"]
    sonuç += [((g, e), "gelecek") for e in GELECEK] + [((g, e), "koşul") for e in KOŞUL]
    for o in s["ortaç"]:
        sonuç += _ortaç(taban + o[0], o[1], bool(o[2]) if len(o) > 2 else True)
    sonuç.append(((taban + s["ulaç"], "ant"), "ulaç"))
    return sonuç


def biçimler(ad: str, kök: FrKök, ekler: FrEkler) -> list[tuple[tuple, str]]:
    """Kökün çekimli biçimleri (yalın biçim hariç): [(tokenlar, ek_adı)]. Tokenlar (gövde, ek…); tek tokenlı biçim
    (3. grup gövdesi: met, vend) ek almaz ama çekimlidir. Sıra deterministik."""
    sonuç: list[tuple[tuple, str]] = []
    for sınıf in kök.sınıflar():
        if sınıf == "fiil":
            if kök.sınıf == "g1":
                sonuç += _g1(ad, kök)
            elif kök.sınıf == "g2":
                sonuç += _g2(ad)
            else:
                sonuç += _sınıf_biçimleri(ad, ekler.sınıflar[kök.sınıf])
        elif sınıf == "sıfat":
            sonuç += _sıfat(ad, kök)
        elif sınıf in ("isim", "özel"):
            sonuç += _çoğul(ad, kök)
            if kök.dişil:                                 # cinsiyet çifti olan ad (acteur → actrice)
                g = kök.dişil[:-1]
                sonuç += [((g, "e"), "dişil"), ((g, "es"), "dişil_çoğul")]
    görülen, benzersiz = set(), []
    for b in sonuç:
        if b not in görülen and "".join(b[0]) != ad:
            görülen.add(b)
            benzersiz.append(b)
    return benzersiz


# ── çözümleme ───────────────────────────────────────────────────────────────────────────────

_DİZİNLER: dict = {}


def _dizin(kökler, ekler) -> dict[str, list[tuple]]:
    """yüzey → [(tokenlar, kök, ek_adı)] (kök sözlüğü kimliğiyle önbellekli; sıralı → deterministik)."""
    kayıt = _DİZİNLER.get("fr")
    if kayıt is None or kayıt[0] is not kökler:
        d: dict[str, list[tuple]] = {}
        for ad in sorted(kökler, key=sıra_anahtarı):
            d.setdefault(ad, []).append(((ad,), ad, ""))
            for tokenlar, ek in biçimler(ad, kökler[ad], ekler):
                liste = d.setdefault("".join(tokenlar), [])
                if not any(t == tokenlar and k == ad for t, k, _ in liste):   # aynı okuma iki kipten (dilek = şimdiki)
                    liste.append((tokenlar, ad, ek))
        kayıt = _DİZİNLER["fr"] = (kökler, d)
    return kayıt[1]


def _istisna(kelime: str, istisnalar):
    """İstisna (kesme biçimi bağımsız: aujourd’hui ↔ aujourd'hui). Tokenlar sözcüğün kendi kesmesiyle döner."""
    if not istisnalar:
        return None
    ist = istisnalar.get(kelime)
    if ist is not None:
        return list(ist.tokens)
    if "’" in kelime:
        ist = istisnalar.get(kelime.replace("’", "'"))
        if ist is not None:
            return [t.replace("'", "’") for t in ist.tokens]
    return None


def çözümle(kelime: str, kökler, ekler: FrEkler, istisnalar=None) -> tuple[list[Çözüm], None]:
    """Sözcüğün tüm okumaları: istisna; ya da (önek) + üretilmiş biçim. (çözümler, None) — EN arayüzüyle aynı."""
    ist = _istisna(kelime, istisnalar)
    if ist is not None:
        return [Çözüm(tokens=ist, kök=kelime, ekler=[])], None
    dizin = _dizin(kökler, ekler)
    çözümler = [Çözüm(tokens=list(t), kök=k, ekler=[e] if e else []) for t, k, e in dizin.get(kelime, ())]
    for önek, izin in ekler.önekler:
        if not kelime.startswith(önek) or len(kelime) - len(önek) < ÖNEK_YÜZEY_EN_KISA:
            continue
        for t, k, e in dizin.get(kelime[len(önek):], ()):
            kök = kökler[k]
            # önek kökü en az 4 harf ve sınıfı önekle uyumlu (re-/dé- fiil, in- sıfat …)
            if len(k) >= ÖNEK_KÖK_EN_KISA and izin & set(kök.sınıflar()):
                çözümler.append(Çözüm(tokens=[önek, *t], kök=k, ekler=["önek_" + önek] + ([e] if e else [])))
    return çözümler, None


def en_iyi(çözümler: list[Çözüm], kökler=None, ad_okuma: bool = False) -> Çözüm:
    """(küçük harfte özel ad SONDA) → BÜTÜN kök → en az ek/önek → öneksiz → seyrek kip sonda → GÖVDESİ DEĞİŞMEMİŞ okuma
    (portes = porte+s ad çoğulu, port+es fiil değil; tekil 'porte' de bütün ad) → geri kök → en az token (suis = être
    biçimi, sui+s değil) → en uzun kök → tam kırıcı. EN düzeninden fark: gövde ölçütü ve token sayısı kök uzunluğundan
    önce (Fransızca düzensiz biçimler tek token)."""
    kökler = kökler or {}
    geri = {ç.kök for ç in çözümler if getattr(kökler.get(ç.kök), "geri", False)
            and any(d.kök != ç.kök for d in çözümler)}
    return min(çözümler, key=lambda ç: (
        not ad_okuma and getattr(kökler.get(ç.kök), "tür", "") == "özel",
        0 if not ç.ekler else 1, len(ç.ekler), sum(e.startswith("önek_") for e in ç.ekler),
        sum(e in SEYREK for e in ç.ekler), _gövde_değişti(ç), ç.kök in geri,
        len(ç.tokens), -len(ç.kök), tuple(ç.tokens), ç.kök, tuple(ç.ekler)))


def _gövde_değişti(ç: Çözüm) -> bool:
    önek = sum(e.startswith("önek_") for e in ç.ekler)
    return ç.tokens[önek] != ç.kök


# ── yedek heceleme ──────────────────────────────────────────────────────────────────────────

# İzinli hece başı ünsüz kümeleri (kapalı liste; tek ünsüz her zaman izinli). ch/gn/ph/qu/th tek ses.
BAŞ_KÜMELERİ = frozenset("bl br ch cl cr dr fl fr gl gn gr ph pl pr qu tr vr th".split())


def _ünlü_mü(s: str, i: int) -> bool:
    c = s[i]
    if c == "y" or c == "ÿ":
        return i > 0 and not (i + 1 < len(s) and s[i + 1] in ÜNLÜ)   # yeux: ünsüz; pays, style: ünlü
    return c in ÜNLÜ


def hecele(kelime: str) -> list[str]:
    """Yazım hecesi (yedek; morfem iddiası yok): ünlü grubu (eau, oi, ou, ai…) çekirdek, aradaki ünsüzlerden izinli
    baş kümesi sağa, kalanı sola. Birleşim = girdi (kayıpsız). Harf dışı karakter ünsüz sayılır."""
    çekirdekler: list[tuple[int, int]] = []
    i = 0
    while i < len(kelime):
        if _ünlü_mü(kelime, i):
            j = i
            while j + 1 < len(kelime) and _ünlü_mü(kelime, j + 1):
                j += 1
            çekirdekler.append((i, j + 1))
            i = j + 1
        else:
            i += 1
    if len(çekirdekler) < 2:
        return [kelime] if kelime else []
    sınırlar = [0]
    for (_, a_son), (b_baş, _) in zip(çekirdekler, çekirdekler[1:]):
        küme = kelime[a_son:b_baş]
        baş = 1 if küme else 0
        if len(küme) >= 2 and küme[-2:] in BAŞ_KÜMELERİ:
            baş = 2
        sınırlar.append(b_baş - baş)
    return [kelime[a:b] for a, b in zip(sınırlar, sınırlar[1:] + [len(kelime)])]

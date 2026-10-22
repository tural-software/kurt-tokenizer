"""Almanca sözcük çözümleyicisi (DE-1): kök sözlüğü + çekim kuralı + bileşik kuralı + ÜRET-DOĞRULA.

İlke Türkçe/AZ/İngilizce/Fransızca ile aynıdır: her kökün yüzey biçimleri KENDİ kurallarımızla üretilir (üret), sözcük
ancak üretilen bir biçime birebir eşitse çözülür. Almanca çekim kapalıdır (FR gibi dizine yazılır); bileşik sözcük
üretken ve sonsuz olduğundan kuralla parçalardan kurulur (parçalar yine üretilmiş biçimlerdir). Hat, casing (Unicode,
<|Ab|>/<|AA|>), vocab, dil kapısı ve onay kuyruğu ortaktır.

Token kuralları (plan docs/arastirma/de_plan.md §2, kullanıcı kararları 2026-10-22):
  - Kök/gövde tek token; umlaut ve ablaut GÖVDE TOKENINDA: Häus+er, Väter, gab+en, ge+sung+en, ält+er.
  - Çekim ekleri ayrı token, sırayla: Häus+er+n (çoğul + yönelme), schön+er+e (üstünlük + sıfat eki), ge+mach+t+e.
  - ge- ortaç öneki ayrı token (ge+mach+t); ayrılmayan önekli fiil (verstehen, bekommen) TEK KÖK (kullanıcı: sahte iş
    yok) — çekimi taban fiilin sınıfından, ge- almadan: verstand+en, verstanden değil versteh+t.
  - Ayrılabilir önekli fiil yalnız SÖZLÜKTE kayıtlıysa önek + taban: an+fangen, an+fäng+t, an+ge+fang+en, an+zu+fangen.
  - Bileşik (kullanıcı kararı a): sözlük dışı sözcük parça + Fugen + parça; Fugen ayrı token (arbeit+s+platz); en az
    parçalı okuma birden çoksa (Staubecken = stau+becken / staub+ecken) BÜTÜN tutulur ve sorulur (ilke #3).
  - Tamamen düzensiz biçim bütün (ist, sind, war; istisnalar ya da tek tokenlı sınıf gövdesi).

Seçim (deterministik): BÜTÜN kök → en az ek → bileşik olmayan → seyrek kip sonda → gövdesi değişmemiş okuma → geri kök
→ en az token → en uzun kök → tam kırıcı. Özel ad okuması her zaman SONDA (Almancada her ad büyük yazılır; Başlık
biçimi özel ad işareti değildir — kullanıcı kararı).
"""

from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from tokenizer.cozumle import Çözüm
from tokenizer.istisna import yükle as istisna_yükle

ALFABE = "aäbcdefghijklmnoöpqrsßtuüvwxyz"
HARFLER = frozenset(ALFABE)
ÜNLÜ = frozenset("aäeioöuüy")
SINIFLAR = frozenset({"isim", "fiil", "sıfat", "zarf", "özel"})
KAPALI = frozenset({"zamir", "belirteç", "edat", "bağlaç", "ünlem", "sayı"})
TÜRLER = SINIFLAR | KAPALI
# Bayraklar (kokler.txt 3. sütun; değerli olanlar 'ad=değer'):
#   isim:  ç=<çoğul eki> (e er en n s nen 0; yoksa çoğul yok), u (çoğulda umlaut: Haus → Häus+er, Vater → Väter),
#          çk=<çoğul gövdesi> (Thema → Them+en), g=<tamlayan> (s es ns), z (zayıf ad: Mensch+en, Junge+n tüm eğik hâl)
#   sıfat: u (üstünlükte umlaut: alt → ält+er), sg=<çekim gövdesi> (hoch → hoh+e), kom=<üstünlük gövdesi> (gut → bess+er), sup=<enüstünlük BÜTÜN> (best,
#          größt), dk (derecelenmez: tot, ganz)
#   fiil:  k=<örnek fiil> (cekim.json: güçlü/karışık/düzensiz; yoksa zayıf), ay=<ayrılabilir önek> (an: anfangen =
#          an + fangen, taban sözlükte), geyok (ortaç ge- almaz: besuchen → besuch+t; ayrılmayan önekli güçlü fiilde
#          örnek fiilden kendiliğinden: verstehen ← stehen)
#   geri:  eşsesli çakışmada geri çekilir (EN/FR gibi)
#   bz:    bileşen değil — bileşikte parça olamaz (korpusta seyrek kısa kök: schi, klett; schieben ≠ schi+eben)
BAYRAKLAR = frozenset({"u", "z", "dk", "geyok", "bz", "geri"})
DEĞERLİ = frozenset({"ç", "çk", "g", "sg", "kom", "sup", "k", "ay"})
ÇOĞUL_EKLERİ = frozenset({"e", "er", "en", "n", "s", "nen", "0"})
TAMLAYAN = frozenset({"s", "es", "ns", "ens"})
AYRILMAZ = ("miss", "emp", "ent", "zer", "ver", "be", "er", "ge")   # ayrılmayan önek: ge- ortacı almaz
SIFAT_EKLERİ = ("e", "er", "es", "en", "em")
FUGEN = ("ens", "es", "en", "er", "n", "s", "e")                    # bileşik bağlama sesleri (+ ∅, e-düşmesi)
BİLEŞEN_EN_KISA = 3
# Fiil gövdesi bileşeni (Wartezimmer = wart+e+zimmer, Lesezeit): en az 4 harf, Fugen yalnız ∅/e, sonraki parça en az 4
# harf. Kısa gövde + Fugen sahte bölüyordu (Gehalt ≠ geh+alt, gebührenfrei ≠ geb+uhr+en, kommentieren ≠ komm+en+tier).
FİİL_BİLEŞEN_EN_KISA = 4
FİİL_FUGEN = ("", "e")
# Yazı dilinde seyrek okumalar: aynı yüzeyin sık okuması varsa o seçilir
SEYREK = frozenset({"konj1", "emir", "yönelme_e", "ad_tamlayan"})


@dataclass(frozen=True)
class DeKök:
    tür: str
    ek_tür: tuple = ()
    çoğul: str = ""          # "" yok | e er en n s nen 0
    çoğul_gövde: str = ""
    umlaut: bool = False
    tamlayan: str = ""
    zayıf: bool = False
    sıfat_gövde: str = ""
    kom: str = ""
    sup: str = ""
    derecesiz: bool = False
    sınıf: str = ""          # fiil: "" zayıf | cekim.json örnek fiili
    ayrılır: str = ""        # ayrılabilir önek
    geyok: bool = False      # ortaç ge- almaz
    bileşensiz: bool = False  # bileşikte parça olamaz
    geri: bool = False

    def sınıflar(self) -> list[str]:
        sonuç = []
        for s in (self.tür, *self.ek_tür):
            if s in SINIFLAR and s not in sonuç:
                sonuç.append(s)
        return sonuç


class DeVeriHatası(Exception):
    def __init__(self, hatalar: list[str]):
        self.hatalar = hatalar
        super().__init__(f"DE verisinde {len(hatalar)} hata:\n  " + "\n  ".join(hatalar))


def sıra_anahtarı(s: str) -> tuple:
    """Alman sözlük sırası (DIN 5007-1): ä = a, ö = o, ü = u, ß = ss; eşitlikte kod noktası (deterministik)."""
    taban = unicodedata.normalize("NFD", s.replace("ß", "ss"))
    return ("".join(c for c in taban if not unicodedata.combining(c)), s)


def umlaut(s: str) -> str:
    """Son gövde ünlüsünü umlautlar: au → äu, a/aa → ä, o/oo → ö, u → ü (Haus → Häus, Saal → Säl, Boot → Böt)."""
    for i in range(len(s) - 1, -1, -1):
        if s[i] in "aou":
            if s[i] == "u" and i > 0 and s[i - 1] == "a":
                return s[:i - 1] + "äu" + s[i + 1:]
            if s[i] == "u" and i > 0 and s[i - 1] == "e":        # eu: umlaut yok (Freund)
                continue
            iki = i > 0 and s[i - 1] == s[i]
            yeni = {"a": "ä", "o": "ö", "u": "ü"}[s[i]]
            return s[:i - 1] + yeni + s[i + 1:] if iki else s[:i] + yeni + s[i + 1:]
    return s


# ── veri ────────────────────────────────────────────────────────────────────────────────────

def kökleri_yükle(yol: str | Path, sınıflar: dict) -> dict[str, DeKök]:
    return kökleri_çöz(Path(yol).read_text(encoding="utf-8").splitlines(), sınıflar)


def kökleri_çöz(satırlar, sınıflar: dict) -> dict[str, DeKök]:
    """kokler.txt satırları ('sözcük|tür[,ek_tür…]|bayrak[,bayrak…]', # yorum) → {sözcük: DeKök} (DeVeriHatası)."""
    sözlük: dict[str, DeKök] = {}
    hatalar: list[str] = []
    önceki = None
    for no, satır in enumerate(satırlar, 1):
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
            hatalar.append(f"{yer}: sözcük küçük DE harfleri olmalı")
            continue
        if önceki is not None and sıra_anahtarı(ad) <= sıra_anahtarı(önceki):
            hatalar.append(f"{yer}: sıra/tekillik bozuk (önceki {önceki!r})")
        önceki = ad
        if any(t not in TÜRLER for t in türler) or len(set(türler)) != len(türler):
            hatalar.append(f"{yer}: tür {türler} geçersiz ({sorted(TÜRLER)})")
            continue
        değer, düz = {}, set()
        for b in bayraklar:
            if "=" in b:
                a, d = b.split("=", 1)
                if a not in DEĞERLİ or not d:
                    hatalar.append(f"{yer}: bayrak {b!r} geçersiz")
                değer[a] = d
            elif b in BAYRAKLAR:
                düz.add(b)
            else:
                hatalar.append(f"{yer}: bayrak {b!r} geçersiz ({sorted(BAYRAKLAR)}, {sorted(DEĞERLİ)})")
        if "ç" in değer and değer["ç"] not in ÇOĞUL_EKLERİ:
            hatalar.append(f"{yer}: ç={değer['ç']} geçersiz ({sorted(ÇOĞUL_EKLERİ)})")
        if "g" in değer and değer["g"] not in TAMLAYAN:
            hatalar.append(f"{yer}: g={değer['g']} geçersiz")
        if ("ç" in değer or "g" in değer or "z" in düz) and not ({"isim", "özel"} & set(türler)):
            hatalar.append(f"{yer}: ç/g/z yalnız isimde")
        sınıf = değer.get("k", "")
        if "fiil" in türler:
            if not ad.endswith("n"):
                hatalar.append(f"{yer}: fiil mastarı -n ile biter")
            if sınıf:
                if sınıf not in sınıflar:
                    hatalar.append(f"{yer}: sınıf {sınıf!r} cekim.json'da yok")
                elif not ad.endswith(sınıf):
                    hatalar.append(f"{yer}: sınıf {sınıf!r} sözcüğün sonu olmalı")
        elif sınıf or "ay" in değer:
            hatalar.append(f"{yer}: k=/ay= yalnız fiilde")
        if "ay" in değer and not ad.startswith(değer["ay"]):
            hatalar.append(f"{yer}: ay={değer['ay']} sözcüğün başı olmalı")
        sözlük[ad] = DeKök(tür=türler[0], ek_tür=tuple(türler[1:]), çoğul=değer.get("ç", ""),
                           çoğul_gövde=değer.get("çk", ""), umlaut="u" in düz, tamlayan=değer.get("g", ""),
                           zayıf="z" in düz, sıfat_gövde=değer.get("sg", ""), kom=değer.get("kom", ""), sup=değer.get("sup", ""),
                           derecesiz="dk" in düz, geyok="geyok" in düz, bileşensiz="bz" in düz, sınıf=sınıf, ayrılır=değer.get("ay", ""), geri="geri" in düz)
    for ad, k in sözlük.items():
        if k.ayrılır and ad[len(k.ayrılır):] not in sözlük:
            hatalar.append(f"{ad!r}: ayrılabilir fiilin tabanı {ad[len(k.ayrılır):]!r} sözlükte yok")
    if hatalar:
        raise DeVeriHatası(hatalar)
    return sözlük


def sınıfları_yükle(yol: str | Path) -> dict:
    """cekim.json: güçlü/karışık/düzensiz örnek fiiller (mastar → alanlar). Alanlar: tekil23 (2./3. tekil şimdiki gövde:
    gib, fähr), geçmiş (gab), ortaç (geb; ek 'en', karışıkta 't'), konj2 (gäb), tür ('güçlü' | 'karışık'), emir (gib),
    şimdiki ([[gövde, ek]] × 6, modal/düzensiz), geçmiş_ekler (6 ek: wurd+e, schrie+n), ortaç_ek ('en' | 't' | 'n')."""
    ham = json.loads(Path(yol).read_text(encoding="utf-8"))
    hatalar = []
    for ad, s in ham.items():
        if s.get("tür") not in ("güçlü", "karışık"):
            hatalar.append(f"{ad!r}: tür güçlü|karışık")
        for alan in ("geçmiş", "ortaç"):
            if alan not in s:
                hatalar.append(f"{ad!r}: {alan} eksik")
        if "şimdiki" in s and len(s["şimdiki"]) != 6:
            hatalar.append(f"{ad!r}: şimdiki 6 kişi")
    if hatalar:
        raise DeVeriHatası(hatalar)
    return ham


@dataclass(frozen=True)
class DeEkler:
    ekler: frozenset
    sınıflar: dict

    def __hash__(self):
        return id(self)


def ekleri_yükle(yol: str | Path, sınıflar: dict) -> DeEkler:
    ham = json.loads(Path(yol).read_text(encoding="utf-8"))
    return DeEkler(ekler=frozenset(t for grup in ham["ekler"].values() for t in grup), sınıflar=sınıflar)


@cache
def veri_yükle(dizin: Path):
    """veri/de/: kokler.txt, ekler.json, cekim.json, istisnalar.json → (kökler, ekler, istisnalar). Üretilen her ek
    tokenı ekler.json'da bildirilmiş olmalı."""
    sınıflar = sınıfları_yükle(dizin / "cekim.json")
    kökler = kökleri_yükle(dizin / "kokler.txt", sınıflar)
    ekler = ekleri_yükle(dizin / "ekler.json", sınıflar)
    istisnalar = istisna_yükle(dizin / "istisnalar.json")
    hatalar = []
    for ad in sorted(kökler, key=sıra_anahtarı):
        for tokenlar, _ in biçimler(ad, kökler[ad], ekler, kökler):
            g = gövde_konumu(tokenlar, kökler[ad])
            önek = 0 if kökler[ad].ayrılır and tokenlar[0] == kökler[ad].ayrılır else -1   # önek bir sözcüktür
            for i, t in enumerate(tokenlar):
                if not t:
                    hatalar.append(f"{ad!r}: boş token ({tokenlar})")
                elif i not in (g, önek) and t not in ekler.ekler:
                    hatalar.append(f"{ad!r}: ek {t!r} ekler.json'da yok ({'+'.join(tokenlar)})")
    if hatalar:
        raise DeVeriHatası(sorted(set(hatalar))[:50])
    return kökler, ekler, istisnalar


def gövde_konumu(tokenlar, kök: DeKök) -> int:
    """Biçimde gövde tokenının sırası: ayrılabilir önek, ge- ve zu atlanır (an+ge+fang+en → 2). Diğer tokenlar ektir."""
    i = 1 if kök.ayrılır and len(tokenlar) > 1 and tokenlar[0] == kök.ayrılır else 0
    if len(tokenlar) > i + 1 and tokenlar[i] in ("ge", "zu"):
        i += 1
    return i


def _kök_tokenları(ad: str, kök: DeKök) -> tuple:
    """Kökün yalın okuması: ayrılabilir fiil önek + taban (an+fangen), diğerleri tek token."""
    if kök.ayrılır:
        return (kök.ayrılır, ad[len(kök.ayrılır):])
    return (ad,)


# ── üretim: ad ───────────────────────────────────────────────────────────────────────────────

def _ad(ad: str, kök: DeKök) -> list[tuple[tuple, str]]:
    sonuç: list[tuple[tuple, str]] = []
    if kök.zayıf:
        ek = "n" if ad.endswith("e") else "en"
        sonuç.append(((ad, ek), "zayıf"))
        if kök.tamlayan == "ns":                           # Name → Namens
            sonuç.append(((ad, "ns"), "tamlayan"))
        return sonuç
    if kök.tamlayan:
        sonuç.append(((ad, kök.tamlayan), "tamlayan"))
        if kök.tamlayan == "es":
            sonuç.append(((ad, "e"), "yönelme_e"))        # zu Hause, im Jahre
    if kök.çoğul:
        gövde = kök.çoğul_gövde or (umlaut(ad) if kök.umlaut else ad)
        if kök.çoğul == "0":
            çoğul = (gövde,) if gövde != ad else ()
        elif kök.çoğul == "e" and gövde.endswith("e") and not kök.çoğul_gövde:
            çoğul = (gövde,)
        else:
            çoğul = (gövde, kök.çoğul)
        yüzey = "".join(çoğul) if çoğul else ad
        if çoğul:
            sonuç.append((çoğul, "çoğul"))
        if not yüzey.endswith(("n", "s")):                 # yönelme çoğul -n: Kinder+n, Väter+n, Häus+er+n
            sonuç.append(((*(çoğul or (ad,)), "n"), "çoğul_yönelme"))
    return sonuç


# ── üretim: sıfat ────────────────────────────────────────────────────────────────────────────

def sıfat_gövdesi(ad: str) -> str:
    """Çekim gövdesi: -el → -l (dunkel → dunkl), -euer/-auer → -eur/-aur (teuer → teur), -e düşer (leise → leis)."""
    if ad.endswith("el") and len(ad) > 3 and ad[-3] not in ÜNLÜ:     # ünsüz + el (viel → viel+e, vil+e değil)
        return ad[:-2] + "l"
    if ad.endswith(("euer", "auer")):
        return ad[:-2] + "r"
    if ad.endswith("e"):
        return ad[:-1]
    return ad


def _sıfat(ad: str, kök: DeKök) -> list[tuple[tuple, str]]:
    g = kök.sıfat_gövde or sıfat_gövdesi(ad)
    sonuç = [((g, e), "sıfat") for e in SIFAT_EKLERİ]
    if kök.derecesiz:
        return sonuç
    kg = kök.kom or (umlaut(g) if kök.umlaut else g)
    sonuç.append(((kg, "er"), "üstünlük"))
    sonuç += [((kg, "er", e), "üstünlük") for e in SIFAT_EKLERİ]
    if kök.sup:
        sonuç += [((kök.sup, e), "enüstünlük") for e in SIFAT_EKLERİ]
    else:
        sg = umlaut(ad) if kök.umlaut else ad
        sg = sg[:-1] if sg.endswith("e") else sg
        ek = "est" if sg.endswith(("d", "t", "s", "ß", "z", "x", "sch")) and not sg.endswith(("end",)) else "st"
        sonuç += [((sg, ek, e), "enüstünlük") for e in SIFAT_EKLERİ]
    return sonuç


# ── üretim: fiil ─────────────────────────────────────────────────────────────────────────────

def _mastar_gövdesi(ad: str) -> str:
    return ad[:-2] if ad.endswith("en") else ad[:-1]       # machen → mach, wandern → wander, tun → tu


def _ek_ünlüsü(gövde: str) -> bool:
    """Zayıf çekimde e araya girer mi: gövde -t/-d ya da ünsüz + m/n (l/r/h hariç) ile biter (arbeit+et, öffn+et)."""
    if gövde.endswith(("t", "d")):
        return True
    return (len(gövde) >= 2 and gövde[-1] in "mn" and gövde[-2] not in ÜNLÜ and gövde[-2] not in "lrhmn")


def _şimdiki_ekleri(gövde: str, ln: bool) -> tuple:
    """1t 2t 3t 1ç 2ç 3ç (zayıf ve güçlü fiilin gövde değişmeyen kişileri)."""
    if ln:                                                 # wandern/handeln: wander+e, wander+st, wander+n
        return ("e", "st", "t", "n", "t", "n")
    e = _ek_ünlüsü(gövde)
    st = "t" if gövde.endswith(("s", "ß", "z", "x")) else ("est" if e else "st")
    return ("e", st, "et" if e else "t", "en", "et" if e else "t", "en")


def _sıfat_ekli(tokenlar: tuple, etiket: str) -> list[tuple[tuple, str]]:
    return [(tokenlar, etiket)] + [((*tokenlar, e), etiket) for e in SIFAT_EKLERİ]


def _fiil(ad: str, kök: DeKök, sınıflar: dict) -> list[tuple[tuple, str]]:
    """Fiil biçimleri (önek yok; ayrılabilir önek _ayrılır'da eklenir). Mastar = kök (bütün)."""
    gövde = _mastar_gövdesi(ad)
    ln = ad.endswith(("eln", "ern"))                       # wandern, handeln: -n mastarı
    s = sınıflar.get(kök.sınıf) if kök.sınıf else None
    önek = ad[:-len(kök.sınıf)] if s else ""               # ayrılmayan önekli fiil: ver + stehen
    ge = not (_ayrılmaz_mı(ad, kök) or ad.endswith("ieren"))
    sonuç: list[tuple[tuple, str]] = []
    if ad.endswith("eln"):                                 # ich handle (handel+e yanında, e düşer)
        sonuç.append(((gövde[:-2] + "l", "e"), "şimdiki"))
    ekler6 = _şimdiki_ekleri(gövde, ln)
    if s and "şimdiki" in s:
        sonuç += [((önek + g, e) if e else (önek + g,), "şimdiki") for g, e in s["şimdiki"]]
    else:
        t23 = önek + s["tekil23"] if s and "tekil23" in s else gövde
        for i, e in enumerate(ekler6):
            g = t23 if i in (1, 2) else gövde
            if i in (1, 2) and g != gövde:                 # güçlü 2./3. tekil: gib+st, gib+t, hält, lies+t
                e = ("t" if g.endswith(("s", "ß", "z", "x")) else "st") if i == 1 else ("" if g.endswith("t") else "t")
            sonuç.append(((g, e) if e else (g,), "şimdiki"))
    for e in ("e", "est", "e", "en", "et", "en"):          # konjunktiv I
        sonuç.append(((gövde, e), "konj1"))
    # geçmiş
    if s is None or s["tür"] == "karışık":
        gg = önek + s["geçmiş"] if s else gövde
        te = "ete" if s is None and _ek_ünlüsü(gövde) else "te"
        ekler = (te, te + "st", te, te + "n", te + "t", te + "n")
        sonuç += [((gg, e), "geçmiş") for e in ekler]
        if s and "konj2" in s:
            sonuç += [((önek + s["konj2"], e), "konj2") for e in ekler]
    else:
        gg = önek + s["geçmiş"]
        e_ara = gg.endswith(("t", "d"))
        st = "est" if gg.endswith(("t", "d", "s", "ß", "z")) else "st"
        for e in s.get("geçmiş_ekler", ("", st, "", "en", "et" if e_ara else "t", "en")):
            sonuç.append(((gg, e) if e else (gg,), "geçmiş"))
        if "konj2" in s:
            sonuç += [((önek + s["konj2"], e), "konj2") for e in ("e", "est", "e", "en", "et", "en")]
    # emir
    if s and "emir" in s:                                  # ünlüsü değişen emir: gib, nimm, lies (gibe yok)
        sonuç.append(((önek + s["emir"],), "emir"))
    else:
        sonuç += [((gövde,), "emir"), ((gövde, "e"), "emir")]
    # ortaçlar
    if s:
        og, oe = önek + s["ortaç"], s.get("ortaç_ek", "en" if s["tür"] == "güçlü" else "t")
    else:
        og, oe = gövde, "et" if _ek_ünlüsü(gövde) else "t"
    ortaç = ("ge", og, oe) if ge else (og, oe)
    sonuç += _sıfat_ekli(ortaç, "ortaç2")
    sonuç += _sıfat_ekli((gövde, "end") if not ln else (gövde, "nd"), "ortaç1")
    sonuç.append(((ad, "s"), "ad_tamlayan"))                # das Leben → des Lebens
    return sonuç


def _ayrılmaz_mı(ad: str, kök: DeKök) -> bool:
    """Ayrılmayan önekli fiil mi (ge- almaz)? Örnek fiilden uzun ve ayrılmayan önekle başlar (verstehen ← stehen);
    sözlükteki zayıf fiil için önek + sözlükte olmayan taban da sayılmaz (bekommen ← kommen sınıfıyla gelir)."""
    if kök.geyok:
        return True
    if kök.sınıf and ad != kök.sınıf:
        return ad[:-len(kök.sınıf)].endswith(AYRILMAZ)
    return False


def _ayrılır(ad: str, kök: DeKök, taban: list[tuple[tuple, str]]) -> list[tuple[tuple, str]]:
    """Ayrılabilir önekli fiil: önek + taban biçimleri (yan cümle: an+fäng+t), ortaç an+ge+fang+en, an+zu+fangen."""
    ö = kök.ayrılır
    sonuç = [((ö, *t), e) for t, e in taban if e != "ad_tamlayan"]
    sonuç.append(((ö, "zu", ad[len(ö):]), "zu_mastar"))
    return sonuç


def biçimler(ad: str, kök: DeKök, ekler: DeEkler, kökler=None) -> list[tuple[tuple, str]]:
    """Kökün çekimli biçimleri (yalın biçim hariç): [(tokenlar, ek_adı)]. Sıra deterministik."""
    sonuç: list[tuple[tuple, str]] = []
    for sınıf in kök.sınıflar():
        if sınıf == "fiil":
            if kök.ayrılır:
                taban_ad = ad[len(kök.ayrılır):]
                taban_kök = (kökler or {}).get(taban_ad) or DeKök(tür="fiil", sınıf=kök.sınıf if kök.sınıf
                                                                    and taban_ad.endswith(kök.sınıf) else "")
                sonuç += _ayrılır(ad, kök, _fiil(taban_ad, taban_kök, ekler.sınıflar))
            else:
                sonuç += _fiil(ad, kök, ekler.sınıflar)
        elif sınıf == "sıfat":
            sonuç += _sıfat(ad, kök)
        elif sınıf in ("isim", "özel"):
            sonuç += _ad(ad, kök)
    yalın = _kök_tokenları(ad, kök)
    görülen, benzersiz = set(), []
    for b in sonuç:
        if b not in görülen and b[0] != yalın and "".join(b[0]) != ad:
            görülen.add(b)
            benzersiz.append(b)
    return benzersiz


# ── çözümleme ───────────────────────────────────────────────────────────────────────────────

_DİZİNLER: dict = {}


def _dizin(kökler, ekler):
    """(yüzey → [(tokenlar, kök, ek_adı)], bileşen önekleri) — kök sözlüğü kimliğiyle önbellekli, deterministik.
    Bileşen = bileşiğin baş-dışı parçası olabilecek yüzey → tür: "ad" (ad/sıfat yalın), "edüş" (-e düşmüş ad: schul ←
    schule; Fugen almaz, energi+e = energie+∅ yinelemesi), "fiil" (gövde: spar ← sparen; FİİL_* kısıtları), "uml:<ek>"
    (umlautlu çoğul gövdesi: güt ← Gut/Güter; yalnız kendi çoğul ekiyle: güt+er+umschlag, büch+er+regal)."""
    kayıt = _DİZİNLER.get("de")
    if kayıt is None or kayıt[0] is not kökler:
        d: dict[str, list[tuple]] = {}
        bileşen: dict[str, str] = {}
        for ad in sorted(kökler, key=sıra_anahtarı):
            kök = kökler[ad]
            d.setdefault(ad, []).append((_kök_tokenları(ad, kök), ad, ""))
            for tokenlar, ek in biçimler(ad, kök, ekler, kökler):
                liste = d.setdefault("".join(tokenlar), [])
                if not any(t == tokenlar and k == ad for t, k, _ in liste):
                    liste.append((tokenlar, ad, ek))
            if kök.geri or kök.bileşensiz or kök.tür == "özel" or len(ad) < BİLEŞEN_EN_KISA:
                continue
            sınıflar = kök.sınıflar()
            if "isim" in sınıflar or "sıfat" in sınıflar:
                bileşen[ad] = "ad"
                if ad.endswith("e") and len(ad) - 1 >= BİLEŞEN_EN_KISA and "isim" in sınıflar:
                    bileşen.setdefault(ad[:-1], "edüş")
                if "isim" in sınıflar and kök.umlaut and kök.çoğul in ("er", "e") and not kök.çoğul_gövde:
                    bileşen.setdefault(umlaut(ad), "uml:" + kök.çoğul)   # Güter+umschlag = güt+er+umschlag
            if "fiil" in sınıflar and not kök.ayrılır:
                g = _mastar_gövdesi(ad)
                if len(g) >= FİİL_BİLEŞEN_EN_KISA:
                    bileşen.setdefault(g, "fiil")
        kayıt = _DİZİNLER["de"] = (kökler, d, bileşen)
    return kayıt[1], kayıt[2]


def _baş_uygun(kökler, k: str) -> bool:
    """Bileşiğin BAŞI (son parça) ad ya da sıfat olmalı (Arbeitsplatz, hochwertig değil: wertig sözlükte sıfatsa)."""
    kök = kökler[k]
    return kök.tür != "özel" and not kök.geri and not kök.bileşensiz and bool({"isim", "sıfat"} & set(kök.sınıflar()))


def _bileşik(kelime: str, kökler, ekler, istisnalar, derinlik: int = 0) -> list[tuple]:
    """Bileşik okumaları: [(tokenlar, baş_kök, ek_adı, parça_sayısı)]. Baş-dışı parça bileşen dizininden, ardından
    Fugen (ya da yok), kalan kısım ya üretilmiş bir biçim (baş) ya da yine bileşik (en çok 4 parça)."""
    dizin, bileşen = _dizin(kökler, ekler)
    sonuç = []
    for i in range(BİLEŞEN_EN_KISA, len(kelime) - BİLEŞEN_EN_KISA + 1):
        ön = kelime[:i]
        if ön not in bileşen:
            continue
        tür = bileşen[ön]
        for fuge in ("", *FUGEN):
            if ((fuge and tür == "edüş") or (tür == "fiil" and fuge not in FİİL_FUGEN)
                    or (tür.startswith("uml:") and fuge != tür[4:]) or not kelime.startswith(fuge, i)):
                continue
            kalan = kelime[i + len(fuge):]
            en_kısa = FİİL_BİLEŞEN_EN_KISA if tür == "fiil" else BİLEŞEN_EN_KISA   # sonraki parçanın kök tokenı
            if len(kalan) < en_kısa:
                continue
            ön_tokenlar = (ön, fuge) if fuge else (ön,)
            for t, k, e in dizin.get(kalan, ()):
                if _baş_uygun(kökler, k) and len(t[0]) >= en_kısa:
                    sonuç.append(((*ön_tokenlar, *t), k, e, 2))
            if derinlik < 2:
                for t, k, e, n in _bileşik(kalan, kökler, ekler, istisnalar, derinlik + 1):
                    if len(t[0]) >= en_kısa:
                        sonuç.append(((*ön_tokenlar, *t), k, e, n + 1))
    return sonuç


def _istisna(kelime: str, istisnalar):
    if not istisnalar:
        return None
    ist = istisnalar.get(kelime)
    return list(ist.tokens) if ist is not None else None


def çözümle(kelime: str, kökler, ekler: DeEkler, istisnalar=None) -> tuple[list[Çözüm], None]:
    """Sözcüğün tüm okumaları: istisna; üretilmiş biçim; yoksa bileşik. Bileşikte en az parçalı okumalar tek token
    dizisi vermiyorsa (Staubecken) çözüm YOK → bütün + kuyruk (ilke #3). (çözümler, None) — EN/FR arayüzü."""
    ist = _istisna(kelime, istisnalar)
    if ist is not None:
        return [Çözüm(tokens=ist, kök=kelime, ekler=[])], None
    dizin, _ = _dizin(kökler, ekler)
    çözümler = [Çözüm(tokens=list(t), kök=k, ekler=[e] if e else []) for t, k, e in dizin.get(kelime, ())]
    if çözümler:
        return çözümler, None
    seçilen = bileşik_seç(_bileşik(kelime, kökler, ekler, istisnalar))
    if seçilen is None:
        return [], None                                    # bileşik yok ya da belirsiz: tahmin yok
    t, k, e, n = seçilen
    return [Çözüm(tokens=list(t), kök=k, ekler=["bileşik"] * (n - 1) + ([e] if e else []))], None


def _sınırlar(tokenlar: tuple) -> tuple:
    """Parça başlangıçları (karakter konumu); Fugen tokenı önceki parçaya sayılır: wart+e+zimmer ≡ warte+zimmer."""
    konum, sınır = 0, []
    for i, t in enumerate(tokenlar):
        if i == 0 or t not in FUGEN:
            sınır.append(konum)
        konum += len(t)
    return tuple(sınır)


def bileşik_seç(adaylar: list[tuple]):
    """En az parçalı okumalar; parça sınırları hepsinde aynıysa (Fugen yazımı farkı: krank+en / kranke+n) en az token,
    sonra en uzun parçalar seçilir; sınırlar farklıysa (stau+becken / staub+ecken) None = belirsiz, bütün tut."""
    if not adaylar:
        return None
    en_az = min(a[3] for a in adaylar)
    adaylar = [a for a in adaylar if a[3] == en_az]
    # parça başlangıçları (Fugen ve baştaki çekim eki önceki parçada sayılır: lampe+n ≡ lampen)
    if len({_sınırlar(a[0]) for a in adaylar}) > 1:
        return None
    return min(adaylar, key=lambda a: (len(a[0]), [-len(t) for t in a[0]], a[0], a[1], a[2]))



def en_iyi(çözümler: list[Çözüm], kökler=None, ad_okuma: bool = False) -> Çözüm:
    """Özel ad SONDA → yazım biçimine uymayan okuma SONDA (Başlık biçimi: ad okuması; küçük harf / HEP BÜYÜK: ad
    olmayan okuma — Almanca yazım kuralı: her ad büyük yazılır; Habe ~ habe = hab+e) → geri kök SONDA → BÜTÜN kök → en az ek → seyrek kip sonda → gövdesi değişmemiş okuma → en az
    token → en uzun kök → tam kırıcı. Geri kök bütün kökten ÖNCE (FR'den fark): Almancada sık çekim biçimiyle aynı
    yazılan seyrek lemma bol (Lampen ~ lampe+n, schönen 'süslemek' ~ schön+en); geri bayrağı korpus aile sıklığıyla
    AYNI TÜR okumalar arasında verilir (kaynak_uret.py). ad_okuma: sözcük Başlık biçiminde (profil.ad_büyük)."""
    kökler = kökler or {}
    geri = {ç.kök for ç in çözümler if getattr(kökler.get(ç.kök), "geri", False)
            and any(d.kök != ç.kök for d in çözümler)}
    return min(çözümler, key=lambda ç: (
        getattr(kökler.get(ç.kök), "tür", "") == "özel", _tür_uyumsuz(ç, kökler, ad_okuma), ç.kök in geri,
        0 if not ç.ekler else 1, len(ç.ekler), sum(e in SEYREK for e in ç.ekler), _gövde_değişti(ç, kökler),
        len(ç.tokens), -len(ç.kök), tuple(ç.tokens), ç.kök, tuple(ç.ekler)))


AD_EKLERİ = frozenset({"çoğul", "çoğul_yönelme", "tamlayan", "yönelme_e", "zayıf"})


def okuma_türü(ç: Çözüm, kökler) -> str:
    """Okumanın türü: 'ad' (ad çekimi ya da yalnız ad olan kökün yalın biçimi), 'diğer' (fiil/sıfat biçimi), 'ikisi'
    (hem ad hem başka sınıfı olan kökün yalın biçimi: Leben, Essen). Bileşikte baş belirler; istisna 'ikisi'."""
    kök = kökler.get(ç.kök)
    if kök is None:
        return "ikisi"
    ek = [e for e in ç.ekler if e != "bileşik"]
    if ek:
        return "ad" if ek[-1] in AD_EKLERİ else "diğer"
    sınıflar = set(kök.sınıflar())
    adlar = sınıflar & {"isim", "özel"}
    return "ikisi" if adlar and sınıflar - adlar else "ad" if adlar else "diğer"


def _tür_uyumsuz(ç: Çözüm, kökler, ad_okuma: bool) -> bool:
    tür = okuma_türü(ç, kökler)
    return tür != "ikisi" and (tür == "ad") != ad_okuma


def _gövde_değişti(ç: Çözüm, kökler) -> bool:
    """Gövde + ek okumasında gövde tokenı lemma/mastar gövdesinden farklı mı (umlaut, ablaut)? Tek tokenlı düzensiz biçim
    gövde değişimi sayılmaz."""
    kök = kökler.get(ç.kök)
    if len(ç.tokens) < 2 or "bileşik" in ç.ekler or kök is None:
        return False
    g = ç.tokens[gövde_konumu(ç.tokens, kök)]
    ad = ç.kök[len(kök.ayrılır):]
    return g not in (ad, _mastar_gövdesi(ad), sıfat_gövdesi(ad))


# ── yedek heceleme ──────────────────────────────────────────────────────────────────────────

# İzinli hece başı ünsüz kümeleri (kapalı liste; tek ünsüz her zaman izinli). sch/ch/ph/qu tek ses birimi.
BAŞ_KÜMELERİ = frozenset("bl br ch ck dr fl fr gl gr kl kn kr pf pfl pfr ph pl pr qu sch schl schm schn schr schw sp spr "
                         "st str tr zw".split())
ÇİFT_ÜNLÜ = ("ei", "ie", "eu", "äu", "au", "aa", "ee", "oo")


def hecele(kelime: str) -> list[str]:
    """Yazım hecesi (yedek; morfem iddiası yok): ünlü grubu çekirdek (ei, ie, eu, äu, au + ikiz ünlü), aradaki
    ünsüzlerden izinli en uzun baş kümesi sağa, kalanı sola. Birleşim = girdi (kayıpsız)."""
    çekirdekler: list[tuple[int, int]] = []
    i = 0
    while i < len(kelime):
        if kelime[i] in ÜNLÜ:
            j = i + 1
            if kelime[i:i + 2] in ÇİFT_ÜNLÜ:
                j = i + 2
            çekirdekler.append((i, j))
            i = j
        else:
            i += 1
    if len(çekirdekler) < 2:
        return [kelime] if kelime else []
    sınırlar = [0]
    for (_, a_son), (b_baş, _) in zip(çekirdekler, çekirdekler[1:]):
        küme = kelime[a_son:b_baş]
        baş = 1 if küme else 0
        for n in (4, 3, 2):
            if len(küme) >= n and küme[-n:] in BAŞ_KÜMELERİ:
                baş = n
                break
        sınırlar.append(b_baş - baş)
    return [kelime[a:b] for a, b in zip(sınırlar, sınırlar[1:] + [len(kelime)])]

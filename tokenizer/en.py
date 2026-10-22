"""İngilizce sözcük çözümleyicisi (EN-1): kök sözlüğü + ek kuralı + ÜRET-DOĞRULA.

Türk dillerinin üreteci (birlestir/cozumle) ünlü uyumu, tampon ve yumuşama üzerine kuruludur; İngilizcede bunların
hiçbiri yoktur, yerine YAZIM kuralları vardır. İlke aynıdır: aday (önek, kök, ek dizisi) üreteçle (üret) yüzeye
çevrilir, yüzey sözcüğe eşitse çözüm kabul edilir; kural tersine kodlanmaz. Hat (pipeline), casing, vocab, dil kapısı,
onay kuyruğu ortaktır.

Token kuralları (plan docs/arastirma/en_plan.md §2):
  - Kök tek token (vocab'da yoksa vocab katmanı hece → harf → bayta indirir; morfem sınırı korunur).
  - Ek tek token: s/es, ed, ing, er, est, ly, ness, ment, ful, less, able …
  - Yazım değişimi kök TOKENINDA (Türkçe yumuşama gibi): making = [mak, ing], carried = [carri, ed],
    knives = [kniv, es]; ÇİFT ünsüz AYRI tampon token (Türkçe tampon gibi): running = [run, n, ing].
  - Önek ayrı token: unhappy = [un, happy], redo = [re, do].
  - Klitik ayrı token (kesme dahil): don't = [do, n't], it's = [it, 's].
  - Düzensiz biçim (went, children, better) bütün token (istisnalar.json 'düzensiz' grubu).

Seçim (deterministik): BÜTÜN kök → en az ek/önek → en uzun kök → en az token → tam kırıcı. Eksik sözlükte sahte bölmeyi
bütün-kök önceliği ve ek-sınıf kısıtı önler (corner ≠ corn+er: -er karşılaştırması sıfat, kişi -er fiil ister).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from functools import cache
from pathlib import Path

from tokenizer.cozumle import Çözüm
from tokenizer.istisna import yükle as istisna_yükle

ÜNLÜ = frozenset("aeiou")
SINIFLAR = frozenset({"isim", "fiil", "sıfat", "zarf"})            # ek alan açık sınıflar
KAPALI = frozenset({"zamir", "belirteç", "edat", "bağlaç", "ünlem", "sayı", "yardımcı"})   # ek almaz (klitik alır)
TÜRLER = SINIFLAR | KAPALI | {"özel"}
BAYRAKLAR = frozenset({"çift", "çift2", "es", "ves", "dg", "dç", "dk", "geri"})
# Düzensiz biçimi olan kökte düzenli ek YOK (see → saw: seed ≠ see+ed; be: bed ≠ be+ed; child → children)
ENGEL = {"dg": "geçmiş", "dç": "çoğul", "dk": ("karşılaştırma", "üstünlük")}
_S_GRUBU = ("s", "x", "z", "ch", "sh")
MAX_EK = 4
ÖNEK_KÖK_EN_KISA = 4
KESMELER = ("'", "’")


@dataclass(frozen=True)
class EnKök:
    tür: str
    ek_tür: tuple = ()
    çift: bool = False     # son ünsüz ünlü-başlı ek önünde ikizlenir, ikizi AYRI token (run → run+n+ing; stop+p+ed)
    es: bool = False       # o-sonu -es alır (go → goes, hero → heroes; photo → photos bayraksız)
    ves: bool = False      # f/fe → v + es (knife → kniv+es, leaf → leav+es; roof → roofs bayraksız)
    çift2: bool = False    # ikizleme isteğe bağlı: iki yazım da yaygın (travel → traveled / travel+l+ed)
    engel: frozenset = frozenset()   # kökün hemen ardından gelemeyen düzenli ekler (düzensiz biçimi var)
    geri: bool = False     # eşsesli çakışmada geri çekilir: aynı yüzeyi daha yaygın bir kök de üretiyorsa o yeğlenir
    #                        (korpus kararı, scripts/en_sozluk/kaynak_uret.py: does = do+es, doe+s değil; putting = put+t+ing)

    def sınıflar(self) -> list[str]:
        sonuç = []
        for t in (self.tür, *self.ek_tür):
            s = "isim" if t == "özel" else t
            if s in SINIFLAR and s not in sonuç:
                sonuç.append(s)
        return sonuç


@dataclass(frozen=True)
class EnEk:
    yüzey: str
    öbek: frozenset        # eklendiği gövde sınıfları
    yuva: int              # sıra: yapım 1 < çekim 2 (çıkış zonu sıfırlar: care+less+ness, build+ing+s)
    çıkış: str = ""        # sınıf değiştiren ek: gövdenin yeni sınıfı
    önek: bool = False     # önek (un-, re-…): kökten ÖNCE, sınıfı korur
    s_eki: bool = False    # -s/-es ailesi (çoğul, 3. tekil): es/ies/ves kuralı


class EnVeriHatası(Exception):
    def __init__(self, hatalar: list[str]):
        self.hatalar = hatalar
        super().__init__(f"EN verisinde {len(hatalar)} hata:\n  " + "\n  ".join(hatalar))


# ── veri ────────────────────────────────────────────────────────────────────────────────────

def kökleri_yükle(yol: str | Path) -> dict[str, EnKök]:
    """kokler.txt: 'sözcük|tür[,ek_tür…]|bayrak[,bayrak…]' satırları, # yorum. Sözcük küçük a-z, tekil, sıralı."""
    sözlük: dict[str, EnKök] = {}
    hatalar: list[str] = []
    önceki = ""
    for no, satır in enumerate(Path(yol).read_text(encoding="utf-8").splitlines(), 1):
        satır = satır.strip()
        if not satır or satır.startswith("#"):
            continue
        alanlar = satır.split("|")
        while len(alanlar) < 3:
            alanlar.append("")
        ad, türler, bayraklar = alanlar[0], alanlar[1].split(","), [b for b in alanlar[2].split(",") if b]
        yer = f"{no}: {ad!r}"
        if not ad or not all("a" <= c <= "z" for c in ad):
            hatalar.append(f"{yer}: sözcük küçük a-z olmalı")
            continue
        if ad <= önceki:
            hatalar.append(f"{yer}: sıra/tekillik bozuk (önceki {önceki!r})")
        önceki = max(önceki, ad)
        if any(t not in TÜRLER for t in türler) or len(set(türler)) != len(türler):
            hatalar.append(f"{yer}: tür {türler} geçersiz ({sorted(TÜRLER)})")
            continue
        if any(b not in BAYRAKLAR for b in bayraklar):
            hatalar.append(f"{yer}: bayrak {bayraklar} geçersiz ({sorted(BAYRAKLAR)})")
            continue
        if ("çift" in bayraklar or "çift2" in bayraklar) and (ad[-1] in ÜNLÜ or ad[-1] in "wxy"):
            hatalar.append(f"{yer}: çift yalnız ünsüz-sonu kökte (w/x/y hariç)")
        if "es" in bayraklar and not ad.endswith("o"):
            hatalar.append(f"{yer}: es yalnız o-sonu kökte")
        if "ves" in bayraklar and not ad.endswith(("f", "fe")):
            hatalar.append(f"{yer}: ves yalnız f/fe-sonu kökte")
        engel = set()
        for b in bayraklar:
            e = ENGEL.get(b)
            if e:
                engel.update((e,) if isinstance(e, str) else e)
        sözlük[ad] = EnKök(tür=türler[0], ek_tür=tuple(türler[1:]), çift="çift" in bayraklar,
                           es="es" in bayraklar, ves="ves" in bayraklar, çift2="çift2" in bayraklar,
                           engel=frozenset(engel), geri="geri" in bayraklar)
    if hatalar:
        raise EnVeriHatası(hatalar)
    return sözlük


def ekleri_yükle(yol: str | Path) -> dict[str, EnEk]:
    ham = json.loads(Path(yol).read_text(encoding="utf-8"))
    ekler, hatalar = {}, []
    for ad, g in ham.items():
        öbek = frozenset(g.get("öbek", ()))
        ek = EnEk(yüzey=g.get("yüzey", ""), öbek=öbek, yuva=g.get("yuva", 0), çıkış=g.get("çıkış", ""),
                  önek=g.get("önek", False), s_eki=g.get("s_eki", False))
        if not ek.yüzey or not all("a" <= c <= "z" for c in ek.yüzey):
            hatalar.append(f"{ad!r}: yüzey küçük a-z olmalı")
        if not öbek or not öbek <= SINIFLAR:
            hatalar.append(f"{ad!r}: öbek {sorted(öbek)} ⊄ {sorted(SINIFLAR)}")
        if ek.çıkış and ek.çıkış not in SINIFLAR:
            hatalar.append(f"{ad!r}: çıkış {ek.çıkış!r} geçersiz")
        if not ek.önek and ek.yuva not in (1, 2):
            hatalar.append(f"{ad!r}: yuva 1 (yapım) ya da 2 (çekim) olmalı")
        ekler[ad] = ek
    if hatalar:
        raise EnVeriHatası(hatalar)
    return ekler


@cache
def veri_yükle(dizin: Path):
    """veri/en/: kokler.txt, ekler.json, istisnalar.json (işlev/düzensiz/kısaltma) → (kökler, ekler, istisnalar)."""
    kökler = kökleri_yükle(dizin / "kokler.txt")
    ekler = ekleri_yükle(dizin / "ekler.json")
    istisnalar = istisna_yükle(dizin / "istisnalar.json")
    return kökler, ekler, istisnalar


# ── üretim ──────────────────────────────────────────────────────────────────────────────────

def _ünsüz_y(gövde: str) -> bool:
    """Ünsüz + y sonu (carry, happy): ek önünde y → i. Ünlü + y (play, enjoy) korunur."""
    return len(gövde) > 1 and gövde[-1] == "y" and gövde[-2] not in ÜNLÜ


def üret(kök_ad: str, kök: EnKök, ek_adları, ekler, önek: str | None = None) -> tuple[list[str], str]:
    """(önek) + kök + ekler → (token listesi, yüzey). Yazım değişimi son kök/ek tokenında; ikiz ünsüz ayrı token."""
    tokenlar = ([ekler[önek].yüzey] if önek else []) + [kök_ad]
    gövde = "".join(tokenlar)

    def son_değiştir(sil: int, ek: str = ""):
        nonlocal gövde
        tokenlar[-1] = tokenlar[-1][:len(tokenlar[-1]) - sil] + ek
        gövde = gövde[:len(gövde) - sil] + ek

    for i, ad in enumerate(ek_adları):
        ek = ekler[ad]
        s = ek.yüzey
        ilk = i == 0                                   # kök bayrakları yalnız kökün hemen ardından
        if ek.s_eki:
            if gövde.endswith(_S_GRUBU) or (ilk and kök.es and gövde.endswith("o")):
                s = "es"
            elif _ünsüz_y(gövde):
                son_değiştir(1, "i"); s = "es"         # study → studi+es
            elif ilk and kök.ves:
                son_değiştir(2 if gövde.endswith("fe") else 1, "v"); s = "es"   # knife → kniv+es
        elif s[0] in ÜNLÜ:
            if gövde.endswith("e"):
                if s == "ing" and gövde.endswith(("ee", "ye", "oe", "inge")):
                    pass                               # seeing, dyeing, singeing (singing = sing+ing kalsın)
                elif s == "ing" and gövde.endswith("ie"):
                    son_değiştir(2, "y")               # tie → ty+ing
                else:
                    son_değiştir(1)                    # make → mak+ing, like → lik+ed, agree → agre+ed
            elif _ünsüz_y(gövde) and s[0] != "i":
                son_değiştir(1, "i")                   # carry → carri+ed, happy → happi+er
            elif ilk and kök.çift:
                tokenlar.append(gövde[-1])             # run → run+n+ing (ikiz ayrı tampon token)
                gövde += gövde[-1]
        elif _ünsüz_y(gövde) and ad != "yapım_ment":
            son_değiştir(1, "i")                       # happy → happi+ly / happi+ness, beauty → beauti+ful
        tokenlar.append(s)
        gövde += s
    return tokenlar, gövde


# ── çözümleme ───────────────────────────────────────────────────────────────────────────────

def _varyantlar(ad: str, kök: EnKök) -> set[str]:
    """Kökün sözcük başında görünebileceği biçimleri (aday bulma; doğrulama üretecindir)."""
    v = {ad}
    if ad.endswith("e"):
        v.add(ad[:-1])
        if ad.endswith("ie"):
            v.add(ad[:-2] + "y")
    if _ünsüz_y(ad):
        v.add(ad[:-1] + "i")
    if kök.ves:
        v.add(ad[:-2] + "v" if ad.endswith("fe") else ad[:-1] + "v")
    return v


_DİZİNLER: dict = {}


def _dizin(kökler) -> dict[str, list[str]]:
    """varyant → kökler (kökler sözlüğü kimliğiyle önbellekli; sıralı → deterministik)."""
    kayıt = _DİZİNLER.get("en")
    if kayıt is None or kayıt[0] is not kökler:
        d: dict[str, list[str]] = {}
        for ad in sorted(kökler):
            for v in _varyantlar(ad, kökler[ad]):
                d.setdefault(v, []).append(ad)
        kayıt = _DİZİNLER["en"] = (kökler, d)
    return kayıt[1]


def _ara(kök_ad, kök, önek, dizi, son_yuva, sınıf, hedef, ekler, çıktı):
    tokenlar, yüzey = üret(kök_ad, kök, dizi, ekler, önek)
    if yüzey == hedef:
        çıktı.append(Çözüm(tokens=tokenlar, kök=kök_ad, ekler=([önek] if önek else []) + list(dizi)))
        return
    if len(dizi) >= MAX_EK or not hedef.startswith(yüzey[:-2]):
        return
    for ad in sorted(ekler):
        ek = ekler[ad]
        if ek.önek or sınıf not in ek.öbek or ek.yuva <= son_yuva:
            continue
        if not dizi and ad in kök.engel:              # düzensiz biçimli kökte düzenli ek yok
            continue
        _, y = üret(kök_ad, kök, dizi + [ad], ekler, önek)
        # öneki tutan dala in; son iki harf sonraki ekle değişebilir (happi+ness → happi+ness+es değil ama
        # care+less → care+less+ness; y→i, e düşmesi) → iki harf payı
        if hedef.startswith(y[:-2]):
            if ek.çıkış:
                _ara(kök_ad, kök, önek, dizi + [ad], 0, ek.çıkış, hedef, ekler, çıktı)
            else:
                _ara(kök_ad, kök, önek, dizi + [ad], ek.yuva, sınıf, hedef, ekler, çıktı)


def _gövde_çözümle(hedef: str, kökler, ekler, istisnalar) -> list[Çözüm]:
    """Klitiksiz sözcük: istisna (işlev/düzensiz) ya da (önek) + kök + ekler okumaları."""
    ist = istisnalar.get(hedef) if istisnalar else None
    if ist is not None:
        return [Çözüm(tokens=list(ist.tokens), kök=hedef, ekler=[])]
    dizin = _dizin(kökler)
    çözümler: list[Çözüm] = []
    önekler = [None] + sorted(a for a, e in ekler.items() if e.önek and hedef.startswith(e.yüzey))
    for önek in önekler:
        baş = len(ekler[önek].yüzey) if önek else 0
        for son in range(baş + 1, len(hedef) + 1):
            for kök_ad in dizin.get(hedef[baş:son], ()):
                kök = kökler[kök_ad]
                sınıflar = kök.sınıflar()
                if önek:
                    # önek kökü en az 4 harf: kısa kök sahte bölmesi (univ = un+iv, dispro = dis+pro) önlenir; kısa
                    # köklü gerçek önekli sözcük (redo, reset, untie) sözlükte bütün kök
                    if kök.tür in KAPALI or len(kök_ad) < ÖNEK_KÖK_EN_KISA:
                        continue
                    sınıflar = [s for s in sınıflar if s in ekler[önek].öbek]
                if not sınıflar and not önek:               # kapalı sınıf: yalnız bütün okunur
                    if kök_ad == hedef:
                        çözümler.append(Çözüm(tokens=[kök_ad], kök=kök_ad, ekler=[]))
                    continue
                for sınıf in sınıflar:
                    _ara(kök_ad, kök, önek, [], 0, sınıf, hedef, ekler, çözümler)
                    if kök.çift2:                       # ikizlemesiz yazım da geçerli (traveled)
                        _ara(kök_ad, replace(kök, çift2=False, çift=not kök.çift), önek, [], 0, sınıf, hedef,
                             ekler, çözümler)
    görülen, benzersiz = set(), []
    for ç in çözümler:
        a = (tuple(ç.tokens), ç.kök, tuple(ç.ekler))
        if a not in görülen:
            görülen.add(a)
            benzersiz.append(ç)
    return benzersiz


def klitik_ayır(kelime: str, klitikler) -> tuple[str, str] | None:
    """'don't' → ('do', "n't"); "it’s" → ('it', "’s"). Klitik kesme biçimi korunur (kayıpsız)."""
    for k in klitikler:
        for kesme in KESMELER:
            kk = k.replace("'", kesme)
            if kelime.endswith(kk) and len(kelime) > len(kk) and kelime[-len(kk) - 1] not in KESMELER:
                return kelime[:-len(kk)], kk
    return None


def çözümle(kelime: str, kökler, ekler, istisnalar=None, klitikler=()) -> tuple[list[Çözüm], str | None]:
    """(çözümler, bilinmeyen_taban). Klitikli sözcükte taban çözülemezse çözüm [taban, klitik] ve taban döner
    (bilinmeyen kuyruğa TABAN gider: Mary's → 'mary')."""
    if istisnalar and kelime in istisnalar:
        return [Çözüm(tokens=list(istisnalar[kelime].tokens), kök=kelime, ekler=[])], None
    ayrım = klitik_ayır(kelime, klitikler)
    if ayrım is None:
        return _gövde_çözümle(kelime, kökler, ekler, istisnalar), None
    taban, kk = ayrım
    ad = "klitik_" + kk.replace("’", "'")
    çs = _gövde_çözümle(taban, kökler, ekler, istisnalar)
    if not çs:
        return [Çözüm(tokens=[taban, kk], kök=taban, ekler=[ad])], taban
    return [Çözüm(tokens=ç.tokens + [kk], kök=ç.kök, ekler=ç.ekler + [ad]) for ç in çs], None


def en_iyi(çözümler: list[Çözüm], kökler=None) -> Çözüm:
    """BÜTÜN kök → en az ek/önek → öneksiz (missing = miss+ing, mis+sing değil) → GERİ kök (başka kök yarışıyorsa) →
    en uzun kök → en az token → tam kırıcı."""
    kökler = kökler or {}
    geri = {ç.kök for ç in çözümler if getattr(kökler.get(ç.kök), "geri", False)
            and any(d.kök != ç.kök for d in çözümler)}
    return min(çözümler, key=lambda ç: (
        0 if not [e for e in ç.ekler if not e.startswith("klitik_")] else 1,
        len(ç.ekler), sum(e.startswith("önek_") for e in ç.ekler), ç.kök in geri, -len(ç.kök), len(ç.tokens), tuple(ç.tokens), ç.kök, tuple(ç.ekler)))


# ── yedek heceleme ──────────────────────────────────────────────────────────────────────────

# İzinli hece başı ünsüz kümeleri (kapalı liste). Tek ünsüz her zaman izinli.
BAŞ_KÜMELERİ = frozenset((
    "bl br ch cl cr dr dw fl fr gl gr kn ph pl pr qu sc sh sk sl sm sn sp st sw th tr tw wh wr "
    "chr sch scr shr sph spl spr squ str thr").split())


def _ünlü_mü(s: str, i: int) -> bool:
    c = s[i]
    if c in ÜNLÜ:
        return True
    # y: sözcük başında ya da ünlüden önce ünsüz (yes, player); aksi halde ünlü (gym, happy, rhythm)
    return c == "y" and i > 0 and not (i + 1 < len(s) and s[i + 1] in ÜNLÜ)


def hecele(kelime: str) -> list[str]:
    """Yazım hecesi (yedek; morfem iddiası yok): ünlü grubu çekirdek, aradaki ünsüzlerden izinli en uzun baş kümesi
    sağa, kalanı sola. Birleşim = girdi (kayıpsız). Harf dışı karakter ünsüz sayılır."""
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
        for n in (3, 2):
            if len(küme) >= n and küme[-n:] in BAŞ_KÜMELERİ:
                baş = n
                break
        sınırlar.append(b_baş - baş)
    return [kelime[a:b] for a, b in zip(sınırlar, sınırlar[1:] + [len(kelime)])]

"""Birleştirme motoru (ÜRETİM): kök + ek listesi → token dizisi + yüzey biçimi.

v1 kapsam: isim zincirleri (çoğul + iyelik + hâl). Yön: üretim (generation) — sonra
çözümleyici için referans/oracle olur.

Token kuralları (CLAUDE.md ile uyumlu):
  - Kök kendi hece tokenlarıyla gelir.
  - Tampon ÜNSÜZ (y/n/s) AYRI token olur:  araba+yönelme → [a, ra, ba, y, a]
  - Ek gövdesi (yardımcı ünlü dahil) tek token olur:  ev+iyelik1 → [ev, im]
  - Kök ünsüz yumuşaması (kitap→kitab) köke uygulanır: ünlüyle başlayan ilk ek gelince.

v1 DIŞI (sonraki kararlar): geniş zaman -Ar/-Ir (sözlüksel düzensiz),
olumsuz+şimdiki (gelme+iyor→gelmiyor), ek-fiil -(y)sA, ek sırası doğrulaması.
"""

from __future__ import annotations

from tokenizer import sesler
from tokenizer.ekler import Ek, ek_çöz


# Pronominal -n-: 3. tekil/çoğul iyelikten sonra HÂL eki gelince araya -n- girer
# (araba+sı+n+da, ev+i+n+de, ev+leri+n+de). Ayrı tampon token olur.
PRONOMİNAL_N = frozenset({"iyelik_3tekil", "iyelik_3çoğul"})
# -n- alan hâl ekleri (5 durum); araç -(y)lA kendi -y- tamponunu kullanır (arabasıyla,
# arabasınla DEĞİL) → araç ve -ki HARİÇ.
HÂL_PRONOMİNAL_N = frozenset({"belirtme", "yönelme", "bulunma", "ayrılma", "tamlayan"})


# Geniş zamanda -Ir alan tek-heceli fiiller (kapalı, bilinen küme); gerisi -Ar/-r.
GENİŞ_IR = frozenset({"al", "bil", "bul", "dur", "den", "gel", "gör", "kal", "kıl",
                      "ol", "öl", "san", "var", "ver", "vur"})


def _geniş_şablon(gövde: str, ad: str) -> str:
    """Geniş zaman ekinin köke göre şablonu: ünlü-sonu→r, çok-heceli ünsüz→Ir,
    tek-heceli→Ar (istisna kümesi→Ir)."""
    if gövde[-1] in sesler.ÜNLÜLER:
        return "r"
    çok_heceli = sum(1 for c in gövde if c in sesler.ÜNLÜLER) > 1
    if çok_heceli:
        return "Ir"
    return "Ir" if ad in GENİŞ_IR else "Ar"


def _edilgen_şablon(gövde: str) -> str:
    """Edilgen (pasif) çatı şablonu: ünlü/l-sonu → (I)n (okun/alın), ünsüz → (I)l (yapıl)."""
    son = gövde[-1]
    return "(I)n" if (son in sesler.ÜNLÜLER or son == "l") else "(I)l"


def _ettirgen_şablon(gövde: str) -> str:
    """Ettirgen (oldurgan) çatı şablonu: ünlü/r-sonu → t (okut/oturt), ünsüz → DIr (yaptır)."""
    son = gövde[-1]
    return "t" if (son in sesler.ÜNLÜLER or son == "r") else "DIr"


def _ünlü_düşür(s: str) -> str:
    """Sözcüğün SON ünlüsünü düşürür (ünlü düşmesi): akıl→akl, ağız→ağz, kıl→kl."""
    for j in range(len(s) - 1, -1, -1):
        if s[j] in sesler.ÜNLÜLER:
            return s[:j] + s[j + 1:]
    return s


def _e_i(s: str) -> str:
    """ye/de düzensizi: sözcüğün son ünlüsü e→i (ye→yi, de→di). Diğer ünlü değişmez."""
    for j in range(len(s) - 1, -1, -1):
        if s[j] in sesler.ÜNLÜLER:
            return s[:j] + ("i" if s[j] == "e" else s[j]) + s[j + 1:]
    return s


def _yumuşat_son(s: str, değişim: dict) -> str:
    """Sözcüğün son ünsüzünü değişim kuralına göre yumuşatır (kitap→kitab)."""
    for kural in değişim:               # ör. "p→b"
        eski, yeni = kural.split("→")
        if s.endswith(eski):
            return s[: -len(eski)] + yeni
    return s


def _ince_çevir(ünlü: str) -> str:
    """İstisnai uyum: art ünlüyü ince karşılığına çevirir (yuvarlaklık korunur):
    a→e, ı→i, o→ö, u→ü (ince ünlüler değişmez). kalp(a)→e ⇒ kalbi, rol(o)→ö ⇒ rolü."""
    return {"a": "e", "ı": "i", "o": "ö", "u": "ü", "â": "e", "û": "ü"}.get(ünlü, ünlü)


def _çöz_parça(şablon: str, gövde: str, son_ü: str | None = None) -> tuple[str, str]:
    """Eki çözüp (tampon, gövde_eki) döndürür.

    Şablondaki parantezli tampon (ünlü ya da ünsüz) emildiyse AYRI token olur
    (CLAUDE.md: gel+Iyor → [gel, i, yor]; araba+A → [araba, y, a]). Tamponlar tek
    karakterdir, bu yüzden yüzey[0] tampon, yüzey[1:] ek gövdesidir.
    `son_ü` (istisnai uyum çapası) verilirse ek_çöz'e geçirilir.
    """
    yüzey = ek_çöz(şablon, gövde, son_ü)
    if şablon.startswith("("):
        simge = şablon[1]
        ünlü_sonu = gövde[-1] in sesler.ÜNLÜLER
        emildi = (simge in "AI" and not ünlü_sonu) or (simge not in "AI" and ünlü_sonu)
        if emildi:
            return yüzey[0], yüzey[1:]
    return "", yüzey


def birleştir(ad: str, kök, ek_adları: list[str], ekler: dict[str, Ek]
              ) -> tuple[list[str], str]:
    """Kök + sıralı ek adları → (token listesi, yüzey biçimi)."""
    tokenlar = list(kök.tokens)
    gövde = ad
    önceki_değişim = kök.değişim          # son morfemin yumuşama kuralı (önce kök, sonra ekler)
    önceki_ek = None                      # bir önceki ek adı (pronominal-n kararı için)
    for idx, ek_adı in enumerate(ek_adları):
        ek = ekler[ek_adı]
        # kök-koşullu ek: şablon gövdeye göre belirlenir (geniş zaman / çatı ekleri).
        kural = getattr(ek, "kök_koşullu", "")
        if kural == "geniş":
            # Olumsuz/yetersizlik sonrası geniş zaman düzensiz: -Ar/-Ir değil -z (gelmez).
            olumsuz_bağlam = any(a in ("olumsuz", "yetersizlik") for a in ek_adları[:idx])
            şablon = "z" if olumsuz_bağlam else _geniş_şablon(gövde, ad)
        elif kural == "edilgen":
            şablon = _edilgen_şablon(gövde)
        elif kural == "ettirgen":
            şablon = _ettirgen_şablon(gövde)
        else:
            şablon = ek.şablon
        # -Iyor daralması: daraltır ek, çok-heceli a/e-sonu gövdeye gelince son ünlü düşer
        # (oyna→oyn+u+yor=oynuyor; ara→arıyor). Dar ünlü (oku/yürü) etkilenmez.
        if (getattr(ek, "daraltır", False) and gövde and gövde[-1] in "ae"
                and any(c in sesler.ÜNLÜLER for c in gövde[:-1])):
            gövde = gövde[:-1]
            tokenlar[-1] = tokenlar[-1][:-1]
            if not tokenlar[-1]:
                tokenlar.pop()
        # Pronominal -n-: 3. tekil/çoğul iyelikten sonra hâl eki → araya -n- (ayrı token);
        # hâl eki artık ünsüz-sonu gövdeye eklenir (arabası+n+da, kendi tamponu düşer).
        if önceki_ek in PRONOMİNAL_N and ek_adı in HÂL_PRONOMİNAL_N:
            tokenlar.append("n")
            gövde = gövde + "n"
        # İstisnai uyum: ince kökte ilk ek, kökün son ünlüsünün İNCE karşılığına uyumlar
        # (kalp→kalbi, rol→rolü). Yalnız ilk ek (sonra gövde zaten ince ünlü taşır).
        uyum_ü = _ince_çevir(kök.son_ünlü) if (idx == 0 and getattr(kök, "ince", False)) else None
        tampon, gövde_eki = _çöz_parça(şablon, gövde, uyum_ü)
        # Yumuşama: ÖNCEKİ morfemin (kök ya da bir önceki ek) son ünsüzü, ünlüyle başlayan
        # ek gelince yumuşar (kök: kitap→kitabı, git→gidiyor; ek: gelecek→geleceğiz k→ğ).
        # Ünsüz öncesi olmaz (git+ti→gitti); tampon ünsüzle başlarsa da olmaz (araba+y+a).
        ilk_ses = (tampon + gövde_eki)[:1]
        # Ünlü düşmesi: düşen-ünlü kökte ilk ekte ünlü-başlı ek gelince kökün son ünlüsü
        # düşer (akıl+ım→aklım, ağız+ı→ağzı). Harmony orijinal son ünlüden alındı (ek_çöz
        # öncesi); kayıp gibi düşen+yumuşamada önce düşer sonra yumuşar (kayp→kayb→kaybı).
        if idx == 0 and getattr(kök, "düşen", False) and ilk_ses in sesler.ÜNLÜLER:
            tokenlar[-1] = _ünlü_düşür(tokenlar[-1])
            gövde = _ünlü_düşür(gövde)
        # ye/de düzensizi: çekirdek e→i, yalnız y-glide'lı ek öncesi (ünlü-başlı ek → tampon
        # y; -Iyor → 'yor'). Ünsüz-başlı ekte (yedi/yer/dedi/der) değişmez. Yalnız ilk ek.
        if (idx == 0 and getattr(kök, "daralan", False)
                and (tampon + gövde_eki).startswith("y")):
            tokenlar[-1] = _e_i(tokenlar[-1])
            gövde = _e_i(gövde)
        # Sınıf-farkındalıklı yumuşama (kural #7): YUMUŞAMA KÖKÜN BİRİNCİL SINIFINA AİTTİR.
        # Kök ikincil sınıfında (ek_tür) okunuyorsa (ilk ek öbeği ≠ birincil tür) değişim
        # UYGULANMAZ. Bu, okumaya-göre-değişen eşsesli yumuşamayı çözer: art→ardı(isim, t→d)
        # ama artıyor(fiil, t sabit); et→ediyor(fiil, t→d) ama eti(isim, t sabit); gerek→
        # gereği(isim, k→ğ) ama gerekiyor(fiil, k sabit). (Birincil sınıf: git→gidiyor korunur.)
        değ = önceki_değişim
        if idx == 0 and ek.öbek in ("isim", "fiil"):
            birincil = "fiil" if kök.tür == "fiil" else "isim"
            if ek.öbek != birincil:                # ikincil sınıf okuması: ek_değişim (yoksa None)
                değ = kök.ek_değişim               # art→None (sabit), tat→{t→d} (tadıyor)
        if değ and ilk_ses in sesler.ÜNLÜLER:
            tokenlar[-1] = _yumuşat_son(tokenlar[-1], değ)
            gövde = _yumuşat_son(gövde, değ)
        if tampon:
            tokenlar.append(tampon)
        tokenlar.append(gövde_eki)
        gövde = gövde + tampon + gövde_eki
        önceki_değişim = ek.değişim          # bu ek artık son morfem (sonraki sınır için)
        önceki_ek = ek_adı
    return tokenlar, gövde

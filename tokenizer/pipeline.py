"""Encode / decode pipeline: metin ↔ token dizisi. Tokenizer'ın dış yüzü.

Akış (CLAUDE.md "Tokenizasyon Akışı"):
  metin → boşlukla parçala → her parça: harf/noktalama altbirimlerine ayır
        → kelime: istisna? → çözümle() → (çoklu çözümde DETERMİNİSTİK SEÇİM) → token
        → bilinmeyen (0 çözüm): BÜTÜN tut + onay kuyruğuna ekle
  Kelime sınırı: SentencePiece tarzı boşluk tokenı "▁" (kelimeler arası).

Seçim politikası (kullanıcı kararı): BÜTÜN-KÖK → en az token → öbek-uyumlu → en uzun kök.
(Bütün-kök: kelime zaten sözlükte kökse o okuma yeğlenir — deneyim/deneme/açacak leksik.)
"""

from __future__ import annotations

import itertools
import re
import unicodedata
from collections import Counter

from tokenizer import alfabe, sesler
from tokenizer.cozumle import çözümle
from tokenizer.dil import PROFİLLER, DOĞAL_DİLLER
from tokenizer.hece import hecele
from tokenizer.kod import DİLLER, PY_İŞLEM, PY_TIRNAK, KOD_SÖZLÜĞÜ, tanımlayıcı_böl

BOŞLUK = "▁"
# düz ve sağ-tek-tırnak (İstanbul'da / İstanbul’da) + kesme olarak kullanılan değiştirici
# harfler (vocab Faz 3): ʼ U+02BC (Cumhuriyetʼi), ʹ U+02B9 (Kemalʹin) — harf sınıfı DIŞI.
KESME = ("'", "’", "ʼ", "ʹ")
KAPANIŞ_TIRNAK = ("»", "”", "\"")   # AZ: kapanış tırnağına ek bitişik (dil profili büyük_tire_eki)
RAKAM_İŞARET = "%²³°"   # AZ: sayıya bağlı işaret + tire + ek (30%-i, km²-dir, 45°-dir; profil rakam_tire_eki)
# LaTeX komutları (metin kipi, vocab bölümü 'latex'): ters bölü DAHİL tek token (\frac, \Delta).
# Büyük/küçük harf komutun parçasıdır (\Delta ≠ \delta) → casing işaretçisi kullanılmaz.
LATEX_KOMUTLARI = (
    "frac dfrac cdot times div sqrt left right "
    "alpha beta gamma delta epsilon varepsilon zeta eta theta lambda mu nu xi pi rho sigma tau "
    "phi varphi chi psi omega Gamma Delta Theta Lambda Sigma Phi Omega "
    "infty sum prod int iint oint lim to leq geq neq approx equiv pm mp partial nabla "
    "vec hat bar overline mathbb mathrm mathbf text begin end pmatrix bmatrix vmatrix cases "
    "sin cos tan cot sec csc log ln exp det min max quad cdots ldots "
    "in notin subset subseteq cup cap emptyset forall exists "
    "rightarrow Rightarrow leftrightarrow Leftrightarrow mapsto circ angle perp parallel degree"
).split()
LATEX_TOKENLARI = ["\\" + k for k in LATEX_KOMUTLARI]
_LATEX = frozenset(LATEX_TOKENLARI)
BAŞ_BÜYÜK = "<|Bb|>"   # sonraki kelime Başlık-biçimi (ilk harf büyük): Bugün
HEP_BÜYÜK = "<|BB|>"   # sonraki kelime HEP BÜYÜK: TÜRK
PAD, UNK, BOS, EOS = "<pad>", "<unk>", "<s>", "</s>"
ÖZEL = {PAD, UNK, BOS, EOS, "<|sistem|>", "<|kullanici|>", "<|asistan|>", "<|bitis|>"}
BÜYÜK = {BAŞ_BÜYÜK, HEP_BÜYÜK}   # casing işaretçileri (decode'da TÜKETİLİR, atılmaz)

# Kod kipi (K1): boşluk kayıpsız. Satır sonu/sekme/CR harfiyen token; boşluk koşusu ▁×n
# (n ≤ EN_UZUN_BOŞLUK; tek boşluk metin kipindeki ▁ ile aynı token). Metin kipi bunlardan
# YALNIZ satır sonunu üretir (SATIR); sekme/CR/boşluk koşusu tek ▁'ye iner, metindeki harfiyen
# ▁ bayta kaçar → karışma yok.
KİPLER = ("metin", "kod")
KOD_BOŞLUKLARI = ("\n", "\t", "\r")
# Metin kipinde satır yapısı: satır sonu = "\n" tokenı (kod-bosluk bölümündeki AYNI token, yeni
# token yok); paragraf = boş satır = iki "\n". Satır içi boşluk tek ▁; satır başı/sonu boşluğu
# atılır. Model paragraf/liste/dize ayırmayı ön eğitimden öğrenir.
SATIR = "\n"
EN_UZUN_BOŞLUK = 16
BOŞLUK_KOŞULARI = [BOŞLUK * n for n in range(2, EN_UZUN_BOŞLUK + 1)]   # vocab bölümü (▁ v1'de)
_BOŞLUK_KOŞULARI = frozenset([BOŞLUK, *BOŞLUK_KOŞULARI])
_BOŞLUK_AYIR = re.compile(r"(\s+)")
_KOD_BÜTÜN = frozenset(PY_İŞLEM + PY_TIRNAK + ("__",))   # dil kipinde bütün token (anahtar hariç)

# Kod kipi tanımlayıcı casing'i (K3): ASCII kuralı (str.upper; i→I, İ değil). Yalnız kod kipi.
ASCII_BAŞ, ASCII_HEP = "<|Ab|>", "<|AA|>"
ASCII_İŞARET = (ASCII_BAŞ, ASCII_HEP)

# Bayt tokenları (vocab Faz 2): vocab'da olmayan HER karakter UTF-8 baytlarına iner → hiçbir
# girdi <unk> üretmez. Tüm 0x00-0xFF (UTF-8'in hiç üretmediği baytlar dahil → tablo tam, basit).
# encode metinden asla '<0x..>' biçiminde TEK token çıkarmaz (harf-dışı karakterler tek tek
# tokenlanır) → bayt tokenı her zaman kaçış demektir, metinle karışmaz.
BAYT_TOKENLARI = [f"<0x{b:02X}>" for b in range(256)]
_BAYT = {t: b for b, t in enumerate(BAYT_TOKENLARI)}


def bayt_tokenları(s: str) -> list[str]:
    """Metnin UTF-8 bayt tokenları (tek başına vekil/surrogate da çökmez: surrogatepass)."""
    return [BAYT_TOKENLARI[b] for b in s.encode("utf-8", "surrogatepass")]


def _bayt_çöz(baytlar) -> str:
    """Bayt koşusu → metin. Kodlayıcının ürettiği koşu her zaman çözülür (vekil dahil);
    geçersiz koşu (ör. model çıktısı) çökmez → U+FFFD."""
    try:
        return bytes(baytlar).decode("utf-8", "surrogatepass")
    except UnicodeDecodeError:
        return bytes(baytlar).decode("utf-8", "replace")

# Türkçe alfabe + büyük harfler + düzeltme imli ünlüler (â/î/û: hikâye, kâğıt, rüzgâr).
# Düzeltme imli ünlüler kelimeyi BÖLMEMELİ (aksi halde "hikâye"→hik+â+ye yanlış bölünür);
# harf sayılır, kelime bütün tutulur (kök eşleşmezse bilinmeyen-bütün, round-trip korunur).
# q/w/x (vocab Faz 1): Türkçe alfabede yok ama Latin metinde yaygın (Windows, XIV, max_index);
# harf sayılır → kelimeyi bölmez. Hiçbir kök/ek/istisna q/w/x içermez → bu harfi taşıyan
# kelime motorca parçalanamaz: bilinmeyen-BÜTÜN (onay kuyruğu), vocab'da hece→harf fallback.
_HARFLER = (set(alfabe.ALFABE) | set("ABCÇDEFGĞHIİJKLMNOÖPRSŞTUÜVYZ") | set("âîûÂÎÛ")
            | set("qwxQWX"))


def _harf_mi(c: str) -> bool:
    """Harf sınıfı (kelime sınırı): Türkçe harfler + q/w/x + TÜM Unicode harfleri ve birleşen
    işaretler (vocab Faz 3), kesme gibi kullanılan ʼ ʹ hariç. Yabancı harfli kelime BÖLÜNMEZ:
    eskiden 'Ōsaka' → Ō + 'saka' (Türkçe çözülüyordu!). Hiçbir kök/ek/istisna Türkçe dışı harf
    içermez → böyle bir kelime motorca parçalanamaz: bilinmeyen-BÜTÜN, vocab'da fallback."""
    if c in _HARFLER:
        return True
    if c in KESME:
        return False
    kategori = unicodedata.category(c)
    if kategori == "Lm" and _üst_alt_simge_mi(c):
        return False
    return c.isalpha() or kategori[0] == "M"


def _üst_alt_simge_mi(c: str) -> bool:
    """Üst/alt simge DEĞİŞTİRİCİ harfi mi (ᵐ ⁿ ⁱ ₖ ᵢ ⱼ ᵝ ʰ ˣ…)? Bunlar harf değil SEMBOLDÜR (² ₃
    gibi): 'aⁿ', 'Eₖ', 'xᵢⱼ' önceki harfe yapışıp bilinmeyen kelime olmamalı. Yalnız Unicode adı
    SUBSCRIPT/SUPERSCRIPT ya da 'MODIFIER LETTER SMALL/CAPITAL <harf>' olanlar; Türkoloji/Türk
    dilleri imleri (ʻ TURNED COMMA, ʿ ʾ HALF RING, ʽ REVERSED COMMA) bu adlara uymaz → harf kalır."""
    ad = unicodedata.name(c, "")
    return ("SUBSCRIPT" in ad or "SUPERSCRIPT" in ad
            or ad.startswith(("MODIFIER LETTER SMALL ", "MODIFIER LETTER CAPITAL ")))


def _harf_durumu(kelime, küçük, profil=None):
    """Kelimenin casing işaretçisi: None (küçük) | BAŞ_BÜYÜK (Başlık) | HEP_BÜYÜK | 'düz'.

    'düz' = küçük-harf biçiminden basit casing ile geri üretilemeyen karışık biçim
    (iPhone gibi) → işaretçisiz, bütün-token korunur (kayıpsızlık için). profil: dilin casing
    kuralı (None = Türkçe; AZ aynı kural, İ/i I/ı + Ə/ə)."""
    if kelime == küçük:
        return None
    if kelime == (sesler.türkçe_başlık(küçük) if profil is None else profil.başlık(küçük)):
        return BAŞ_BÜYÜK
    if kelime == (sesler.türkçe_büyült(küçük) if profil is None else profil.büyült(küçük)):
        return HEP_BÜYÜK
    return "düz"


def _öbek_uyumsuz(çöz, kökler, ekler) -> int:
    """Çözümdeki ek öbeği ile gövde sınıf(lar)ı uyuşmazlık sayısı (eşseslide çok sınıf).

    Nominalizer (çıkış) sonrası gövde sınıfı değişir → sonraki ekler yeni sınıfa göre
    denetlenir (oku+mA+lar: çoğul fiil-köke değil, isimleşmiş gövdeye uyumlu)."""
    if çöz.kök not in kökler:        # istisna çözümü (kök=bütün kelime): öbek kısıtı yok
        return 0
    kök = kökler[çöz.kök]
    sınıflar = {"fiil" if t == "fiil" else "isim" for t in [kök.tür, *(kök.ek_tür or [])]}
    say, geçiş = 0, None
    for ek_ad in çöz.ekler:
        ek = ekler[ek_ad]
        aktif = {geçiş} if geçiş else sınıflar
        if ek.öbek != "her" and ek.öbek not in aktif:
            say += 1
        if ek.çıkış:
            geçiş = ek.çıkış
    return say


def _ikincil_okuma(çöz, kökler, ekler) -> int:
    """Çözüm kökü İKİNCİL sınıfında (ek_tür) mı okuyor? 1 = evet. Okunan sınıf: çıkıştan önceki ilk
    ad/fiil öbekli ekin öbeği; yalnız koşaç ('her') ekleri varsa ad (koşaç çıplak fiile bağlanmaz)."""
    kök = kökler.get(çöz.kök)
    if kök is None or not çöz.ekler or not kök.ek_tür:
        return 0
    birincil = "fiil" if kök.tür == "fiil" else "isim"
    okunan = "isim"
    for ad in çöz.ekler:
        öbek = ekler[ad].öbek
        if öbek != "her":
            okunan = öbek
            break
    return int(okunan != birincil)


def _birim(çöz, kökler) -> int:
    """Çözümün BİRİM sayısı: kök hecesi + ek sayısı (tampon tokenı morfem sayılmaz). İstisna çözümünde
    (kök sözlükte değil) token sayısı."""
    kök = kökler.get(çöz.kök)
    return (len(kök.tokens) if kök is not None else len(çöz.tokens)) + len(çöz.ekler)


def _türemiş(çöz, kökler) -> int:
    """Türemiş kök okuması cezası: "hep" 2; "ekli" 1 yalnız ekliyken; "çıplak" 1 yalnız eksizken. İki
    türemiş okuma yarışırsa (görünür başlığı ↔ görün+ür) zayıf olan kazanır."""
    kök = kökler.get(çöz.kök)
    if kök is None or not kök.türemiş:
        return 0
    if kök.türemiş == "hep":
        return 2
    return int(bool(çöz.ekler) == (kök.türemiş == "ekli"))


_AM_ÇAKIŞMA = {("koşaç_1tekil_t1",), ("iyelik_1tekil",)}


def geri_eş_ek(a, b) -> bool:
    """Geri kök çakışması: iki okumanın EK DİZİSİ aynı (fark kök sınırında: bac+ı+m ↔ bacı+m, gəmik+ə ↔ gəmi+y+ə)
    ya da AZ -(y)Am çakışması (tələb+əm koşaç ↔ tələbə+m iyelik). Eksiz okuma çakışma sayılmaz (məsələn bütün)."""
    return bool(a) and (list(a) == list(b) or {tuple(a), tuple(b)} == _AM_ÇAKIŞMA)


def _geri_cezalı(çözümler, kökler) -> set[str]:
    """Geri çekilen kökler: kökü 'geri' (sema.Kök.geri, AZ korpus kararı) ve bir okuması rakip bir kökün okumasıyla
    çakışıyor (geri_eş_ek) → o kökün TÜM okumaları geri (bacım = bacı+m; məsələni = məsələ+n+i, məsələn+i değil).
    Çakışma yoksa etkisiz (məsələn, dərin bütün kalır)."""
    cezalı = set()
    for ç in çözümler:
        kök = kökler.get(ç.kök)
        if (ç.kök not in cezalı and kök is not None and kök.geri
                and any(d.kök != ç.kök and geri_eş_ek(ç.ekler, d.ekler) for d in çözümler)):
            cezalı.add(ç.kök)
    return cezalı


# TR seyrek ardışık ekler: -An ortacı + ek-fiil (atandı = ata+n+dı, at+an+dı değil); başka okuma yoksa seçilir (satandı)
_TR_SEYREK_DİZİ = frozenset({("ortaç_an", "ek_fiil_idi"), ("ortaç_an", "ek_fiil_imiş")})
# TR seyrek ek: ad→fiil -lA başka okuma varsa geride (verilen = ver+i+l+en, veri+le+n değil; yayınlanan = yayın+la+n+an)
_TR_SEYREK_EK = frozenset({"yapım_la"})


_KİŞİ_İYELİK = frozenset({"iyelik_1tekil", "iyelik_2tekil", "iyelik_1çoğul", "iyelik_2çoğul"})


def _özel(çöz, kökler, ad_okuma=False) -> int:
    """Özel ad kökü okuması mı (tür 'özel', AZ ozel_adlar.json)? Küçük harfli sözcükte ceza: sıradan kökün okuması
    yeğlenir (əli = əl+i). ad_okuma (Başlık biçimi) için tercih ölçüsü: 1./2. kişi iyelikli ad okuması sayılmaz —
    ad bunları nadiren alır, cümle başı sıradan sözcük öyle okunur (Əlimdə = əl+im+də, Əli+m+də değil)."""
    kök = kökler.get(çöz.kök)
    if kök is None or kök.tür != "özel":
        return 0
    return int(not (ad_okuma and _KİŞİ_İYELİK & set(çöz.ekler)))


def _seyrek(ek_adları, seyrek, seyrek_dizi) -> int:
    """Seyrek ek + seyrek ardışık ek çifti sayısı (profil.seyrek_ekler / seyrek_diziler)."""
    n = sum(e in seyrek for e in ek_adları)
    if seyrek_dizi:
        n += sum(çift in seyrek_dizi for çift in zip(ek_adları, ek_adları[1:]))
    return n


def _zamir_değil(çöz, kökler) -> int:
    kök = kökler.get(çöz.kök)
    return 0 if kök is not None and kök.tür == "zamir" else 1


def en_iyi_çözüm(çözümler, kökler, ekler, profil=None, ad_okuma=False):
    """Deterministik seçim: BÜTÜN-KÖK → en az token → en az öbek-uyumsuzluk → en uzun kök.

    BÜTÜN-KÖK önceliği (bilgi-tabanlı): kelime ZATEN sözlükte bir kök ise (ek yok) o okuma,
    nadir bir kök+ek parçalanmasına yeğlenir (deneyim → 'deneyim' [experience], 'den'+istek
    DEĞİL; açacak [opener] → bütün, 'aç'+gelecek DEĞİL). Rule #6 gereği ÇEKİMLİ/türetilmiş
    biçimler kök değildir (X-ebilme #6-ihlalleri temizlendi) → yalnız LEKSİK eşsesli (deneyim/
    gelecek/açacak/yedi/gelir) etkilenir; bileşimsel biçimler (geleceğim=gel+ecek+im) kök
    DEĞİL → etkilenmez. Parçalanma-berabere eşsesli (baksın) bu bonusla çözülmez (ikisi de
    ek alır) → 'en uzun kök' politikası karar verir (belgeli sınır).

    SON KIRICI (tam sıra): politika eşit bıraktığında token dizisi → kök → ek adları sözlük
    sırası. Olmazsa seçim çözümlerin SIRASINA, o da PYTHONHASHSEED'e bağlı kalır (paralel
    hatta işçiden işçiye farklı çıktı). Örn. resmin: resim+tamlayan [re,sm,in] ile
    resmi+iyelik_2tekil [res,mi,n] tüm ölçütlerde berabere → [re,sm,in].

    profil (None = Türkçe) politikayı yalnız genişletir; Türkçe anahtar birebir aynıdır. AZ sırası:
      0. ÖZEL ad kökü (tür 'özel'): küçük harfli sözcükte sıradan kökün her okuması yeğlenir (əli = əl+i, şəkili =
         şəkil+i); Başlık biçimli sözcükte (ad_okuma) tersine, bütün-kök ölçütünden hemen sonra ad okuması öne
         geçer (Gəncə, Quranın, Amerikanın = amerika+n+ın; Azəri bütün kalır);
      1. seyrek ek/dizi (üretken dönüşlü, edebî istek kişileri, ortaç+idi) ve normatif dışı (ünlüsü düşmemiş
         danışıq) okuma: başka çözüm varsa seçilmez
         (yerinə = yer+i+n+ə; atam = ata+m);
      2. TÜREMİŞ kök (bileşik biçimle eşsesli sözlük başlığı, sema.Kök.türemiş): bileşik okuma varsa
         seçilmez (çıplak 'gəlir' = gəl+ir; açmalımı = aç+malı+mı, açma+lı+m+ı değil); ardından GERİ kök
         (sema.Kök.geri, korpus kararı: bacım = bacı+m, bac+ı+m değil);
      3. son_çare_ekler (bitişik soru -mI) → bütün-kök → birincil sınıf (yalnız aynı kökün okumaları);
      4. BİRİM (kök hecesi + ek sayısı; tampon tokenı morfem sayılmaz) → az ek → zamir → token sayısı →
         yeğlenmeyen ekler → öbek uyumu → en uzun kök → son kırıcı."""
    if profil is not None and (profil.son_çare_ekler or profil.az_ek_önce or profil.seyrek_ekler
                               or profil.seyrek_diziler
                               or profil.birincil_önce or profil.yeğlenmeyen_ekler or profil.birim_say):
        son_çare, yeğlenmeyen = profil.son_çare_ekler, profil.yeğlenmeyen_ekler
        seyrek, seyrek_dizi = profil.seyrek_ekler, profil.seyrek_diziler
        # birincil sınıf ölçütü yalnız AYNI kökün birden çok okuması yarışırken (yazsan: yaz fiil+şart ↔ yaz
        # ad+koşaç); farklı kökler arasında (kəs 'kişi' ad ↔ kəsən = kəs+ən) birim/ek sayısı karar verir
        çoklu = ({k for k, n in Counter(ç.kök for ç in çözümler).items() if n > 1}
                 if profil.birincil_önce else frozenset())
        geri = _geri_cezalı(çözümler, kökler)
        return min(
            çözümler,
            key=lambda ç: (0 if ad_okuma else _özel(ç, kökler),
                           _seyrek(ç.ekler, seyrek, seyrek_dizi) + ç.normatif_dışı, _türemiş(ç, kökler), ç.kök in geri,
                           sum(e in son_çare for e in ç.ekler),
                           0 if not ç.ekler else 1, -_özel(ç, kökler, ad_okuma=True) if ad_okuma else 0,
                           _ikincil_okuma(ç, kökler, ekler) if ç.kök in çoklu else 0,
                           _birim(ç, kökler) if profil.birim_say else len(ç.tokens),
                           len(ç.ekler) if profil.az_ek_önce else 0,
                           _zamir_değil(ç, kökler) if profil.zamir_önce else 0, len(ç.tokens),
                           sum(e in yeğlenmeyen for e in ç.ekler),
                           _öbek_uyumsuz(ç, kökler, ekler), -len(ç.kök),
                           tuple(ç.tokens), ç.kök, tuple(ç.ekler)),
        )
    return min(
        çözümler,
        key=lambda ç: (ç.normatif_dışı, 0 if not ç.ekler else 1,
                       sum(çift in _TR_SEYREK_DİZİ for çift in zip(ç.ekler, ç.ekler[1:]))
                       + sum(e in _TR_SEYREK_EK for e in ç.ekler), len(ç.tokens),
                       _öbek_uyumsuz(ç, kökler, ekler), -len(ç.kök),
                       tuple(ç.tokens), ç.kök, tuple(ç.ekler)),
    )


def _altbirimler(parça):
    """Bir parçayı harf (kelime) ve harf-dışı (noktalama) koşularına ayırır."""
    for harf_mi, grup in itertools.groupby(parça, key=_harf_mi):
        yield "".join(grup), bool(harf_mi)


def _klitik_birleştir(altbirimler, profil):
    """Kesmeli klitiği sözcükle tek birime birleştirir (EN don't, it’s, we're): [harf, kesme, harf] üçlüsünde kesme
    sonrası harf koşusu bir klitiğin kesme sonrası kısmıysa (n't'de önceki koşu 'n' ile bitmeli). Diğer kesmeler
    (O'Brien, rock'n'roll) dokunulmaz → harf koşuları ayrı sözcük kalır."""
    sonuç, j = [], 0
    while j < len(altbirimler):
        a, h = altbirimler[j]
        if (not h and len(a) == 1 and a in KESME and sonuç and sonuç[-1][1]
                and j + 1 < len(altbirimler) and altbirimler[j + 1][1]):
            önce, sonra = sonuç[-1][0], altbirimler[j + 1][0]
            ö, s = profil.küçült(önce), profil.küçült(sonra)
            for kl in profil.klitikler:
                kö, ks = kl.split("'")
                if s == ks and ö.endswith(kö) and len(ö) > len(kö):
                    sonuç[-1] = (önce + a + sonra, True)
                    j += 2
                    break
            else:
                sonuç.append((a, h))
                j += 1
            continue
        sonuç.append((a, h))
        j += 1
    return sonuç


def _elizyon_birleştir(altbirimler, profil):
    """Soldaki elizyonu tek birime birleştirir (FR l'homme, qu’il): [harf, kesme, harf] üçlüsünde ilk harf koşusu
    (küçük harfle) bir elizyonsa kesmeyle birleşir ve AYRI birim olur → [l', homme]. Başka kesmeler (aujourd'hui,
    O'Neill) dokunulmaz; kesmeli bütün sözcükleri çözümleyicinin istisnası ayrıca birleştirir (_kesmeli_birleştir)."""
    sonuç, j = [], 0
    while j < len(altbirimler):
        a, h = altbirimler[j]
        if (h and j + 2 < len(altbirimler) and altbirimler[j + 1][0] in KESME[:2]
                and altbirimler[j + 2][1] and profil.küçült(a) in profil.elizyonlar):
            sonuç.append((a + altbirimler[j + 1][0], True))
            j += 2
            continue
        sonuç.append((a, h))
        j += 1
    return sonuç


def _kesmeli_birleştir(altbirimler, istisnalar, profil):
    """Kesmeli bütün sözcük (FR aujourd'hui, presqu'île): [harf, kesme, harf] birleşimi istisnaysa tek birim."""
    sonuç, j = [], 0
    while j < len(altbirimler):
        if (j + 2 < len(altbirimler) and altbirimler[j][1] and altbirimler[j + 1][0] in KESME[:2]
                and altbirimler[j + 2][1]):
            birleşik = altbirimler[j][0] + altbirimler[j + 1][0] + altbirimler[j + 2][0]
            if profil.küçült(birleşik).replace("’", "'") in istisnalar:
                sonuç.append((birleşik, True))
                j += 3
                continue
        sonuç.append(altbirimler[j])
        j += 1
    return sonuç


def _kelime_token(kelime, kökler, ekler, istisnalar, kuyruk, bağlam, profil=None, ad_okuma=False):
    """(token_listesi, bilinmeyen_mi) döndürür. bilinmeyen_mi: çözülemedi → kuyruğa alındı.
    ad_okuma: kelime Başlık biçiminde (profil.özel_ad_başlık) → özel ad okuması yeğlenir (Gəncə = gəncə, gənc+ə değil)."""
    if profil is not None and profil.motor == "fr":
        from tokenizer import fr                 # Fransızca çekim üreteçli çözümleyici (FR-1)
        çs, _ = fr.çözümle(kelime, kökler, ekler, istisnalar)
        if çs:
            return list(fr.en_iyi(çs, kökler, ad_okuma).tokens), False
        if kuyruk is not None:
            kuyruk.ekle(kelime, bağlam)
        return [kelime], True
    if profil is not None and profil.motor == "de":
        from tokenizer import de                 # Almanca çekim üreteçli + bileşik çözümleyici (DE-1)
        çs, _ = de.çözümle(kelime, kökler, ekler, istisnalar)
        if çs:
            return list(de.en_iyi(çs, kökler, ad_okuma).tokens), False
        if kuyruk is not None:
            kuyruk.ekle(kelime, bağlam)
        return [kelime], True
    if profil is not None and profil.motor == "en":
        from tokenizer import en                 # İngilizce yazım kurallı çözümleyici (EN-1)
        çs, taban = en.çözümle(kelime, kökler, ekler, istisnalar, profil.klitikler)
        if taban is not None and kuyruk is not None:   # klitikli bilinmeyen: taban sorulur (Mary's → mary)
            kuyruk.ekle(taban, bağlam)
        if çs:
            return list(en.en_iyi(çs, kökler, ad_okuma).tokens), taban is not None
        if kuyruk is not None:
            kuyruk.ekle(kelime, bağlam)
        return [kelime], True
    çs = çözümle(kelime, kökler, ekler, istisnalar, profil)
    if çs:
        return list(en_iyi_çözüm(çs, kökler, ekler, profil, ad_okuma).tokens), False
    if kuyruk is not None:                       # bilinmeyen → bize sorulur
        kuyruk.ekle(kelime, bağlam)
    return [kelime], True                        # BÜTÜN tut


def boşluk_tokenları(koşu: str) -> list[str]:
    """Kod kipinde bir boşluk koşusunun tokenları (kayıpsız). Satır sonu/sekme/CR kendi
    tokenı; boşluk koşusu en uzun ▁-koşusu tokenından başlayarak açgözlü (16 → 1). Diğer
    boşluk karakterleri (NBSP, \\f, \\v…) kendisi döner → vocab'da bayt yedeğine iner."""
    tokenlar: list[str] = []
    for boşluk_mu, grup in itertools.groupby(koşu, key=lambda c: c == " "):
        g = "".join(grup)
        if not boşluk_mu:
            tokenlar.extend(g)                   # \n \t \r (ya da bayta inecek nadir boşluk)
            continue
        n = len(g)
        while n:
            k = min(n, EN_UZUN_BOŞLUK)
            tokenlar.append(BOŞLUK * k)
            n -= k
    return tokenlar


def _kod_dil_ekle(parçalar, tokenlar, kökler, ekler, istisnalar, kuyruk, önbellek, metin):
    """Dil lexer'ının (tür, metin) parçalarını tokenlar (K2).

    anahtar / çok karakterli işlem / üçlü tırnak → BÜTÜN token (vocab kod-python bölümü).
    metin (yorum, string içeriği) → boşluk kayıpsız + Türkçe hat; bilinmeyen kelime kuyruğa.
    ad / sayı / önek / tek karakter → Türkçe hattın parça işlemesi, KUYRUKSUZ (tanımlayıcılar
    onay kuyruğunu İngilizce adlarla doldurmasın; K3'te tanımlayıcı bölme gelecek)."""
    for tür, s in parçalar:
        if tür == "boşluk":
            tokenlar.extend(boşluk_tokenları(s))
        elif tür == "anahtar" or s in _KOD_BÜTÜN:
            tokenlar.append(s)
        elif tür == "metin":
            for i, p in enumerate(_BOŞLUK_AYIR.split(s)):
                if i % 2:
                    tokenlar.extend(boşluk_tokenları(p))
                elif p:
                    _parça_ekle(p, tokenlar, kökler, ekler, istisnalar, kuyruk, önbellek, metin)
        elif tür == "ad":
            _ad_ekle(s, tokenlar, kökler, ekler, istisnalar, önbellek, metin)
        else:
            _parça_ekle(s, tokenlar, kökler, ekler, istisnalar, None, önbellek, metin)


def _ad_ekle(ad, tokenlar, kökler, ekler, istisnalar, önbellek, metin):
    """Tanımlayıcı (K3): tanımlayıcı_böl parçaları; ASCII parça ASCII casing kuralıyla (kullanıcı
    kararı: getItem → get <|Ab|> item, 'ıtem' DEĞİL), Türkçe/Unicode parça Türkçe hatla. Kuyruksuz.

    DEĞİŞMEZ (decode doğruluğu): camel sınırı yalnız BÜYÜK harften önce düşer → ilk parçadan
    sonraki her harf parçası büyük harfle başlar ve KENDİ işaretçisini taşır; önceki parçanın
    HEP koşusu (HTTP) işaretsiz küçük parçaya taşamaz. Karışık parça (HTTPs) bütün kalır.
    test_tanımlayıcı_rastgele bunu rastgele tanımlayıcılarla kilitler."""
    for p in tanımlayıcı_böl(ad):
        if not p[0].isalpha():                   # '_' / rakam: casing koşusunu zaten bitirir
            tokenlar.append(p) if p in _KOD_BÜTÜN else _parça_ekle(
                p, tokenlar, kökler, ekler, istisnalar, None, önbellek, metin)
            continue
        if p.isascii():
            küçük = p.lower()
            işaret = (None if p == küçük else ASCII_BAŞ if p == küçük.capitalize()
                      else ASCII_HEP if p == p.upper() else "düz")
        else:
            küçük = sesler.türkçe_küçült(p)
            işaret = _harf_durumu(p, küçük)
        if işaret == "düz":                      # karışık parça (HTTPs) → bütün, casing'siz
            _parça_ekle(p, tokenlar, kökler, ekler, istisnalar, None, önbellek, metin)
            continue
        if işaret:
            tokenlar.append(işaret)
        if p.isascii():
            # ASCII parça Türkçe MOTORA GİRMEZ (ilke #1): İngilizce parça sahte bölünüyordu
            # (size → siz+e, time → tim+e, sort → sor+t; stdlib'de 46 parça/4.877 oluşum).
            # Kod sözlüğü → yoksa hece (Türkçe ASCII ad 'kok_bul' yine v1 hecelerine iner).
            tokenlar.extend([küçük] if küçük in KOD_SÖZLÜĞÜ else hecele(küçük))
        else:
            _parça_ekle(küçük, tokenlar, kökler, ekler, istisnalar, None, önbellek, metin)


def encode(metin, kökler, ekler, istisnalar=None, kuyruk=None, önbellek=None,
           kip: str = "metin", dil: str | None = None) -> list[str]:
    """Metni token dizisine çevirir.

    kip "metin" (varsayılan, Türkçe metin hattı): satır içi boşluk dizileri tek ▁'ye iner, satır
    sonları "\n" tokenı olarak KORUNUR (boş satır = paragraf = iki "\n"); satır başı/sonu boşluğu
    ve metnin baş/son boş satırları atılır → decode(encode(x)) == metin_kanonik(x) (kurt-veri
    normalleştirmesiyle uyumlu). kip "kod": boşluk, satır sonu ve girinti KAYIPSIZ korunur
    (boşluk_tokenları); boşluk dışı her parça metin hattıyla aynı işlenir. Kip AÇIKÇA verilir,
    tahmin edilmez (ilke #3). dil, kip "kod" iken programlama dili (ör. "python"): o dilin lexer'ı
    ile anahtar sözcük/operatör bütün token, yorum/string Türkçe hat (_kod_dil_ekle). dil, kip
    "metin" iken doğal dil (ör. "az"; None = Türkçe): kökler/ekler/istisnalar O DİLİN verisi
    olmalı (tokenizer.diller), çözümleme o dilin profiliyle yapılır; boşluk/satır/casing/
    noktalama/LaTeX davranışı Türkçe metin kipiyle aynıdır.

    önbellek (opsiyonel dict): {küçük_kelime: token_listesi} — büyük korpusta (Aşama 1)
    aynı kelimeyi tekrar çözmemek için memoization. Deterministik (aynı kelime hep aynı
    token); yalnız hız. kuyruk yan-etkisi ilk görülüşte işler (kuyruk zaten tekilleştirir)."""
    if kip not in KİPLER:
        raise ValueError(f"bilinmeyen kip: {kip!r} (geçerli: {', '.join(KİPLER)})")
    profil = None
    if dil is not None:
        if kip == "kod" and dil not in DİLLER:
            raise ValueError(f"kod kipinde dil şunlardan biri: {', '.join(DİLLER)} ({dil!r})")
        if kip == "metin":
            if dil not in DOĞAL_DİLLER:
                raise ValueError(f"metin kipinde dil şunlardan biri: "
                                 f"{', '.join(sorted(DOĞAL_DİLLER))} (Türkçe: dil verilmez) ({dil!r})")
            profil = PROFİLLER[dil]
    tokenlar: list[str] = []
    if dil is not None and kip == "kod":
        _kod_dil_ekle(DİLLER[dil](metin), tokenlar, kökler, ekler, istisnalar, kuyruk,
                      önbellek, metin)
        return tokenlar
    if kip == "kod":
        for i, parça in enumerate(_BOŞLUK_AYIR.split(metin)):
            if i % 2:                            # tek indeks = boşluk koşusu
                tokenlar.extend(boşluk_tokenları(parça))
            elif parça:
                _parça_ekle(parça, tokenlar, kökler, ekler, istisnalar, kuyruk, önbellek, metin)
        return tokenlar
    for j, satır in enumerate(_satırlar(metin)):
        if j > 0:
            tokenlar.append(SATIR)
        for i, parça in enumerate(satır.split()):
            if i > 0:
                tokenlar.append(BOŞLUK)
            _parça_ekle(parça, tokenlar, kökler, ekler, istisnalar, kuyruk, önbellek, metin,
                        latex=True, profil=profil)
    return tokenlar


def _satırlar(metin: str) -> list[str]:
    """Metin kipi satırları: "\n" ile bölünür (\r\n/\r önce \n olur); baştaki ve sondaki boş
    satırlar atılır. Boşluktan ibaret satır boş satırdır (paragraf ayırıcı)."""
    satırlar = metin.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    while satırlar and not satırlar[0].strip():
        satırlar.pop(0)
    while satırlar and not satırlar[-1].strip():
        satırlar.pop()
    return satırlar


def metin_kanonik(metin: str) -> str:
    """Metin kipinin geri verdiği biçim: decode(encode(x)) == metin_kanonik(x). Satır içi boşluk
    tek boşluk, satır başı/sonu boşluğu yok, satır sonları ve boş satırlar korunur, metnin baş/son
    boş satırları atılır."""
    return "\n".join(" ".join(s.split()) for s in _satırlar(metin))


def _parça_ekle(parça, tokenlar, kökler, ekler, istisnalar, kuyruk, önbellek, metin,
                latex=False, profil=None):
    """Boşluk içermeyen bir parçanın tokenlarını ekler (iki kipte ortak).

    latex (yalnız metin kipi): ters bölü + TAM komut adı (\\frac, \\Delta) tek token. Ters bölü
    koşusu TEK sayıda olmalı (\\\\frac = satır sonu komutu + düz 'frac') ve harf koşusu komut adına
    BİREBİR eşit olmalı (\\fracx, \\Frac komut değil → eskisi gibi). Kod kipinde kapalı: Python
    dizgesindeki '\\nu' kaçış dizisidir, LaTeX değil.

    profil (None = Türkçe): doğal dil; önbellek anahtarı dil ayrımlıdır (aynı yüzey iki dilde
    farklı tokenlanır): Türkçe anahtar düz 'kelime', diğer dil ('az', 'kelime'); özel_ad_başlık profilinde Başlık
    biçimli sözcük ('az', 'kelime', 'ad') — okuması küçük harfliden farklı olabilir (Gəncə ↔ gəncə)."""
    önceki_kesme = False                        # bir önceki altbirim kesme ile mi bitti?
    altbirimler = list(_altbirimler(parça))
    if profil is not None and profil.klitikler:
        altbirimler = _klitik_birleştir(altbirimler, profil)
    if profil is not None and profil.elizyonlar:
        if istisnalar:
            altbirimler = _kesmeli_birleştir(altbirimler, istisnalar, profil)
        altbirimler = _elizyon_birleştir(altbirimler, profil)
    kesme_eki = profil is None or profil.kesme_eki
    atla = False
    for j, (altbirim, kelime_mi) in enumerate(altbirimler):
        if atla:
            atla = False
            continue
        if (latex and not kelime_mi and altbirim.endswith("\\") and j + 1 < len(altbirimler)
                and "\\" + altbirimler[j + 1][0] in _LATEX
                and (len(altbirim) - len(altbirim.rstrip("\\"))) % 2):
            for c in altbirim[:-1]:
                tokenlar.extend(bayt_tokenları(c) if c == BOŞLUK else c)
            tokenlar.append("\\" + altbirimler[j + 1][0])
            önceki_kesme, atla = False, True
            continue
        if not kelime_mi:                        # noktalama: her karakter ayrı token
            for c in altbirim:                   # HARFİYEN '▁' boşluk tokenıyla karışmasın → bayt
                tokenlar.extend(bayt_tokenları(c) if c == BOŞLUK else c)
            önceki_kesme = (kesme_eki and altbirim[-1] in KESME) or (
                profil is not None and profil.rakam_tire_eki and altbirim[-1] == "-"
                and len(altbirim) > 1 and (altbirim[-2].isdigit() or altbirim[-2] in RAKAM_İŞARET))
            #                                            AZ: 2024-cü, 5-də, 30%-i, km²-dir
            if (not önceki_kesme and profil is not None and profil.büyük_tire_eki
                    and 0 < j < len(altbirimler) - 1 and altbirimler[j - 1][1]
                    and altbirimler[j + 1][1] and altbirimler[j + 1][0][0].islower()
                    and ((altbirim == "-" and (altbirimler[j - 1][0][0].isupper()
                                               or not any(c in profil.ünlüler for c in altbirimler[j - 1][0])))
                         or altbirim[-1] in KAPANIŞ_TIRNAK)):
                önceki_kesme = True                  # AZ: ABŞ-ın, Magnitsky-nin, XX-ci, km-i; «pullar»ın
            continue
        if önceki_kesme:
            # Kesme sonrası harf-koşusu = EK (özel ad/akronim/sayı eki: İstanbul'da,
            # Ahmet'in, 2024'te) → hecele, BİLİNMEYEN kuyruğuna atma. Küçük harf eki
            # olduğu gibi hecelenir; büyük harfli (nadir) bütün/harf-fallback kalır.
            tokenlar.extend(hecele(altbirim, profil))
            önceki_kesme = False
            continue
        küçük = sesler.türkçe_küçült(altbirim) if profil is None else profil.küçült(altbirim)
        durum = _harf_durumu(altbirim, küçük, profil)
        if profil is not None and profil.casing == "unicode" and durum in BÜYÜK:
            # EN: Python casing'i, decode'un ASCII işaretçisiyle aynı kural (str.upper; 'I' → 'i', 'ı' değil).
            # Klitikli HEP BÜYÜK sözcük (DON'T) bütün: decode'da kesme koşuyu bitirir, klitik büyütülemezdi.
            # Elizyon birimi (QU') kesmeyle BİTER: kesme koşuyu yalnız sonunda bitirir → işaretçi yeterli.
            durum = ("düz" if durum == HEP_BÜYÜK and any(c in KESME for c in altbirim[:-1])
                     else ASCII_BAŞ if durum == BAŞ_BÜYÜK else ASCII_HEP)
        if durum == "düz":                       # karışık biçim → bütün-token, koru
            tokenlar.append(altbirim)
            continue
        if durum:                                # casing işaretçisi (Başlık / HEP BÜYÜK)
            tokenlar.append(durum)
        ad_okuma = (profil is not None and (profil.özel_ad_başlık or profil.ad_büyük)
                    and durum in (BAŞ_BÜYÜK, ASCII_BAŞ))
        anahtar = küçük if profil is None else (profil.kod, küçük, "ad") if ad_okuma else (profil.kod, küçük)
        if önbellek is not None and anahtar in önbellek:
            _tk, _bilinmeyen = önbellek[anahtar]
            if _bilinmeyen and kuyruk is not None:   # isabet'te de kuyruğa al (frekans doğru)
                kuyruk.ekle(küçük, metin)
            tokenlar.extend(_tk)
            continue
        _tk, _bilinmeyen = _kelime_token(küçük, kökler, ekler, istisnalar, kuyruk, metin, profil, ad_okuma)
        if önbellek is not None:
            önbellek[anahtar] = (_tk, _bilinmeyen)
        tokenlar.extend(_tk)


def decode(tokenlar, kip: str = "metin", düz=frozenset()) -> str:
    """Token dizisini metne geri çevirir (özel tokenları atar, ▁→boşluk, casing uygular).

    kip "kod": baş/son boşluk KIRPILMAZ (girinti ve son satır sonu koddur); ▁-koşusu tokenı
    o kadar boşluk, satır sonu/sekme/CR harfiyen. Boşluk casing koşusunu bitirir (iki kipte).

    Casing işaretçisi yalnız KENDİNDEN SONRAKİ harf-koşusuna uygulanır; noktalama (ör.
    kesme) ya da boşluk koşuyu bitirir → "TBMM'de" ALLCAPS yalnız TBMM'ye, 'de eke değil.
    Koşu sınırı encode'unkiyle AYNI ölçüttür (_harf_mi): encode'da harf-dışı olan her karakter
    (noktalama, sembol, kesme) koşuyu bitirir → casing yalnız işaretçinin ait olduğu kelimeye.

    Bayt tokenları: ardışık koşu UTF-8 çözülür ve HARFİYEN metin olur (asla boşluk/özel token
    sayılmaz: metindeki '▁' geri '▁' döner); casing ona da aynı ölçütle uygulanır.

    düz: harfiyen yazılan tokenlar (v2 kaynaşık yüzeyleri: "▁Haus" → " Haus"; tokenizer/v2.py)."""
    sonuç: list[str] = []
    durum = None                                 # bekleyen casing işaretçisi
    baytlar = bytearray()

    def metin_ekle(t):
        nonlocal durum
        for parça, harf_mi in _altbirimler(t):
            if not harf_mi:                      # noktalama/rakam: casing koşusunu bitir
                durum = None
                sonuç.append(parça)
            elif durum == ASCII_HEP:
                sonuç.append(parça.upper())
            elif durum == ASCII_BAŞ:
                sonuç.append(parça[:1].upper() + parça[1:]); durum = None
            elif durum == HEP_BÜYÜK:
                sonuç.append(sesler.türkçe_büyült(parça))     # koşu boyunca sürer
            elif durum == BAŞ_BÜYÜK:
                sonuç.append(sesler.türkçe_başlık(parça)); durum = None   # yalnız ilk token
            else:
                sonuç.append(parça)

    for t in tokenlar:
        b = _BAYT.get(t)
        if b is not None:
            baytlar.append(b)
            continue
        if baytlar:
            metin_ekle(_bayt_çöz(baytlar))
            baytlar.clear()
        if t in düz:
            sonuç.append(" " + t[1:] if t[0] == BOŞLUK else t)
            durum = None
        elif t in BÜYÜK or t in ASCII_İŞARET:
            durum = t
        elif t in _BOŞLUK_KOŞULARI:
            sonuç.append(" " * len(t))
            durum = None
        elif t in KOD_BOŞLUKLARI:
            sonuç.append(t)
            durum = None
        elif t in ÖZEL:
            continue
        else:
            metin_ekle(t)
    if baytlar:
        metin_ekle(_bayt_çöz(baytlar))
    çıktı = "".join(sonuç)
    return çıktı if kip == "kod" else çıktı.strip()

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

from tokenizer import alfabe, sesler
from tokenizer.cozumle import çözümle
from tokenizer.hece import hecele

BOŞLUK = "▁"
KESME = ("'", "’")   # düz ve sağ-tek-tırnak (İstanbul'da / İstanbul'da)
BAŞ_BÜYÜK = "<|Bb|>"   # sonraki kelime Başlık-biçimi (ilk harf büyük): Bugün
HEP_BÜYÜK = "<|BB|>"   # sonraki kelime HEP BÜYÜK: TÜRK
PAD, UNK, BOS, EOS = "<pad>", "<unk>", "<s>", "</s>"
ÖZEL = {PAD, UNK, BOS, EOS, "<|sistem|>", "<|kullanici|>", "<|asistan|>", "<|bitis|>"}
BÜYÜK = {BAŞ_BÜYÜK, HEP_BÜYÜK}   # casing işaretçileri (decode'da TÜKETİLİR, atılmaz)

# Türkçe alfabe + büyük harfler + düzeltme imli ünlüler (â/î/û: hikâye, kâğıt, rüzgâr).
# Düzeltme imli ünlüler kelimeyi BÖLMEMELİ (aksi halde "hikâye"→hik+â+ye yanlış bölünür);
# harf sayılır, kelime bütün tutulur (kök eşleşmezse bilinmeyen-bütün, round-trip korunur).
# q/w/x (vocab Faz 1): Türkçe alfabede yok ama Latin metinde yaygın (Windows, XIV, max_index);
# harf sayılır → kelimeyi bölmez. Hiçbir kök/ek/istisna q/w/x içermez → bu harfi taşıyan
# kelime motorca parçalanamaz: bilinmeyen-BÜTÜN (onay kuyruğu), vocab'da hece→harf fallback.
_HARFLER = (set(alfabe.ALFABE) | set("ABCÇDEFGĞHIİJKLMNOÖPRSŞTUÜVYZ") | set("âîûÂÎÛ")
            | set("qwxQWX"))


def _harf_durumu(kelime, küçük):
    """Kelimenin casing işaretçisi: None (küçük) | BAŞ_BÜYÜK (Başlık) | HEP_BÜYÜK | 'düz'.

    'düz' = küçük-harf biçiminden basit casing ile geri üretilemeyen karışık biçim
    (iPhone gibi) → işaretçisiz, bütün-token korunur (kayıpsızlık için)."""
    if kelime == küçük:
        return None
    if kelime == sesler.türkçe_başlık(küçük):
        return BAŞ_BÜYÜK
    if kelime == sesler.türkçe_büyült(küçük):
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


def en_iyi_çözüm(çözümler, kökler, ekler):
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
    resmi+iyelik_2tekil [res,mi,n] tüm ölçütlerde berabere → [re,sm,in]."""
    return min(
        çözümler,
        key=lambda ç: (0 if not ç.ekler else 1, len(ç.tokens),
                       _öbek_uyumsuz(ç, kökler, ekler), -len(ç.kök),
                       tuple(ç.tokens), ç.kök, tuple(ç.ekler)),
    )


def _altbirimler(parça):
    """Bir parçayı harf (kelime) ve harf-dışı (noktalama) koşularına ayırır."""
    for harf_mi, grup in itertools.groupby(parça, key=lambda c: c in _HARFLER):
        yield "".join(grup), bool(harf_mi)


def _kelime_token(kelime, kökler, ekler, istisnalar, kuyruk, bağlam):
    """(token_listesi, bilinmeyen_mi) döndürür. bilinmeyen_mi: çözülemedi → kuyruğa alındı."""
    çs = çözümle(kelime, kökler, ekler, istisnalar)
    if çs:
        return list(en_iyi_çözüm(çs, kökler, ekler).tokens), False
    if kuyruk is not None:                       # bilinmeyen → bize sorulur
        kuyruk.ekle(kelime, bağlam)
    return [kelime], True                        # BÜTÜN tut


def encode(metin, kökler, ekler, istisnalar=None, kuyruk=None, önbellek=None) -> list[str]:
    """Metni token dizisine çevirir.

    önbellek (opsiyonel dict): {küçük_kelime: token_listesi} — büyük korpusta (Aşama 1)
    aynı kelimeyi tekrar çözmemek için memoization. Deterministik (aynı kelime hep aynı
    token); yalnız hız. kuyruk yan-etkisi ilk görülüşte işler (kuyruk zaten tekilleştirir)."""
    tokenlar: list[str] = []
    for i, parça in enumerate(metin.split()):
        if i > 0:
            tokenlar.append(BOŞLUK)
        önceki_kesme = False                     # bir önceki altbirim kesme ile mi bitti?
        for altbirim, kelime_mi in _altbirimler(parça):
            if not kelime_mi:                    # noktalama: her karakter ayrı token
                tokenlar.extend(altbirim)
                önceki_kesme = altbirim[-1] in KESME
                continue
            if önceki_kesme:
                # Kesme sonrası harf-koşusu = EK (özel ad/akronim/sayı eki: İstanbul'da,
                # Ahmet'in, 2024'te) → hecele, BİLİNMEYEN kuyruğuna atma. Küçük harf eki
                # olduğu gibi hecelenir; büyük harfli (nadir) bütün/harf-fallback kalır.
                tokenlar.extend(hecele(altbirim))
                önceki_kesme = False
                continue
            küçük = sesler.türkçe_küçült(altbirim)
            durum = _harf_durumu(altbirim, küçük)
            if durum == "düz":                   # karışık biçim → bütün-token, koru
                tokenlar.append(altbirim)
                continue
            if durum:                            # casing işaretçisi (Başlık / HEP BÜYÜK)
                tokenlar.append(durum)
            if önbellek is not None and küçük in önbellek:
                _tk, _bilinmeyen = önbellek[küçük]
                if _bilinmeyen and kuyruk is not None:   # isabet'te de kuyruğa al (frekans doğru)
                    kuyruk.ekle(küçük, metin)
                tokenlar.extend(_tk)
                continue
            _tk, _bilinmeyen = _kelime_token(küçük, kökler, ekler, istisnalar, kuyruk, metin)
            if önbellek is not None:
                önbellek[küçük] = (_tk, _bilinmeyen)
            tokenlar.extend(_tk)
    return tokenlar


def decode(tokenlar) -> str:
    """Token dizisini metne geri çevirir (özel tokenları atar, ▁→boşluk, casing uygular).

    Casing işaretçisi yalnız KENDİNDEN SONRAKİ harf-koşusuna uygulanır; noktalama (ör.
    kesme) ya da boşluk koşuyu bitirir → "TBMM'de" ALLCAPS yalnız TBMM'ye, 'de eke değil."""
    sonuç: list[str] = []
    durum = None                                 # bekleyen casing işaretçisi
    for t in tokenlar:
        if t in BÜYÜK:
            durum = t
        elif t == BOŞLUK:
            sonuç.append(" ")
            durum = None
        elif t in ÖZEL:
            continue
        elif any(c.isalpha() for c in t):        # harf-içeren token: casing uygula
            if durum == HEP_BÜYÜK:
                sonuç.append(sesler.türkçe_büyült(t))     # koşu boyunca sürer
            elif durum == BAŞ_BÜYÜK:
                sonuç.append(sesler.türkçe_başlık(t)); durum = None   # yalnız ilk token
            else:
                sonuç.append(t)
        else:                                    # noktalama/rakam: casing koşusunu bitir
            durum = None
            sonuç.append(t)
    return "".join(sonuç).strip()

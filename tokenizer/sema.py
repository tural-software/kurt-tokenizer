"""Kök sözlüğü şeması ve doğrulaması.

Alan adları .claude/CLAUDE.md ile birebir aynıdır (JSON anahtarları = dataclass
alanları): tokens, tür, son_ünlü, son_ses, değişim. Doğrulama saf stdlib ile
yapılır; harici bağımlılık yoktur.

Not: Heceleme *yapısı* (CVCC vb.) burada doğrulanmaz — o, hece motoru maddesine
aittir. Şimdilik yalnızca `"".join(tokens) == kök_adı` değişmezi denetlenir.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from tokenizer import sesler

İZİNLİ_TÜRLER: frozenset[str] = frozenset(
    {"fiil", "isim", "sıfat", "zarf", "zamir", "edat", "bağlaç", "ünlem", "özel"}
)  # özel: özel ad (AZ veri/az/ozel_adlar.json) — ad sınıfında çekimlenir, seçimde sıradan köke yenilir
İZİNLİ_SON_SES: frozenset[str] = frozenset({"ünlü", "ünsüz"})


TÜREMİŞ_TÜRLERİ = frozenset({"", "hep", "ekli", "çıplak"})


@dataclass(frozen=True)
class Kök:
    """Tek bir kök kaydı. Alanlar CLAUDE.md şemasıyla birebir eşleşir."""

    tokens: list[str]
    tür: str
    son_ünlü: str
    son_ses: str
    değişim: dict | None = None
    ek_tür: list = field(default_factory=list)   # eşsesli: ikincil türler (yaz: fiil + [isim])
    düşen: bool = False   # ünlü düşmesi: son ünlü, ünlü-başlı ek gelince düşer (akıl→aklım)
    ince: bool = False    # istisnai uyum: art ünlü ama ince ek alır (kalp→kalbi, rol→rolü)
    sadece_koşaç: bool = False  # yalnız koşaç/ek-fiil alır, isim eki almaz (mı, değil)
    daralan: bool = False  # ye/de düzensizi: çekirdek e→i, y-glide'lı ek öncesi (ye→yiyor)
    y_tampon: bool = False  # (n) tamponu yerine y (AZ su→suyu/suyun, nə→nəyi/nəyin; düzensiz)
    qoşa_tek: bool = False  # son çift ünsüz, ünsüzle başlayan İLK ek önünde teke iner (AZ xətt → xətlər,
    #                         xətdə; hədd+dən → həddən). hiss/həll korur (hisslər) → bayraksız
    türemiş: str = ""       # bileşik biçimle eşsesli sözlük başlığı; bileşik okuma varsa o yeğlenir
    #                         (pipeline.en_iyi_çözüm, dil profili). "hep": her zaman (AZ olan = ol+an,
    #                         gəlir = gəl+ir); "ekli": yalnız ek alınca (-mA adı: düymə bütün, gəlməliyəm =
    #                         gəl+məli+y+əm); "çıplak": yalnız eksizken (-Ir ettirgen: artır = art+ır,
    #                         artırmalı = artır+malı)
    geri: bool = False      # eşsesli kök çakışmasında geri çekilir: aynı yüzeyi rakip bir kök de üretiyorsa o
    #                         yeğlenir (AZ korpus kararı, scripts/az_sozluk/geri.py: bacım = bacı+m, bac+ı+m
    #                         değil; siyahımıza = siyahı+mız+a). Tek okumada etkisiz
    ikiz: bool = False      # son ünsüz, ünlüyle başlayan İLK ek önünde ikizleşir (TR hak → hakk+ı, his → hiss+i,
    #                         tıp → tıbb+ı; TDK taki). Ünsüz önünde tek (haklar)
    ek_değişim: dict | None = None  # İKİNCİL sınıf (ek_tür) okumasının yumuşaması; None=ikincilde
    #                                 yumuşama yok (art→artıyor). tat gibi her-iki-yön: {t→d} (tadıyor)


def doğrula(ad: str, kök: Kök, profil=None) -> list[str]:
    """Bir kök kaydını doğrular. Tüm hata mesajlarını liste olarak döndürür.

    İlk hatada durmaz; elle düzenlenen sözlükte tek geçişte tüm sorunları
    görebilmek için bütün ihlalleri toplar. Boş liste = geçerli.
    """
    hatalar: list[str] = []
    ünlüler = sesler.ÜNLÜLER if profil is None else profil.ünlüler

    # 1. tokens boş değil; her token boş olmayan metin
    if not kök.tokens:
        hatalar.append(f"{ad!r}: tokens boş olamaz")
    else:
        for i, t in enumerate(kök.tokens):
            if not isinstance(t, str) or t == "":
                hatalar.append(
                    f"{ad!r}: tokens[{i}] boş olmayan metin olmalı, bulundu {t!r}"
                )

    # 2. tokens birleşimi kök adını (yüzey biçimini) vermeli
    if kök.tokens and all(isinstance(t, str) for t in kök.tokens):
        birleşim = "".join(kök.tokens)
        if birleşim != ad:
            hatalar.append(
                f"{ad!r}: tokens birleşimi {birleşim!r} köke eşit değil"
            )

    # 3. son_ünlü geçerli bir ünlü olmalı
    if kök.son_ünlü not in ünlüler:
        hatalar.append(f"{ad!r}: son_ünlü {kök.son_ünlü!r} geçerli bir ünlü değil")

    # 4. son_ünlü, kökün gerçek son ünlüsüyle aynı olmalı
    gerçek = sesler.son_ünlü_bul(ad) if profil is None else profil.son_ünlü_bul(ad)
    if gerçek is None:
        hatalar.append(f"{ad!r}: kökte hiç ünlü yok")
    elif kök.son_ünlü in ünlüler and gerçek != kök.son_ünlü:
        hatalar.append(
            f"{ad!r}: son_ünlü {kök.son_ünlü!r} ama yüzey biçiminin son ünlüsü {gerçek!r}"
        )

    # 5. son_ses geçerli ve son karaktere uygun olmalı
    if kök.son_ses not in İZİNLİ_SON_SES:
        hatalar.append(f"{ad!r}: son_ses {kök.son_ses!r} geçersiz (ünlü|ünsüz)")
    elif ad:
        beklenen = "ünlü" if ad[-1] in ünlüler else "ünsüz"
        if kök.son_ses != beklenen:
            hatalar.append(
                f"{ad!r}: son_ses {kök.son_ses!r} ama son karakter {ad[-1]!r} → {beklenen}"
            )

    # 6. tür izinli türlerden olmalı
    if kök.tür not in İZİNLİ_TÜRLER:
        hatalar.append(f"{ad!r}: tür {kök.tür!r} izinli türlerden değil")

    # 6b. ek_tür (eşsesli ikincil türler) izinli ve birincilden farklı olmalı
    for t in (kök.ek_tür or []):
        if t not in İZİNLİ_TÜRLER:
            hatalar.append(f"{ad!r}: ek_tür {t!r} izinli türlerden değil")
        elif t == kök.tür:
            hatalar.append(f"{ad!r}: ek_tür {t!r} birincil tür ile aynı")

    # 6c. düşen bool olmalı; düşen kök çok-heceli olmalı (tek hecede düşecek son ünlü yok)
    if not isinstance(kök.düşen, bool):
        hatalar.append(f"{ad!r}: düşen alanı bool olmalı, bulundu {kök.düşen!r}")
    elif kök.düşen and len(kök.tokens or []) < 2:
        hatalar.append(f"{ad!r}: düşen kök en az iki heceli olmalı")
    if not isinstance(kök.ince, bool):
        hatalar.append(f"{ad!r}: ince alanı bool olmalı, bulundu {kök.ince!r}")
    if not isinstance(kök.sadece_koşaç, bool):
        hatalar.append(f"{ad!r}: sadece_koşaç alanı bool olmalı, bulundu {kök.sadece_koşaç!r}")
    if not isinstance(kök.daralan, bool):
        hatalar.append(f"{ad!r}: daralan alanı bool olmalı, bulundu {kök.daralan!r}")
    if not isinstance(kök.qoşa_tek, bool):
        hatalar.append(f"{ad!r}: qoşa_tek alanı bool olmalı, bulundu {kök.qoşa_tek!r}")
    elif kök.qoşa_tek and not (len(ad) > 2 and ad[-1] == ad[-2] and ad[-1] not in ünlüler):
        hatalar.append(f"{ad!r}: qoşa_tek yalnız çift ünsüzle biten kökte anlamlı")
    if kök.türemiş not in TÜREMİŞ_TÜRLERİ:
        hatalar.append(f"{ad!r}: türemiş alanı {sorted(TÜREMİŞ_TÜRLERİ)} olmalı, bulundu {kök.türemiş!r}")
    if not isinstance(kök.ikiz, bool):
        hatalar.append(f"{ad!r}: ikiz alanı bool olmalı, bulundu {kök.ikiz!r}")
    elif kök.ikiz and not (ad and ad[-1] not in ünlüler):
        hatalar.append(f"{ad!r}: ikiz yalnız ünsüzle biten kökte anlamlı")
    if not isinstance(kök.geri, bool):
        hatalar.append(f"{ad!r}: geri alanı bool olmalı, bulundu {kök.geri!r}")
    if not isinstance(kök.y_tampon, bool):
        hatalar.append(f"{ad!r}: y_tampon alanı bool olmalı, bulundu {kök.y_tampon!r}")
    elif kök.y_tampon and kök.son_ses != "ünlü":
        hatalar.append(f"{ad!r}: y_tampon yalnız ünlü-sonu kökte anlamlı")

    # 7. değişim / ek_değişim None ya da dict[str, str] olmalı
    for alan_ad, alan in (("değişim", kök.değişim), ("ek_değişim", kök.ek_değişim)):
        if alan is None:
            continue
        if not isinstance(alan, dict):
            hatalar.append(f"{ad!r}: {alan_ad} None ya da sözlük olmalı")
        else:
            for k, v in alan.items():
                if not isinstance(k, str) or not isinstance(v, str):
                    hatalar.append(
                        f"{ad!r}: {alan_ad} girdisi {k!r}: {v!r} metin→metin olmalı"
                    )
    # 7b. ek_değişim ancak ek_tür (ikincil sınıf) varsa anlamlı
    if kök.ek_değişim and not (kök.ek_tür or []):
        hatalar.append(f"{ad!r}: ek_değişim var ama ek_tür yok (ikincil sınıf tanımsız)")

    return hatalar

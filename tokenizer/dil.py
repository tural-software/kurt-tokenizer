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
    edilgen_tek_heceli_y: bool = False  # tek heceli ünlü-sonu gövdede edilgen (y)Il (AZ deyil, yeyil)
    ettirgen_çok_heceli_rl: bool = False  # -t yalnız ünlü + ÇOK heceli r/l sonrası (AZ oturt/azalt;
                                          # tek heceli gördür/aldır). False: Türkçe (ünlü/r → t)
    rakam_tire_eki: bool = False  # rakamdan (ya da % ² ³ ° işaretinden) sonra tire + harf = ek (AZ 2024-cü,
    #                               5-də, 30%-i, km²-dir; kesme gibi)
    büyük_tire_eki: bool = False  # büyük harfli ya da ÜNLÜSÜZ küçük harfli parça + tek tire + küçük harfli
    #                               parça = ek (AZ ABŞ-ın, Magnitsky-nin, XX-ci, km-i, mm-dir: kısaltma/yabancı
    #                               özel ada ek tireyle; ünlüsüz dizi AZ sözcüğü olamaz → ev-ev bileşik kalır)
    kişi_lisansı: tuple = ()    # ortak KİŞİ_LİSANS'a dile özgü ek: (ek_adı, tip, kaynak) üçlüleri
    # Seçim politikası eklentileri (pipeline.en_iyi_çözüm; Türkçe politika değişmez):
    son_çare_ekler: frozenset = frozenset()  # bu ekleri içeren çözüm yalnız başka çözüm yoksa
    #                                          (AZ bitişik soru -mI: özümü = öz+ü+m+ü, öz+ü+mü değil)
    az_ek_önce: bool = False    # token sayısı eşitse daha az ekli çözüm (gəl+məli+y+əm, gəl+mə+liy+əm değil)
    birincil_önce: bool = False # eşsesli kök birincil sınıfıyla okunabiliyorsa o okuma (yazsan = yaz+sa+n
    #                             'yazarsan', yaz [mevsim]+san değil)
    seyrek_ekler: frozenset = frozenset()  # İLK ölçüt: bu (seyrek) ekleri içeren çözüm, başka çözüm varsa
    #                                          seçilmez — türemiş kökten de önce (AZ üretken dönüşlü -(I)n:
    #                                          yerinə = yer+i+n+ə, yeri+n+ə değil; edebî istek kişileri
    #                                          -(y)Am/-(y)AlAr: atam = ata+m, at+am değil)
    zamir_önce: bool = False  # birim + ek sayısı eşitliğinde kapalı sınıf zamir kökü yeğlenir (AZ haraya =
    #                           hara+y+a, haray 'feryat'+a değil)
    düşen_isteğe_bağlı: bool = False  # ünlü düşmesi kökü düşmeden de çözülür (AZ danışıq: şəkili ↔ normatif şəkli)
    özel_ad_başlık: bool = False  # Başlık biçimli sözcükte (Gəncə, Quran) özel ad kökü okuması yeğlenir; küçük harflide
    #                               (gəncə) sıradan kök. Önbellek anahtarı ayrı: (dil, kelime, "ad")
    birim_say: bool = False  # token sayısı yerine BİRİM (kök hecesi + ek sayısı): tampon tokenı (n/y/s)
    #                          morfem sayılmaz → ünlü-sonu kök cezalanmaz (AZ ata+n+ı = 3 birim, at+an+ı
    #                          = 3; eşitlikte az ek: ata). Token sayısı sonraki kırıcı.
    seyrek_diziler: frozenset = frozenset()  # seyrek_ekler ile aynı katman: bu ARDIŞIK ek çiftleri
    #                                          (AZ ortaç -An + idi/imiş: yenilənmiş = yenilə+n+miş, yen+il+ən+miş
    #                                          değil; tamlayan + idi: oxundu = oxu+n+du, ox+un+du değil)
    # Dil ailesi (EN-1): Türk dilleri ünlü uyumlu üreteci (birlestir/cozumle) paylaşır; İngilizce yazım
    # kurallı kendi üretecini (tokenizer/en.py) kullanır. Hat, casing, vocab, kuyruk ve seçim ortak.
    motor: str = "türk"         # "türk" | "en" | "fr" (sözcük çözümleyicisi)
    casing: str = "türk"        # "türk": İ/i I/ı, işaretçi <|Bb|>/<|BB|> | "unicode": str.lower/upper,
    #                             işaretçi <|Ab|>/<|AA|> (İngilizce 'I' → 'ı' olmaz)
    hece: str = "türk"          # yedek heceleme kuralı: "türk" (hece.py) | "en" (en.hecele) | "fr" (fr.hecele)
    kesme_eki: bool = True      # kesme sonrası harf koşusu EK (Türkçe İstanbul'da); EN'de kapalı (O'Brien)
    klitikler: tuple = ()       # kesmeli klitikler (EN 's 're n't …): sözcükle birleşik okunur (en.py)
    elizyonlar: tuple = ()      # SOLDAKİ kesmeli klitikler (FR l' d' qu' …): kesmeyle tek birim, sonraki sözcükten
    #                             ayrı token (l'homme = l' + homme; pipeline._elizyon_birleştir)
    yeğlenmeyen_ekler: frozenset = frozenset()  # aynı token sayısında bu ekleri içermeyen çözüm
    #                             yeğlenir (AZ 2. kişi iyelik: altından = alt+ı+n+dan, altı+n+dan değil;
    #                             edilgen/ettirgen: yerinə = yer+i+n+ə, yeri+n+ə değil; yapım -lI: həlli =
    #                             həll+i 'çözümü', həll+li değil — çift ünsüz tekleşmesi aynı yüzeyi verir)

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

    # ── yazım (casing: Türk dilleri İ/i, I/ı; unicode = Python varsayılanı, decode ASCII işaretçisiyle aynı) ──
    def küçült(self, s: str) -> str:
        return s.lower() if self.casing == "unicode" else sesler.türkçe_küçült(s)

    def büyült(self, s: str) -> str:
        return s.upper() if self.casing == "unicode" else sesler.türkçe_büyült(s)

    def başlık(self, s: str) -> str:
        return s[:1].upper() + s[1:] if self.casing == "unicode" else sesler.türkçe_başlık(s)

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
    değişken_son="aəkqşzt",         # ş: -mIş + sAn → gəlmisən (son_düşer); z: -mAz → -mAr (gəlmərəm);
    #                                 t: ettirgen -t ünlü önünde d (oxu+t+ur → oxudur)
    daralan_son="aə",
    daraltma="olumsuz",
    geniş="az",
    ettirgen_ünsüz="dIr",
    ettirgen_çok_heceli_rl=True,
    edilgen_tek_heceli_y=True,
    rakam_tire_eki=True,
    büyük_tire_eki=True,
    # -(y)Ib geçmişi (gəlibsən, gəliblər) ve gereklilik (gəlməliyəm, gəlməliyik) kişi eki alır.
    kişi_lisansı=(("geçmiş_ib", 1, "V"), ("gereklilik", 1, "V"), ("ek_fiil_di", 2, "K")),
    son_çare_ekler=frozenset({"soru"}),
    az_ek_önce=True,
    birincil_önce=True,
    # danışıq (konuşma) ekleri ve -(y)AsI ortacı da seyrek: normatif okuma varsa o seçilir (atası = ata+sı)
    seyrek_ekler=frozenset({"dönüşlü", "istek_1tekil", "istek_2tekil", "istek_2çoğul", "istek_3çoğul",
                            "emir_2çoğul_kibar", "şahıs_2çoğul_k", "gelecek_1tekil_k", "ortaç_ası",
                            "soyad_ov", "soyad_ova", "soyad_yev", "soyad_yeva", "soyad_zadə"}),
    seyrek_diziler=frozenset({("ortaç_an", "ek_fiil_idi"), ("ortaç_an", "ek_fiil_imiş"),
                              ("tamlayan", "ek_fiil_idi"), ("tamlayan", "ek_fiil_imiş"),
                              ("ortaç_an", "ek_fiil_di"), ("tamlayan", "ek_fiil_di"),
                              ("koşaç_3çoğul", "koşaç_ise")}),
    birim_say=True,
    özel_ad_başlık=True,
    düşen_isteğe_bağlı=True,
    zamir_önce=True,
    yeğlenmeyen_ekler=frozenset({"iyelik_2tekil", "iyelik_2çoğul", "edilgen", "ettirgen", "yapım_lı",
                                 "ek_fiil_idi", "ek_fiil_di"}),
)

# İngilizce (EN-1): ünlü uyumu yok; ek yüzeyleri sabit, yazım değişimi (çift ünsüz, e düşmesi, y→i) en.py'de.
# Ses alanları (kalın/ince…) Türk üretecine aittir, EN'de kullanılmaz. y yazımda ünlü de olabilir (hece/kural).
EN = DilProfili(
    kod="en",
    alfabe="abcdefghijklmnopqrstuvwxyz",
    ünlüler=frozenset("aeiou"),
    kalın=frozenset(),
    ince=frozenset(),
    düz=frozenset(),
    yuvarlak=frozenset(),
    sert=frozenset(),
    geniş_ince="",
    ince_karşılık=(),
    değişken_son="",
    daralan_son="",
    daraltma="",
    motor="en",
    casing="unicode",
    hece="en",
    kesme_eki=False,
    klitikler=("n't", "'s", "'re", "'ve", "'ll", "'d", "'m"),
    özel_ad_başlık=True,
)

# Fransızca (FR-1): ünlü uyumu yok; çekim kendi üretecinde (tokenizer/fr.py, veri/fr/cekim.json). Harfler a-z +
# à â æ ç é è ê ë î ï ô œ ù û ü ÿ. Elizyon solda ayrı token; kesme sonrası ek kuralı kapalı (aujourd'hui, l'homme).
FR = DilProfili(
    kod="fr",
    alfabe="aàâæbcçdeéèêëfghiîïjklmnoôœpqrstuùûüvwxyÿz",
    ünlüler=frozenset("aàâæeéèêëiîïoôœuùûüyÿ"),
    kalın=frozenset(),
    ince=frozenset(),
    düz=frozenset(),
    yuvarlak=frozenset(),
    sert=frozenset(),
    geniş_ince="",
    ince_karşılık=(),
    değişken_son="",
    daralan_son="",
    daraltma="",
    motor="fr",
    casing="unicode",
    hece="fr",
    kesme_eki=False,
    elizyonlar=("l", "d", "j", "m", "t", "s", "n", "c", "ç", "qu", "jusqu", "lorsqu", "puisqu", "quoiqu", "quelqu"),
    özel_ad_başlık=True,
)

PROFİLLER: dict[str, DilProfili] = {"tr": TR, "az": AZ, "en": EN, "fr": FR}
# Metin kipinde seçilebilen doğal diller (None = Türkçe). Kod kipindeki 'dil' programlama dilidir.
DOĞAL_DİLLER = frozenset(k for k in PROFİLLER if k != "tr")

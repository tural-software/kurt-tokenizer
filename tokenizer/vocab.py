"""Token vocabulary: token ↔ ID eşlemesi ve ID-düzeyi encode/decode.

Tokenizer'ın asıl çıktısı: bir modelin tüketebileceği SABİT vocab + ID dizisi. Bu modül
motorun ürettiği token kümesini DETERMİNİSTİK toplayıp dondurur (BPE gibi corpus'tan
öğrenmez — kurallarımızdan türer):

  1. ÖZEL tokenlar      <pad>/<unk>/<s>/</s>/<|...|>/<|Bb|>/<|BB|>/▁   (sabit ID önek)
  2. ATOMİK taban       tüm harf (iki büyüklük) + â/î/û + rakam + noktalama  (fallback zemini)
  3. HECE/MORFEM        46k kökün tüm heceleri + ek yüzeyleri + tamponlar + istisna tokenları

Bilinmeyen kelime (sabit vocab'da bütün-token OLAMAZ): HECE→HARF→BAYT fallback ile
atomik tabana iner (kayıpsız); "bütün tut" felsefesi onay kuyruğunda korunur (kelime yine
insana sorulur). Vocab'da olmayan karakter (ā, Ω, emoji…) UTF-8 bayt tokenlarına iner
(Faz 2) → encode_ids hiçbir girdi için <unk> üretmez (<unk> ID 1 model uyumu için durur).

SONA-EKLEME SÖZLEŞMESİ: model her tokenı ID'siyle öğrenir → bir ID'nin anlamı ASLA değişmez.
Vocab bölümlerden oluşur: v1 (yukarıdaki 1-3, Türkçe çekirdek, 4112, DONMUŞ — statik veri/vocab_v1.json) + EK_BÖLÜMLER
sırayla SONA eklenir. Yeni token yalnız YENİ bir bölümle girer; var olan bölüm değişmez, araya
token girmez. DONMUŞ_BÖLÜMLER her bölümün boyu + SHA-256 özetini kilitler (test_vocab önek
kapısı): bir kök eklemesi v1'i kaydırırsa ya da bir bölüm sessizce değişirse test KIRMIZI.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from tokenizer import sesler
from tokenizer.hece import hecele
from tokenizer.pipeline import (encode, decode, BOŞLUK, BAŞ_BÜYÜK, HEP_BÜYÜK, ÖZEL, REZERV,
                                BAYT_TOKENLARI, bayt_tokenları, KOD_BOŞLUKLARI,
                                BOŞLUK_KOŞULARI, ASCII_İŞARET, SATIR, LATEX_TOKENLARI)
from tokenizer.kod import PY_ANAHTAR, PY_İŞLEM, PY_TIRNAK, KOD_SÖZLÜK_YENİ
from tokenizer.dil import PROFİLLER, DOĞAL_DİLLER
from tokenizer.v2 import SÜRÜMLER, kaynaştır, harf_tokenı

# Python anahtar sözcüklerinden v1'de Türkçe hece/token olarak zaten bulunanlar (tekrar eklenmez;
# yanlış bırakılırsa bölümleri_ekle tekrar hatası verir → liste kendini denetler).
_PY_V1_ORTAK = frozenset({"and", "as", "def", "del", "for", "if", "in", "is", "not", "or"})

# Sabit önek: özel tokenlar (ID 0..) — sıra KALICI olmalı (model bağımlılığı).
ÖZEL_TOKENLAR = ["<pad>", "<unk>", "<s>", "</s>", "<|sistem|>", "<|kullanici|>",
                 "<|asistan|>", "<|bitis|>", BAŞ_BÜYÜK, HEP_BÜYÜK, BOŞLUK]


# ── Faz 3 karakter aileleri (kaynakların tamamında ölçüldü: 3,18 milyar karakter, 16 kaynak;
#    eşik ≥1.000 oluşum + ≥3 kaynak, aileler tamamlanır; kullanıcı onaylı). Yalnız KÜÇÜK harf:
#    büyük harfi casing işaretçisi taşır. Mojibake (Ģ Ġ › ¤ º…) GİRMEZ → bayt + Faz V onarımı.
_TÜRKOLOJİ = "āīūēōḥḫḳṣṭẓżḍẕŝġñŋķĥïʿʾʽ"      # Osmanlıca/Türkoloji transkripsiyon (oġlı, *beniŋ)
_TÜRK_DİLLERİ = "əäýňžʻ"                      # Azerbaycan, Türkmen, Özbek
_KÜRTÇE = "ê"                                  # Kurmancî/Zazaca (î û v1'de)
_AVRUPA = "éèáàíìóòúùãôøåæßëćčšđśńșɑ"         # özel adlar, dil dersleri, pinyin + IPA ɑ
_YUNAN = "αβγδεζηθικλμνξοπρσςτυφχψω"          # bilim (α β μ δ…), alfabe tamamlandı
_BİRLEŞEN = "̇̄̅̂"         # üst nokta, makron, üst çizgi (x̅), şapka
_MATEMATİK = "±−×÷≠≤≥≈≡≅∼∝∞√∑∏∫∂∇∆∈∉∀∃∅∩∪⊂⊆⊃⊇∠⊥∥∧∨¬⋅∙∘⊕⊗∓∗⋯⟨⟩≪≫ℝℕℤℚℂ"
_OK = "→←↑↓↔↕⇒⇐⇔↗↘⟶⟹↦"
_SİMGE = "¹⁰⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿ₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎"      # üst/alt simge tam aile (² ³ v1'de)
_KESİR = "½¼¾⅓⅔"
_PARA = "₺€£¥₽₿"                               # $ v1'de
_MADDE = "●■▪◦○□◆◇►▶◀▲▼△✓✔✗✘✅❌★☆†‡¶"          # liste, onay, şekil (• v1'de)
_KUTU = "─│┌┐└┘├┤┬┴┼═║█"                       # terminal/kod çıktısı (├── └──)
_TİPOGRAFİ = "‐‑‒―‖„‚‛′″‰№⁄‿¡¿§©®™℃℉ℓµ"
_ARAP = ("ابتثجحخدذرزسشصضطظعغفقكلمنهوي"        # 28 temel harf
         "ءآأإئةى"                              # hemze/elif biçimleri, tâ-i merbûta, elif-i maksûre
         "یـ"                                   # Fars ye, tatvil
         "پچژگکڭ"                               # Osmanlı/Fars ek harfleri (sağır kef dahil)
         "ًَُِّْ"  # hareke: üstün, esre, cezm, ötre, şedde, tenvin
         "،؟؛")                                 # Arap virgül, soru, noktalı virgül
_KİRİL = "абвгдеёжзийклмнопрстуфхцчшщъыьэюя" "әғқңөүұһі"   # Rusça + Türk dilleri
_BİLİM = ("ℏħ∮∯"                                 # fizik: h-bar (ħ ayrıca Arapça transkripsiyon/IPA)
          "⇌⇀↽⇄⇋"                                # kimya: denge okları
          "∴∵∎⊢⊨⊤⊻∄"                             # mantık / ispat
          "∡∢⟂∦⌀"                                # geometri: açı, dik, çap
          "⋂⋃∖⊊⊋⊄∋∐∬∭"                           # küme / analiz
          "≃≢≺≻∛∜⌈⌉⌊⌋∣∤"                         # ilişki / işlem: tavan, taban, böler
          "ℙ𝔼℘ℑℜℵ")                              # olasılık, beklenen değer, özel harfler
_ÜST_ALT_HARF = ("ₐₑₒₓₔₕₖₗₘₙₚₛₜᵢⱼᵣᵤᵥᵦᵧᵨᵩᵪ"            # alt simge harfler (Latin + Yunan)
                 "ᵃᵇᶜᵈᵉᶠᵍʰⁱʲᵏˡᵐᵒᵖʳˢᵗᵘᵛʷˣʸᶻᵝᵞᵟᶿᵠᵡ")  # üst simge harfler (ⁿ 'sembol'de)
_MATEMATİK_SÖZCÜK = ("cos", "cot")              # sin/tan/sec/log/ln/lim/exp/det v1'de


def _büyük_karşılıklar(küçükler: str) -> list[str]:
    """Küçük harflerin tek-karakter büyük karşılıkları, ilk görülme sırasıyla, tekrarsız
    (σ/ς → Σ, μ/µ → Μ tek). Büyüğü olmayanlar (ʿ, birleşen işaret, ß→SS) atlanır."""
    sonuç: list[str] = []
    for c in küçükler:
        b = sesler.türkçe_büyült(c)
        if len(b) == 1 and b != c and b not in sonuç:
            sonuç.append(b)
    return sonuç

def _statik_bölüm(yol: Path) -> list[str]:
    """Statik (dosyadan) bölüm: dil bölümleri sözlükten HESAPLANMAZ — liste dondurulduğu gibi okunur
    (az-1, az-2: üretici şemsiye scripts/az_sozluk/vocab_bolum.py; sözlük büyüse de bölüm değişmez)."""
    return json.loads(yol.read_text(encoding="utf-8"))["tokenlar"]


_VERİ = Path(__file__).resolve().parent.parent / "veri"

# Ek bölümler (ad, tokenlar) — SIRA KALICI; yeni faz yalnız listenin SONUNA bölüm ekler.
EK_BÖLÜMLER: list[tuple[str, list[str]]] = [
    # Faz 1 — Türkçe alfabede olmayan Latin harfleri (önceden <unk> → metinden SİLİNİYORDU).
    ("harf-qwx", ["q", "w", "x", "Q", "W", "X"]),
    # Faz 2 — byte-fallback: <0x00>…<0xFF>. Vocab'da olmayan her karakter bunlara iner.
    ("bayt", BAYT_TOKENLARI),
    # Faz 3 — sık gerçek karakterler (bayttan tek tokena): harf, sembol, Arap yazısı, Kiril.
    ("harf-genis", list(_TÜRKOLOJİ + _TÜRK_DİLLERİ + _KÜRTÇE + _AVRUPA + _YUNAN + _BİRLEŞEN)),
    ("sembol", list(_MATEMATİK + _OK + _SİMGE + _KESİR + _PARA + _MADDE + _KUTU + _TİPOGRAFİ)),
    ("arap", list(_ARAP)),
    ("kiril", list(_KİRİL)),
    # Faz 3b — bilim sembolleri (alan listelerinden; korpus bilimde zayıf → eşik yok).
    ("sembol-bilim", list(_BİLİM)),
    # Faz 3b — büyük harf karşılıkları. Tek başına büyük harfi casing işaretçisi taşır (Ω →
    # <|Bb|> ω), ama KARIŞIK yazımlı kelime bütün-token kalır ve harf harf fallback'lenir:
    # "kΩ" → k + Ω → Ω vocab'da yoksa bayta düşüyordu. Latin tabanda iki büyüklük zaten var.
    ("harf-buyuk", _büyük_karşılıklar(_TÜRKOLOJİ + _TÜRK_DİLLERİ + _KÜRTÇE + _AVRUPA + _YUNAN
                                      + _TİPOGRAFİ + _KİRİL + _BİLİM)),
    # Kod K1 — kayıpsız boşluk: satır sonu, sekme, CR + ▁×2…▁×16 girinti/hizalama koşuları.
    ("kod-bosluk", list(KOD_BOŞLUKLARI) + BOŞLUK_KOŞULARI),
    # Kod K2 — Python anahtar sözcükleri + çok karakterli operatörler + üçlü tırnak. v1'de Türkçe
    # hece olarak zaten bulunan 10 anahtar sözcük (and/def/if/in/…) AYNI tokenı paylaşır.
    ("kod-python", [t for t in PY_ANAHTAR + PY_İŞLEM + PY_TIRNAK if t not in _PY_V1_ORTAK]),
    # Kod K3a — tanımlayıcı: ASCII casing işaretçileri (Başlık / HEP) + dunder '__'.
    ("kod-tanimlayici", list(ASCII_İŞARET) + ["__"]),
    # Kod K3b — kod sözlüğü (veri/kod_sozlugu.json 'yeni'): stdlib + web/veri-ML/SQL/JS-TS/
    # sistem/test alan listeleri. Yalnız kod kipinde (kod-* → Vocab._yalnız_kod).
    ("kod-sozluk", list(KOD_SÖZLÜK_YENİ)),
    # Matematik — üst/alt simge değiştirici harfler (aᵐ, Eₖ, xᵢⱼ; ⁿ 'sembol'de) + ‴ + birleşen
    # vektör oku (v⃗). Harf sınıfı DIŞI (pipeline._üst_alt_simge_mi) → önceki harfe yapışmaz.
    ("sembol-matematik2", list(_ÜST_ALT_HARF + "‴⃗")),
    # Matematik — LaTeX komutları (\frac, \Delta…), ters bölü dahil; yalnız metin kipi.
    ("latex", LATEX_TOKENLARI),
    # Matematik — v1'de olmayan işlev adları. Yalnız BÜTÜN sözcük olarak (bilinmeyen 'cos'):
    # hece yedeğinde kullanılmaz (Vocab._yalnız_bütün) → 'coskun' gibi sözcükler değişmez.
    ("matematik-sozcuk", list(_MATEMATİK_SÖZCÜK)),
    # AZ-5 — Azerbaycan Türkçesi: AZ motor tokenları − mevcut vocab (ek/tampon/istisna hepsi; kök heceleri ve
    # değişken biçimleri korpusta üretilenler). Yalnız dil="az" metin kipinde açık (dil_bölümü → _dil_izni).
    ("az-1", _statik_bölüm(_VERİ / "az" / "vocab_az1.json")),
    # AZ-7 — danışıq ekleri (-(y)AcAm), -(y)AsI ortacı, soyad ekleri (-ova/-yeva/-zadə) ve özel ad/danışıq kök
    # heceleri (AZ payının kalanı ≤ 165'ten 39). Yalnız dil="az" metin kipinde.
    ("az-2", _statik_bölüm(_VERİ / "az" / "vocab_az2.json")),
    # EN-4 — İngilizce: EN motor tokenları − mevcut vocab (ek/önek/klitik hepsi + FineWeb'de kazancı en yüksek bütün
    # gövdeler + yedek yazım heceleri; pay 5.000). Yalnız dil="en" metin kipinde açık.
    ("en-1", _statik_bölüm(_VERİ / "en" / "vocab_en1.json")),
    # FR-4 — Fransızca: FR motor tokenları − mevcut vocab (ek/önek/elizyon/istisna parçası + œ Œ ÿ Ÿ hepsi + FineWeb-2
    # train'de kazancı en yüksek bütün gövdeler + yedek yazım heceleri; pay 3.500). Yalnız dil="fr" metin kipinde açık.
    ("fr-1", _statik_bölüm(_VERİ / "fr" / "vocab_fr1.json")),
    # DE-4 — Almanca: DE motor tokenları − mevcut vocab (ek/Fugen/önek/istisna parçası + ẞ hepsi + FineWeb-2 deu
    # train/000'de kazancı en yüksek bütün gövdeler + yedek yazım heceleri; pay 3.800). Yalnız dil="de" metin kipinde açık.
    ("de-1", _statik_bölüm(_VERİ / "de" / "vocab_de1.json")),
    # V2-1 — v2 kodlaması: sözcük başı ▁ + Başlık işaretçisi + ilk token kaynaşık yüzeyleri (▁Haus, ▁gel, Gel). Beş
    # dilin eğitim örnekleminde (10M karakter/dil) ≥10 oluşum; üretici şemsiye scripts/v2/kaynasma_uret.py. Yalnız
    # sürüm="v2" metin kipinde (Vocab._v2); v1 kipi bu tokenları hiç üretmez.
    ("v2-kaynasma", _statik_bölüm(_VERİ / "v2" / "kaynasma.json")),
    # V2-2 — morfem demetleri: sözcük birimi içindeki ardışık tokenların birleşimi (lerin, ▁geliyorum, ▁Azərbaycan).
    # v2-demet yalnız harf tokenları (decode sıradan), v2-demet-duz ▁/Başlık önekli (decode harfiyen). Seçim: eğitim
    # örnekleminin gerçek bölmesindeki kazanç; üretici şemsiye scripts/v2/demet_uret.py. Yalnız sürüm="v2" metin kipinde.
    ("v2-demet", _statik_bölüm(_VERİ / "v2" / "demet.json")),
    ("v2-demet-duz", _statik_bölüm(_VERİ / "v2" / "demet_duz.json")),
    # V2-3 — gövde: v1'de yedeğe (hece/harf/bayt) düşen sık motor tokenları (vocab'da olmayan kök/gövde, bütün tutulan
    # sözcük: unexpectedly, windows, itibariyle) tek token; sıradan decode. Süzgeç: tek yazı sistemi, ≥10 belge, kumar/
    # yetişkin kalıbı dışı. Üretici şemsiye scripts/v2/govde_uret.py. Ardından ikinci tur demet (gövdelerin ▁/Başlık
    # önekli ve iç demetleri dahil; scripts/v2/demet_uret.py bütçe 19.813). Yalnız sürüm="v2" metin kipinde.
    ("v2-govde", _statik_bölüm(_VERİ / "v2" / "govde.json")),
    ("v2-demet2", _statik_bölüm(_VERİ / "v2" / "demet2.json")),
    ("v2-demet2-duz", _statik_bölüm(_VERİ / "v2" / "demet2_duz.json")),
    # VB-1 — Türkçe kök sözlüğünün (K-1a–K-2) vocab'da olmayan morfem tokenları (hakk, hiss, tıbb, kş…; eskiden yedeğe
    # düşüyordu). Yalnız Türkçe metin kipinde (Vocab._yalnız_tr): AZ/EN/FR/DE ve kod kipi çıktısı birebir.
    ("tr-1", _statik_bölüm(_VERİ / "vocab_tr1.json")),
    # VB-1 — vocab 196.608'e büyütme: üçüncü tur demet (scripts/v2/demet_uret.py bütçe 65.402; tr-1 vocab'dayken;
    # V2-6 birimi özel tokensız). Yalnız sürüm="v2" metin kipinde.
    ("v2-demet3", _statik_bölüm(_VERİ / "v2" / "demet3.json")),
    ("v2-demet3-duz", _statik_bölüm(_VERİ / "v2" / "demet3_duz.json")),
    # VB-1 — ayrılmış özel tokenlar (ileride sohbet rolü/araç; ID kaydırmadan). Metinden üretilmez, decode atar;
    # boyutu 196.608'e (1536 × 128) tamamlar (demet3 ikinci geçişi 10 adayı düşürdü; 1 yer tr-1'e: yd).
    ("ozel-rezerv", list(REZERV)),
]

# Tamamlanmış (dondurulmuş) bölümler: (ad, boy, SHA-256 özeti). Faz bitince buraya işlenir.
DONMUŞ_BÖLÜMLER: list[tuple[str, int, str]] = [
    ("v1", 4112, "fd1aa7a47946a3cf36438c61d293e86b59928662e98e5be97331724b988aa4cd"),
    ("harf-qwx", 6, "4977405745b97c2adebb1a215928b87e2e6cd1d4bb246b4259d60eae040513d1"),
    ("bayt", 256, "5c7fd0e25b2836efc016d0c39612ba381cf25d6d644baba6aa980505e5962cc0"),
    ("harf-genis", 85, "62ca742eb32a44ac002be39838729eef0cae3ea25cf27bdd2a1069a6ad4ae24c"),
    ("sembol", 171, "e39b20c04e5a72ee701475751445972ddb7494069140e86434a84c68f3bf8c13"),
    ("arap", 52, "f965cd13d8d9872862df6128392d2934612a54c35a79279c078bc03e1249367c"),
    ("kiril", 42, "2789ca16dd0ff9786dddf236b3bec4b73547c9a7de4e9ce17a4950b943156de4"),
    ("sembol-bilim", 50, "bd3ec86cba4fa61fd1dece2faa37418823ed3e9961cbe990b837c290117eb7aa"),
    ("harf-buyuk", 118, "1c163979561e895a9ebdfb23c90fd4f77736ae245336c1f90f0adbd97eb7c97c"),
    ("kod-bosluk", 18, "710a4e2868cb36798f2302116ce5533c9f9ad7d2ecadbe0dad483bfc1c1eb6b9"),
    ("kod-python", 54, "d794c29ef7654e6994c3b9da0d8847398f6ace4a6db4dc2dc05c493fac747c8d"),
    ("kod-tanimlayici", 3, "aea3f558a51675552ca961d564536d588d4532b2a631ea6a99d072d804889d96"),
    ("kod-sozluk", 1511, "109087d4bc0a6ac23e031bc67a40f37c20229ffd16927b8b83b480065fcbae9c"),
    ("sembol-matematik2", 55, "a2ff1beaa4b0e0718a7293f68845884eaf84a878018e6eab60ebf74cd1655e00"),
    ("latex", 102, "2336c23eb1a5a01f72eb449e8beed6e1a44541fe3794208ddacff465c7ad93e0"),
    ("matematik-sozcuk", 2, "923883cb54c3d93703e272598b085b6099713e2fed2d09c93c41cf2250ddac95"),
    ("az-1", 1835, "cdb901d0ac52cc598eb11983f2a8e973032db66dcdbd6020f3dc40d363aa07d9"),
    ("az-2", 39, "87a9d197aa20b2e7f585d4e6c1a54fb4eb54f13f96189aba27c060f671b54d3a"),
    ("en-1", 5000, "ff21a7d8b7530ebc407724110d5ad35830351951c512c24b1a39a14c11ba613f"),
    ("fr-1", 3500, "aed960a28afc27e1332de5d39b387b8019ea854e3e0111a36d5e2aed2d6f44b6"),
    ("de-1", 3800, "3def40fac7a1c2845ec9c67c5fcf3735c93871305ae4ed217979e6417d001d5b"),
    ("v2-kaynasma", 20448, "896202c33e1b98943467948f05c00ea9e5d42eb00f248af20b5dbdf39b6c5200"),
    ("v2-demet", 1099, "6b5937f61e479ec129450725fe10927836495521588aba1132fb782c32b36747"),
    ("v2-demet-duz", 48901, "dc6a839db635d523cabb0ff8e407126a68a8e71dfdde9220eed07c9534fb8304"),
    ("v2-govde", 10326, "67a0078e8564cdfe0e95a95d5b1fcfb70cc658e1cde1a4a23f1fbf0987dcc82a"),
    ("v2-demet2", 12169, "5577d5a601be378a8a6662696807ac3e35480bec5fc0eaf79d048a5b1919f1ee"),
    ("v2-demet2-duz", 17318, "61ed06926ffa1c26360039b7eb99322a043b442836ade24110251f9014a56b25"),
    ("tr-1", 135, "d784a6a4ef04501877a98a181c9a56eff37ddb70ccca0c15df72b7d205ca4b76"),
    ("v2-demet3", 7474, "ad846101ac60183032498be8314e9a446c0fd60bd82b8d2e98db1a059b2b6bad"),
    ("v2-demet3-duz", 57918, "744ea5ddf9c21e410f2cb747d4d253b1f056fdbe1b65b1bb24a10041de90bddb"),
    ("ozel-rezerv", 9, "c33f12e90bbdae937426323a9cf2c8d25be02e39311066c0748966ec20b3dd12"),
]


def bölüm_özeti(tokenlar) -> str:
    """Bölümün SHA-256 özeti (JSON dizisi üzerinden → token sınırı belirsizliği yok)."""
    return hashlib.sha256(json.dumps(list(tokenlar), ensure_ascii=False).encode("utf-8")).hexdigest()


def bölümleri_ekle(taban: list[str], bölümler) -> list[str]:
    """Tabanın SONUNA bölümleri sırayla ekler. Zaten var olan (ya da bölüm içinde tekrarlanan)
    token ValueError verir — sessiz yutma yok: her yeni token gerçekten yeni olmalı."""
    tokenlar, görülen = list(taban), set(taban)
    for ad, bölüm in bölümler:
        for t in bölüm:
            if t in görülen:
                raise ValueError(f"'{ad}' bölümünde zaten var olan token: {t!r}")
            görülen.add(t)
            tokenlar.append(t)
    return tokenlar


def vocab_kur(kökler=None, ekler=None, istisnalar=None) -> list[str]:
    """Deterministik vocab: v1 çekirdek (statik, veri/vocab_v1.json) + EK_BÖLÜMLER (sırayla sona eklenir).

    v1 eskiden kök sözlüğünden hesaplanıyordu (kök heceleri + ek yüzeyleri + istisna tokenları, uzunluk/Türkçe alfabe
    sıralı). K-1a (2026-10-24) Türkçe sözlüğü büyütünce yeni heceler v1'i kaydıracaktı → v1 dondurulmuş listedir. Yeni
    Türkçe kökün vocab'da olmayan heceleri harf yedeğine düşer (kayıpsız) ve veri/bekleyen_tokenlar.json'da vocab
    büyütme fazını bekler. Parametreler geriye uyumluluk için durur (kullanılmaz)."""
    return bölümleri_ekle(_statik_bölüm(_VERİ / "vocab_v1.json"), EK_BÖLÜMLER)


# Metin kipinde ASCII casing işaretçilerini (kod-tanimlayici bölümü) kullanan doğal diller (EN: Unicode casing).
_ASCII_CASING_DİLLERİ = frozenset(k for k, p in PROFİLLER.items() if p.casing == "unicode")
# Metin kipinde kod sözlüğü ve öteki dil bölümlerinin tokenlarını da kullanan diller (EN-4: İngilizce 'time', 'data'
# kod sözlüğünde, 'very', 'hard' AZ hecesi olarak zaten var; yinelenen token eklenemez → paylaşılır). Bu dillerin
# KENDİ bölümleri (en-1) yine yalnız kendi metin kipinde açıktır. FR-1: Fransızca da (de, la, ment, tion ortak dizgi). DE-1: Almanca da (und, der, ein…).
_ORTAK_KULLANAN_DİLLER = frozenset({"en", "fr", "de"})


def dil_bölümü(ad: str) -> str | None:
    """Bölüm bir doğal dile mi ait? '<dil>-…' önekli bölüm (az-1, az-2…) → dil kodu, yoksa None."""
    dil = ad.split("-", 1)[0]
    return dil if "-" in ad and dil in DOĞAL_DİLLER else None


class Vocab:
    """Token ↔ ID; ID-düzeyi encode/decode (mevcut pipeline'ı sarar)."""

    def __init__(self, id2tok: list[str], bölümler=None):
        self.id2tok = id2tok
        self.tok2id = {t: i for i, t in enumerate(id2tok)}
        self._unk = self.tok2id["<unk>"]
        self._baytlı = BAYT_TOKENLARI[0] in self.tok2id   # v1 vocab'ında bayt tokenı yok
        # Kod bölümlerinin tokenları YALNIZ kod kipinde: metindeki İngilizce 'from/class' kod
        # tokenına değil, eskisi gibi harflere iner (kod kalıbı ≠ metin kelimesi). v1'de Türkçe
        # hece olarak bulunan and/def/if/in… v1 tokenıdır, bu kümeye girmez. Satır sonu (SATIR)
        # da girmez: hiçbir metin kelimesiyle karışmaz, metin kipi onu satır yapısı için üretir.
        bölümler = EK_BÖLÜMLER if bölümler is None else bölümler
        self._yalnız_kod = frozenset(self.tok2id[t] for ad, bölüm in bölümler
                                     if ad.startswith("kod-") for t in bölüm
                                     if t in self.tok2id and t != SATIR)
        # EN-4: İngilizce metin kipinde kod sözlüğü/anahtar sözcük tokenları (time, class, data) metin sözcüğüdür →
        # açık; boşluk koşuları (kod-bosluk) kapalı kalır. Türkçe/AZ metin kipi değişmez.
        self._kod_boşluk = frozenset(self.tok2id[t] for ad, bölüm in bölümler if ad == "kod-bosluk"
                                     for t in bölüm if t in self.tok2id)
        # Dil bölümlerinin (az-1…) tokenları YALNIZ o dilin metin kipinde: Türkçe metin kipi ve kod
        # kipi bunları hiç üretemez (yedek hecede de) → Türkçe çıktı dil eklense de birebir aynı.
        # Var olan (Türkçe/ortak) tokenlar her dilde açıktır: AZ 'ev', 'lar' aynı ID'yi kullanır.
        self._dil_izni: dict[int, frozenset[str]] = {
            self.tok2id[t]: frozenset({dil}) for ad, bölüm in bölümler
            if (dil := dil_bölümü(ad)) for t in bölüm if t in self.tok2id}
        # FR-4: ortak kullanan dil (EN, FR) yalnız KENDİ ilk bölümünden ÖNCE eklenmiş dil bölümlerini paylaşır → sonradan
        # eklenen dil (fr-1) önceki dilin (EN) çıktısını değiştirmez; FR en-1/az-1 dizgilerini kullanmaya devam eder.
        sıra = {ad: i for i, (ad, _) in enumerate(bölümler)}
        ilk: dict[str, int] = {}
        for ad, _ in bölümler:
            if (dil := dil_bölümü(ad)):
                ilk.setdefault(dil, sıra[ad])
        self._dil_sırası: dict[int, int] = {
            self.tok2id[t]: sıra[ad] for ad, bölüm in bölümler
            if dil_bölümü(ad) for t in bölüm if t in self.tok2id}
        self._dil_ilk = ilk
        # Bütün-sözcük tokenları (matematik-sozcuk): hece yedeğinde kullanılmaz.
        self._yalnız_bütün = frozenset(self.tok2id[t] for t in _MATEMATİK_SÖZCÜK
                                       if t in self.tok2id)
        # v2 bölümleri (kaynaşık yüzeyler): yalnız sürüm="v2" metin kipinde, kaynaştır() üzerinden.
        self._v2 = frozenset(t for ad, bölüm in bölümler if ad.startswith("v2-")
                             for t in bölüm if t in self.tok2id)
        self._v2_id = frozenset(self.tok2id[t] for t in self._v2)
        # Harfiyen decode edilen (▁/Başlık önekli) v2 tokenları; v2-demet sıradan token gibi çözülür.
        self._düz = frozenset(t for ad, bölüm in bölümler if ad == "v2-kaynasma" or (ad.startswith("v2-")
                                                                                   and ad.endswith("-duz"))
                              for t in bölüm if t in self.tok2id)
        # Türkçe bölümleri (tr-1…): yalnız Türkçe metin kipinde (dil None) açık — AZ/EN/FR/DE ve kod kipi bu tokenları
        # (yedek hecede de) üretmez → o dillerin çıktısı birebir aynı kalır.
        self._yalnız_tr = frozenset(self.tok2id[t] for ad, bölüm in bölümler if ad.startswith("tr-")
                                    for t in bölüm if t in self.tok2id)
        # Başka bölümde (v2-govde/demet, dil bölümü, kod sözlüğü) zaten bulunan Türkçe morfem tokenları (hakk, vr, zad,
        # pid): aynı dizgi iki bölüme eklenemez → Türkçe v1 metin kipinde de açık (o bölümün kapısı Türkçede aşılır)
        self._tr_açık = frozenset(self.tok2id[t] for t in _statik_bölüm(_VERİ / "vocab_tr_acik.json")
                                  if t in self.tok2id)

    def __len__(self):
        return len(self.id2tok)

    def _id(self, t: str, kip: str, dil: str | None = None) -> int | None:
        """Tokenın ID'si; metin kipinde kod bölümü tokenı, o dilin metin kipi dışında dil bölümü
        tokenı yok sayılır (None)."""
        tid = self.tok2id.get(t)
        if tid in self._tr_açık and kip == "metin" and dil is None:
            return tid
        if tid in self._v2_id:
            return None
        if tid in self._yalnız_tr and not (kip == "metin" and dil is None):
            return None
        ortak = kip == "metin" and dil in _ORTAK_KULLANAN_DİLLER
        if tid is not None and kip != "kod" and tid in self._yalnız_kod and not (
                (t in ASCII_İŞARET and dil in _ASCII_CASING_DİLLERİ)      # Unicode casing: <|Ab|> <|AA|>
                or (ortak and tid not in self._kod_boşluk)):              # EN metin kipi: kod sözcükleri
            return None
        if tid is not None and self._dil_izni:
            izin = self._dil_izni.get(tid)
            if izin is not None and (kip != "metin" or (dil not in izin and not (
                    ortak and self._dil_sırası[tid] < self._dil_ilk.get(dil, len(self.id2tok))))):
                return None
        return tid

    def v2_izinli(self, kip: str, dil: str | None):
        """v2 sözcük birimine girebilen token: vocab'daki her harf tokenı (önekli/düz v2 tokenı hariç). v2'de dil kapısı
        YOK: dil bölümü kapısı v1 çıktısını birebir korumak içindi; v2'de Türkçe metindeki 'the' en-1 tokenını kullanır."""
        açık: dict[str, bool] = {}

        def izinli(t):
            r = açık.get(t)
            if r is None:
                r = açık[t] = harf_tokenı(t) and t in self.tok2id and t not in self._düz
            return r
        return izinli

    def _v2_yedek(self, tokenlar, izinli, dil):
        """v2: vocab'da olmayan harf tokenını yedek PARÇALARINA açar (hece; vocab'da yoksa harf; o da yoksa bayt) — parçalar
        sözcük birimine girer, kaynaştır ardışık parçaları en uzun eşleşmeyle birleştirir (yine yalnız sınır kalkar)."""
        profil = PROFİLLER[dil] if dil in DOĞAL_DİLLER else None
        çıktı: list[str] = []
        for t in tokenlar:
            if not harf_tokenı(t) or izinli(t):
                çıktı.append(t)
                continue
            for hece in hecele(t, profil):
                if izinli(hece):
                    çıktı.append(hece)
                    continue
                for ch in hece:
                    çıktı.extend([ch] if ch in self.tok2id else bayt_tokenları(ch))
        return çıktı

    def _fallback(self, kelime: str, kip: str = "metin", dil: str | None = None) -> list[int]:
        """Bilinmeyen bütün-token → hece (dilin ünlüleriyle), vocab'da yoksa harf, o da yoksa
        UTF-8 baytları (bayt bölümü olmayan eski vocab'da son çare <unk>)."""
        ids: list[int] = []
        profil = PROFİLLER[dil] if kip == "metin" and dil in DOĞAL_DİLLER else None
        for hece in hecele(kelime, profil):
            tid = self._id(hece, kip, dil)
            if tid is not None and tid not in self._yalnız_bütün:
                ids.append(tid)
                continue
            for ch in hece:
                tid = self.tok2id.get(ch)
                if tid is not None and tid in self._dil_izni:       # dil bölümü harfi (fr-1 œ) yalnız o dilde
                    tid = self._id(ch, kip, dil)
                if tid is not None:
                    ids.append(tid)
                elif self._baytlı:
                    ids.extend(self.tok2id[t] for t in bayt_tokenları(ch))
                else:
                    ids.append(self._unk)
        return ids

    def encode_ids(self, metin, kökler, ekler, istisnalar=None, kuyruk=None,
                   önbellek=None, kip: str = "metin", dil: str | None = None,
                   sürüm: str = "v1") -> list[int]:
        """Metin → ID dizisi. Bilinen token doğrudan; bilinmeyen bütün-token fallback'lenir.
        önbellek: büyük korpus için kelime-memoization (encode'a iletilir). kip: "metin"|"kod";
        dil: kod kipinde programlama dili (ör. "python"), metin kipinde doğal dil (ör. "az";
        None = Türkçe) — o zaman kökler/ekler/istisnalar o dilin verisidir. sürüm: "v1" (donmuş kodlama) |
        "v2" (metin kipinde sözcük başı kaynaşması, tokenizer/v2.py; kod kipinde v1 ile aynı)."""
        if sürüm not in SÜRÜMLER:
            raise ValueError(f"bilinmeyen sürüm: {sürüm!r} (geçerli: {', '.join(SÜRÜMLER)})")
        tokenlar = encode(metin, kökler, ekler, istisnalar, kuyruk, önbellek, kip, dil)
        if sürüm == "v2" and kip == "metin":
            izinli = self.v2_izinli(kip, dil)
            tokenlar = self._v2_yedek(tokenlar, izinli, dil)
            tokenlar = kaynaştır(tokenlar, izinli, lambda t, düz: t in self._düz if düz else izinli(t))
        ids: list[int] = []
        for t in tokenlar:
            if sürüm == "v2" and kip == "metin" and (t in self._düz or izinli(t)):
                ids.append(self.tok2id[t])
                continue
            tid = self._id(t, kip, dil)
            ids.append(tid) if tid is not None else ids.extend(self._fallback(t, kip, dil))
        return ids

    def decode_ids(self, ids, kip: str = "metin") -> str:
        """ID dizisi → metin (casing/▁/özel tokenlar pipeline.decode ile çözülür)."""
        return decode([self.id2tok[i] for i in ids], kip, self._düz)

    def kaydet(self, yol: str | Path) -> None:
        Path(yol).write_text(json.dumps({"id2tok": self.id2tok}, ensure_ascii=False),
                             encoding="utf-8")

    @classmethod
    def yükle(cls, yol: str | Path) -> "Vocab":
        ham = json.loads(Path(yol).read_text(encoding="utf-8"))
        return cls(ham["id2tok"])

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
Vocab bölümlerden oluşur: v1 (yukarıdaki 1-3, Türkçe çekirdek, 4112, DONMUŞ) + EK_BÖLÜMLER
sırayla SONA eklenir. Yeni token yalnız YENİ bir bölümle girer; var olan bölüm değişmez, araya
token girmez. DONMUŞ_BÖLÜMLER her bölümün boyu + SHA-256 özetini kilitler (test_vocab önek
kapısı): bir kök eklemesi v1'i kaydırırsa ya da bir bölüm sessizce değişirse test KIRMIZI.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from tokenizer import sesler
from tokenizer.alfabe import ALFABE, alfabetik_anahtar
from tokenizer.hece import hecele
from tokenizer.birlestir import birleştir
from tokenizer.pipeline import (encode, decode, BOŞLUK, BAŞ_BÜYÜK, HEP_BÜYÜK, ÖZEL,
                                BAYT_TOKENLARI, bayt_tokenları, KOD_BOŞLUKLARI,
                                BOŞLUK_KOŞULARI)
from tokenizer.kod import PY_ANAHTAR, PY_İŞLEM, PY_TIRNAK

# Python anahtar sözcüklerinden v1'de Türkçe hece/token olarak zaten bulunanlar (tekrar eklenmez;
# yanlış bırakılırsa bölümleri_ekle tekrar hatası verir → liste kendini denetler).
_PY_V1_ORTAK = frozenset({"and", "as", "def", "del", "for", "if", "in", "is", "not", "or"})

# Sabit önek: özel tokenlar (ID 0..) — sıra KALICI olmalı (model bağımlılığı).
ÖZEL_TOKENLAR = ["<pad>", "<unk>", "<s>", "</s>", "<|sistem|>", "<|kullanici|>",
                 "<|asistan|>", "<|bitis|>", BAŞ_BÜYÜK, HEP_BÜYÜK, BOŞLUK]

NOKTALAMA = list(".,;:!?'\"`()[]{}<>-–—/\\|@#$%&*+=~^_°²³…’‘“”«»·•")
RAKAM = list("0123456789")

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


def _büyük_karşılıklar(küçükler: str) -> list[str]:
    """Küçük harflerin tek-karakter büyük karşılıkları, ilk görülme sırasıyla, tekrarsız
    (σ/ς → Σ, μ/µ → Μ tek). Büyüğü olmayanlar (ʿ, birleşen işaret, ß→SS) atlanır."""
    sonuç: list[str] = []
    for c in küçükler:
        b = sesler.türkçe_büyült(c)
        if len(b) == 1 and b != c and b not in sonuç:
            sonuç.append(b)
    return sonuç

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


def _atomik_taban() -> list[str]:
    """Her dizinin temsil edilebilmesi için zemin: harf (iki büyüklük) + rakam + noktalama."""
    küçük = set(ALFABE) | set("âîû")
    büyük = {sesler.türkçe_büyült(c) for c in küçük}
    return sorted(küçük | büyük | set(RAKAM) | set(NOKTALAMA))


def _ek_yüzeyleri(kökler, ekler) -> set[str]:
    """Ek yüzey + tampon tokenlarını, çeşitli kökler üzerinde çekim üreterek toplar.

    Her ekin yüzeyi gövdenin son ünlüsüne/sesine bağlı → tüm son_ünlü sınıflarını +
    ünsüz/ünlü/l/r-sonu + yumuşama/düşen/ince köklerini kapsayan bir prob kümesi seçilir.
    """
    # Çeşitli prob kökleri: her son_ünlü + özel sınıflar, isim ve fiil ayrı.
    isim_prob, fiil_prob = {}, {}
    for ad, k in kökler.items():
        hedef = isim_prob if k.tür != "fiil" else fiil_prob
        anahtar = (k.son_ünlü, ad[-1] in sesler.ÜNLÜLER, ad[-1] in "lr",
                   bool(k.değişim), getattr(k, "düşen", False), getattr(k, "ince", False))
        hedef.setdefault(anahtar, ad)
    isimler, fiiller = list(isim_prob.values()), list(fiil_prob.values())

    isim_zinc = [[e] for e, x in ekler.items() if x.öbek == "isim"]
    isim_zinc += [["çoğul", "iyelik_1tekil"], ["iyelik_3tekil", "bulunma"],
                  ["iyelik_3tekil", "araç"], ["iyelik_2tekil", "bulunma", "aitlik"]]
    fiil_zinc = [[e] for e, x in ekler.items() if x.öbek == "fiil"]
    fiil_zinc += [["şimdiki_zaman", "şahıs_1tekil_t1"], ["görülen_geçmiş", "şahıs_1tekil_t2"],
                  ["gelecek_zaman", "şahıs_1çoğul_t1"], ["olumsuz", "geniş_zaman"],
                  ["edilgen", "görülen_geçmiş"], ["ettirgen", "edilgen", "görülen_geçmiş"],
                  ["ortaç_dik", "iyelik_3tekil"], ["şimdiki_zaman", "ek_fiil_idi"]]
    her_zinc = [["ek_fiil_idi"], ["ek_fiil_imiş"], ["koşaç_1tekil_t1"]]

    tokens: set[str] = set()
    for kökler_l, zincirler in ((isimler, isim_zinc), (fiiller, fiil_zinc),
                                (isimler + fiiller, her_zinc)):
        for ad in kökler_l:
            kök = kökler[ad]
            for zinc in zincirler:
                try:
                    tk, _ = birleştir(ad, kök, zinc, ekler)
                    tokens.update(tk)
                except Exception:
                    pass

    # Yumuşama/düşme TÜM köklerde kök-son heceyi değiştirir (kitap→tab, böcek→böceğ,
    # affet→fed, akıl→akl). Bu yüzden değişim/düşen köklerin ünlü-başlı çekimini üret.
    for ad, kök in kökler.items():
        if not (kök.değişim or getattr(kök, "düşen", False)):
            continue
        z = ([["şimdiki_zaman"], ["gelecek_zaman", "şahıs_1tekil_t1"]]
             if kök.tür == "fiil" else [["belirtme"], ["iyelik_3tekil"]])
        for zinc in z:
            try:
                tk, _ = birleştir(ad, kök, zinc, ekler)
                tokens.update(tk)
            except Exception:
                pass
    return tokens


def vocab_kur(kökler, ekler, istisnalar) -> list[str]:
    """Deterministik vocab: v1 çekirdek + EK_BÖLÜMLER (sırayla sona eklenir)."""
    return bölümleri_ekle(_v1_kur(kökler, ekler, istisnalar), EK_BÖLÜMLER)


def _v1_kur(kökler, ekler, istisnalar) -> list[str]:
    """v1 — Türkçe çekirdek (DONMUŞ): özel + atomik taban + hece/morfem/ek/istisna tokenları."""
    morfem: set[str] = set()
    for kök in kökler.values():                 # kök heceleri
        morfem.update(kök.tokens)
    for ist in istisnalar.values():             # istisna bütün-tokenları
        morfem.update(ist.tokens)
    morfem |= _ek_yüzeyleri(kökler, ekler)      # ek yüzeyleri + tamponlar

    atom = _atomik_taban()
    morfem -= set(ÖZEL_TOKENLAR) | set(atom)    # önce-gelenleri çıkar (tekrar yok)
    # Sıra: önce hece sayısı/uzunluk, sonra Türkçe alfabetik, son TAM kırıcı ham token
    # (â/î/û temel ünlüye eşlendiğinden 'di'/'dî' aynı anahtara düşer → kararlılık için ham).
    _harfli = set(ALFABE) | set("âîû")
    sıralı_morfem = sorted(morfem, key=lambda t: (
        len(t), alfabetik_anahtar("".join(c for c in t if c in _harfli) or "a"), t))
    return ÖZEL_TOKENLAR + atom + sıralı_morfem


class Vocab:
    """Token ↔ ID; ID-düzeyi encode/decode (mevcut pipeline'ı sarar)."""

    def __init__(self, id2tok: list[str]):
        self.id2tok = id2tok
        self.tok2id = {t: i for i, t in enumerate(id2tok)}
        self._unk = self.tok2id["<unk>"]
        self._baytlı = BAYT_TOKENLARI[0] in self.tok2id   # v1 vocab'ında bayt tokenı yok

    def __len__(self):
        return len(self.id2tok)

    def _fallback(self, kelime: str) -> list[int]:
        """Bilinmeyen bütün-token → hece, vocab'da yoksa harf, o da yoksa UTF-8 baytları
        (bayt bölümü olmayan eski vocab'da son çare <unk>)."""
        ids: list[int] = []
        for hece in hecele(kelime):
            if hece in self.tok2id:
                ids.append(self.tok2id[hece])
                continue
            for ch in hece:
                tid = self.tok2id.get(ch)
                if tid is not None:
                    ids.append(tid)
                elif self._baytlı:
                    ids.extend(self.tok2id[t] for t in bayt_tokenları(ch))
                else:
                    ids.append(self._unk)
        return ids

    def encode_ids(self, metin, kökler, ekler, istisnalar=None, kuyruk=None,
                   önbellek=None, kip: str = "metin", dil: str | None = None) -> list[int]:
        """Metin → ID dizisi. Bilinen token doğrudan; bilinmeyen bütün-token fallback'lenir.
        önbellek: büyük korpus için kelime-memoization (encode'a iletilir). kip: "metin"|"kod";
        dil: yalnız kod kipinde (ör. "python")."""
        ids: list[int] = []
        for t in encode(metin, kökler, ekler, istisnalar, kuyruk, önbellek, kip, dil):
            tid = self.tok2id.get(t)
            ids.append(tid) if tid is not None else ids.extend(self._fallback(t))
        return ids

    def decode_ids(self, ids, kip: str = "metin") -> str:
        """ID dizisi → metin (casing/▁/özel tokenlar pipeline.decode ile çözülür)."""
        return decode([self.id2tok[i] for i in ids], kip)

    def kaydet(self, yol: str | Path) -> None:
        Path(yol).write_text(json.dumps({"id2tok": self.id2tok}, ensure_ascii=False),
                             encoding="utf-8")

    @classmethod
    def yükle(cls, yol: str | Path) -> "Vocab":
        ham = json.loads(Path(yol).read_text(encoding="utf-8"))
        return cls(ham["id2tok"])

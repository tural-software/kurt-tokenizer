"""Kod kipi doğrulama (K4): python kipi kayıpsızlık + lexer sınırlarının stdlib tokenize ile
karşılaştırması.

Kullanım (kurt-tokenizer/ dizininden):
  python -X utf8 -m araclar.kod_dogrula [kök_dizin=stdlib] [--sınır-only]

1. KAYIPSIZLIK: her .py dosyası encode_ids(kip="kod", dil="python") → decode_ids birebir mi?
   Bayt tokenı ve <unk> sayılır.
2. SINIR: tokenize'ın ürettiği her NAME/NUMBER/OP/COMMENT tokenı bizim lexer'da AYNI aralıkta
   aynı sınıfta bir parça mı; STRING (ve f-string bütünü) bizim bir string'imizin başı/sonu
   ile çakışıyor mu? tokenize'ın hata verdiği dosyalar (bilerek hatalı test girdileri) sayılır,
   atlanır. Uyuşmazlıklar sınıf başına örnekle raporlanır.
"""

from __future__ import annotations

import io
import os
import sys
import tokenize
from collections import Counter, defaultdict
from pathlib import Path

from tokenizer.kokler import çalışma_sözlüğü
from tokenizer.ekler import yükle as ekleri_yükle
from tokenizer.istisna import yükle as istisna_yükle
from tokenizer.kod import python_parçala
from tokenizer.vocab import Vocab

VERİ = Path(__file__).resolve().parent.parent / "veri"
_BEKLENEN = {tokenize.NAME: {"ad", "anahtar"}, tokenize.NUMBER: {"sayı"},
             tokenize.OP: {"işlem"}, tokenize.COMMENT: {"metin"}}
# f-string (3.12+) ve t-string (3.14+) tokenize'da parçalı gelir → bütün aralık karşılaştırılır.
_FSTART = {getattr(tokenize, a) for a in ("FSTRING_START", "TSTRING_START") if hasattr(tokenize, a)}
_FEND = {getattr(tokenize, a) for a in ("FSTRING_END", "TSTRING_END") if hasattr(tokenize, a)}


def _satır_başları(kod: str) -> list[int]:
    başlar, i = [0], 0
    for satır in kod.splitlines(keepends=True):
        i += len(satır)
        başlar.append(i)
    return başlar


def sınır_karşılaştır(kod: str):
    """(uyuşmazlık listesi, karşılaştırılan token sayısı) ya da tokenize hatasında None."""
    try:
        toks = list(tokenize.generate_tokens(io.StringIO(kod).readline))
    except (tokenize.TokenError, SyntaxError, IndentationError):
        return None
    başlar = _satır_başları(kod)
    ofs = lambda sc: başlar[sc[0] - 1] + sc[1]
    bizim, i = {}, 0
    dize_başı, dize_sonu = set(), set()
    önceki = None
    for tür, s in python_parçala(kod):
        bizim[i] = (tür, s)
        if tür in ("önek", "tırnak") and önceki not in ("önek", "tırnak", "metin"):
            dize_başı.add(i)                     # string'in ilk parçası (önek ya da açılış)
        if tür == "tırnak" and önceki == "metin" or tür == "tırnak" and önceki == "tırnak":
            dize_sonu.add(i + len(s))            # kapanış tırnağının sonu
        önceki = tür if tür != "boşluk" else None
        i += len(s)
    hatalar, sayı, fyığın = [], 0, []
    for t in toks:
        if t.type in _FSTART:
            fyığın.append(ofs(t.start))
            continue
        if t.type in _FEND:
            baş, son = fyığın.pop(), ofs(t.end)
            if not fyığın:
                sayı += 1
                if baş not in dize_başı or son not in dize_sonu:
                    hatalar.append(("f-string", kod[baş:son][:60]))
            continue
        if fyığın:                               # f-string içi: bütün olarak karşılaştırıldı
            continue
        baş, son = ofs(t.start), ofs(t.end)
        if t.type == tokenize.STRING:
            sayı += 1
            if baş not in dize_başı or son not in dize_sonu:
                hatalar.append(("string", t.string[:60]))
        elif t.type in _BEKLENEN:
            sayı += 1
            b = bizim.get(baş)
            if not b or b[1] != t.string or b[0] not in _BEKLENEN[t.type]:
                hatalar.append((tokenize.tok_name[t.type], f"{t.string!r} ≠ {b}"))
    return hatalar, sayı


def main(argv):
    kök = Path(argv[0]) if argv and not argv[0].startswith("--") else Path(os.__file__).parent
    yalnız_sınır = "--sınır-only" in argv
    dosyalar = sorted(p for p in kök.glob("**/*.py") if "site-packages" not in p.parts)
    if not yalnız_sınır:
        k = çalışma_sözlüğü(VERİ / "kokler", VERİ / "zamirler.json", VERİ / "islev_kokleri.json")
        e, i, v = ekleri_yükle(VERİ / "ekler.json"), istisna_yükle(VERİ / "istisnalar.json"), \
            Vocab.yükle(VERİ / "vocab.json")
        bayt = {v.tok2id[t] for t in v.id2tok if t.startswith("<0x")}
        önbellek: dict = {}
    kayıplı, kar, tok, bayt_say, unk = [], 0, 0, 0, 0
    sınır_hata, sınır_say, tokenize_ret = defaultdict(list), 0, 0
    for n, yol in enumerate(dosyalar, 1):
        kod = yol.read_text(encoding="utf-8", errors="surrogateescape")
        if not yalnız_sınır:
            ids = v.encode_ids(kod, k, e, i, önbellek=önbellek, kip="kod", dil="python")
            if v.decode_ids(ids, kip="kod") != kod:
                kayıplı.append(str(yol))
            kar += len(kod)
            tok += len(ids)
            bayt_say += sum(1 for x in ids if x in bayt)
            unk += ids.count(v.tok2id["<unk>"])
        r = sınır_karşılaştır(kod)
        if r is None:
            tokenize_ret += 1
        else:
            for sınıf, örnek in r[0]:
                sınır_hata[sınıf].append((yol.name, örnek))
            sınır_say += r[1]
        if n % 200 == 0:
            print(f"  … {n}/{len(dosyalar)}", file=sys.stderr)
    print(f"dosya {len(dosyalar):,}")
    if not yalnız_sınır:
        print(f"KAYIPSIZLIK  kayıplı dosya {len(kayıplı)}  |  {kar:,} karakter → {tok:,} token "
              f"({tok / kar:.3f}/karakter), bayt tokenı {bayt_say:,}, <unk> {unk}")
        for y in kayıplı[:10]:
            print("   kayıplı:", y)
    toplam_h = sum(len(x) for x in sınır_hata.values())
    print(f"SINIR        tokenize token {sınır_say:,}, uyuşmazlık {toplam_h:,} "
          f"(tokenize'ın reddettiği dosya {tokenize_ret})")
    for sınıf, l in sorted(sınır_hata.items(), key=lambda x: -len(x[1])):
        print(f"   {sınıf:8} {len(l):>6}  örn. {l[:4]}")
    return 0 if not kayıplı and not toplam_h else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

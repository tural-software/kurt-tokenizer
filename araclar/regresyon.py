"""Vocab regresyon kapısı: bir tokenizer/vocab değişikliğinin ETKİSİNİ parça düzeyinde ölçer.

encode() metni boşlukla parçalara ayırır ve her parçayı bağımsız kodlar (parçalar ▁ ile
birleşir) → belge çıktısı = parça çıktılarının birleşimi. Bu yüzden parça düzeyinde
karşılaştırma belge düzeyindekine eşdeğerdir ve daha keskindir (HANGİ kelime değişti).

Kullanım (kurt-tokenizer/ dizininden):
  python -X utf8 -m araclar.regresyon kaydet      <örnek.txt> <referans.json>
  python -X utf8 -m araclar.regresyon karsilastir <örnek.txt> <referans.json> [--hedef KARAKTERLER]
                                                   [--hedef-kayiplilar] [--hedef-baytlilar]
                                                   [--hedef-yeni-tokenlar]

örnek.txt    satır başına bir belge (normalleştirilmiş metin)
kaydet       her benzersiz parçanın ID dizisini + kayıplı parça/karakter kümesini yazar
karsilastir  güncel tokenizer'la aynı ölçümü yapar (--hedef-kayiplilar: referanstaki TÜM kayıplı
             karakterler hedefe eklenir — kayıp gideren fazlar için; --hedef-baytlilar: referansta
             BAYTLA kodlanan tüm karakterler — bayttan tek tokena / harf sınıfına alan fazlar için;
             --hedef-yeni-tokenlar: yeni kodlaması referanstan sonra eklenen çok karakterli bir
             tokenı içeren parça da geçerli — çok karakterli token ekleyen fazlar için, ör. kod-python).
             KAPILAR (hepsi geçmeli):
  1. değişen her parça --hedef karakterlerinden en az birini içerir
  2. yeni kayıplı parça yok        (kayıplı_sonra ⊆ kayıplı_önce)
  3. yeni kayıplı karakter yok ve --hedef karakterlerinin hiçbiri artık kayıplı değil
  Çıkış kodu: 0 = YEŞİL, 1 = KIRMIZI.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from tokenizer.kokler import çalışma_sözlüğü
from tokenizer.ekler import yükle as ekleri_yükle
from tokenizer.istisna import yükle as istisna_yükle
from tokenizer.pipeline import BAYT_TOKENLARI
from tokenizer.vocab import Vocab

KÖK = Path(__file__).resolve().parent.parent
VERİ = KÖK / "veri"


def _ölç(örnek: Path) -> dict:
    """Örneklemi güncel tokenizer'la kodlar: parça→ID, kayıplı parça/karakter, <unk>, token."""
    k = çalışma_sözlüğü(VERİ / "kokler", VERİ / "zamirler.json", VERİ / "islev_kokleri.json")
    e = ekleri_yükle(VERİ / "ekler.json")
    i = istisna_yükle(VERİ / "istisnalar.json")
    v = Vocab.yükle(VERİ / "vocab.json")
    unk = v.tok2id["<unk>"]
    bayt = {v.tok2id[t] for t in BAYT_TOKENLARI if t in v.tok2id}

    sıklık: Counter[str] = Counter()
    with örnek.open(encoding="utf-8") as f:
        for satır in f:
            sıklık.update(satır.split())

    parçalar, kayıplı, unk_say, token_say, bayt_say = {}, [], 0, 0, 0
    for p in sorted(sıklık):
        ids = v.encode_ids(p, k, e, i)
        parçalar[p] = ids
        if v.decode_ids(ids) != p:
            kayıplı.append(p)
        unk_say += ids.count(unk) * sıklık[p]
        token_say += len(ids) * sıklık[p]
        bayt_say += sum(x in bayt for x in ids) * sıklık[p]

    karakterler = sorted({c for p in sıklık for c in p})
    kayıplı_kar, baytlı_kar = [], []
    for c in karakterler:
        ids = v.encode_ids(c, k, e, i)
        if v.decode_ids(ids) != c:
            kayıplı_kar.append(c)
        if bayt.intersection(ids):
            baytlı_kar.append(c)
    return {"vocab_boy": len(v), "parçalar": parçalar, "kayıplı_parçalar": kayıplı,
            "kayıplı_karakterler": kayıplı_kar, "baytlı_karakterler": baytlı_kar,
            "unk": unk_say, "token": token_say, "bayt": bayt_say,
            "oluşum": sum(sıklık.values())}


def kaydet(örnek: Path, referans: Path) -> None:
    ölçüm = _ölç(örnek)
    referans.write_text(json.dumps(ölçüm, ensure_ascii=False), encoding="utf-8")
    print(f"{referans}  ←  {len(ölçüm['parçalar']):,} benzersiz parça, vocab {ölçüm['vocab_boy']}, "
          f"<unk> {ölçüm['unk']:,}, kayıplı karakter {len(ölçüm['kayıplı_karakterler'])}")


def karşılaştır(örnek: Path, referans: Path, hedef: str, kayıplılar: bool = False,
                baytlılar: bool = False, yeni_tokenlar: bool = False) -> bool:
    """yeni_tokenlar: referanstan sonra eklenen çok karakterli tokenlar da hedeftir — değişen parça,
    yeni kodlaması bu tokenlardan birini içeriyorsa geçerli (ör. kod-python 'from' metindeki
    İngilizce 'from'u harf-harf yerine tek tokenla yakalar)."""
    önce = json.loads(referans.read_text(encoding="utf-8"))
    sonra = _ölç(örnek)
    yeni_idler: set[int] = set()
    if yeni_tokenlar:
        v = Vocab.yükle(VERİ / "vocab.json")
        yeni_idler = {x for x in range(önce["vocab_boy"], len(v)) if len(v.id2tok[x]) > 1}
    hedef_k = set(hedef) | (set(önce["kayıplı_karakterler"]) if kayıplılar else set())
    if baytlılar:
        if "baytlı_karakterler" not in önce:
            print("KIRMIZI: referansta baytlı_karakterler yok (eski referans → yeniden kaydet)")
            return False
        hedef_k |= set(önce["baytlı_karakterler"])
    if set(önce["parçalar"]) != set(sonra["parçalar"]):
        print("KIRMIZI: örneklem referansla aynı değil (farklı örnek.txt?)")
        return False

    değişen = [p for p, ids in sonra["parçalar"].items() if önce["parçalar"][p] != ids]
    hedef_dışı = [p for p in değişen
                  if not hedef_k & set(p) and not yeni_idler & set(sonra["parçalar"][p])]
    yeni_kayıplı = sorted(set(sonra["kayıplı_parçalar"]) - set(önce["kayıplı_parçalar"]))
    kk_önce, kk_sonra = set(önce["kayıplı_karakterler"]), set(sonra["kayıplı_karakterler"])
    yeni_kk = sorted(kk_sonra - kk_önce)
    hedef_hâlâ = sorted(hedef_k & kk_sonra)

    print(f"vocab            {önce['vocab_boy']} → {sonra['vocab_boy']}")
    print(f"değişen parça    {len(değişen):,} / {len(sonra['parçalar']):,} benzersiz")
    print(f"kayıplı parça    {len(önce['kayıplı_parçalar']):,} → {len(sonra['kayıplı_parçalar']):,}")
    print(f"kayıplı karakter {len(kk_önce)} → {len(kk_sonra)}  "
          f"(düzelen: {''.join(sorted(kk_önce - kk_sonra)) or '-'})")
    print(f"<unk> oluşumu    {önce['unk']:,} → {sonra['unk']:,}  "
          f"(örneklem {sonra['oluşum']:,} parça)")
    print(f"toplam token     {önce['token']:,} → {sonra['token']:,}")
    if "bayt" in önce:
        print(f"bayt tokenı      {önce['bayt']:,} → {sonra['bayt']:,}  "
              f"(baytlı karakter {len(önce['baytlı_karakterler'])} → {len(sonra['baytlı_karakterler'])})")

    kapılar = [
        ("1 değişen her parça hedef karakter içerir", hedef_dışı),
        ("2 yeni kayıplı parça yok", yeni_kayıplı),
        ("3a yeni kayıplı karakter yok", yeni_kk),
        ("3b hedef karakterlerin hiçbiri kayıplı değil", hedef_hâlâ),
    ]
    yeşil = True
    for ad, ihlal in kapılar:
        print(f"  [{'OK' if not ihlal else 'KIRMIZI'}] {ad}"
              + (f"  → {len(ihlal)} ihlal, örn. {ihlal[:10]}" if ihlal else ""))
        yeşil &= not ihlal
    print("SONUÇ:", "YEŞİL" if yeşil else "KIRMIZI")
    return yeşil


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    alt = ap.add_subparsers(dest="komut", required=True)
    a = alt.add_parser("kaydet")
    a.add_argument("örnek", type=Path)
    a.add_argument("referans", type=Path)
    b = alt.add_parser("karsilastir")
    b.add_argument("örnek", type=Path)
    b.add_argument("referans", type=Path)
    b.add_argument("--hedef", default="", help="bu fazda değişmesine izin verilen karakterler")
    b.add_argument("--hedef-kayiplilar", action="store_true",
                   help="referanstaki tüm kayıplı karakterleri hedefe ekle")
    b.add_argument("--hedef-baytlilar", action="store_true",
                   help="referansta baytla kodlanan tüm karakterleri hedefe ekle")
    b.add_argument("--hedef-yeni-tokenlar", action="store_true",
                   help="değişen parça referanstan sonra eklenen çok karakterli bir tokenı içerebilir")
    ar = ap.parse_args(argv)
    if ar.komut == "kaydet":
        kaydet(ar.örnek, ar.referans)
        return 0
    return 0 if karşılaştır(ar.örnek, ar.referans, ar.hedef, ar.hedef_kayiplilar,
                            ar.hedef_baytlilar, ar.hedef_yeni_tokenlar) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

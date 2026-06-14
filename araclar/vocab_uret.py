"""Token vocabulary üretici: motorun token kümesini deterministik kurup veri/vocab.json'a yazar.

Kullanım:
  python -X utf8 -m araclar.vocab_uret
"""

from __future__ import annotations

from pathlib import Path

from tokenizer.kokler import çalışma_sözlüğü
from tokenizer.ekler import yükle as ekleri_yükle
from tokenizer.istisna import yükle as istisna_yükle
from tokenizer.vocab import vocab_kur, Vocab

KÖK = Path(__file__).resolve().parent.parent
KÖK_DİZİN = KÖK / "veri" / "kokler"
EK = KÖK / "veri" / "ekler.json"
İST = KÖK / "veri" / "istisnalar.json"
ZAMİR = KÖK / "veri" / "zamirler.json"
İŞLEV = KÖK / "veri" / "islev_kokleri.json"
ÇIKTI = KÖK / "veri" / "vocab.json"


def üret() -> Vocab:
    k = çalışma_sözlüğü(KÖK_DİZİN, ZAMİR, İŞLEV)
    e = ekleri_yükle(EK)
    i = istisna_yükle(İST)
    v = Vocab(vocab_kur(k, e, i))
    v.kaydet(ÇIKTI)
    return v


if __name__ == "__main__":
    v = üret()
    print(f"veri/vocab.json  ←  {len(v)} token")

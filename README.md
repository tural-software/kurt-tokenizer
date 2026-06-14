# Kurt Tokenizer

**Türkçe için sıfırdan, deterministik, kural ve bilgi tabanlı bir tokenizer.**

Kurt Tokenizer; Türkçe'yi birinci sınıf dil olarak ele alan **Kurt** dil modeli
projesinin temel taşıdır. İstatistiksel (BPE/WordPiece gibi) değil; Türkçe'nin
morfolojisini elle modellenmiş kök sözlüğü, ek listesi ve birleştirme kurallarıyla
çözen **deterministik** bir sistemdir.

> Bu bileşen, "vatana millete hayırlı uğurlu olsun" niyetiyle **MIT lisansıyla
> herkese açık** bırakılmıştır.

## Felsefe

```
1. Yanlış bölme   →  asla, sıfır tolerans
2. Büyük token    →  kabul edilebilir
3. Bilinmeyen     →  bütünü koru, tahmin etme
4. Dış araç yok   →  Zemberek vb. hiçbir kara kutu girmez
5. Deterministik  →  istatistiksel değil, kural + bilgi tabanlı
```

Sistem iki durumu bilir: **biliyorum** veya **bilmiyorum**. Üçüncüsü yoktur.
Bilinmeyen kelime kayıpsız biçimde hece→harf'e iner; "bütün tut" felsefesi korunur.

## Öne çıkanlar

- **Saf Python, sıfır bağımlılık** (yalnız standart kütüphane).
- **~44.500 kök** (TDK tabanlı), 74 ek, **4.112 token'lık donmuş vocab**.
- Türkçe morfofonolojisi: ünlü uyumu, ünsüz yumuşaması (t→d, k→ğ, p→b, ç→c),
  ünlü düşmesi, kaynaştırma/tampon sesler — hepsi kural tabanlı.
- **Kayıpsız round-trip** (büyük harf, kesme eki, sayı dahil): `decode(encode(x)) == x`.
- Harf büyüklüğü casing işaretçileriyle taşınır (Türkçe-duyarlı: İ↔i, I↔ı).

## Kurulum

Bağımlılık yoktur; depoyu klonlamak yeterli (Python 3.11+):

```bash
git clone https://github.com/tural-software/kurt-tokenizer.git
cd kurt-tokenizer
```

## Kullanım

```python
from tokenizer.kokler import çalışma_sözlüğü
from tokenizer.ekler import yükle as ekleri_yükle
from tokenizer.istisna import yükle as istisna_yükle
from tokenizer.vocab import Vocab

kökler = çalışma_sözlüğü("veri/kokler", "veri/zamirler.json", "veri/islev_kokleri.json")
ekler = ekleri_yükle("veri/ekler.json")
istisnalar = istisna_yükle("veri/istisnalar.json")
vocab = Vocab.yükle("veri/vocab.json")

ids = vocab.encode_ids("Türkçe'yi gerçekten anlayan bir model.", kökler, ekler, istisnalar)
print(ids)
print(vocab.decode_ids(ids))   # kayıpsız geri döner
```

## Yapı

```
tokenizer/      çekirdek motor (sesler, alfabe, hece, kökler, ekler, birleştir,
                çözümle, trie, vocab, pipeline, istisna, onay, şema)
veri/           kök sözlüğü (harf başına), ek/istisna/zamir/işlev-kökü listeleri,
                donmuş vocab.json, doğrulama korpusu
araclar/        kaynak → JSON üretici (uret), vocab üretici (vocab_uret),
                korpus doğrulayıcı (dogrula_korpus)
testler/        stdlib unittest (155 test) — round-trip ve kapı testleri dahil
```

## Veriyi yeniden üretme

Kök sözlüğü `araclar/kaynak/<harf>.txt` kaynaklarından deterministik üretilir:

```bash
python -X utf8 -m araclar.uret --hepsi          # tüm kökleri üret
python -X utf8 -m araclar.vocab_uret            # vocab.json'u üret
```

## Testler

```bash
python -X utf8 -m unittest discover -s testler -t . -v
```

## Lisans

[MIT](LICENSE) © 2026 Furkan Tural

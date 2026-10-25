# Kurt Tokenizer

**Türkçe için sıfırdan, deterministik, kural ve bilgi tabanlı bir tokenizer.**

Kurt Tokenizer; Türkçe'yi birinci sınıf dil olarak ele alan **Kurt** dil modeli
projesinin temel taşıdır. İstatistiksel (BPE/WordPiece gibi) değil; Türkçe'nin
morfolojisini elle modellenmiş kök sözlüğü, ek listesi ve birleştirme kurallarıyla
çözen **deterministik** bir sistemdir. Aynı motor Azerbaycan Türkçesini de kendi
kök sözlüğü ve ek kurallarıyla çözer; İngilizce, Fransızca ve Almanca için aynı ilkeyle (kök sözlüğü + ek kuralı +
üret-doğrula) yazılmış kendi çözümleyicileri vardır.

> Bu bileşen, "vatana millete hayırlı uğurlu olsun" niyetiyle **MIT lisansıyla
> herkese açık** bırakılmıştır.

## Felsefe

```text
1. Yanlış bölme   →  asla, sıfır tolerans
2. Büyük token    →  kabul edilebilir
3. Bilinmeyen     →  bütünü koru, tahmin etme
4. Dış araç yok   →  Zemberek vb. hiçbir kara kutu girmez
5. Deterministik  →  istatistiksel değil, kural + bilgi tabanlı
```

Sistem iki durumu bilir: **biliyorum** veya **bilmiyorum**. Üçüncüsü yoktur.
Bilinmeyen kelime kayıpsız biçimde hece → harf → bayt'a iner; `<unk>` hiç üretilmez.

## Öne çıkanlar

- **Saf Python, sıfır bağımlılık** (yalnız standart kütüphane).
- **Türkçe:** ~48.500 kök (TDK Güncel Türkçe Sözlük 12. baskı tabanlı; yalnız başlık, tür ve çekim işareti), 79 ek; ünlü uyumu, ünsüz yumuşaması (t→d, k→ğ, p→b, ç→c),
  ünlü düşmesi, ikizleşme (`hak → hakk+ı`), kaynaştırma/tampon sesler — hepsi kural tabanlı. Norm dışı web yazımı
  (`kontrolu`, `omuzu`) de çözülür; normatif okuma varsa o seçilir. ~1.040 özel ad (kapalı liste: `İstanbul'da`,
  `Konya`); ad okuması yalnız sıradan okuma yoksa seçilir (`Deniz` = deniz).
- **Azerbaycan Türkçesi** (`dil="az"`): 65.740 kök (400 özel ad dahil), 96 ek; kendi ses kuralları (ə, q~ğ / k~y
  yumuşaması, -(y)Ar geniş zaman, -mAlI, çift ünsüz tekleşmesi). Özel adlar Başlık biçiminde ad olarak okunur
  (`Gəncə`), küçük harfte sıradan sözcük olarak (`gəncə` = gənc+ə); soyadlar ad + ek (`Əliyev`, `Məmmədova`).
  Konuşma yazımı da çözülür (`burda`, `edəcəm`, `bilərsiz`, `şəkili`); normatif okuma varsa o seçilir.
  Türkçe metnin çıktısı AZ desteğinden etkilenmez.
- **İngilizce** (`dil="en"`): yazım kurallı kendi çözümleyicisi (`tokenizer/en.py`) — çekim ve yapım
  ekleri (`running = run+n+ing`, `carried = carri+ed`, `knives = kniv+es`), önek (`un+happy`), klitik (`do+n't`), düzensiz
  biçimler bütün; büyük harf Unicode kuralıyla (`I` → `i`, `ı` değil). ~64.900 kök (Open English WordNet + elle güncel
  sözcükler), ~4.400'ü özel ad (`London`, `Kennedys = kennedy+s`; küçük harfte sıradan okuma yeğlenir). Tek harf,
  kısaltma, web parçası (`www`, `5th = 5+th`) ve konuşma kalıbı (`gonna`) bütün token. Yazım bayrakları ve eşsesli kök
  kararları korpus kanıtıyla. 5.000 tokenlık `en-1` bölümü (ekler, sık gövdeler bütün, yedek yazım heceleri):
  İngilizce web metninde 0,47 token/karakter (Türkçe kipte 0,74).
- **Fransızca** (`dil="fr"`): çekim üreteçli kendi çözümleyicisi (`tokenizer/fr.py`) — her kökün biçimleri kendi
  kurallarımızla üretilir (1. grup ç/ge/è/ikizleşme, 2. grup -iss-, 3. grup 60 çekim sınıfı, dişil/çoğul/zarf);
  gövde değişimi gövde tokenında, ek tek token (`commenç+ons`, `parl+ées`, `viendr+ai`), elizyon solda ayrı
  (`l'+homme`, `qu’+il`), düzensiz biçim bütün (`est`, `sont`). ~26.000 kök (Wikidata Lexemes CC0 + elle), ~3.300
  özel ad, sıra sayısı/Roma rakamı (`deux+ième`, `xix+e`). 3.500 tokenlık `fr-1` bölümü (ekler, elizyonlar, œ Œ ÿ Ÿ,
  sık gövdeler bütün, yedek heceler): Fransızca web metninde 0,45 token/karakter (Türkçe kipte 0,70).
- **Almanca** (`dil="de"`): çekim üreteçli ve bileşik kurallı kendi çözümleyicisi (`tokenizer/de.py`) — umlaut ve
  ablaut gövde tokenında, ekler sırayla ayrı (`häus+er+n`, `schön+er+e`, `ge+mach+t`, `gab+en`); ayrılmayan önekli
  fiil tek kök (`verstand+en`), ayrılabilir önek ayrı (`an+ge+fang+en`, `aus+ge+statt+et`). Bileşik sözcük parça +
  Fugen + parça (`arbeit+s+platz`, `benutzer+ober+fläche`); birden çok bölme mümkünse bütün tutulur. Adlar büyük
  yazıldığı için yazım biçimi okumayı seçer (`habe = hab+e`, `Habe`). İsviçre ve eski yazım (`gross+e`, `muß+te`).
  ~123.600 kök (Wikidata Lexemes CC0 + elle), ~2.900 özel ad. 3.800 tokenlık `de-1` bölümü (ekler, Fugen, ẞ, sık
  gövdeler, yedek heceler): Almanca web metninde 0,47 token/karakter (Türkçe kipte 0,75).
- **Kod kipi** (`kip="kod"`, `dil="python"`): boşluk/satır birebir korunur; kendi Python lexer'ı,
  tanımlayıcı bölme ve kod sözlüğü.
- **v2 kodlaması** (`sürüm="v2"`, büyük modeller için): sözcük başındaki boşluk ve Başlık harfi ilk tokenla
  kaynaşır (`▁ <|Bb|> haus` → `▁Haus`), sık morfem dizileri tek token olur (`▁annelerin`, `ların`, `▁gedir`), v1'de
  yedeğe düşen sık gövdeler tek tokendır. Yalnız var olan sınırlar kalkar, yeni sınır oluşmaz; decode metni v1 ile
  birebir aynı; vocab'da olmayan sözcüğün hece/harf yedeği de aynı kuralla birleşir; boşluk noktalama/rakamla da
  kaynaşır (`▁(`, `▁1`, `▁l’`). Token/karakter (~1M karakter örneklem): TR 0,62 → 0,25, AZ 0,59 → 0,24, EN 0,46 → 0,24,
  FR 0,46 → 0,25, DE 0,47 → 0,23.
  Varsayılan `sürüm="v1"` donmuş kodlamadır.
  Web metni (FineWeb-2 / FineWeb test bölümleri, ~190 bin belge, 611M karakter; round-trip hepsinde kayıpsız; vocab
  196.608), token/karakter:

  | Dil | Kurt v1 | **Kurt v2** | GPT-4o (o200k) | GPT-4 (cl100k) | Qwen2.5 | Mistral Nemo |
  |---|---:|---:|---:|---:|---:|---:|
  | Türkçe | 0,571 | **0,209** | 0,291 | 0,389 | 0,338 | 0,326 |
  | Azerbaycan T. | 0,567 | **0,200** | 0,318 | 0,491 | 0,471 | 0,356 |
  | İngilizce | 0,468 | 0,244 | 0,216 | 0,218 | 0,223 | 0,227 |
  | Fransızca | 0,456 | 0,242 | 0,234 | 0,273 | 0,274 | 0,244 |
  | Almanca | 0,469 | **0,229** | 0,234 | 0,282 | 0,284 | 0,254 |
- **196.608 (1536 × 128) token'lık vocab, sona-ekleme sözleşmesiyle:** ilk 4.112 ID (v1) donmuş; her yeni bölüm (bayt,
  harf, sembol, kod, `az-1`, `az-2`, `en-1`, `fr-1`, `de-1`, `v2-*`, `tr-1`, 9 ayrılmış özel token) sona eklenir ve özetiyle kilitlenir → var olan hiçbir ID kaymaz. Bir
  dilin bölümü yalnız o dilin metin kipinde kullanılır; İngilizce metin kipi kod sözlüğündeki (`time`, `data`) ve AZ
  bölümündeki aynı yazımlı tokenları da paylaşır (aynı dizgi iki kez eklenemez).
- **Kayıpsız round-trip** (büyük harf, kesme eki, sayı dahil): metin kipinde
  `decode(encode(x)) == metin_kanonik(x)` — satır içi boşluk tek boşluğa iner, **satır sonları ve
  paragraflar (boş satır) korunur**; kod kipinde boşluk dahil birebir `x`.
- Harf büyüklüğü casing işaretçileriyle taşınır (dile duyarlı: İ↔i, I↔ı, Ə↔ə).

## Kurulum

Bağımlılık yoktur; depoyu klonlamak yeterli (Python 3.11+):

```bash
git clone https://github.com/tural-software/kurt-tokenizer.git
cd kurt-tokenizer
```

## Kullanım

```python
from tokenizer import diller
from tokenizer.vocab import Vocab

vocab = Vocab.yükle("veri/vocab.json")

tr = diller.yükle()              # Türkçe
ids = vocab.encode_ids("Türkçe'yi gerçekten anlayan bir model.", tr.kökler, tr.ekler, tr.istisnalar)
print(vocab.decode_ids(ids))     # kayıpsız geri döner

az = diller.yükle("az")          # Azerbaycan Türkçesi
ids = vocab.encode_ids("Uşaqlar səhər tezdən məktəbə gedirlər.",
                       az.kökler, az.ekler, az.istisnalar, dil="az")
print(vocab.decode_ids(ids))

ids = vocab.encode_ids("Türkçe'yi gerçekten anlayan bir model.", tr.kökler, tr.ekler, tr.istisnalar,
                       sürüm="v2")      # v2 kodlaması: daha az token, aynı metin
```

## Yapı

```text
tokenizer/      çekirdek motor: sesler, alfabe, hece, kökler, ekler, birleştir (üretim),
                çözümle (ek soyma + üretimle doğrulama), trie, pipeline (encode/decode),
                vocab, istisna, onay (bilinmeyen kuyruğu), kod (Python lexer),
                dil (dil profilleri), diller (dil verisi yükleyici), v2 (v2 kaynaşma ve demetleme)
veri/           Türkçe kök sözlüğü (harf başına), ek/istisna/zamir/işlev-kökü listeleri,
                vocab.json, kod sözlüğü, doğrulama korpusu
veri/az/        Azerbaycan Türkçesi: kök sözlüğü, ekler, istisnalar, vocab bölümü (az-1),
                altın liste ve doğrulama metni
veri/en/        İngilizce: kök sözlüğü (kokler.txt), ekler, istisnalar (düzensiz/kısaltma), altın liste
veri/fr/        Fransızca: kök sözlüğü (kokler.txt), çekim sınıfları (cekim.json), ekler, istisnalar,
                vocab bölümü (fr-1), altın liste ve doğrulama metni
veri/de/        Almanca: kök sözlüğü (kokler.txt), çekim sınıfları (cekim.json), ekler, istisnalar,
                vocab bölümü (de-1), altın liste ve doğrulama metni
veri/v2/        v2 bölümleri (kaynasma, demet, demet_duz, govde, demet2, demet2_duz)
araclar/        kaynak → JSON üretici (uret), vocab üretici (vocab_uret), korpus doğrulayıcı
                (dogrula_korpus), regresyon karşılaştırıcı (regresyon), kod doğrulayıcı (kod_dogrula)
testler/        stdlib unittest (334 test) — round-trip, sahte bölme, regresyon ve dil kapısı dahil
```

## Veri kaynakları (Azerbaycan Türkçesi)

- **Kök listesi:** AMEA *Azərbaycan dilinin orfoqrafiya lüğəti* (7. nəşr, 2021) — yalnız madde başı
  sözcükler ve türü (dil olgusu) alındı; tanım ve açıklama alınmadı. Ek bilgiyi (yumuşama, ünlü düşmesi,
  eşsesli seçimi) biz yazdık.
- **Yazım kuralları:** *Orfoqrafiya normaları* (NK 2019 №174) ve *Orfoepiya normaları* (NK 2021 №175) —
  resmî belgeler.
- **Korpus kanıtı:** FineWeb-2 `azj_Latn` (ODC-By). Belirsiz etiket kararları (yumuşama, çift ünsüz,
  eşsesli kök önceliği) bu korpustaki gerçek kullanımla bir kez verilip veri dosyalarına işlendi;
  çalışma anında frekans kullanılmaz. Korpus metni depoda yoktur.

## Veri kaynakları (İngilizce)

- **Kök listesi:** [Open English WordNet](https://github.com/globalwordnet/english-wordnet) 2025 sürümü
  (CC BY 4.0), Princeton WordNet'ten türetilmiştir (WordNet License, © Princeton University). Yalnız başlık
  sözcük, tür ve düzensiz biçimler alındı; tanım ve örnek alınmadı. Büyük harfli lemmalar özel ad kökü olur.
  Kapalı sınıf sözcükleri, güncel sözcükler, kısaltma listeleri ve düzeltmeler bizim.
- **Korpus kanıtı:** FineWeb `sample-10BT` (ODC-By). Yazım bayrakları (çift ünsüz, -es, -ves), eşsesli kök
  kararları ve elle denetlenen özel ad/sözcük adayları bu korpustaki gerçek kullanımla bir kez verilip veri dosyasına
  işlendi; çalışma anında frekans kullanılmaz. Korpus metni depoda yoktur.

## Veri kaynakları (Fransızca)

- **Kök listesi:** [Wikidata Lexemes](https://www.wikidata.org/wiki/Wikidata:Lexicographical_data) (CC0) — Fransızca
  lemma, tür ve biçimler (biçimler yalnız bayrak kanıtı: çoğul -x/-aux, dişil, -iss-). Çekim kuralları, çekim
  sınıfları, istisnalar, özel ad listesi ve eksik sözcükler bizim (elle). Copyleft ya da kısıtlı şartlı sözlük
  kullanılmadı.
- **Korpus kanıtı:** FineWeb-2 `fra_Latn` (ODC-By). Eşsesli kök kararları, elle denetlenen sözcük/özel ad adayları ve
  vocab bölümü seçimi bu korpustaki gerçek kullanımla bir kez verilip veri dosyasına işlendi; çalışma anında frekans
  kullanılmaz. Korpus metni depoda yoktur.

## Veri kaynakları (Almanca)

- **Kök listesi:** [Wikidata Lexemes](https://www.wikidata.org/wiki/Wikidata:Lexicographical_data) (CC0) — Almanca
  lemma, tür, biçimler (yalnız bayrak kanıtı: çoğul, tamlayan, ortaç) ve bileşik parça bildirimleri (doğrulama).
  Çekim kuralları, güçlü fiil sınıfları, bileşik kuralı, istisnalar, özel ad listesi ve eksik sözcükler bizim (elle).
  Copyleft ya da kısıtlı şartlı sözlük kullanılmadı.
- **Korpus kanıtı:** FineWeb-2 `deu_Latn` (ODC-By). Fiil sınıfı, iki yönlü önek, tamlayan biçimi, seyrek/bileşen olmayan
  kök kararları, elle denetlenen sözcük/özel ad adayları ve vocab bölümü seçimi bu korpustaki gerçek kullanımla bir kez
  verilip veri dosyasına işlendi; çalışma anında frekans kullanılmaz. Korpus metni depoda yoktur.

## Veriyi yeniden üretme

Kök sözlüğü `araclar/kaynak/` kaynaklarından deterministik üretilir:

```bash
python -X utf8 -m araclar.uret --hepsi             # Türkçe kökleri üret
python -X utf8 -m araclar.uret --dil az --hepsi    # AZ kökleri üret
python -X utf8 -m araclar.vocab_uret               # vocab.json'u üret
```

## Testler

```bash
python -X utf8 -m unittest discover -s testler -t . -v
```

## Lisans

[MIT](LICENSE) © 2026 Furkan Tural

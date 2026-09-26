# Kurt Tokenizer — Kod Modu ve .NET Veri Haznesi Planı

> Durum: **taslak / karar bekliyor.** Bu belge uygulamadan önce üzerinde anlaşılacak
> yol haritasıdır. Hiçbir kod değişikliği bu plan onaylanmadan yapılmaz.

## 0. Özet

- Hedef: Kurt Tokenizer'ı, Türkçe performansını **bir bit bile değiştirmeden**, önce C#/.NET,
  ileride XML/JSON, HTML, CSS, JavaScript ve Razor kodunu kayıpsız ve verimli bölebilir hâle getirmek.
- Yöntem: Felsefe aynen korunur, yani sistem kural ve bilgi tabanlı, deterministik ve BPE'siz kalır.
  Kod için ayrı bir **mod** açılır. Yeni token'lar yalnızca **sona eklenir** (append-only),
  böylece mevcut 0–4111 ID'leri sabit kalır.
- Sıra: önce **veri haznesi ve lisans envanteri**, sonra **dil bağımsız temel**. Ardından
  **C# 7.3 / .NET Framework 4.8** tabanı kurulur, sonra sürüm sürüm katmanlar eklenir
  (Core 3.1 → 5 → 6 → 7 → 8 → 9 → 10 → 11). En sonda **kod vocab'ı dondurulur** ve eğitim
  korpusu tokenize edilir.

## 1. Temel ilkeler ve önemli bir ayrım

### 1.1 Tokenizer "öğrenmez"; biz ona bilgi ekleriz

Kurt'un vocab'ı korpustan istatistikle çıkmıyor, kurallardan türüyor. Kod için de öyle olacak.
Token kaynakları şunlar:

1. **Dil grameri:** C# anahtar kelimeleri, operatörleri, literal ve yorum biçimleri.
2. **API bilgisi:** Her sürümün resmî API listesinden çıkan tip ve üye adlarının parçaları
   (PascalCase sınırlarından bölünmüş hâlleri).
3. **Biçim:** Boşluk, girinti ve satır sonları.

Korpus yalnızca **ölçüm ve doğrulama** içindir, vocab'ı belirlemez.

### 1.2 Sürüm sırası iki farklı yerde anlam taşır

| | Tokenizer katmanları | Model eğitimi müfredatı |
|---|---|---|
| Ne sıralanıyor? | Vocab'a eklenen token grupları | Modele gösterilen verinin sırası ve oranı |
| Sürüm farkı ne kadar? | **Küçük.** Sözdizimi sürümden sürüme az değişir. Farkın çoğu API adlarında ve onlar da ortak parçalara bölünür | **Büyük.** Sürümler arasındaki asıl bilgi farkı burada |
| Sonuç | Katmanlı geliştirme **tasarım ve test** içindir | Kademeli besleme (4.8 → … → 11) **eğitimde** anlamlıdır |

**Kural:** Eğitim korpusu tek bir donmuş vocab sürümüyle tokenize edilir. Vocab değişirse
korpusun **tamamı** yeniden tokenize edilir. Deterministik tokenizasyon, eğitime göre
ucuzdur. Aynı kod parçası farklı parçalarda farklı bölünürse model tutarsız veri görür.
Her tokenize parçanın (shard) metadata'sında vocab sürümü ve özeti (hash) tutulur.

### 1.3 Dokunulmazlar (regresyon kapıları)

- `veri/vocab.json` içindeki 0–4111 ID'leri **asla değişmez**.
- Türkçe mod için `encode_ids` çıktısı, mevcut `veri/korpus/dogrulama.txt` üzerinde
  **birebir aynı** kalır. Bu bir kapı testi olarak eklenir. Tek istisna, bilinçli olarak
  kararlaştırılacak satır sonu davranışıdır (bkz. Karar K2).
- 155 mevcut test geçmeye devam eder.

## 2. Veri haznesi

Hazne üç ayrı havuzdan oluşur. Bunlar birbirine karıştırılmaz.

| Havuz | Amaç | Boyut | Repoya girer mi? |
|---|---|---|---|
| **A. Bilgi kaynakları** | Vocab üretimi (gramer ve API adları) | Küçük, türetilmiş listeler | Evet, türetilmiş JSON olarak |
| **B. Ölçüm korpusu** | Her sürüm için token/karakter oranı, `<unk>` ve round-trip ölçümü | Sürüm başına ~100–300 dosya | Evet (yalnızca MIT/CC BY örnekler) |
| **C. Eğitim korpusu** | Modelin ön eğitimi | Büyük (GB–TB) | **Hayır**, ayrı depolama |

### 2.1 Havuz A — Bilgi kaynakları

| Kaynak | İçerik | Lisans | Kullanım |
|---|---|---|---|
| C# dil belirtimi ve "What's new in C# X" sayfaları (`dotnet/csharplang`, `dotnet/docs`) | Sürüm başına sözdizimi | MIT / CC BY 4.0 | Anahtar kelime, operatör ve literal listeleri |
| Roslyn `SyntaxKind` listesi (`dotnet/roslyn`) | Tüm token türleri | MIT | Operatör ve anahtar kelime listesinin çapraz kontrolü |
| **`dotnet/dotnet-api-docs`** | Her tip ve üye için XML; sürüm etiketleri (`netframework-4.8`, `net-5.0` … `net-10.0`) | CC BY 4.0 + MIT | **Sürüm başına API adı listesi.** Sürüm farkları buradan hesaplanır (bkz. §4.2) |
| Referans assembly paketleri (`Microsoft.NETFramework.ReferenceAssemblies.net48`, `Microsoft.NETCore.App.Ref` x.y) | Kesin public API | MIT | api-docs'un çapraz kontrolü (isteğe bağlı) |
| `dotnet/core` sürüm notları ve API diff'leri | Sürüm yenilikleri | MIT / CC BY | Doğrulama |

Not: Tokenizer çalışırken **sıfır bağımlılık** ilkesi korunur. XML'ler `araclar/` altında
stdlib `xml.etree` ile bir kez işlenir ve çıktı JSON olarak repoya girer. Tokenizer yalnızca
bu JSON'u okur.

### 2.2 Havuz B — Ölçüm korpusu

Her sürüm için sabit, hash'lenmiş ve el ile seçilmiş bir örnek set hazırlanır:

- `dotnet/samples` ve `dotnet/docs` içindeki kod örnekleri (MIT), sürüme göre ayrılır.
- Her sette farklı yazım biçimleri bulunur: sınıf, LINQ, async, attribute, generic,
  `#region`, XML doc comment (`///`), verbatim, interpolated ve raw string, tab ve boşluk
  girintisi, CRLF satır sonu.
- **Türkçe içeren kod** ayrıca test edilir: Türkçe yorumlar, Türkçe string'ler ve Türkçe
  tanımlayıcılar (`MüşteriGetir`, `SiparisOlustur`).

### 2.3 Havuz C — Eğitim korpusu (tokenizer'dan sonra)

| Kaynak | Lisans | Not |
|---|---|---|
| `dotnet/runtime`, `aspnetcore`, `efcore`, `roslyn`, `winforms`, `wpf`, `maui` | MIT | Commit ve tag'lere göre sürüm eşlemesi yapılır |
| `microsoft/referencesource` (.NET Framework 4.x kaynağı) | MIT | 4.8 dönemi için ana kaynak |
| `dotnet/docs`, `dotnet/dotnet-api-docs` | CC BY 4.0 (metin) + MIT (kod) | Atıf zorunlu |
| Açık kaynak GitHub projeleri | Yalnızca MIT, Apache-2.0, BSD-2/3, CC0, Unlicense | Lisans otomatik tespit edilir |
| **Hariç tutulanlar** | GPL, AGPL, LGPL, CC BY-SA (Stack Overflow), CC BY-NC, lisanssız | Temkin ilkesi (hukuki görüş alınmalı) |

### 2.4 Kayıt şeması (her belge için JSONL)

```json
{
  "id": "sha256:…",
  "kaynak": "github.com/dotnet/aspnetcore",
  "commit": "…", "yol": "src/…/Foo.cs",
  "lisans": "MIT",                    // SPDX
  "tür": "kod | belge | sürüm-notu | api-ref | proje-dosyası",
  "dil": "csharp | xml | json | md | razor | html | css | js",
  "tfm": ["net48"],                   // çoklu hedefte birden fazla
  "dotnet": "4.8", "csharp": "7.3",
  "sürüm_kaynağı": "csproj | api-docs-moniker | repo-tag | elle",
  "dedup_küme": "…", "boyut": 1234, "tarih": "…"
}
```

### 2.5 Sürüm tespit kuralları

1. **SDK tarzı csproj:** `<TargetFramework(s)>` → `net48`, `netcoreapp3.1`, `net5.0` … `net11.0`.
2. **Eski tarz csproj:** `<TargetFrameworkVersion>v4.8</TargetFrameworkVersion>`.
3. `<LangVersion>` varsa C# sürümü buradan, yoksa TFM'nin varsayılanından alınır (bkz. §4.1 tablo).
4. Dokümanlarda api-docs monikerleri ve "Applies to" bilgisi kullanılır.
5. Çoklu hedefte (`net48;net8.0`) dosya birden fazla etiket alır. Eğitimde ayrıca işaretlenir.
6. Tespit edilemeyen dosya **"bilinmiyor"** olarak kalır. Tahmin yapılmaz (Kurt ilkesi #3).

### 2.6 Temizlik

- Dosya ve fonksiyon düzeyinde yakın kopya tespiti yapılır (dedup).
- Otomatik üretilmiş dosyalar dışlanır: `*.Designer.cs`, `*.g.cs`, `*.g.i.cs`, `AssemblyInfo.cs`,
  `Migrations/*`, `obj/`, `bin/` ve `<auto-generated>` başlığı taşıyan dosyalar.
- Sır tarama yapılır: bağlantı dizeleri, API anahtarları, `appsettings.*.json` içindeki sırlar.
- `KAYNAKLAR.md` / `NOTICE` dosyası oluşturulur: kullanılan her kaynak, lisansı ve atfı.

## 3. Faz 0 — Dil bağımsız temel (kod modundan önce şart)

| # | İş | Neden | Çıkış kriteri |
|---|---|---|---|
| 0.1 | **Katman manifestosu** `veri/vocab_katmanlar.json`: her katmanın adı, ID aralığı ve hash'i | Append-only düzeni kalıcı ve denetlenebilir kılar | `vocab_uret` mevcut 0–4111'i yeniden sıralamaz, yeni katmanları sona ekler |
| 0.2 | **Tam atomik taban:** eksik ASCII karakterler (q, w, x, Q, W, X vb.) + 256 byte-fallback token'ı | `<unk>` tamamen kalkar | Rastgele Unicode ve binary benzeri metinde `<unk>` = 0 ve round-trip birebir |
| 0.3 | **Boşluk koruması:** `\n`, `\r\n`, `\t`, çoklu boşluk token'ları | Şu an `metin.split()` satır yapısını siliyor | Her metinde `decode(encode(x)) == x` (byte düzeyinde) |
| 0.4 | **Mod işaretçileri:** `<|kod:csharp|>` … `<|/kod|>` ve ileride diğer diller için yer | Türkçe motor koda karışmaz | Modlar iç içe geçebilir (Razor için şart) |
| 0.5 | **Sürüm etiketleri:** `<|tfm:net48|>`, `<|tfm:netcoreapp3.1|>`, `<|tfm:net5.0|>` … | Model sürüm bağlamını ayırt eder | Özel token olarak decode'da atılır |
| 0.6 | **Regresyon kapısı:** Türkçe korpusun ID çıktısı birebir aynı kalır | Mevcut eğitim verisini korur | Kapı testi CI'da geçer |

## 4. Faz 1+ — C#/.NET katmanları

### 4.1 Sürüm eşlemesi

| Katman | .NET | Varsayılan C# | Tokenizer açısından önemli yenilikler |
|---|---|---|---|
| **L0 — taban** | Framework 4.8 | 7.3 | Tüm C# 7.3 grameri: ~80 anahtar kelime ve bağlamsal kelimeler (`var`, `async`, `await`, `nameof`, `yield`, `get/set`, LINQ `from/select/where`…), operatörler (`=>`, `?.`, `??`, `::`, `<<=`…), `@"…"`, `$"…"`, `$@"…"`, `'c'`, `1_000`, `0x`/`0b`, sayı sonekleri, `#region/#if/#pragma`, `///` XML doc, attribute'lar, generic'ler, tuple'lar |
| L1 | Core 3.1 | 8.0 | `??=`, `..` (range), `^` (index), switch ifadesi ve `_ =>`, `using var`, `await foreach`, `#nullable` |
| L2 | .NET 5 | 9.0 | `record`, `init`, `with`, `and/or/not` desenleri, `nint/nuint`, target-typed `new()`, `delegate*`, top-level statements |
| L3 | .NET 6 | 10.0 | `global using`, dosya kapsamlı `namespace X;`, `record struct` |
| L4 | .NET 7 | 11.0 | **Raw string `"""…"""` ve `$$"""…"""`** (lexer için kritik), `required`, `file`, `scoped`, `>>>`/`>>>=`, `u8` soneki, liste desenleri `[1, .., 3]` |
| L5 | .NET 8 | 12.0 | Collection expression `[1, 2]` ve spread `..`, primary constructor |
| L6 | .NET 9 | 13.0 | `\e` kaçış dizisi, `params` koleksiyonları, `partial` property |
| L7 | .NET 10 | 14.0 | `field` anahtar kelimesi, `extension` blokları, null-conditional atama `a?.B = x` |
| L8 | .NET 11 | 15.0 | **Önizleme; GA'da (Kasım 2026 beklentisi) doğrulanacak.** O zamana kadar katman açık tutulur |

Notlar:

- ".NET Core 5.0" diye bir sürüm yok. 5'ten itibaren adında "Core" yok. Son "Core" sürümü **3.1**.
  3.1, `Startup.cs` ve `IHostBuilder` döneminin ve piyasadaki çok sayıda projenin temeli
  olduğu için L1 olarak eklenmesini öneriyorum.
- Kod tarafında sözdizimi farkları küçüktür. Sürüm farkının büyük kısmı API'lerdedir
  (`WebApplication.CreateBuilder`, `DateOnly`, `TimeProvider`, `HybridCache`…) ve bu adlar
  §4.2'deki parçalara bölünür.

### 4.2 API adı katmanları (bilgi tabanlı, deterministik)

1. `dotnet-api-docs` üzerinden her sürüm için public tip ve üye adı kümesi çıkarılır: `API(net48)`, `API(net5.0)`, …
2. Her katmanın yeni adları: `API(sürüm) − ⋃ API(önceki sürümler)`.
3. Adlar deterministik kuralla parçalanır:
   - PascalCase/camelCase sınırları: `GetById` → `Get|By|Id`
   - Arayüz öneki: `IActionResult` → `I|Action|Result`
   - Kısaltma blokları: `HTTPClient` → `HTTP|Client`, `XmlReader` → `Xml|Reader`
   - Rakamlar: `Utf8Json` → `Utf|8|Json`
   - Alt çizgi: `_context` → `_|context`
4. Vocab'a **parçalar** girer, tam adlar girmez. Seçim kuralı deterministik ve belgelidir:
   "en az *k* farklı API adında geçen parça" gibi. *k* değeri ölçümle belirlenir.
5. Tam adla eklenecek istisnalar (`Task`, `string`, `Console` gibi çok sık tipler) ayrı bir listede ve gerekçeleriyle tutulur.

### 4.3 C# lexer tasarımı (kod modu içinde)

- **Büyük/küçük harf aynen korunur.** Kodda harf büyüklüğü anlam taşır. Türkçe moddaki
  `<|Bb|>`/`<|BB|>` işaretçileri kod modunda kullanılmaz (bkz. Karar K4).
- **Yorumlar ve string içerikleri** Türkçe motora geri yönlendirilir. Böylece
  `// Müşteriyi getir` Türkçe gibi bölünür.
- **Girinti:** 4/8/12/16 boşluk ve tab için hazır token'lar kullanılır.
- **Bilinmeyen tanımlayıcı** önce parçalara, sonra harflere, en son byte'a iner. Kayıpsızdır ve tahmin yapılmaz.
- **Hata toleransı:** Kapanmamış string veya yorum lexer'ı çökertmez. Kalan kısım byte düzeyinde kayıpsız aktarılır.

### 4.4 Proje dosyaları

.NET projeleri yalnızca `.cs` dosyasından oluşmaz: `.csproj`, `web.config`, `appsettings.json`,
`.sln`, `Directory.Build.props`, `global.json`. Sürüm bilgisini taşıyanlar bunlardır. Bu
yüzden **XML ve JSON modları**, HTML'den önce ve C# L0'dan hemen sonra gelmelidir. XML
modu daha sonra HTML modunun temeli olur.

## 5. Ölçüm ve kabul kriterleri (her katmanda)

| Metrik | Hedef |
|---|---|
| `<unk>` oranı (ölçüm korpusu) | **0** |
| Round-trip (byte düzeyinde) | **%100** |
| Türkçe ID regresyonu | **0 fark** |
| C# karakter/token oranı | Başlangıç ~1,16 (166 karakter → 143 ID). Hedef ≥ 3,0 (ölçümle netleşir) |
| Katman başına eklenen token | Raporlanır. Beklenti: taban ~300–400, C# grameri ~200, API parçaları birkaç bin |
| Hız | Kelime önbelleğiyle MB/s olarak raporlanır. Eğitim korpusu için paralel tokenizasyon planlanır |

Tahmini toplam vocab 4.112'den ~10–15 bine çıkar. Bu, 64K+ BPE vocab'larına göre hâlâ küçüktür.

## 6. Gelecek diller (sıra önerisi)

1. **XML / JSON** (.NET proje dosyaları için gerekli; bkz. §4.4)
2. **HTML** (XML modunun üstüne; etiketler, attribute'lar, entity'ler)
3. **CSS** (seçiciler, özellik adları, birimler; özellik adları W3C/MDN listelerinden)
4. **JavaScript** (ECMAScript grameri; Web API adları için benzer bir liste)
5. **Razor** (`.cshtml`, `.razor`): HTML ile C# iç içe. `@`, `@{ }`, `@code { }` ve
   `@if` geçişleri. Bu yüzden **mod yığını** (0.4) ilk günden iç içe tasarlanır.

Her dil aynı düzeni izler: gramer katmanı, ad/API katmanı, ölçüm korpusu ve kapı testleri.
Tanımlayıcı parçaları (`Get`, `Id`, `Async`…) diller arasında **paylaşılır**. Aynı
parça iki kez eklenmez.

## 7. Uygulama sırası

| Adım | İş | Çıktı |
|---|---|---|
| 1 | Bu planın onayı ve §8'deki kararlar | Güncellenmiş plan |
| 2 | Lisans matrisi ve kaynak envanteri (§2) | `belgeler/KAYNAKLAR.md`, lisans tespit aracı |
| 3 | Faz 0 (§3) | Append-only vocab, byte tabanı, boşluk koruması, mod işaretçileri ve kapı testleri |
| 4 | Havuz A çıkarıcıları | `araclar/api_cikar.py` → `veri/kod/csharp/api_<tfm>.json` |
| 5 | Havuz B ölçüm setleri | `veri/korpus/kod/csharp/<tfm>/` |
| 6 | L0: C# 7.3 / net48 | Lexer, tanımlayıcı bölücü ve ölçüm raporu |
| 7 | L1…L7 sırayla, her biri ölçüm raporuyla | Katman başına bir PR |
| 8 | XML/JSON modu | |
| 9 | **Kod vocab v1 dondurma** | Sürüm etiketi ve hash |
| 10 | Havuz C'nin toplanması ve tokenizasyonu | Shard'lar ve metadata |
| 11 | L8 (.NET 11 GA), HTML, CSS, JS, Razor | v2, v3… (her biri tam yeniden tokenizasyon gerektirir) |

## 8. Karar bekleyen konular

| # | Soru | Önerim |
|---|---|---|
| K1 | Taban sürüm seti | net48 + **netcoreapp3.1** + net5.0 ile başlamak |
| K2 | Türkçe modda satır sonları: paragraf yapısı korunsun mu? (Korunursa mevcut Türkçe korpusun yeniden tokenize edilmesi gerekir) | Korunsun. Model paragrafı ve listeyi görmeli. Tokenizasyon ucuz |
| K3 | Kod bölgesi nasıl tespit edilecek? Yalnızca açık işaretçiler mi, yoksa ```` ```csharp ```` blokları ve dosya uzantısından otomatik mi? | Ön işlemede otomatik (uzantı ve fence), tokenizer'da yalnızca açık işaretçi. Böylece deterministik kalır |
| K4 | Kod modunda büyük/küçük harf | Aynen korunsun, casing işaretçisi kullanılmasın |
| K5 | Ticari kullanım hedefi var mı? (Lisans matrisinin sıkılığını belirler) | Varsayılan olarak sıkı matris (§2.3) |
| K6 | .NET 11 önizleme verisi alınsın mı? | GA'ya kadar yalnızca ölçüm yapılsın, vocab'a eklenmesin |
| K7 | Türkçe ASCII tanımlayıcılar (`SiparisOlustur`) Türkçe motora gitsin mi? | Başta hayır. Parça bölücü yeterli. Ölçüm sonrası yeniden değerlendirilsin |

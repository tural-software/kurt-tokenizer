# Kurt Tokenizer — Kod Modu ve .NET Veri Haznesi Planı

> Durum: **taslak v2.1 (2026-09-26).** K1, K2, K4, K5 ve K8 kararlaştırıldı. K3, K6 ve K7
> örneklerle açıklandı, karar bekliyor. Kaynak envanteri:
> [KAYNAKLAR.md](KAYNAKLAR.md). Tokenizer kodu bu plan onaylanmadan değişmez.

## Karar kaydı

| # | Konu | Durum | Karar | Plana etkisi |
|---|---|---|---|---|
| K1 | Taban sürüm | ✅ Karar | **L0 = yalnızca .NET Framework 4.8 (C# 7.3).** Bir katman onaylanmadan sonrakine geçilmez | §4.1, §7 |
| K2 | Türkçe paragraf yapısı | ✅ Karar | **Korunur.** Türkçe eğitim korpusu Faz 0'dan sonra yeniden tokenize edilir | §1.3, §3 (0.3) |
| K3 | Kod bölgesi tespiti | Karar bekliyor | Ön işlemede otomatik (dosya uzantısı ve ```` ``` ```` blokları), tokenizer'da yalnızca açık işaretçi | §3 (0.4) |
| K4 | Kod modunda harf büyüklüğü | ✅ Karar | **Aynen korunur, casing işaretçisi kullanılmaz** | §4.3 |
| K5 | Kullanım amacı | ✅ Karar | **Bireysel, ticari olmayan kullanım.** Ticari karar alınırsa hukuki süreç o zaman başlatılır | §2.3 |
| K6 | .NET 11 önizlemesi | Karar bekliyor | GA'ya kadar yalnızca ölçüm yapılır, vocab'a eklenmez | §4.1 |
| K7 | Türkçe tanımlayıcılar (`SiparisOlustur`, `MüşteriGetir`) | Karar bekliyor | Öneri: parça bölücü; parçayı Türkçe motora yalnızca motor onu tam tanıyorsa gönder | §4.3 |
| K8 | NuGet paketlerinin API adları | ✅ Karar | **Her katman önce yalnızca çerçevenin kendi API'siyle kurulur. O sürümde kullanılan NuGet paketleri (net48 için MVC 5, Web API 2, EF6…) ayrı bir paket alt katmanı (L0b, L1b, …) olarak eklenir.** Paket seçim kuralı alt katmanın sırası gelince belirlenir | §4.2, §7 |

**K1 gerekçesi (neden 3.1 değil de 4.8):**

1. **Gramer alt küme ilişkisi:** C# 7.3 ⊂ 8 ⊂ … ⊂ 15. 4.8 ile başlayınca her katman yalnızca
   ekleme yapar; L0'da hiçbir şey sonradan geri alınmaz.
2. **Aynı gramer daha geniş bir kod tabanını kapsar:** Resmî tabloya göre .NET Framework'ün tüm
   sürümleri, .NET Standard 2.0/1.x ve .NET Core 2.x varsayılan olarak C# 7.3 kullanır. L0 bunların
   hepsini sözdizimi düzeyinde kapsar.
3. **Kaynak zengin:** `microsoft/referencesource`, .NET Framework 4.8'in kendi kaynak kodudur
   (MIT, 14.641 `.cs` dosyası).
4. **3.1 hemen arkasından gelir (L1).** Modern .NET (5–11) API'leri Framework'ün değil Core'un
   devamıdır. Bu yüzden L1'de büyük bir API sıçraması beklenir; ölçüm raporu bunu gösterecek.

## 0. Özet

- **Hedef:** Kurt Tokenizer'ı, Türkçe performansını değiştirmeden, önce C#/.NET, ileride
  XML/JSON, HTML, CSS, JavaScript ve Razor kodunu kayıpsız ve verimli bölebilir hâle getirmek.
- **Yöntem:** Felsefe aynen korunur: kural ve bilgi tabanlı, deterministik, BPE yok. Kod için
  ayrı bir **mod** açılır. Yeni token'lar yalnızca **sona eklenir**; 0–4111 aralığındaki ID'ler sabit kalır.
- **Sıra:**
  1. Veri haznesi ✅
  2. Dil bağımsız temel (Faz 0)
  3. **L0: yalnızca C# 7.3 / .NET Framework 4.8** ve ölçüm raporu (onay kapısı)
  4. Sonra her seferinde **tek katman**: 3.1 → 5 → 6 → 7 → 8 → 9 → 10
  5. Kod vocab'ı dondurulur ve eğitim korpusu tokenize edilir

## 1. Temel ilkeler

### 1.1 Tokenizer "öğrenmez", biz ona bilgi ekleriz

Kurt'un vocab'ı korpustan istatistikle çıkmaz, kurallardan türer. Kod için de öyle olacak:

1. **Dil grameri:** C# anahtar kelimeleri, operatörler, literal ve yorum biçimleri
   (ECMA-334 standardı ve Roslyn'den).
2. **API bilgisi:** Her sürümün referans assembly'lerinden çıkan tip ve üye adlarının parçaları.
3. **Biçim:** Boşluk, girinti ve satır sonları.

Korpus yalnızca **ölçüm ve doğrulama** içindir, vocab'ı belirlemez.

### 1.2 Sürüm sırası iki farklı yerde anlam taşır

| | Tokenizer katmanları | Model eğitimi müfredatı |
|---|---|---|
| Sıralanan şey | Vocab'a eklenen token grupları | Modele gösterilen verinin sırası ve oranı |
| Sürüm farkının büyüklüğü | **Küçük.** Roslyn eşlemesine göre C# 7.x'in 36 özelliğinden yalnızca üçü yeni bir sözcük biçimi getiriyor (`0b1010`, `1_000`, `0x_FF`), bir tanesi de yeni bir bağlamsal kelime (`unmanaged`). Farkın çoğu API adlarında ve o adlar da ortak parçalara bölünüyor | **Büyük.** Asıl bilgi farkı burada |
| Sonuç | Katman katman ilerleme **tasarım ve ölçüm** içindir | Kademeli besleme (4.8 → … → 11) **eğitimde** anlamlıdır. "Hepsini bir anda eğitmeyelim" ilkesi burada da geçerli |

**Kural:** Eğitim korpusu tek bir donmuş vocab sürümüyle tokenize edilir. Vocab değişirse
korpusun **tamamı** yeniden tokenize edilir. Deterministik tokenizasyon eğitime göre ucuzdur.
Aynı kod farklı parçalarda farklı bölünürse model tutarsız veri görür. Her tokenize parçanın
(shard) metadata'sında vocab sürümü ve özeti (hash) tutulur.

### 1.3 Dokunulmazlar (regresyon kapıları)

- `veri/vocab.json` içindeki 0–4111 ID'leri **asla değişmez.** K2'den sonra Türkçe korpus yeniden
  tokenize edilecek olsa da append-only kuralı sürer: katmanlar denetlenebilir kalır ve eski/yeni
  çıktılar karşılaştırılabilir.
- **Satır bazlı Türkçe kapı:** `veri/korpus/dogrulama.txt` dosyasının her satırı (tek boşluklu) için
  ID dizisi **birebir aynı** kalır. `araclar/dogrula_korpus.py` zaten satır satır çalıştığı için
  bu kapı K2 ile uyumludur.
- **Dosya bazlı yeni kapı (K2):** Aynı dosyanın tamamı, satır sonları ve boş satırlarıyla birlikte,
  byte düzeyinde geri dönüşümlü (round-trip) olmalıdır. Bugün bu test başarısız oluyor.
- Mevcut 155 test geçmeye devam eder. Hiçbiri satır sonu, tab, çoklu boşluk veya
  `decode`'daki `.strip()` davranışına dayanmadığı için K2 onları etkilemez (kontrol edildi).

## 2. Veri haznesi

Ayrıntılı ve doğrulanmış liste: **[KAYNAKLAR.md](KAYNAKLAR.md)** (L0 için tamamlandı).

| Havuz | Amaç | Boyut | Repoya girer mi? |
|---|---|---|---|
| **A. Bilgi kaynakları** | Vocab üretimi (gramer, API adları) | Küçük, türetilmiş listeler | Evet (JSON olarak) |
| **B. Ölçüm korpusu** | Token/karakter oranı, `<unk>` ve round-trip ölçümü | Katman başına ~250 dosya | Evet (yalnızca MIT ve CC BY) |
| **C. Eğitim korpusu** | Modelin ön eğitimi | Büyük (GB–TB) | **Hayır**, ayrı depolama |

### 2.1 Havuz A — Bilgi kaynakları

| Kaynak | Rol | Lisans |
|---|---|---|
| `dotnet/csharpstandard` (`standard-v7` = ECMA-334:2023, C# 7.x) | L0 sözcük grameri | CC BY 4.0 + MIT |
| `dotnet/roslyn` → `MessageID.RequiredVersion()` | Özellik → C# sürümü eşlemesi (C# 1–15). Katman sınırları buradan | MIT |
| `dotnet/roslyn` → `SyntaxKind`, `SyntaxKindFacts` | Token metinlerinin çapraz kontrolü | MIT |
| Referans assembly paketleri (net48: `Microsoft.NETFramework.ReferenceAssemblies.net48` 1.0.3; L1 ve sonrası: `Microsoft.NETCore.App.Ref` …) | Sürüm başına kesin public API adları | MIT |
| `dotnet/docs` → `default-langversion-table.md` | Hedef çerçeve → varsayılan C# | CC BY 4.0 |

**v1'den düzeltme:** `dotnet-api-docs` ana dalı artık yalnızca net-8.0 ve sonrasını içeriyor.
.NET Framework BCL ve 3.1–7.0 indeksleri kaldırılmış (ayrıntı: KAYNAKLAR.md). Bu yüzden API adları
**referans assembly'lerden** okunur. Bunun için `araclar/` altına stdlib ile yazılmış küçük bir
ECMA-335 metadata okuyucu eklenir; sıfır bağımlılık ilkesi korunur.

### 2.2 Havuz B — Ölçüm korpusu

L0 için: referencesource (~120 dosya), aspnetdocs kod parçaları (~60), `samples/framework`
WCF/WF (~40). Türkçe yorum, string ve tanımlayıcıların doğru yönlendirildiği ayrı bir korpus
gerektirmez; bunu birkaç elle yazılmış birim testi doğrular.
Seçim deterministiktir: her alt grupta `sha256(commit + yol)` sırasına göre ilk *N* dosya alınır.

Her sette şu biçimler bulunmalıdır: sınıf, LINQ, async, attribute, generic, `#region`, `///` XML
doc, verbatim ve interpolated string, tab ve boşluk girintisi, **CRLF** (Framework repolarında yaygın).

### 2.3 Lisans matrisi (K5)

| Hedef | İzin verilenler |
|---|---|
| **Repoya giren her şey** (A'dan türetilen listeler, B örnekleri) | MIT, CC BY 4.0 (atıfla). Repo herkese açık olduğu için bu kural **ticari amaçtan bağımsızdır** |
| **Havuz C** (repo dışı, bireysel eğitim) | MIT, Apache-2.0, BSD, CC0, Unlicense, CC BY + **K5 ile** CC BY-SA (Stack Overflow), CC BY-NC, GPL/LGPL/AGPL |
| **Hiçbir yerde** | Lisanssız repolar (kullanım izni yok; nitelikli kod zaten yeterli) |

- Her belge SPDX lisans etiketi taşır. Ticari karar alınırsa "ticari kullanıma uygun alt küme" tek
  filtreyle çıkarılır ve model o alt kümeyle yeniden eğitilir. **Verinin yeniden toplanması gerekmez.**
- **Gözden geçirme tetikleyicileri:**
  1. Ticari kullanım kararı.
  2. Model ağırlıklarının veya çıktılarının herkese açık yayımlanması. Ticari olmasa bile
     SA/GPL/NC koşulları bu noktada devreye girebilir.

### 2.4 Kayıt şeması (her belge için JSONL)

```json
{
  "id": "sha256:…",
  "kaynak": "github.com/microsoft/referencesource",
  "commit": "ec9fa9a", "yol": "System.Web/…/Foo.cs",
  "lisans": "MIT",                    // SPDX
  "tür": "kod | belge | sürüm-notu | api-ref | proje-dosyası",
  "dil": "csharp | xml | json | md | razor | html | css | js",
  "tfm": ["net48"],                   // çoklu hedefte birden fazla
  "dotnet": "4.8", "csharp": "7.3", "katman": "L0",
  "sürüm_kaynağı": "csproj | repo-belgesi | api-ref | elle",
  "durum": "hazır | mod-bekliyor",    // ör. .aspx, .cshtml, web.config → mod-bekliyor
  "dedup_küme": "…", "boyut": 1234, "tarih": "…"
}
```

### 2.5 Sürüm tespit kuralları

1. **SDK tarzı csproj:** `<TargetFramework(s)>` → `net48`, `netcoreapp3.1`, `net5.0` … `net11.0`.
2. **Eski tarz csproj:** `<TargetFrameworkVersion>v4.8</TargetFrameworkVersion>`.
3. **Varsayılan C# sürümü** resmî tablodan alınır:

   | Hedef | C# |
   |---|---|
   | .NET Framework (tüm sürümler), .NET Standard 1.x/2.0, .NET Core 2.x | 7.3 |
   | .NET Core 3.x, .NET Standard 2.1 | 8 |
   | .NET 5 / 6 / 7 / 8 / 9 / 10 / 11 | 9 / 10 / 11 / 12 / 13 / 14 / 15 |

4. `<LangVersion>` varsayılanı ezer. `latest` veya `preview` değerleri derleyiciye göre değiştiği için
   dosya **"belirsiz"** etiketi alır.
5. **Çoklu hedef:** `LangVersion` yoksa ortak kod her hedefte derlenmek zorundadır. Bu yüzden etkin
   sürüm, hedeflerin varsayılanlarının **en küçüğüdür.** `#if` blokları ayrıca işaretlenir.
6. Tespit edilemeyen dosya **"bilinmiyor"** olarak kalır. Tahmin yapılmaz (Kurt ilkesi #3).
7. **L0'a giriş koşulu:** etkin C# sürümü ≤ 7.3 olan `.cs` dosyaları.

### 2.6 Temizlik

- Dosya ve fonksiyon düzeyinde yakın kopya tespiti (dedup).
- Otomatik üretilmiş dosyalar dışlanır: `*.Designer.cs`, `*.g.cs`, `*.g.i.cs`, `AssemblyInfo.cs`,
  `Reference.cs` (WCF servis referansları), `Migrations/*`, `obj/`, `bin/` ve
  `<auto-generated>` başlığı taşıyan dosyalar.
- Sır taraması: bağlantı dizeleri, API anahtarları, `web.config` ve `appsettings.*.json` içindeki sırlar.

## 3. Faz 0 — Dil bağımsız temel (kod modundan önce şart)

| # | İş | Neden | Çıkış kriteri |
|---|---|---|---|
| 0.1 | **Katman manifestosu** `veri/vocab_katmanlar.json`: her katmanın adı, ID aralığı ve hash'i | Append-only düzeni kalıcı ve denetlenebilir kılar | `vocab_uret` 0–4111'i yeniden sıralamaz, yeni katmanları sona ekler |
| 0.2 | **Tam atomik taban:** eksik ASCII karakterleri (q, w, x, Q, W, X…) ve 256 byte-fallback token'ı | `<unk>` tamamen kalkar | Rastgele Unicode ve binary benzeri metinde `<unk>` = 0 ve round-trip birebir |
| 0.3 | **Boşluk koruması (K2).** Tek boşluk yine `▁` olarak kalır (Türkçe kapı bu sayede korunur). `\n`, `\r\n` (tek token), `\t` ve boşluk dizileri için ayrı token'lar eklenir. Baştaki ve sondaki boşluklar korunur, `decode`'daki `.strip()` kalkar. NBSP (U+00A0) gibi diğer Unicode boşlukları byte yedeğiyle kayıpsız aktarılır; sık görülürlerse ayrı token alırlar | Bugün `metin.split()` satır yapısını siliyor | Her metinde `decode(encode(x)) == x` (byte düzeyinde); §1.3'teki iki kapı |
| 0.4 | **Mod işaretçileri:** `<\|kod:csharp\|>` … `<\|/kod\|>` ve diğer diller için yer | Türkçe motor koda karışmaz (K3) | Modlar iç içe geçebilir (Razor için şart) |
| 0.5 | **Sürüm etiketleri:** `<\|tfm:net48\|>`, `<\|tfm:netcoreapp3.1\|>` … | Model sürüm bağlamını ayırt eder | Özel token olarak decode'da atılır |
| 0.6 | **Regresyon kapıları** (§1.3) | Türkçe davranışı korur | Kapı testleri geçer |

Faz 0 bitince Türkçe eğitim korpusu yeniden tokenize edilebilir (K2). Bunun için kod modunun
beklenmesi gerekmez.

## 4. C#/.NET katmanları

### 4.1 Katman eşlemesi

Özellik sayıları Roslyn `MessageID.RequiredVersion()` eşlemesinden alındı (`90083ec`).

| Katman | .NET | C# | Roslyn özellik sayısı | Tokenizer açısından önemli yenilikler |
|---|---|---|---|---|
| **L0 — taban** | **Framework 4.8** | 1–7.3 | 7.x: 36 | Tüm C# 7.3 grameri: anahtar kelimeler ve bağlamsal kelimeler (`var`, `async`, `await`, `nameof`, `yield`, `when`, LINQ `from/select/where`…), operatörler (`=>`, `?.`, `??`, `::`, `<<=`…), `@"…"`, `$"…"`, `$@"…"`, `'c'`, `0b1010`, `1_000`, `0x_FF`, sayı sonekleri, `#region/#if/#pragma`, `///` XML doc, attribute'lar, generic'ler, tuple'lar |
| L1 | Core 3.1 | 8 | 20 | `??=`, `..`, `^` (indeks), `@$"`, `#nullable`, switch ifadesi, `await foreach`, `await using` |
| L2 | .NET 5 | 9 | 24 | `record`, `init`, `with`, `and/or/not`, `nint/nuint`, `delegate*`, target-typed `new()` |
| L3 | .NET 6 | 10 | 17 | `global using`, dosya kapsamlı `namespace X;`, `record struct` |
| L4 | .NET 7 | 11 | 15 | **Raw string `"""…"""` ve `$$"""…"""`** (lexer için kritik), `u8` soneki, `>>>`/`>>>=`, `required`, `file`, `scoped`, liste desenleri |
| L5 | .NET 8 | 12 | 8 | Collection expression `[1, 2]` ve spread `..`, primary constructor |
| L6 | .NET 9 | 13 | 9 | `\e` kaçış dizisi (Roslyn'de "lexer check" olarak işaretli), `params` koleksiyonları, `partial` property, `allows ref struct` |
| L7 | .NET 10 | 14 | 9 | `field`, `extension` blokları, null-conditional atama `a?.B = x`, partial constructor/event |
| L8 | .NET 11 | 15 | 6 | **Önizleme (K6).** `Unions`, `LabeledBreakContinue`, `CollectionExpressionArguments`, `ExtensionIndexers`, `ClosedClasses`, `StaticMembersInInterfaces`. GA'da (Kasım 2026 beklentisi) kesinleşecek |

- **4.8.1 (`net481`)** L0'a dahildir (gramer aynı, API farkı çok küçük).
- **.NET Standard 2.0** aynı grameri kullanır ve API'si net48'in alt kümesidir. Ayrı katman gerekmez;
  yalnızca `<|tfm:netstandard2.0|>` etiketi eklenir ve L0 onaylandıktan sonra ölçüm setine katılır.
- ".NET Core 5.0" diye bir sürüm yok: 5'ten itibaren adında "Core" yok, son "Core" sürümü 3.1.

### 4.2 API adı katmanları (bilgi tabanlı, deterministik)

1. Her sürümün referans assembly'lerinden public tip ve üye adları çıkarılır: `API(net48)`,
   `API(netcoreapp3.1)`, … Kaynaklar KAYNAKLAR.md'de.
2. Her katmanın yeni adları: `API(sürüm) − ⋃ API(önceki katmanlar)`. L1 farkı büyük olacaktır (bkz. K1 gerekçesi, madde 4).
3. Adlar deterministik kuralla parçalanır:
   - PascalCase ve camelCase sınırları: `GetById` → `Get|By|Id`
   - Arayüz öneki: `IActionResult` → `I|Action|Result`
   - Kısaltma blokları: `HTTPClient` → `HTTP|Client`, `XmlReader` → `Xml|Reader`
   - Rakamlar: `Utf8Json` → `Utf|8|Json`
   - Alt çizgi: `_context` → `_|context`
4. Vocab'a tam adlar değil **parçalar** girer. Seçim kuralı deterministik ve belgelidir
   (ör. "en az *k* farklı API adında geçen parça"). *k* değeri L0 ölçümüyle belirlenir.
5. Tam adla eklenecek istisnalar (`Task`, `String`, `Console` gibi çok sık tipler) gerekçeleriyle
   ayrı bir listede tutulur.
6. **Paket alt katmanları (K8):** Her sürüm katmanından sonra, o sürümde kullanılan NuGet
   paketlerinin API adları ayrı bir alt katman olarak eklenir (L0b: MVC 5, Web API 2, EF6…;
   L1b: o dönemin paketleri…). Adlar yine parçalara bölünür; paket başına özel token gerekmez.

### 4.3 C# lexer tasarımı (kod modu içinde)

- **Harf büyüklüğü aynen korunur (K4).** `Get` ve `get` ayrı token'lardır. Kod modunda
  `<|Bb|>`/`<|BB|>` kullanılmaz.
- **Yorumlar ve string içerikleri** Türkçe moda geri döner. Orada casing işaretçileri her zamanki
  gibi çalışır. Böylece `// Müşteriyi getir` Türkçe gibi bölünür.
- **Girinti:** 4/8/12/16 boşluk ve tab için hazır token'lar kullanılır.
- **Bilinmeyen tanımlayıcı** önce parçalara, sonra harflere, en son byte'a iner. Kayıpsızdır ve tahmin yapılmaz.
- **Türkçe ASCII tanımlayıcılar (K7):** `SiparisOlustur` → `Siparis|Olustur`. Türkçe motora gönderilmez.
- **Hata toleransı:** Kapanmamış string veya yorum lexer'ı çökertmez; kalan kısım byte düzeyinde kayıpsız aktarılır.

### 4.4 Proje dosyaları ve diğer türler

.NET projeleri yalnızca `.cs` dosyalarından oluşmaz. Framework döneminde `.csproj` (eski tarz),
`packages.config`, `web.config`, `Global.asax`, `.aspx`/`.ascx` (Web Forms) ve `.cshtml` (MVC 5
Razor) dosyaları da vardır. **L0 yalnızca `.cs` dosyalarını kapsar.** Diğerleri Havuz C'de
`mod-bekliyor` etiketiyle toplanır ve XML/JSON, HTML ve Razor modları geldiğinde işlenir.
Sürüm tespiti (§2.5) proje dosyalarını tokenizer değil **ön işleme** okuduğu için bu sıralama
tespiti etkilemez.

## 5. Ölçüm ve kabul kriterleri (her katmanda)

| Metrik | Hedef |
|---|---|
| `<unk>` oranı (ölçüm korpusu) | **0** |
| Round-trip (byte düzeyinde, CRLF dahil) | **%100** |
| Türkçe kapılar (§1.3) | **Geçer** |
| C# karakter/token oranı | Başlangıç ~1,16 (166 karakter → 143 ID). Hedef ≥ 3,0 (L0 ölçümüyle netleşir) |
| Katman başına eklenen token | Raporlanır. Beklenti: taban ~300–400, C# grameri ~200, API parçaları birkaç bin |
| Hız | Kelime önbelleğiyle MB/s olarak raporlanır |

**Katman ölçüm raporu** şunları içerir: alt grup başına karakter/token oranı, en çok parçalanan
50 tanımlayıcı (parça seçimini yönlendirir), eklenen token listesi, önceki katmana göre fark.
**Bir sonraki katmana, bu rapor onaylanmadan geçilmez (K1).**

Tahmini toplam vocab 4.112'den ~10–15 bine çıkar; 64K+ BPE vocab'larına göre hâlâ küçüktür.

## 6. Gelecek diller (sıra önerisi)

1. **XML / JSON:** .NET proje dosyaları için. C# katmanlarından sonra, v1 dondurulmadan önce gelir.
2. **HTML:** XML modunun üstüne; etiketler, attribute'lar, entity'ler.
3. **CSS:** Seçiciler, özellik adları, birimler.
4. **JavaScript:** ECMAScript grameri ve Web API adları.
5. **Razor** (`.cshtml`, `.razor`): HTML ile C# iç içe. MVC 5 döneminden beri var. `@`, `@{ }`,
   `@code { }` geçişleri için mod yığını (0.4) ilk günden iç içe tasarlanır.

Her dil aynı düzeni izler: gramer katmanı, ad/API katmanı, ölçüm korpusu ve kapı testleri.
Tanımlayıcı parçaları (`Get`, `Id`, `Async`…) diller arasında **paylaşılır**.

## 7. Uygulama sırası

| Adım | İş | Durum |
|---|---|---|
| 1 | Plan v1 | ✅ |
| 2 | Kararlar K1, K2, K4, K5 → plan v2 | ✅ |
| 3 | L0 kaynak envanteri, lisans doğrulaması ve sürüm sabitleme ([KAYNAKLAR.md](KAYNAKLAR.md)) | ✅ |
| 4 | **Faz 0** (§3): manifesto, byte tabanı, boşluk koruması, mod işaretçileri, kapı testleri | Sırada |
| 5 | Havuz A araçları: ECMA-335 okuyucu → `veri/kod/csharp/api_net48.json`; C# 7.3 gramer listesi (standard-v7 + Roslyn) | |
| 6 | Havuz B: L0 ölçüm seti (~220 dosya, deterministik seçim) | |
| 7 | **L0** uygulaması (lexer ve parça bölücü) + ölçüm raporu → **onay kapısı** | |
| 7b | **L0b:** net48 döneminin NuGet paketleri (K8) → rapor → onay | |
| 8 | L1 (netcoreapp3.1 / C# 8) ve L1b → rapor → onay; sonra L2 … L7 aynı döngüyle, **tek tek** | |
| 9 | XML/JSON modu | |
| 10 | **Kod vocab v1 dondurma** (sürüm etiketi ve hash) | |
| 11 | Havuz C'nin toplanması ve tüm korpusun (Türkçe dahil, K2) tokenizasyonu | |
| 12 | L8 (.NET 11 GA), HTML, CSS, JS, Razor → v2, v3… (her biri tam yeniden tokenizasyon gerektirir) | |

## 8. Sonraya bırakılanlar

- Havuz C için GitHub'daki net48 projelerini keşif yöntemi (Adım 11'de seçilecek).
- Stack Overflow veri dökümünün güncel erişim koşulları (indirme sırasında).
- Eski sürümlerin API dokümantasyon metinleri için `dotnet-api-docs` git geçmişi (gerekirse; ad listesi için gerekmiyor).
- `ef6` ve `aspnetwebstack` projelerinde `LangVersion` ayarının doğrulanması (Havuz C etiketlemesi için).

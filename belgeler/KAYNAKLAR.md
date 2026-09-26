# Kaynak Envanteri

> Kapsam: **L0 — .NET Framework 4.8 / C# 7.3** (Karar K1). Sonraki katmanlar kendi
> sıraları gelince bu belgeye eklenir.
> Doğrulama tarihi: **2026-09-26.** Her lisans, kaynağın kendi LICENSE dosyasından veya
> NuGet paket tanımından okundu. Her kaynak bir commit'e veya paket sürümüne
> **sabitlendi**. Aynı girdiler her zaman aynı vocab'ı üretir (deterministik ilke).
>
> Bu belge aynı zamanda **atıf kaydıdır.** CC BY 4.0 lisanslı kaynaklardan türetilen her veri
> buradan kaynağına bağlanır.

## Lisans kuralı (Karar K5 sonrası)

| Hedef | İzin verilen lisanslar | Neden |
|---|---|---|
| **Repoya giren her şey** (Havuz A'dan türetilen listeler, Havuz B ölçüm örnekleri) | MIT, CC BY 4.0 (atıfla) | Repo herkese açık ve MIT lisanslı. Repoya giren dosya yeniden dağıtılmış olur. Bu kural **ticari amaçtan bağımsızdır** |
| **Havuz C** (repo dışı, bireysel ve ticari olmayan eğitim) | Yukarıdakiler + Apache-2.0, BSD, CC0, Unlicense + K5 ile CC BY-SA, CC BY-NC, GPL/LGPL/AGPL | Bireysel ve ticari olmayan kullanım. Her belge SPDX etiketi taşır, ileride tek filtreyle ayıklanabilir |
| **Hiçbir yerde** | Lisanssız repolar | Kullanım izni yok. Nitelikli MIT/Apache kodu zaten yeterince var |

Apache-2.0 kaynaklar, NOTICE yükümlülüğü nedeniyle repoya alınmaz; Havuz C'de serbesttir.

---

## Havuz A — Bilgi kaynakları (vocab'ı belirler)

| # | Kaynak | Sabit sürüm | Lisans (doğrulandı) | L0'daki rolü |
|---|---|---|---|---|
| A1 | `dotnet/csharpstandard`, dal `standard-v7`: **ECMA-334:2023 (C# 7.x standardı)** | `02d1a90` (2024-03-28) | Metin CC BY 4.0, araç kodu MIT | C# 7 sözcük grameri: anahtar kelimeler, operatör ve noktalama, literal biçimleri (`standard/lexical-structure.md`, `standard/grammar.md`) |
| A2 | `dotnet/roslyn`, `src/Compilers/CSharp/Portable/Errors/MessageID.cs` → `RequiredVersion()` | `90083ec` (2026-09-26) | MIT | **Özellik → C# sürümü eşlemesi.** C# 1'den 15'e kadar her özelliğin hangi sürümde geldiğini söyler. L0 sınırını (≤ 7.3) ve sonraki katman farklarını buradan alırız |
| A3 | `dotnet/roslyn`, `Syntax/SyntaxKind.cs` ve `Syntax/SyntaxKindFacts.cs` | `90083ec` | MIT | Anahtar kelime ve noktalama metinlerinin eksiksiz listesi (A1'in çapraz kontrolü) |
| A4 | NuGet `Microsoft.NETFramework.ReferenceAssemblies.net48` | `1.0.3` (en son sürüm) | MIT (paketin `licenseUrl` alanı → `microsoft/dotnet` LICENSE, `fb8d575`'te doğrulandı) | **.NET Framework 4.8 public API adları** (tip ve üye adları). Parça bölücünün girdisi |
| A5 | `dotnet/docs`, `docs/csharp/language-reference/includes/default-langversion-table.md` | `d2ba342` (2026-09-25) | CC BY 4.0 | Hedef çerçeve → varsayılan C# sürümü eşlemesi (sürüm tespit kuralı) |

### A2'den çıkan L0 sınırı

Roslyn eşlemesine göre L0 = C# 1 … 7.3. C# 7.x bu sınırın içinde toplam **36 özellik** taşıyor
(7.0'da 11, 7.1'de 4, 7.2'de 8, 7.3'te 13). Bunlardan yalnızca üçü yeni bir **sözcük biçimi**
getiriyor: ikili literal `0b1010`, basamak ayırıcı `1_000` ve baştaki ayırıcı `0x_FF`. Buna bir de
yeni bağlamsal kelime (`where T : unmanaged`) ekleniyor. Geri kalanı var olan token'ların yeni
kullanımları (`out var`, `ref readonly`, `private protected`, `default` literal…). Yani tokenizer
açısından sürüm farkı küçük, model açısından büyük (Plan §1.2).

### API adları için neden `dotnet-api-docs` değil?

`dotnet/dotnet-api-docs` (`14438973`, 2026-09-25; CC BY 4.0 + MIT) ana dalında yalnızca desteklenen
sürümlerin indeksi kalmış: `net-8.0` … `net-11.0` ve `windowsdesktop-*`. .NET Framework için
yalnızca `netframework-4.x-pp` dosyaları var. Bunlar Framework'ün kendi API'si değil; net48'e NuGet
ile eklenebilen paketlerin (`Microsoft.Bcl.*`, `Microsoft.Extensions.*`) listesi.
`netcore-3.1`, `net-5.0`, `net-6.0` ve `net-7.0` indeksleri ise tamamen kaldırılmış.
Bu yüzden API adları **referans assembly paketlerinden** çıkarılır. Bu yöntem tüm sürümler için
tek tip ve kesindir. `dotnet-api-docs`, net-8.0 ve sonrası için yalnızca çapraz kontrol olarak kullanılır.

Araç: sıfır bağımlılık ilkesi korunur. `araclar/` altına, stdlib ile yazılmış küçük bir
ECMA-335 metadata okuyucu eklenir. Bu okuyucu PE dosyasından tip ve üye adlarını okur,
çıktıyı JSON olarak repoya yazar. Tokenizer yalnızca bu JSON'u görür.

---

## Havuz B — L0 ölçüm korpusu (repoya girer, ~220 dosya)

| # | Kaynak | Sabit sürüm | Lisans | İçerik | Pay |
|---|---|---|---|---|---|
| B1 | `microsoft/referencesource` | `ec9fa9a` (2025-10-15) | MIT | **.NET Framework 4.8'in kendi kaynak kodu.** Commit geçmişi bunu doğruluyor: "Update Reference Sources to .NET Framework 4.8" (2019-04-16), "4.8 ZDP" (2019-08-13), "4.8 patched files" (2019-09-24). Toplam 14.641 `.cs` dosyası; en büyük bölümler System.Web 1.761, System.ServiceModel 1.722, System.Data 1.630, mscorlib 1.257, System 1.224 | ~120 |
| B2 | `aspnet/aspnetdocs` | `1a82bb8` (2026-07-26) | Kod MIT, metin CC BY 4.0 | ASP.NET 4.x doküman kod parçaları, toplam 3.093 `.cs` dosyası: MVC 1.006, Web Forms 719, Web API 518, SignalR 428, Web Pages 126, Identity 108 | ~60 |
| B3 | `dotnet/samples`, `framework/` klasörü | `acb39ce` (2026-09-18) | Kod MIT | WCF (373 v4.0 ve 10 v4.8 proje) ve Windows Workflow Foundation (74 v4.0 proje) | ~40 |

**Seçim deterministik yapılır:** Her alt grupta dosyalar `sha256(commit + yol)` sırasına dizilir ve
ilk *N* dosya alınır. Aynı commit her zaman aynı seti verir. Seçilen dosyaların listesi ve
özetleri (hash) repoya yazılır.

**B'ye alınmayan adaylar ve nedenleri:**

| Aday | Neden |
|---|---|
| `dotnet/ef6` (`7a68d38`, MIT) | Çoklu hedef (`net40;net45` ile `netstandard2.1`/`net8.0` birlikte). Ortak kod C# 7.3 ile derlenmek zorunda olsa da `LangVersion` ayarı henüz doğrulanmadı. Havuz C'ye alınır |
| `aspnet/aspnetwebstack` (`c98468c`, Apache-2.0) | Apache-2.0 olduğu için repoya alınmaz (yukarıdaki kural). MVC 5 / Web API 2 kaynağı olarak Havuz C'ye alınır |
| `microsoft/wpf-samples` (`811d01e`, MIT) | 252 projenin 229'u artık `net10.0-windows` hedefliyor. L0'a uygun eski hâli ancak git geçmişinden alınabilir |

---

## Havuz C — L0 dönemi eğitim korpusu adayları (repo dışı; Adım 11'de toplanır)

| Kaynak | Lisans | Not |
|---|---|---|
| `microsoft/referencesource` (tamamı) | MIT | .NET Framework 4.8 |
| `dotnet/ef6` | MIT | Entity Framework 6 |
| `aspnet/aspnetwebstack` | Apache-2.0 | ASP.NET MVC 5, Web API 2, Web Pages (L0b API adları için de aday) |
| `aspnet/aspnetdocs` (tamamı) | Metin CC BY 4.0, kod MIT | ASP.NET 4.x makaleleri ve kod parçaları |
| `dotnet/docs`, `docs/framework/` | Metin CC BY 4.0, kod MIT | .NET Framework dokümanları: 5.454 makale (WCF, WF, veri, ağ, dağıtım, sürüm notları…) |
| `dotnet/samples`, `framework/` | MIT | WCF ve WF örnekleri |
| `microsoft/wpf-samples` (net10 göçünden önceki hâli) | MIT | Git geçmişinden |
| GitHub'daki açık kaynak net48 projeleri | MIT, Apache, BSD (+ K5 ile GPL ailesi, etiketli) | Keşif yöntemi Havuz C zamanı gelince seçilecek |
| Stack Overflow (`.net-framework`, `asp.net-mvc-5`, `wcf`, `entity-framework-6`, `webforms` etiketleri…) | CC BY-SA | K5 ile bireysel eğitimde kabul. Veri dökümünün erişim koşulları indirme sırasında ayrıca okunacak |

**L0 dışında tutulan dosya türleri:** `.aspx`, `.ascx`, `.cshtml`, `web.config`, `.csproj` ve
`packages.config` gibi dosyalar Havuz C'de toplanır ama **"mod bekliyor"** diye etiketlenir.
Bu dosyalar XML, HTML ve Razor modları geldiğinde işlenir. L0 yalnızca `.cs` dosyalarını kapsar.

---

## Sonraki katmanlar için not edilenler

- **L1 (netcoreapp3.1):** API listesi için NuGet `Microsoft.NETCore.App.Ref` paketi kullanılacak. Lisansı `3.1.0` sürümünde MIT olarak doğrulandı; kesin sürüm L1'de sabitlenecek. ASP.NET Core ve Windows Desktop API'leri ayrı paketlerden gelir (`Microsoft.AspNetCore.App.Ref`, `Microsoft.WindowsDesktop.App.Ref`).
- **C# 8 grameri:** `dotnet/csharpstandard` ana dalı C# 8 taslağıdır (ECMA-334:2023'ün yerine geçecek sürüm). Roslyn eşlemesi (A2) C# 8'de 20 özellik gösteriyor.
- **.NET 11 / C# 15:** Varsayılan tabloya (A5) göre .NET 11 C# 15 kullanıyor. Roslyn ana dalında (`90083ec`) C# 15 için 6 özellik tanımlı: `Unions`, `LabeledBreakContinue`, `CollectionExpressionArguments`, `ExtensionIndexers`, `ClosedClasses`, `StaticMembersInInterfaces`. Liste GA'da kesinleşecek (Karar K6).

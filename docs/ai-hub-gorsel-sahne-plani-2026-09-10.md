# AI Hub Görsel Sahnesi — Kapsamlı Düzeltme Planı

**Tarih:** 2026-09-10 · **Durum:** ONAY BEKLİYOR (kod yazılmadı) · **Kapsam:** 13 AI modülünün tamamı

Sahibin bildirimi (2026-09-09, fantom ekran görüntüleriyle):

> "kullanıcı yüklüyor fotoyu fantomun ama fotoğrafın pixeline göre değişiyor boyut bazen küçük
> bazen büyük oluyor. analiz ete tıklayınca ilk yüklediği input fotosu kayboluyor sonuç da küçük
> ve yazıları okunmaz geliyor. buna kapsamlı bir çözüm bul. her ai modeli için düşün.
> butonlu bir uı iyi olabilir sağ yön butonuna kullanıcı tıkladıkça sonuca gider ya da girişe
> döner sol yön butonuyla."

Ekran görüntüsü gerekmedi: 13 modül **kaynaktan** envanterlendi (12 paralel ajan, ölçümler
gömülü Python 3.10 + cv2 4.11 ile gerçek test girdileri üzerinde koşturuldu).

---

## 0. Üç arıza, ölçülmüş kök nedenler

### Arıza 1 — Girdi fotoğrafı analiz sonrası kayboluyor

Kök neden tek satır ve **5 yerde birebir kopyalanmış**:

```
pf/src/screens/AiHubScreen.tsx  satır 1535, 1922, 2219, 3074, 3828
<Image source={{ uri: result?.image_base64 ? `data:image/jpeg;base64,${result.image_base64}` : imageUri }} ... />
```

Veri kaybı YOK — `imageUri` state'te ve `visionCache`'te duruyor. Sorun **salt gösterim**:
`result` dolduğu an ternary sonuç dalına geçiyor ve `imageUri`'yi çizen başka hiçbir JSX yok.
Geri dönüş yolu yok; tek çıkış fotoğrafı yeniden seçmek — o da sonucu siliyor.

Ağırlaştırıcı: fantom/petri'de sunucu `image_base64`'ü **her iki** yolda gönderiyor
(başarı → mozaik; `no_detection` → orijinalin yeniden kodlanmışı, ai_router.py:2645/2822),
dolayısıyla ternary **asla** `imageUri` dalına düşmüyor.

Etkilenen 5 modül: VisionModule (4 uç), Phantom, Petri, KidneyCT, CatOrgan.
CatOrgan'da ek kayıp: overlay orijinalin üzerine çizildiği için kullanıcı fotoğrafını görür ama
**etiketsiz kıyas karesini** kaybeder.

### Arıza 2 — Sonuç küçük, yazıları okunmaz

Aritmetik (ölçüldü, masaüstü 1600×900, kap ~1000×330 px):

| Girdi | Mozaik (07_combined) | Oran | Ekranda | Panel başına | Küçültme |
|---|---|---|---|---|---|
| 3024×4032 (web, ham) | 6048×12256 | 0,49 | 163×330 | ~81 px | **37×** |
| 1500×2000 (native) | 3000×6160 | 0,49 | 161×330 | ~80 px | **18,7×** |
| 4032×3024 (yatay) | 8064×9232 | 0,87 | 288×330 | ~144 px | 21× |

`07_combined` = 2 kolon × 3 satır mozaik. Panelin içine `cv2.putText` ile yazılmış ~12 px'lik
metin (phantom_cv/render.py:248-272 `T1 (+x,+y)mm E_kanser=0.1234`) ekranda **~0,35 px** →
tamamen kayboluyor. Kap genişliğinin **%84'ü boş letterbox** (163/1000).

⚠️ **Bu, oran kilidiyle ÇÖZÜLMEZ.** Mozaik zaten uzun ve ince; kutuyu 0,49 oranına kilitlemek
161×330 veriyor — aynı sonuç. Tek panele bölünürse (oran ~0,74) 330 px tavanda 244 px genişlik
→ 12× küçültme, hâlâ okunmaz. **Okunabilirliğin bağlayıcı kısıtı sahne yüksekliği tavanıdır**
(`useStageHeight()` = clamp(pencereY×0,45; rs(180); rs(300)) → masaüstünde 330 px sabit).

Çözüm zorunlu olarak **iki parçalı**: (a) mozaiği tek tek panellere böl, (b) tavanı aşan bir
tam-ekran/yakınlaştırma kipi ver. (a) tek başına yetmez.

### Arıza 3 — Boyut fotoğrafın pikseline göre değişiyor

İki bağımsız kaynak:

1. **İstemci asimetrisi.** Native yolda `shrinkForUpload` uzun kenarı 1500 px'e çekiyor
   (AiHubScreen.tsx:50-63; çağrılar 390, 418, 1282, 1311, 1827, 1849, 2105, 2127, 2981).
   **Web yolunda küçültme YOK** — `URL.createObjectURL(file)` + ham `File` postalanıyor
   (382, 410, 1273, 1302, 1820, 1842, 2098, 2120, 2976). Sahibin ekran görüntüleri masaüstü
   olduğu için **en kötü senaryo** orada.
2. **Sunucu kapağı yok.** `cv2.imencode('.jpg', panels["07_combined"])` (ai_router.py:2642, 2819)
   ne kalite ne boyut argümanı almıyor → OpenCV varsayılanı **q95**, kapak **yok**.
   640×480 girdi → 1280×1564 mozaik (2,0 MP); 4032×3024 girdi → 8064×9232 (**74 MP**).
   Aynı modül, **8× ölçü farkı** — sahibin "bazen küçük bazen büyük"ünün tam aritmetiği.

---

## 1. Yayın boyutu: gerçek foto ölçeğinde YARIYA iniyor (küçük girdide %14 büyür)

Sunucu `render_all_panels` ile **zaten 7 panel üretiyor** ve 6'sını aynı satırda çöpe atıyor:

| | Fantom (phantom_cv/render.py:303-326) | Petri (petri_cv/render.py:326-351) |
|---|---|---|
| 01 | `01_input` | `01_input` |
| 02 | `02_phantom_detect` | `02_yolo_dets` |
| 03 | `03_phantom_mask` | `03_yolo_masks` |
| 04 | `04_tumors` | `04_classify` |
| 05 | `05_local_coords` | `05_local_coords` |
| 06 | `06_predictions` | `06_predictions` |
| 07 | `07_combined` ← **yalnız bu gidiyor** | `07_combined` ← **yalnız bu gidiyor** |

⚠️ Panel adları iki modülde **FARKLI** → ortak galeri modül-başına anahtar eşlemesi ister
(SCRATCH_GALERI deseni gibi).

Ölçülen yük (gerçek test girdileri: `ai_hub/PEMF_AI_Test_Girdileri/05_FantomTumor.jpeg`):

| Senaryo | fantom yatay | fantom dikey |
|---|---|---|
| **BUGÜN** (tek mozaik, q95, kapaksız) | 1.645,6 KB | 2.412,6 KB |
| 6 panel aynen eklenirse (kapaksız) | 3.250 KB | 4.814 KB ← kabul edilemez |
| **7 panel @1280px + q85** | **960,6 KB** | **1.399,9 KB** |
| Öneri: 01-06 @1280 + 07 @1600 | 1.054,7 KB | 1.542,0 KB |
| Uç durum bugün (4032px girdi, kapaksız) | 6.950 KB | — |

Deponun **canlı emsalinin** desenini (`inference_paper_dilek_hoca.py:710,722` — 1280 px kapak
+ q85) uygulayınca 7 panelin toplamı bugünkü **tek** alandan **%36-42 küçük**. Emsalin ölçülmüş
tavanı (scratch, explain'li 7 görsel = 1,66-1,91 MB) da bunun üstünde.

### ⚠️ DÜZELTME (2026-09-10, doğrudan ölçüldü — kazanç ÖLÇEĞE BAĞLI)

Yukarıdaki satırlar tek girdi oranı üzerinden hesaplanmıştı. Boru hattı iki ölçekte **bizzat
koşturuldu** (`05_FantomTumor.jpeg`, gömülü Python + cv2 4.11, gerçek base64 uzunlukları):

| Girdi | BUGÜN (tek mozaik, kapaksız) | ÖNERİ (7 panel, kapaklı q85) | Fark |
|---|---|---|---|
| **1500 px** (istemcinin çektiği boyut) | 1.973,5 KB | **1.038,8 KB** | **−47%** |
| **338 px** (deponun test görüntüsü) | 287,5 KB | 327,1 KB | **+14%** |

**Kazanç panel sayısından değil, KAPAK+KALİTE'den geliyor.** 338 px'te mozaik (676×1126) zaten
her kapağın altında kaldığı için kapak hiçbir şey kazandırmıyor ve 6 ek panel net bir ekleme
oluyor. Sahibin gerçek fotoğrafı 1500 px olduğu için **karar veren ölçek −47%'lik olan**; küçük
girdide mutlak boyut da 0,3 MB, yani pratikte önemsiz. ⚠️ Plan metninde "her koşulda küçülür"
denmemeli — doğru ifade: **gerçek foto ölçeğinde yarıya iner, küçük girdide %14 büyür.**

Ayrıca ölçülen ikinci bulgu: fantom tespiti, test görüntüsü **500 px üstüne büyütülünce
başarısız** oluyor (`success=False`; 700/900/1100/1300/1500 px'in tamamında, hem cubic hem
lanczos). Bu plan kapsamı dışında ama sahada büyük fotoğrafla tespit kaçırılıyorsa ayrı bir
inceleme konusu — **not edildi, kovalanmadı.**

CPU: `render_all_panels` 53 ms (yatay) / 84 ms (dikey); 6 ek küçültme+encode 27/46 ms.
ONNX inference saniyeler mertebesinde → ek maliyet **<%5**.

**Yanıt boyutu sınırı — net ayrım:** Starlette/FastAPI/uvicorn'da **yanıt** gövdesi için sınır
YOKTUR. `ai_router.py:41-45`'teki 1 MB, MultiPartParser'ın `max_part_size` değeridir; yalnız
**istek** yönünde ve yalnız dosya-olmayan form alanlarına uygulanır, ayrıca `_allow_large_upload`
ile 50 MB'a yükseltilmiş. nginx `client_max_body_size` ayarlanmamış (varsayılan 1m) — o da
**yükleme** yönü; `shrinkForUpload`'ın <1MB hedefinin sebebi tam bu. Yanıt yönünde nginx fazlayı
geçici dosyaya spool eder, kesme yok. Zaman aşımları (istemci 120 s, httpx 180 s, nginx 300 s)
1-2 MB'a yaklaşmıyor bile.

**Gerçek istemci maliyeti ağ değil BELLEK:** 7 base64 `<Image>` aynı anda mount edilirse
RN/Hermes her biri için ayrı decode kopyası tutar (10,6 MP panel ≈ 40 MB ham RGBA).
→ **Yalnız aktif panel render edilir** (ScratchModule zaten böyle yapıyor; maliyet sıfır, ŞART).

---

## 2. Tasarım — tek ortak sahne bileşeni

**`pf/src/components/ui/GorselSahne.tsx` (yeni)** — ScratchModule'ün çalışan çip galerisi
deseninin (`SCRATCH_GALERI` :3338-3348 + `scChipRow`/`scStage` :3568-3582) genelleştirilmesi.
Sıfırdan tasarım değil, **kanıtlanmış deseni taşımak**.

### Sayfa modeli

```
[ Girdi ]  [ 01 Giriş ]  [ 02 Tespit ]  [ 03 Maske ]  [ 04 Tümör ]  [ 05 Koordinat ]  [ 06 Tahmin ]  [ 07 Tam Özet ]
   ↑ her zaman var, HER ZAMAN yerel imageUri'den beslenir (backend'e HİÇ bağımlı değil)
```

- **Girdi sayfası backend'e bağımlı olmadığı için sahibin 1. şikayeti eski backend'de de çözülür.**
- Sonuç panelleri modülün kendi tablosundan gelir; **alanı boş olan panel çip üretmez**
  (ScratchModule `aktifGaleri` filtresi emsali).

### Gezinme (sahibin istediği)

```
 ‹ Önceki görsel        [Girdi] [01] [02] [03] [04] [05] [06] [07]        Sonraki görsel ›
                                      «  4 / 8  »                          [ ⛶ Tam ekran ]
```

- Sol/sağ ok + çip şeridi + sayaç. Sınırlarda **clamp**, sarma YOK (0'da sol ok devre dışı).
- Yeni analiz gelince indeks **sıfırlanır**.

⚠️ **Tasarım kararı — varsayılan sayfa.** Sonuç geldiğinde varsayılan sayfa **Girdi DEĞİL,
birincil sonuç panelidir** (fantomda `04_tumors`, petride `02_yolo_dets`). Sahibin ok mantığı
aynen korunur — sol ok girdiye doğru geri yürür, sağ ok sonuçlara doğru — ama analiz biter
bitmez sonuç ekranda olur. Aksi hâlde "analiz ettim, sonuç iki tık arkada" diye **ters yönde**
bir arıza üretirdik (ScratchModule B4 emsali).

### Okunabilirlik — sahne tavanını aşan kip

Sahnede `⛶ Tam ekran` düğmesi → RN Modal, panel pencerenin tamamını alır + **%100 / %200 / %400
kademeli yakınlaştırma** (yeni npm paketi YOK — kesikli adım, mevcut Modal + hesaplanan stil).
Tam ekran içinde de ileri/geri çalışır; kapanışta seçim sahneye taşınır, sayfa indeksi korunur.

Bu, "yazılar okunmaz"ın **gerçek** cevabıdır: 330 px'lik sahne 700×540 sözleşmesi yüzünden
büyütülemez, ama tam ekran o sözleşmenin dışındadır.

### Oran kilidi

⚠️ **DÜZELTİLDİ (2026-09-10).** İlk yazdığım biçim **hatalıydı** ve üretime girerse tıbbi
sınıf bir hata doğuruyordu:

```ts
// ❌ YANLIŞ — ilk taslakta böyle yazmıştım
kutu = kameraKutusu(onizlemeW, kareOrani(aktifPanel), pencereY, 0.55)
yukseklik = Math.min(useStageHeight(), kutu.h)
```

Yüksekliği kırpıp `kutu.width`'i olduğu gibi bırakmak **oranı yeniden bozar** — bu, tam olarak
`kameraKutusu.ts`'in yasakladığı `aspectRatio + maxHeight` tuzağıdır ve CatOrgan/AI-Pro'da
organ işaretlerinin görüntüyle kaymasına yol açar. Tavan **hesabın içine** girmeli:

```ts
// ✅ DOĞRU — tavan kameraKutusu'nun KENDİ tavanı olur, oran hiç bozulmaz
const icTavan = useStageHeight() - kontrolH - notH;        // kontrol satırı bütçeden DÜŞER
const tavanH  = Math.min(icTavan, Math.round(pencereY * 0.55));
const kutu    = kameraKutusu(olculenKapW, kareOrani(aktifSayfa.boyut, portre), tavanH, 1);
// kameraKutusu: h = min(kapW/oran, tavanH) · w = round(h*oran) → letterbox 0, oran TAM
```

- Oran **panel başına** `image_w/image_h`'ten gelir. ⚠️ Kök tek bir `image_w` **YETMEZ**:
  mozaik `panel_07_combined`'de yeniden ölçekleniyor, oranı girdinin oranı **değil**.
- `kameraKutusu` matematiği **yeniden yazılmaz** — CatOrgan/AI-Pro organ işaretlerinin hizasını
  garanti eden tek kaynak o; ikinci bir hesap = işaret kayması = **tıbbi hata**.
  4. parametre (`tavan`) zaten var; `1` verilerek kendi tavanımız ona devredilir.
- `useStageHeight()` **tavan olarak** korunur → 700×540'ta "Analiz Et kaydırmasız görünür"
  sözleşmesi (S1 adım 7 / aihub-10) regresyon yapmaz.
- ⚠️ **Kontrol satırı bütçeden düşmek zorunda.** Ok + çip + sayaç satırı ~44-74 px yer alır;
  sahneye tam `useStageHeight()` verilirse **toplam** taşar. Ölçüldü: 1600×900'da sahne
  330 → **256 px**, 700×540'ta 243 → **169 px**. Yani sahne görseli bugüne göre %20-25
  **küçülür** — bu bilinçli: sahne artık okuma değil **gezinme** yüzeyi, okuma tam ekranda.
- `aspectRatio` ve `maxHeight` **birlikte kullanılmaz** (kameraKutusu.ts'in kendi yasağı).

### Işık masası: sayısal satırdan tümöre odaklan

Tasarım turundan gelen ve **kabul edilen** fikir. Sayısal sonuç listesindeki her tümör satırı
tıklanabilir (`⌖ Göster`): basıldığında tam ekran açılır, **1:1 kaynak** katına kilitlenir ve
görüntü o tümörün piksel koordinatına kaydırılır.

- Koordinat kaynağı yanıtın kendi alanı: `tumor_regions[i].centroid_px` (+ panel başlık bandı
  ofseti, `panel.h - girdi.h`). Tahmin veya yeniden hesap **yok**.
- Klinik soru *"T1 nerede?"* elle gezinmeden cevaplanır. Bu, "sayıları JSON'dan HTML olarak çiz"
  kararının doğal devamı: **metin okunur, görsel ise konumu gösterir.**
- Aynı mekanizma petride kuyu satırlarına, CatOrgan'da organ satırlarına genişletilebilir.
- ⚠️ Odaklanma **yeni ağ isteği üretmez** (bileşenin 1. değişmezi) — panel zaten yanıtta.

Demoda çalışır durumda: her tümör satırının sağındaki `⌖ Göster`.

### Yakınlaştırma merdiveni: sabit katlar değil, `1:1 kaynak`

Sabit %100/%200/%400 yetmiyor — ölçüldü, 700×540'ta %400 bile 9,2 px'te kalıyor ve pencere
küçüldükçe garanti kayboluyor. Merdivenin son basamağı **kaynak piksele kilitlenmeli**:

| Pencere | Sahne | Gömülü 12 px yazı | Tam ekran ×1 | ×4 | **1:1 kaynak** |
|---|---|---|---|---|---|
| 1600×900 | 192×256 | 1,5 px | 4,5 px | 17,9 px | **12,0 px** |
| 700×540 | 127×169 | 1,0 px | 2,3 px | 9,2 px | **12,0 px** |
| 375×812 | 174×232 | 1,4 px | 2,8 px | 11,2 px | **12,0 px** |
| 900×430 yatay | 121×161 | 1,0 px | 1,6 px | 6,5 px | **12,0 px** |
| 07 mozaik @1600 | 125×256 | 0,5 px | 1,5 px | 5,8 px | **12,0 px** |

Adımlar: `Sığdır` · `2×` · `4×` · `1:1 kaynak` (`k = image_w / kutu.width`). 1:1'i **aşan**
katlar listelenmez; `image_w` yoksa 1:1 çipi hiç görünmez (zarif düşüş).
⚠️ Kenarı **4096 px**'i aşan panelde 1:1 **gizlenir** — düşük-uçlu Android'de GL doku sınırı
(çoğu cihazda 4096) ve OOM riski. Mozaik zaten "özet" sayfası; okuma yolu tek paneldir.

---

## 3. Kapsam — 13 modülün tamamı sınıflandırıldı

| Katman | Modül | Bulgu | Bu turda |
|---|---|---|---|
| **1** | VisionModule (landmark, segmentation, thermal, reticulocytes), Phantom, Petri, KidneyCT, CatOrgan | ternary arızası VAR (5 satır) | Ortak sahne + Girdi sayfası + oran kilidi |
| **2** | Scratch (7 görsel — **emsal**), Histopath (2 XAI, 224 px) | girdi kaybolmuyor; çoklu görsel var | Ortak sahneye göç, sözleşmesi korunarak |
| **3** | PetOwnerAiScreen, CatSound | tek görsel / yalnız XAI | Tam ekran + oran kilidi |
| **4** | Disease, RNA, KidneyDisease | görsel YOK | Kapsam dışı |

**Katman 2'de bulunan ayrı arıza (aynı sınıf, ters yön):** PetOwner "Yeni Fotoğraf" düğmesi
`setImageUri(null)` yapıyor ama **`setResult(null)` YAPMIYOR** (satır 536; diğer 4 çağrı noktası
— 383, 394, 411, 422 — temizliyor) → foto silinince ekranda **girdisiz, bayat FGS sonucu** kalır.
Ayrıca o blob URL'i revoke edilmiyor. Aynı turda kapatılmalı.

**Katman 1'de bulunan iki ek arıza (fantom):**
- "Fantom boyu (cm)" alanı sonuç geldikten sonra değiştirilince sonuç **bayat işaretlenmiyor**
  (ScratchModule'ün `parametreDegisti`/`yenidenGerek` deseni burada yok) → piksel modunda
  üretilmiş mozaik, kutuda "10" yazarken gösterilebilir.
- Stale-yanıt yarışı: `analyze` yalnız zaman aşımı için AbortController kuruyor; **istek-kimliği
  ve `mountedRef` YOK** (ScratchModule `istekRef` :3358 emsali) → geç gelen yanıt yeni girdinin
  sonucu sanılabilir.

---

## 4. Adımlar

### ADIM 1 — Saf kazanç, davranış-nötr (backend + istemci)

- `_encode_jpg_b64`'ün **5 kalite-argümansız** çağrısına `quality=85`
  (ai_router.py:444, 2401, 2494, 2569, 3305 — parametre :277'de **hazır**, kullanılmıyor).
- fantom/petri `imencode`'una (2642, 2819) `quality=85` + **1600 px kapak**.
- **Web yolundaki küçültme boşluğunu kapat**: `shrinkForUpload` eşdeğeri web'de de uygulanır
  (Canvas ile) → girdi boyutu platformdan bağımsız 1500 px olur.

Ölçülen kazanç: segmentasyon 797→358 KB (−55%), termal 286→141 KB, fantom mozaik 1.646→364 KB.
Yan fayda: gömülü↔mikroservis **q95/q85 sapmasını kapatır** (aynı analiz bugün 1,9× farklı boyut).

**Kapı:** AST — "ai_router.py'de kalite argümansız `_encode_jpg_b64` / `imencode('.jpg', ...)`
çağrısı KALMAMALI". Mutasyon: argümanı geri sil → KIRMIZI.

### ADIM 2 — Parite (backend)

- `**_kare_boyutu(...)` → **em_fantom (2686), em_petri (2852), cat_organ (3569)**.
  Bugün 6 çağrı var (545, 2316, 2403, 2496, 2589, 3309); bu 3'ü **yok**.
- `ai_service/app.py`'ye `image_w`/`image_h`: dosyada **hiç yok** (grep 0 eşleşme) →
  landmark/segmentation/thermal/reticulocytes/kidney_ct'nin oran kilidi **GPU profilinde sessizce
  yön varsayılanına düşüyor**. `ai_client.py:52` mikroservis JSON'unu aynen geçirdiği için
  app.py'ye eklenmeyen her alan GPU dağıtımında kaybolur (bu sınıf depoda 2026-08-27/28'de
  **5 kez** ölçüldü).
- `pnp_residual_px` → app.py (router:3573'te var, app.py:785-793'te yok) → arayüz bugün canlıda
  **"PnP undefinedpx"** yazıyor (AiHubScreen.tsx:3879).

**Kapı:** `**_kare_boyutu(` sayacını **>= 9**'a çıkar + uç adlarını **açık allowlist**'e al +
`ai_service/app.py` için **ayrı parite kapısı** (uç başına alan KÜMELERİ karşılaştırılır).
Mutasyon: tek bir uçtan alanı sil → KIRMIZI.

### ADIM 3 — Çoklu-panel sözleşmesi (backend)

fantom/petri yanıtlarına:

```python
"paneller": [{"k": "01_input", "image_base64": ..., "image_w": ..., "image_h": ...}, ...]
```

- **Varsayılan AÇIK, bayraksız.** Bayrak tuzağı ölçüldü: `ai_client.py:47` None alanları atar ve
  FastAPI tanımadığı form alanını **sessizce** düşürür — petri ayarlarında tam bu yaşandı.
  Yük zaten büyümediği için bayrağa gerek yok.
- Kök `image_base64` (07_combined) **KALIR** → eski istemci etkilenmez
  (`test_ai_kare_boyutu.py::test_alan_yalniz_EK_oldugu_icin_geriye_uyumlu` bunu zaten iddia ediyor).
- Panel adı + kapak + kalite **TEK KAYNAK**: `petri_ayar.py` deseninde küçük bir
  `panel_yayin.py`. Yoksa iki uç sürüklenir (bugün 2643 ve 1045 aynı satırı bağımsız yazıyor).
- **AYNI COMMIT'te** `ai_service/app.py:1075` ve `:1147`.

**Kapı (G8):** `TestClient` + monkeypatch'li sahte pipeline (`test_petri_ayar_parametreleri.py::yakala`
deseni — modeller CI'da yüklü değil). `render_panels` 7 anahtarı **farklı shape'li gerçek numpy
dizileriyle** döndürür; her panelin `image_w/image_h`'i **o panelin gerçek shape'iyle birebir**
doğrulanır. Mutasyon: bir paneli yayından çıkar → KIRMIZI.

### ADIM 4 — Arayüz

`GorselSahne.tsx` + oklar (`IconButton`) + çipler (`Chip`) + sayaç + tam ekran/zoom;
**5 ternary kaldırılır**; normalizasyon **zorunlu**:

```ts
const paneller = result?.paneller ?? (result?.image_base64
  ? [{ k: "07_combined", image_base64: result.image_base64 }] : []);
```

Bu yoksa yeni istemci eski backend'de **boş galeri** gösterir (yeni↔eski senaryo B).

### ADIM 5 — Ayrı, küçük PR

Backend'e `GZipMiddleware` (ölçüldü oran 0,73-0,75: 960,8 KB → 699,2 KB). Kazanç **yalnız**
Tauri/doğrudan :8000 yolunda — docker/web'de nginx bunu zaten yapıyor
(Dockerfile.frontend:41-46). Faydalı ama asıl çözüm değil.

---

## 5. Kıracağım mevcut kapılar — bütçe açıkça yazılı

Sahne refaktörü **en az 8** mevcut kapıya dokunuyor. Bunlar **aynı commit'te** güncellenecek;
çoğu yalnız yeni dosya koşturulurken **görünmez** → TAM SÜİT şart.

| Kapı | Bugün | Neden kırılır / çözüm |
|---|---|---|
| `tests/test_responsive_grafik_kapisi.py:90` | `kameraKutusu(onizlemeW` **== 2** | **Planın en net kırılma noktası.** 5-6'ya çıkar; ortak bileşene taşınırsa **0'a düşer**. İki durumda da KIRMIZI. Çıpa ortak bileşene **ve onu KULLANAN modüllere** yeniden pinlenecek (kapının gerekçesi: "saf hesap testleri bileşenin o hesabı KULLANMAYI bırakmasını yakalayamaz"). |
| `tests/test_dokunma_hedefi_kapisi.py:39` | `KALAN_IHLAL = 118` | Yeni ok/çip ham `TouchableOpacity` ile yazılırsa **artar**; Scratch çipleri `Chip`e göçerse **düşer**. → oklar `IconButton` (touch.min), çipler `Chip` (touch.sm). `hitSlop` muafiyet **DEĞİL**. |
| `tests/test_arayuz_yazi_olcegi_kapisi.py:136` | `rf(9\|10)` **== 7** | Sayfa sayacı/panel açıklaması `rf(9)` ile yazılırsa aşar → `typography.small` (11). Zaten hedef "okunmaz yazı" olmasın; küçük punto **çözüm olamaz**. |
| `pf/.../xaiIsiHaritasiBoyut.test.tsx` | XAI64'lü `<Image>` **== 1**; `height !== '100%'` | XAI hem bağımsız blokta hem galeride çizilirse 2 olur. Görselin **kendisi** açık yükseklik/aspectRatio taşımaya devam etmeli (`{%100/%100}` deseni YASAK). |
| `pf/.../xaiKalanA.test.tsx` A1 | Isı haritası etiketi **varsayılanda** ekranda | Isı haritası galeri sayfasına taşınırsa KIRMIZI. → **XAI bağımsız blokta KALIR**, galeri yalnız fantom/petri panellerini taşır (bu, `toBe(1)` kilidiyle de uyumlu). |
| `pf/.../catOrganCanliKalinti.test.tsx` | Canlıya geçişte eski sonucun **hiçbir izi** yok | Galeri sayfaları gizli-ama-**mount** kalırsa eski overlay `<Image>` sayısı > 0. → canlıya geçişte **sayfa indeksi + panel listesi de sıfırlanır**. |
| `pf/.../scratchModule.test.tsx` (9 test) | `testID 'sc-stage'` + 7 çip metni birebir | `source.uri` **doğrudan** o düğümde kalmalı (sarmalanmış alt bileşende değil); "Kapanma" metnini üreten yeni bir düğüm (ör. sayaç "Kapanma 1/7") eklenirse `getAllByText` indeksi kayar. |
| `pf/.../petriGelismisAyarlar.test.tsx` (9 test) | `getByText('Galeriden Seç')` **tekil** | İkinci bir "Galeriden Seç" CTA'sı konursa çoklu-eşleşmeden **atar** → yeni düğmelere farklı metin ("Yeni görüntü seç") ya da yalnız `accessibilityLabel`. |

**Kasten kırılmayanlar:** `useStageHeight.test.tsx` (tavan korunuyor — hook silinirse/imzası
değişirse 5 vaka + aihub-10 sözleşmesi regresyon), `kameraKutusu.test.ts` (matematik yeniden
yazılmıyor; yeni parametre **sona ve opsiyonel**), `test_route_contract.py` (**yeni uç açılmıyor**
— paneller mevcut yanıta biniyor), `test_ai_kare_boyutu.py` (`>= 6` eşiği yükseliyor, yeşil kalır),
`test_ai_zaman_asimi.py` (`aiHataMesaji` sayısı sabit — paneller TEK yanıtta geldiği sürece
yeni catch yolu eklenmiyor), `aiHubOtonomOnayKapisi.test.tsx` (sayfa geçişi ağ çağrısı üretmez).

⚠️ `test_ai_kare_boyutu.py`'de `"imageW" == 2` **TAM** sayaçtır → yeni bir `ai_vision` WS yayını
**EKLENMEYECEK**.

---

## 6. Yeni kapılar (13) — hepsi mutasyonla kanıtlanacak

| # | Ne ölçer | Mutasyon |
|---|---|---|
| **G1** | Girdi sonuç gelince erişilebilir kalır: 5 modülde akış sürülür, "Girdi" sayfasında `source.uri` **tam olarak** yerel uri; `fetch` sayısı DEĞİŞMEZ | sahneyi eski ternary'ye çevir → KIRMIZI |
| **G2** | Oran görüntüye uyar, letterbox olmaz: `fireEvent 'layout'` ile 900 px genişlik verilir; kutu w/h ≈ aktif panelin oranı (±%1); çip değişince oran DEĞİŞİR | oran kilidini sabit yüksekliğe çevir → KIRMIZI |
| **G3** | Gezinme sınırlarda clamp (sarma YOK), sayaç doğru artar, **varsayılan sayfa birincil sonuç**, yeni analizde indeks sıfırlanır | clamp'i `(i+1)%n` yap → sarma → KIRMIZI |
| **G4** | 700×540'ta kutu yüksekliği <= 243 **VE** "Analiz Başlat" hâlâ render (kaydırma yok) | `Math.min(sahneH, ...)` tavanını kaldır → KIRMIZI |
| **G5** | Backend panel göndermezse **zarif düşüş**: 2 sayfa, `undefined` uri yok, çökme yok, **yanıltıcı uyarı basılmaz** | boş-alan filtresini kaldır → `base64:undefined` → KIRMIZI |
| **G6** | Tam ekran açılır-kapanır, aynı uri, kapanışta **sayfa indeksi korunur**; %200'de sayısal boyut 2× | `visible={true}` sabitle → KIRMIZI |
| **G7** | Isı haritası **varsayılan görünümde** kalır ve XAI'li `<Image>` TAM 1 | XAI'yi galeri sayfasına taşı → KIRMIZI (mevcut A1 de kırılır) |
| **G8** | Python: `paneller` 7 öğe, panel başına gerçek `image_w/image_h`, kök `image_base64` korunur, **iki uç senkron** | bir paneli yayından çıkar → KIRMIZI |
| **G9** | Sayaç bütçesi (§5) bilinçli güncellendi + çıpalar yeniden pinlendi | — (§5 tablosu) |
| **G10** | Organ işareti hizası: taban görsel ile overlay **aynı sayısal kutuyu** alır | overlay'e `{%100/%100}` ver, kabı oran-kilitsiz yap → KIRMIZI |
| **G11** | **TOPLAM yükseklik** (sahne + kontrol + not) <= tavan | `- kontrolH - notH` çıkarmasını sil → KIRMIZI |
| **G12** | Yakınlaştırma **kaynak piksele kilitli**: `image_w > kutu.w` olan her panelde 1:1 adımı VAR, hiçbir adım 1:1'i AŞMAZ, kenar > 4096 px'te 1:1 GİZLİ | adımları sabit `[1,2,4]` yap → KIRMIZI |
| **G13** | `Chip`'in varsayılan `accessibilityRole`'ü **'button' KALIR** | varsayılanı `'tab'` yap → KIRMIZI (mevcut ~11 çip satırı yanlış rolle duyurulur) |

⚠️ **G11 neden ayrı bir kapı:** G4 yalnız **kutu** yüksekliğini ölçüyor (<=243). Kontrol satırı
eklendiği için G4, toplam taşarken **YEŞİL kalır**. Bu tam olarak bu turda demo üzerinde
gözlendi: sahneye tam `useStageHeight()` verilince 700×540'ta içerik taştı ve oklar kırpıldı.

### Sayaç çıpasının yeniden pinlenmesi (§5'in en net kırılma noktası, çözümü)

`test_responsive_grafik_kapisi.py`'deki `kameraKutusu(onizlemeW` == 2 sayacı, hesap ortak
bileşene taşınınca **0'a düşer**. Doğru yeniden pinleme dört parçalı:

1. `pf/src/components/ui/GorselSahne.tsx` içinde `kameraKutusu(` == **1** (tek kaynak),
2. `AiHubScreen.tsx`'te `<GorselSahne` == **TAM N** (katman 1+2 modül sayısı),
3. `PetOwnerAiScreen.tsx`'te `<GorselSahne` == **1**,
4. `AiProPanel.tsx`'in `kameraKutusu(kutuW` çıpası **DOKUNULMADAN** kalır.

Ayrıca aynı dosyadaki `aspectRatio` yasağı `GorselSahne.tsx`'e de genişletilmeli — yeni dosya
kapının kör noktasıdır. Mutasyon: bileşende `aspectRatio` kullan → KIRMIZI.

### Panel anahtar eşlemesinde Türkçe collation tuzağı

Fantom ve petri panel adları farklı (`02_phantom_detect` ↔ `02_yolo_dets`). Eşleme sözlüğünde
anahtar karşılaştırması **büyük/küçük harf duyarlı** olmalı ve `toLowerCase()`
**KULLANILMAMALI** — Türkçe I/İ/ı collation tuzağı yeni bir sessiz "panel yok" arızası üretir
(bkz. `arama_katla` dersi). Anahtarlar sabit ASCII literal olarak eşleştirilir.

### ⚠️ Ölçülen sahte-yeşil riski

**Bugün hiçbir test `onLayout` ateşlemiyor** → `onizlemeW = 0` → oran-kilitli dal **hiç
koşmuyor**; `{height: sahneH}` dalını silen bir mutasyon bile mevcut süitte yeşil kalabilir.
Her oran kapısı `fireEvent(node, 'layout', { nativeEvent: { layout: { width, height } } })` ile
ölçülen genişliği **kendi** vermek zorunda. (RTL bu olayı destekliyor — doğrulandı.)

### Mutasyon disiplini (memory kuralları)

Sıra zorunlu: kapıyı yaz → YEŞİL gör → **üretim satırını** mutasyona uğrat → KIRMIZI olduğunu
**kanıtla (çıktıyı kaydet)** → geri al → tekrar YEŞİL. Kanıt olmadan kapı "yazıldı" sayılmaz.

- Mutasyonu **ASLA `git checkout` ile geri alma** (commit'lenmemiş gerçek düzeltmeyi de siler).
  Dosyayı önce scratchpad'e kopyala.
- Çıpa **yoruma/dokümana değil üretim koduna**, tercihen **AST**'ye pinlenir — bu depoda düz-metin
  araması kendi açıklama yorumunu bulup mutasyonu yeşil bıraktı (bu hata bu depoda **3 kez** tekrarlandı).
- **Gevşek eşik yasak**: `>= N` bir modülün sessizce kopmasına izin verir. Yeni sayaçlar **TAM**.
- **TAM SÜİT**: `pf/` içinde `npm test` VE `guii/` içinde `../python.exe -m pytest tests -q`.

---

## 7. Uygulanmayacaklar (ve neden)

- **Lazy tek-panel ucu** (`GET /api/ai/vision/em_fantom/panel/{ad}`): uç **auth-muaf** → cache
  anahtarı tahmin edilirse **başka hastanın paneli** döner (PII); `ctx`'i istek ötesinde tutmak
  yeni yaşam döngüsü + AI Pro'nun ONNX belleğiyle yarış; fetch sayan 2 kapıyı kırar; 6 ek
  gidiş-dönüş hotspot'ta hissedilir. Ayrıca `test_route_contract.py` sayacını kırar.
- **Disk/URL yolu** (`save_all_panels` hazır olsa da): "bellek-içi base64, disk YOK" kararına ve
  "kayıtlar makinede / şifreli tek kaynak" ilkesine aykırı; **şifresiz kalıcı iz** ekler.
- **q85 altı kalite / 1024 px altı kapak**: panele gömülü yazı 1 px kalınlıkta
  (`Style.font_small = max(0,30; s*0,45)`), q80 altında blok/ringing artefaktına girer →
  "yazılar okunmaz" hedefiyle **doğrudan** çelişir. q85 **taban**.
- **07_combined'ı yükten çıkarma**: eski istemciler `image_base64`'e bağlı → geriye-uyum kırılır.
  Yerine 1600 px'e kapanır; çip galerisi mozaiği zaten gereksiz kılar.
- **Petri YOLO `imgsz` 640**: **dokunulmaz** (ONNX girdisi sabit). Paneller yalnız render'dan gelir.
- **AI uçlarının auth muafiyeti**: korunur (P0 sanıp geri konmaz).

---

## 8. Onay gereken tek karar

Panel yükünün **varsayılan açık** olması (§ADIM 3). Ölçüm bunun yükü küçülttüğünü gösteriyor
(1.646 → 1.055 KB), bayrak ise sessiz-ölü-alan tuzağı taşıyor. Yine de bu, her fantom/petri
analizinde tel üstünde 7 görsel demek.

**Alternatif** (istenirse): `paneller` yalnız kapak+kalite düzeltmesiyle gönderilir ama istemci
varsayılan olarak tek panel gösterir — galeri kullanıcı çipe basınca dolar. Yük aynı, algı farklı.

---

**Ölçüm kaynağı:** 12 paralel envanter ajanı (13 modül + backend yükü + test kapıları),
2026-09-09 23:00-23:30. Tasarım/hakem turu oturum limitine takıldı; sentez elle yapıldı ve
plandaki tüm sayılar bu turda **yeniden doğrulandı** (5 ternary satırı, 4 sayaç kapısı,
`_encode_jpg_b64` 5 argümansız çağrı, `ai_service`'te `image_w` 0 eşleşme, `_kare_boyutu`
6 çağrı, 7 panel anahtarı × 2 modül, web küçültme boşluğu).

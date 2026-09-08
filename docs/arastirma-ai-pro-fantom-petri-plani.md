# Araştırma Modu AI Pro — Fantom + Petri Entegrasyon Planı (2026-09-08)

> **DURUM (2026-09-08): PLAN — uygulama başlamadı.** Sahip isteği: AI Pro kapalı döngüsünde
> araştırma modunda (userMode `researcher`) KEDİ yerine İKİ model olsun — **Fantom Tümör**
> (`inference_em_fantom` + `phantom_cv`) ve **Petri Kuyu** (`inference_em_petri` + `petri_cv`);
> kedi (`em_kedi` + `cat_organ`) yalnız veteriner modunda kalsın; akış kod bilmeyen bir
> araştırmacı için kullanıcı dostu olsun.
>
> **Keşif yöntemi:** 16 ajanlı workflow (7 paralel derin okuyucu → 3 bağımsız tasarımcı → 2 hakem →
> 4 eleştirmen: güvenlik/regresyon, kod uygunluğu, UX, tamlık) + sahibin oturumundaki bağımsız
> doğrulama. 181 bulgu, 129 bağlantı noktası, 51 eleştiri (3 P0). Satır numaraları commit
> `27c0743` (dal `production-hardening`) içindir; uygulama öncesi çıpalar fonksiyon adına pinlenir.
>
> **Planın ortaya çıkardığı ÜÇ MEVCUT KUSUR (kaynakta doğrulandı, bu iş başlamadan ayrı commit'lerle kapatılır):**
> 1. `servers/ai_router.py:1187` — sunucu-kameralı **seans** döngüsü `_localize_organ` sonucunu 7 isme açıyor,
>    fonksiyon 2026-08-26'dan beri 8'li tuple döndürüyor → her lokalizasyon `ValueError` ile yutuluyor,
>    bobin **hiç sürülmüyor**, 3. turda "hedef kaybı" STOP'u yayınlanıyor. Hazırlık (1016) ve mobil (1796)
>    yolları `*l_ek` ile doğru. Mevcut testler 6'lı/7'li sahte tuple kullandığı için kusuru maskeliyor.
> 2. `servers/ai_router.py:1696-1705` — `/api/ai/pro/hazirlik/baslat` **aktif seans sürerken** `_ai_organ_id`,
>    `_ai_relocalize` ve cache `localized=False` yazımlarını kilit ve aktiflik kontrolünden ÖNCE, sahiplik
>    (`_ai_kare_yabanci`) kontrolü OLMADAN yapıyor; sonra "Seans zaten aktif" ile sessiz başarı dönüyor.
>    Onaylı organ yerine başka organa enerji yönlendirilebilir (`/organ` ucunda 403 kapısı var, burada yok).
> 3. `servers/jeton.py:294` — serbest listede `/api/ai/pro/frame` var, gerçek rota `/api/ai/ai_pro/frame`
>    (`test_route_contract.py:22`) → ölü girdi; `tests/test_jeton_gate.py:93` ölü yolu doğruluyor.
>    FREE_MODE=true gizliyor; ücretlendirme açılırsa kare başına 1 jeton.

---

## 0. Yönetici Özeti

- **Güvenlik iskeleti model-bağımsız, kediye bağlılık beş noktada toplu.** Hazırlık → öneri → onay → seans
  durum makinesi, kare sahipliği, hedef-kaybı STOP, E-stop teardown ve 7 bobin per-coil sürüş
  (`_drive_coils_ai_pro`) hiç değişmez. Kediye bağlı kod `servers/ai_router.py`'de: yükleyici çifti
  (690-714), lokalizer (717-828), EM tahmin (831-885), organ beyaz listesi `(0..6)` dört yerde
  (1397, 1577, 1666, 1699) ve `_ORGAN_NAMES` metinleri; frontend'de `AiProPanel.tsx` ORGANS + hayvan metinleri.
- **Mimari karar: "Hedef Sağlayıcı" arayüzü.** Kedi sağlayıcısı mevcut fonksiyonları aynen sarar (13+ testin
  monkeypatch/regex çıpaları korunur); fantom ve petri sağlayıcıları yeni `servers/ai_pro_hedef.py`'de
  yaşar ve `PhantomCvPipeline`/`PetriCvPipeline` + `PhantomPredictor`/`PetriPredictor`'ı yalnız ÇAĞIRIR
  (ai_hub'a kopya yok; ai_hub import'ları fonksiyon içinde — PYZ koruma kapısı).
- **Yeni rota YOK.** Model seçimi mevcut payload'lara `model: 'kedi'|'fantom'|'petri'` alanı olarak gelir,
  onay mührüne (`specs.model`) yazılır, `/start` onu MÜHÜRDEN okur (gövdedeki yok sayılır). Route-contract
  sabit sayaç 98 ve auth-muafiyet prefix'leri değişmez; "fantom öner → kedi başlat" yapısal olarak imkânsız.
- **Frontend: tek panel, mod-farkındalı.** `ControlScreen` profili okur ve `AiProPanel`'e `hedefKumesi`
  prop'u geçer (panele `useUserMode` sokulmaz → 5 jest dosyasına mock gerekmez). Araştırmacı 5 adımlı
  sihirbaz görür (Model kartı → Kamera → Kare üstünde hedef seçimi → Doz özeti → Onay/Seans); veteriner
  görünümü ve kedi metin bloğu BİREBİR kalır. Kedi araştırmacıda, fantom/petri veterinerde hiç görünmez.
- **Modeller uyumlu ama üç tuzak var.** Üç EM modeli aynı 6 girdiyi alır ve aynı D1-7/P1-7 üretir; ancak
  (a) E anahtarı farklı (`result_E` vs `result_E_healthy/cancer/avg` → adaptörsüz e_field sessizce 0),
  (b) `organ_id` anlamı farklı (kedi organ 0-6; fantom/petri doku sınıfı 0=sağlıklı, 1=kanser),
  (c) kedi `_mm` ×10 dönüşümü fantom/petri'nin zaten mm olan koordinatına uygulanırsa 10× hata.
- **En büyük gerçek risk: koordinat çerçevesi.** `phantom_cv`/`petri_cv` `coord_transform.py` ArUco modunda
  rotasyonsuz (`ray_cabin = ray_marker`) + Z=0 düzlem kesişimi kullanır; kedi hattı kabin-merkezli PnP.
  EM modele "aynı çerçevede x,y,z" verildiği KANITLANMAMIŞ; fantom eğitim aralığı çok dar
  (x∈[−56,6; −30,6] mm). Bu yüzden fantom/petri sürüşü **tezgâh doğrulaması geçilene kadar backend'de
  bayrak arkasında** (`PEMF_ARASTIRMA_AIPRO`), coord_transform yaması ise **hoca kararı olmadan yapılmaz**;
  önce mevcut dönüşümün ne ürettiğini ölçen karakterizasyon testi yazılır.
- **Paketleme hazır.** Fantom/petri ağırlıkları (BiLSTM 60 MB, BaggingRegressor 239 MB, yolo11m-seg 90 MB)
  zaten `research.zip`'te; yeni pip bağımlılığı yok → deps sha ve research sha değişmez, model indirme sıfır.
  Hazırlık kapısı üç EM modelini tanır ama petri YOLO ağırlığını ve CV paketlerini ölçmez (eklenecek).
- **Yayın kadansı bölünür:** Faz 0+1 (kusur düzeltmeleri + backend iskeleti, UI'sız) → app 1.9.44;
  Faz 2+3 (fantom/petri + sihirbaz) → app 1.9.45; mobil 2.3.34 ayrı karar (#15/#21).

---

## 1. Bugünkü Durum (kod-kanıtlı)

### 1.1 Araştırmacı bugün ne görüyor
`pf/src/config/access.ts:34` researcher'a `control` rotasını verir (2026-08-06 sahip kararı); `ControlScreen.tsx:739-743`
"AI Pro" sekmesinde `AiProPanel`'i profil okumadan monte eder → araştırmacı **kedi** AI Pro'sunu görür ve
em_kedi ile seans başlatabilir. Araştırma-yalnız kurulumda em_kedi yalnız `vet.zip`'te olduğu için hazırlık
"AI modeli yüklenemedi" ile biter: araştırmacı AI Pro'yu fiilen hiç kullanamaz.

### 1.2 Kediye bağlı noktalar (backend)

| Yer (`servers/ai_router.py`) | Ne | Fantom/petri için gereken |
|---|---|---|
| 690-714 `_get_or_load_kedi` / `_get_or_load_catorgan` | yükleyici çifti; hazırlık 977-978 ve seans 1121-1122 koşulsuz çağırır | sağlayıcı `load()`; analiz uçlarındaki `_load_em_fantom` (2192-2205) / `_load_em_petri` (2309-2337) kapanışları modül fonksiyonuna TAŞINIR ve paylaşılır |
| 717-748 `_extract_organ_target`, 763-828 `_localize_organ*` | cat_organ dict → 8'li tuple; `_mm` ×10 cm→mm ±300 klemp; `kedi_var` | sağlayıcı `localize(frame, hedef_id)` aynı 8'li tuple; fantom/petri mm'dir, ×10 YOK |
| 831-885 `_predict_and_drive*` | `KediPredictor.predict`, `delegate_json_sync('em_kedi')`, `result_E`, `_AI_ACHIEVED_B=0.001`, `_AI_DUTY_SUM=1.5`, D clip 0..0.50 yalnız cpu/gpu içinde | sağlayıcı `predict()`; E eşlemesi sınıfa göre; clip TEK yere (zarf) |
| 1397, 1577, 1666, 1699 | `if oid not in (0,1,2,3,4,5,6)` ×4 | `provider.target_ids` tek kaynak; literal SIFIR kez geçer (yapısal kapı) |
| 647-659 `_ORGAN_NAMES` | mode dizesi, WS `organName`, status, 409 ipucu | `provider.target_name(id)`, `provider.hint(...)`; mode `f"AI Pro · {title}"` ('AI' öneki korunur — `startswith('AI')` kontrolleri 605, 1357, 1651, 1836, api_server 2790) |
| 1441-1448 | propose XAI `ai_hub.em_kedi` doğrudan import | `provider.xai_sensitivity(...)`; zarif düşüş korunur |
| 667-686 `_ai_organ_cache` | model kimliği yok; tazelik organ_id + 120 sn | `model` anahtarı; tazelik `c['model'] == aktif`; `kedi_var` anahtar adı KALIR ("özne kadrajda") |
| 1365-1378 payload'lar, 1451-1465 specs, 1555-1583 start | model alanı yok; start yalnız organ/süre mühürden | `model` alanı; `specs['model']`; start mühürden okur |

### 1.3 Modeller ve lokalizasyon hatları

| | Kedi | Fantom | Petri |
|---|---|---|---|
| Lokalizasyon | `CatOrganPredictor.predict(dosya)` YOLOseg+pose+PnP, 1-4 s/kare | `PhantomCvPipeline.process_image(ndarray)` klasik HSV CV, ~0,1 s (README) | `PetriCvPipeline.process_image(ndarray)` YOLO11m-seg + HSV, CPU **1-3 s (tahmin, ölçülmedi)** |
| Çıktı | `organs{id: coord_cabin_cm, reliability}` | `tumor_regions[RegionPrediction]`: `organ_id` 0/1, `centroid_px`, `centroid_cabin_mm`, D[7], P[7], E_cancer; **reliability YOK** | `wells[WellPrediction]`: `well_id 'W1..'` (kareler arası KARARSIZ), `organ_id`, `reliability=conf×solidity`, `centroid_cabin_mm` |
| Kalibrasyon | ArUco/`coord_3d_cm` | `method`: `aruco_pnp` / `phantom_length` / `pixel` (mm_per_px=1, z=0) | `aruco_pnp` / `petri_diameter` / `pixel` |
| Özne yok | `RuntimeError('segmentasyon:')` → `kedi_var=False` | `error='phantom_not_detected'` (istisna değil) | `yolo_no_well_detected`; makullik reddi `not_a_petri_plate` (fotoğraf ucunda 422) |
| EM model | `KediPredictor` ORGAN_IDS 0-6, `result_E` | `PhantomPredictor` ORGAN_IDS [0,1], `result_E_healthy/cancer/avg` | `PetriPredictor` ORGAN_IDS [0,1], aynı; **eğitimde organ_id sabit 0** → kanser=1 ekstrapolasyon |
| Ağırlık | `vet.zip` em_kedi 60 MB | `research.zip` 60 MB | `research.zip` 239 MB + YOLO 90 MB |

### 1.4 Frontend kediye bağlı noktalar (`pf/src/components/domain/AiProPanel.tsx`)
ORGANS sabiti (30-33), organId state (153), payload gövdeleri (336, 384, 425, 550, 576), `asamaMetni` 4 dallı
hayvan metni (704-720, **kaynak-regex kapısı** `tests/test_ai_pro_asamali_akis.py:203-209, 353-383` bu bloğu
ve 'Hayvan aranıyor'/'catDetected' literal'lerini ister), not metni "KEDİYE doğrultun" (736-740), 120 sn tavan
metni (470-475), 'Hasta seçilmedi' diyaloğu (284-291), Metric 'Organ' + cat_organ güven dökümü (792-811),
organ çipleri (828-843). Onay modalı `AiSpecApprovalModal.tsx`: 'Organ', 'E (öngörü)', XAI etiketi 'organ
seçimi'; `meta.x_mm/y_mm/z_mm` tanımlı ama çizilmiyor (37-39). Mobil dal `/hazirlik/baslat` çağırmaz:
`/calibrate {client_id}` + 1500 ms kare → `/ai/ai_pro/frame` (307-318, 592-639).

---

## 2. Hedef Deneyim — Araştırmacı Sihirbazı

Sekme adı **"AI Pro"** kalır; bölüm başlığı araştırmacıda **"AI Pro — Fantom / Petri Kapalı-Döngü"**. Üstte
adım göstergesi (1/5 … 5/5, a11y "Adım 2 / 5: Kamera") ve her adımda **Geri**. ACİL DURDUR sekme çubuğunun
üstünde aynen. Giriş cümlesi bir iddia değil KURAL olarak yazılır:
*"Bu ekran deney hedefini kamerayla bulur, 7 bobin için doz önerir ve SİZ onaylamadan hiçbir bobini çalıştırmaz."*

| Adım | Ekran | Backend |
|---|---|---|
| **1 · Model** | İki kart: **🎯 Fantom Tümör** "Silikon fantomdaki mavi tümör odaklarını bulur; odağa doz önerir." · **🧫 Petri Kuyu** "Petri plakasındaki kuyuları bulur; kanserli kuyuya doz önerir." Kartta hazır rozeti: "Model kurulu ✓" / "Araştırma model paketi bu cihazda kurulu değil" (+ gerçek kurulum yolu, karar #18) / "Deneysel — tezgâh doğrulaması bekleniyor" (bayrak kapalıysa, kart pasif). Kart altında **Seans süresi (dk)** (varsayılan 20, 1-120) ve — karar #2 evetse — **"Sağlıklı bölgeye kontrol dozu vermeye izin ver"** anahtarı (kapalı varsayılan). Seans/hazırlık sürerken kartlar kilitli: "Seans sürerken model değiştirilemez — önce durdurun". | `GET /api/ai/hazirlik` (kart ekranı açılınca 1 kez, poll yok; 401/402'de "durum bilinmiyor") |
| **2 · Kamera** | "Hazırlığı Başlat" → web: sunucu kamerası önizlemesi; mobil: telefon kamerası (karar #15). Şerit metinleri (hazırlık aşaması `hazirlikAsama`): "Model hazırlanıyor… (ilk açılışta 10 sn sürebilir)" → "🔎 Fantom aranıyor… fantomu tepsinin ortasına alın, kabin işareti kadrajda olsun" / "🔎 Petri plakası aranıyor… plakayı tepsiye düz yerleştirin". 45 sn ipucu: "Bulunamıyor: kabin ışığını artırın, fantomu/plakayı tepsinin ortasına alın, işaret üzerinde parlama olmasın." 120 sn: "Hedef 2 dakikadır bulunamadı; kamera durduruldu. Yerleşimi ve ışığı düzenleyip Hazırlığı yeniden başlatın." Geri = `/hazirlik/durdur` + model sıfırla. | `POST /ai/pro/hazirlik/baslat {model, organ_id:0, client_id}` (web) · `POST /ai/pro/calibrate {model, client_id}` + kareler (mobil) |
| **3 · Hedef** | Kare üstünde tıklanabilir halkalar (`targets[]`): Fantom → "Tümör 1", "Tümör 2" (dolu halka + ✕), "Sağlıklı doku" (kesikli, yalnız izin verildiyse); Petri → "Kuyu 3 · Kanserli", "Kuyu 5 · Sağlıklı" (**kalıcı kimlik**, `well_id` yerine). Varsayılan otomatik seçim: en büyük tümör / en yüksek güvenli kanserli kuyu; etiket "otomatik seçildi". Her halka `accessibilityRole="button"`, `accessibilityState={{selected, disabled}}`, label "Hedef 2 / 4: Kanserli kuyu, güven %82, otomatik seçildi". Halkalar çakışırsa kare altında aynı hedeflerin liste görünümü (≥44 px satırlar) ZORUNLU yedek. Kalibrasyon rozeti sade dille: "3B konum: kabin işaretiyle doğrulandı ✓" / "Konum ölçülemedi — kabin işareti görünmüyor". | `POST /ai/pro/organ {model, organ_id: hedef_id, client_id}` |
| **4 · Doz özeti ve onay** | Hedef kilitlenince öneri otomatik istenir (web: ilk kararlı lokalizasyonda; mobil: ardışık 2 ölçümde — şerit metinleri platforma göre: "Hedef kilitlendi · öneri hesaplanıyor…" / "Hedef görüldü · ikinci ölçüm bekleniyor (1/2)"). Onay modalı: başlık "AI Seans Önerisi — Fantom Tümör · Tümör 1" + alt satır **"Araştırma amaçlı model tahmini"**; Meta: **Hedef** (Organ yerine), **Konum (mm)** x/y/z, Süre, Sürülen bobin 7/7, **Tahmini alan (göreli, birimsiz): hedefte 0,13 · çevrede 0,06** (oran yalnız çevre > 0,01 ise), 3B konum rozeti, OOD satırı "Konum model eğitim aralığı dışında olabilir — sonuç araştırma amaçlıdır" (meta.ood), petri için "Kanserli/sağlıklı ayrımı bu modelde sınırlı doğrulanmıştır"; Bobin/Duty/Faz tablosu (gösterilen = sürülen, bkz. Faz 1 clip); XAI satırı ("dozu en çok belirleyen: konum / doku tipi"). Düğmeler: "Onayla ve Başlat" (önce `/approve`, sonra `/start`) · "Reddet (gerekçe zorunlu)". | `POST /ai/pro/propose {model, organ_id, duration_minutes}` → `approve` → `start {proposal_id, client_id}` |
| **5 · Seans** | Kare + seçili hedef halkası, "Kalan 18:42", per-coil tablo, canlı E barı ("E alanı (hedefte, canlı)"), güven şeridi, "son görülme 4 sn önce". Hedef kaybı: **"Hedef ~30 sn'dir görülmüyor — bobinler durduruldu. Fantomu/plakayı yerine koyun; hedef yeniden görülünce sürüş kendiliğinden devam eder. Bitirmek için AI Pro'yu Durdur."** (kod: 3 lokalizasyon turu × 10 sn, seans bitmez). Bitiş: "Seans tamamlandı · Seans Geçmişi'ne kaydedildi (AI Pro · Fantom Tümör · Tümör 1)". | `GET /ai/pro/status` 3 sn, WS `ai_vision`, `POST /ai/pro/stop` |

**Veteriner modu:** ekran, metinler, organ çipleri, "Hayvan aranıyor…" şeridi BİREBİR bugünkü gibi; payload'lara
`model:'kedi'` sessizce eklenir; fantom/petri kartları görünmez. **Evcil hayvan sahibi:** AI Pro yok (değişmez).

### 2.1 Hata metinleri (sınıf → eylem; ham teknik metin ASLA)

| Sınıf (`_ai_hazirlik_hata.kod`) | Metin |
|---|---|
| `kamera` | "Kamera açılamadı — kabloyu ve başka bir uygulamanın kamerayı kullanmadığını kontrol edin." |
| `model_paketi` | "Araştırma model paketi bu cihazda kurulu değil — {karar #18 yolu}." (mobilde: "Bu cihazın sunucusunda araştırma paketi yok.") |
| `model_yukleme` | "Model yüklenemedi ({model adı}). Uygulamayı yeniden başlatıp tekrar deneyin." (istisna metni yalnız log'a) |
| `zaman_asimi` | 120 sn metni (yukarıda) |
| Öneri 409 (hedef yok) | sağlayıcı `hint()`: "Kadrajda petri plakası görünmüyor — plakayı tepsiye düz yerleştirin, kamera tepeden tam kadraja alsın." / "Fantom görünmüyor — fantomu tepsinin ortasına alın." |
| Öneri 409 (konum ölçülemedi) | "Konum ölçülemedi — kabin işareti (arka duvar) kadrajda değil; kamera açısını kontrol edin." |
| Öneri 409 (bayrak kapalı) | "Araştırma modeli tezgâh doğrulaması bekliyor — bu sürümde yalnız görüntüleme yapılabilir." |
| 422 model/hedef | "Bu hedef seçili model için geçerli değil — Adım 1'e dönüp modeli yeniden seçin." |
| Seans sürerken model/hedef değişimi | 409 "Seans sürerken hedef/model değiştirilemez — önce durdurun." |

Kapı: hata metinlerinde `VideoCapture`, `Traceback`, `Error`, `PEMF_AI_`, `yükle`, `modül`, `Ayarlar → Model paketleri`
geçmez (kaynak-regex + birim test). Petri makullik reddinin ölçüm ayrıntısı (dairesellik/güven) şeride değil
`guvenDokumu`ya gider.

### 2.2 Boş durum matrisi

| Durum | Metin | Beklenen |
|---|---|---|
| Özne yok | "Fantom/plaka görünmüyor" + yerleşim ipucu | öneri gelmez, 45/120 sn sayaçları işler |
| Fantom var, mavi odak yok | "Fantom görüldü, işaretli tümör odağı yok — bu fantomda mavi işaret yoksa Fantom modeli kullanılamaz." | öneri gelmez |
| Plaka var, tüm kuyular sağlıklı | "Plakada kanserli kuyu bulunamadı — yalnız sağlıklı kuyular var; kontrol dozu için Adım 1'de izin verin." | öneri gelmez |
| Hedef var, konum ölçülemedi | "Hedef bulundu, konum ölçülemedi (kabin işareti yok)." | öneri 409 |

---

## 3. Mimari

### 3.1 Hedef Sağlayıcı (backend)

```
istemci payload {model}  ──►  /hazirlik/baslat | /calibrate | /organ | /propose
                                   │  (aktif seans/hazırlık varken farklı model → 409)
                                   ▼
                       _ai_hedef_modeli ('kedi'|'fantom'|'petri', _ai_loop_lock altında)
                                   │
        _localize_organ(frame,id) ─┴─► saglayici.localize(frame,id) → 8'li tuple (localized,x,y,z,rel,overlay,ozne_var,dokum)
        _predict_and_drive(x,y,z,id) ─► saglayici.predict(x,y,z,id) → (D7,P7,e_field)  ── clip 0..0.50 (zarf, TEK yer)
                                   │
        /propose → ai_approval.create(specs={..., model, target_label, e_cancer?, e_healthy?}, meta={..., method, ood, ...})
        /start   → model = _spec['model']  (gövdedeki model YOK SAYILIR)  → start_ai_session(..., f"AI Pro · {title}")
```

`servers/ai_pro_hedef.py` (yeni):

```python
class HedefSaglayici(Protocol):
    ad: str                 # 'kedi' | 'fantom' | 'petri'
    title: str              # 'Kedi Organ' | 'Fantom Tümör' | 'Petri Kuyu'
    subject_label: str      # 'hayvan' | 'fantom' | 'petri plakası'
    target_ids: Collection[int]   # kedi range(0,7); fantom/petri range(0,9) (0 = otomatik)
    varsayilan_hedef: int
    achieved_B: float; duty_sum: float      # kedi 0.001/1.5 ; fantom/petri cfg 0.001/2.4 (karar #5)
    join_timeout_s: float                   # kedi 6 ; petri ≥10 (ölçüme göre)
    def load(self) -> None
    def localize(self, frame_bgr, target_id) -> tuple  # 8'li, kedi ile birebir
    def predict(self, x_mm, y_mm, z_mm, target_id) -> tuple[list[float], list[float], float]
    def target_name(self, target_id) -> str
    def targets_snapshot(self) -> list[HedefAdayi]     # kare üstü adaylar (kedi: [])
    def hint(self, subject_present: bool, target_name: str) -> str
    def xai_sensitivity(self, x, y, z, target_id) -> list | None
    def son_lokalizasyon_meta(self) -> dict            # method, mm_per_px, ood, e_cancer, e_healthy
```

- **KediSaglayici** ai_router'daki `_get_or_load_kedi/_get_or_load_catorgan/_localize_organ_cpu/_gpu/_predict_and_drive_cpu/_gpu`
  fonksiyonlarına GEÇ-BAĞLI delegasyon yapar (testlerin monkeypatch'i etkili kalır). Kedi gövdeleri DEĞİŞMEZ.
- **FantomSaglayici / PetriSaglayici**: `load()` → `_get_or_load_model('em_fantom_cv' | 'em_petri_cv')` (analiz
  uçlarıyla AYNI önbellek; 239 MB petri ONNX iki kez yüklenmez). `localize()` her karede pipeline'ı hafif
  kurar ve **önbellekli predictor/YOLO'yu ENJEKTE eder** (`pl._predictor = cache['predictor']`, petri
  `pl.yolo = cache['yolo']`; aksi hâlde her karede 60-90 MB model yeniden açılır — `pipeline.py:121-124`);
  `manual_fallback=False` ZORUNLU (cv2 penceresi headless serviste kilitlenir); `process_image(frame,
  achieved_B=..., duty_sum=...)` keyword ile.
- **Hedef takibi**: ilk tespitte kalıcı kimlik (Tümör 1..n / Kuyu 1..n) merkez-yakınlık eşlemesiyle sabitlenir;
  iki kapı: eşleşme mesafesi ≤ hedefin yarıçapı (bbox) ve **sınıf değişmezliği** (mühürlenen `target_label`
  sınıfı) — aksi `localized=False` → mevcut 3-ardışık STOP mekanizması. Etiket kalıcı kimlikten üretilir.
- **Güven vekili (fantom)**: `solidity × min(1, n_blue_inside) × yöntem tavanı` (aruco_pnp 1.0 / diğerleri
  0.25) → piksel/ölçek modunda reliability `_MIN_RELIABILITY=0.3`'ü YAPISAL olarak geçemez (karar #4 ve #7).
  Kedi eşiği 0.3 DEĞİŞMEZ. Petri `reliability=conf×solidity` mevcut, aynı tavan uygulanır.
- **E eşlemesi**: `e_field` = hedef sınıfının E'si (sınıf 1 → `result_E_cancer`, sınıf 0 → `result_E_healthy`);
  `e_cancer`/`e_healthy` specs'e yalnız-ek. `ood` = fantom eğitim aralığı dışı ∨ petri sınıf 1.
- **Duty clip**: mevcut 0..0.50 kırpma (`AI_PRO_DUTY_MAX_RATIO`, `utils/stm32_protocol_limits.py:15`) kedi
  cpu/gpu fonksiyonlarından `_predict_and_drive` ZARFINA taşınır → tüm sağlayıcılar geçer, kedi davranışı
  bit-bit aynı, onay modalında **gösterilen = sürülen**. Bu YENİ sınır değildir; backend freq/duty/48 °C
  güvenlik sınırı değişmezine dokunulmaz.
- **Bayrak**: `PEMF_ARASTIRMA_AIPRO` backend'de uygulanır: `propose` ve `start` (mühür) model ≠ kedi iken
  bayrak `'1'` değilse 409. Taşıyıcı: `deploy/device.env` satırı (karar #17); status/hazirlik yanıtına yalnız-ek
  `arastirmaAiProAcik: bool`, `arastirmaAiProNeden: str`. Backend `.env`'i otomatik yüklemez
  (`api_server.py:176-177`) → servis env'ine giriş yolu Faz 1 iş kalemi.
- **efield_live**: `set_context(regions, organ_id=None, model=None)` opsiyonel parametre; `_predictor(model)`
  router önbelleğinden (ikinci yükleme yok); `start_ai_pro`, `stop_ai_pro` ve teardown'da `set_context([])`.
- **Yükleme sırası**: iki döngüde `provider.load()` `VideoCapture(0)`'dan ÖNCE (kamera tutma süresi yükten
  bağımsız); kamera açılamayınca `_active_session.is_active=False` + `update_live_session_state(False)`.
- **Import disiplini**: `servers/ai_pro_hedef.py` ai_hub'ı YALNIZ fonksiyon gövdesinde import eder
  (`scripts/build_backend_exe.ps1:248-260` PYZ koruma kapısı; tip için `TYPE_CHECKING`).

### 3.2 Veri modeli (yalnız-ek alanlar; mevcut anahtarlar aynen)

| Nerede | Eklenen |
|---|---|
| `AiProProposePayload` / `AiProStartPayload` (calibrate, organ, hazirlik/baslat da bu sınıfı kullanır) | `model: str = 'kedi'` |
| `_ai_organ_cache` | `model`, `targets`, `method`, `mm_per_px`, `target_name` (`kedi_var`, `guven_dokumu` aynen) |
| `ai_approval` specs | `model`, `target_label`, `e_cancer?`, `e_healthy?` |
| `ai_approval` meta | `method`, `mm_per_px`, `subject_label`, `achieved_B`, `duty_sum`, `ood`, `client_mode?` (istemcinin bildirdiği userMode — denetim izi) |
| `/status`, WS `ai_vision`, `/frame` | `model`, `modelName`, `subjectLabel`, `subjectDetected` (=kedi_var), `targetName`, `targets[{id,label,px,x,y,z,organ_id,reliability,secili}]`, `method`, `mmPerPx`, `eCancer?`, `eHealthy?`, `hazirlikAsama`, `arastirmaAiProAcik`, `sonGorulmeSn` |
| `_ai_hazirlik_hata` | `{kod, mesaj}` (kod: kamera | model_paketi | model_yukleme | zaman_asimi) |
| Frontend tipleri | `HedefModeli`, `HedefAdayi`, `AiProStatus += …?` (opsiyonel) |
| `/ai/log` (karar #16) | `module_id 'em_fantom'|'em_petri'`, `input_type 'camera'`, `mode=userMode` |

### 3.3 API değişiklikleri — **yeni rota YOK**

| Uç | Değişiklik |
|---|---|
| `POST /api/ai/pro/hazirlik/baslat` | + `model`; mutasyon (organ/model/cache) `_ai_loop_lock` İÇİNE ve aktiflik kontrolünden SONRA; seans aktif → 409; hazırlık aktif + farklı model → 409; `_ai_kare_yabanci(client_id)` → 403 (Faz 0 kusur #2) |
| `POST /api/ai/pro/calibrate` | + `model` (MOBİL hazırlığın tek giriş noktası); seans yokken `_ai_hedef_modeli` set; aktifken farklı model → 409 |
| `POST /api/ai/pro/organ` | + `model` (aktif modelle uyuşmazsa 422); `organ_id` = hedef indeksi; 403 aynen |
| `POST /api/ai/pro/propose` | + `model`; kapı `provider.target_ids`; bayrak; `specs`/`meta` ekleri; 409 gövdesi sağlayıcı ipucu ('kamera' + 'konumland' kelimeleri korunur — test_ai_pro_approval_gate) |
| `POST /api/ai/pro/start` | `model` kabul edilir AMA yok sayılır (mühürden); yanıt + `model`, `modelName`, `targetName` |
| `POST /api/ai/pro/stop` | + `efield_live.set_context([])`; `_ai_hedef_modeli` seans sonu 'kedi'ye döner (karar) |
| `GET /api/ai/pro/status`, WS `ai_vision`, `POST /api/ai/ai_pro/frame` | yalnız-ek alanlar (3.2); `/frame` opsiyonel Form `model` (eski APK göndermez → aktif state) |
| `GET /api/ai/hazirlik` | envantere `petri_yolo` + CV paketleri; `arastirmaAiPro` bloğu |
| `ai_service` (Faz 5, opsiyonel) | `POST /infer/em_fantom/predict`, `/infer/em_petri/predict` (guii route-contract kapsamı dışı) |

`tests/test_route_contract.py` GOLDEN_ROUTES ve sabit sayaç **98 DEĞİŞMEZ**; `servers/auth.py:43-44`
`_EXEMPT_PREFIXES` (`/api/ai/pro`, `/api/ai/ai_pro`) DEĞİŞMEZ (yeni pozitif kilit testi eklenir).

### 3.4 Frontend

- `ControlScreen.tsx`: `const { isResearcher } = useUserMode()` (3 testi zaten mock'lu — `dozKaynagiRozeti.test.tsx:59`
  mock'u `isResearcher` döndürmez → undefined = eski başlık; yeni testte açıkça `isResearcher:true`);
  `<AiProPanel patientName hedefKumesi={isResearcher ? 'arastirma' : 'kedi'} />`; başlık koşullu.
- `AiProPanel.tsx`: `hedefKumesi` prop (varsayılan `'kedi'` → 5 jest dosyası mock'suz geçer); `hedefModeli`
  state + **`hedefModeliRef`** (deps çıpası `[hazirlik, mobileResult, organId, duration]` `test_ai_pro_asamali_akis.py:321`
  korunur; `clientIdRef` deseni); kedi `asamaMetni` bloğu ve 'Hayvan aranıyor' literal'i DOKUNULMAZ;
  `asamaMetniArastirma` AYRI yardımcı fonksiyon, kedi bloğundan boş satırla ayrılmış (kapı regex'i önce
  KIRMIZI görülür); tüm apiPost gövdelerine `model`.
- Yeni bileşenler `pf/src/components/domain/aipro/`: `ModelSecimKartlari.tsx`, `HedefSecici.tsx`, `DozOzeti.tsx`,
  `KalibrasyonRozeti.tsx`, `AdimGostergesi.tsx`; `pf/src/components/domain/aiProProfilleri.ts` tablosu
  (ikon, metinler, `MODELLER_PROFILE_GORE = {veterinarian:['kedi'], researcher:['fantom','petri'], pet_owner:[]}`)
  + pytest kaynak-regex "researcher listesinde kedi YOK" (mutasyon: kedi ekle → kırmızı).
- `AiSpecApprovalModal.tsx`: `specs.model?`, meta ekleri; 'Organ' → 'Hedef' (model ≠ kedi); x/y/z çizilir;
  XAI etiketi 'doku tipi'; E göreli/birimsiz Türkçe ondalık virgülü 2 hane; OOD satırı; `ScrollableModalCard`
  + testID `ai-onay` korunur. Karar #4 tek dal: ArUco zorunluysa piksel-modu şeridi YOK (409 zaten engeller).
- Taşımalar (kopya değil): `AiHubScreen` → `pf/src/components/domain/ResultInterpretation.tsx`
  (+MedicalDisclaimer, dutyYuzde); `PatientGate.sozluk()` → `pf/src/utils/profilSozlugu.ts` (export; AiProPanel
  'Örnek seçilmedi — seans kaydı örneksiz kalır. Örneksiz başlat?').
- `AiHubScreen.tsx:1139` toast `isResearcher ? 'onay gerektirir' : 'hekim onayı gerektirir'`; Fantom/Petri
  modülleri sonuç altına "Bu hedefe AI Pro seansı → Kontrol" (yalnız `navigateTo('control')` + ön-seçim;
  `/ai/pro/*` ÇAĞRILMAZ — `aiHubOtonomOnayKapisi` kilidi); doc yorumu "Canlı kamera/otonom YOK" güncellenir.
- Terminoloji (karar #12): araştırmacıda 'hekim onayı' → 'onay', 'Hasta' → 'Örnek', "Seans Geçmişi'ne kaydedildi".

---

## 4. Fazlar

Her faz: **kapıları ÖNCE kırmızı gör** (mutasyon), pre-commit sonrası `git log -1` doğrula, tam süit yeşil.
Kedi koduna dokunulmadığının kanıtı davranışsal golden'dır (aynı sahte cat_organ çıktısı → aynı tuple/D/P).

### Faz 0 — Sahip kararları + mevcut kusurların bağımsız düzeltmesi (yayın: app 1.9.44'ün hasta-güvenliği maddesi)

| İş | Dosya | Kapı (mutasyonla kırmızı) |
|---|---|---|
| §5 tablosundaki 21 kararı al, bu dokümana "✅ KESİN" olarak işle | bu dosya | — |
| **Kusur #1**: `ai_router.py:1187` → `lz, lx, ly, lzz, lrel, lov, lkedi, *l_ek = _localize_organ(frame, _oid)` + cache'e `guven_dokumu` (1016/1796 paritesi); ayrı commit | `servers/ai_router.py`, `tests/test_ai_pro_seans_dongusu_lokalizasyon.py` (yeni) | `test_kalan_regression_gaps.py:629-711` `_SahteCv2`/sahte time harness'ı ile `_ai_pro_loop` GERÇEK 8'li tuple altında koşar → `_drive_coils_ai_pro` ≥1 kez çağrılır, `cache.localized` True. Mutasyon: 7'li açılıma geri al → kırmızı. Ek yapısal kapı: hazırlık ve seans döngüsü `_localize_organ` sonucunu AYNI biçimde açar (1187 tam da bu paritenin kopmasından çıktı). |
| **Kusur #2**: `/hazirlik/baslat` organ/model/cache mutasyonu `_ai_loop_lock` içine, aktiflik kontrolünden sonra; seans aktif → 409; `_ai_kare_yabanci(client_id)` → 403; ayrı commit | `servers/ai_router.py`, `tests/test_ai_pro_hazirlik_mutasyon_kilidi.py` (yeni) | aktif seans (organ 2 mühürlü) + `/hazirlik/baslat {organ_id:5}` → 409 ve `_ai_organ_id` 2 kalır, cache `localized` değişmez; yabancı client → 403. Mutasyon: mutasyonu kilit öncesine taşı → kırmızı. `test_ai_pro_web_hazirlik.py:131-139` (hazırlık NO-OP) yeşil kalır. |
| **Kusur #3**: `jeton.py:294` `/api/ai/pro/frame` → `/api/ai/ai_pro/frame` ekle (+ `/api/ai/pro/hazirlik/baslat|durdur`, `GET /api/ai/hazirlik` serbest); `test_jeton_gate.py:93` gerçek yol; `docs/JETON-SISTEMI.md` | `servers/jeton.py`, `tests/test_jeton_gate.py`, docs | `esle('/api/ai/ai_pro/frame') is None`. FREE_MODE değişmezine dokunulmaz. |
| Hazırlık envanterine `('petri_yolo', 'ai_hub.inference_petri_dish.petri_cv.petri_detector', 'ai_hub/inference_petri_dish/yolo11m-seg.onnx')`; derin=1'de `phantom_cv`/`petri_cv` import + yaml/npz varlığı ayrı "kabin" bloğu | `servers/ai_router.py:3141-3208`, `tests/test_ai_hazirlik_envanteri.py` | yolo yolu monkeypatch ile 'yok' → `/api/ai/hazirlik` eksik listesinde `petri_yolo`. Mutasyon: satırı sil → kırmızı. Mevcut kurallar (None yasak, PROFILLER'de var, ≥15) yeşil. |
| Karakterizasyon golden'ı: mevcut `pixel_to_cabin_mm`'in 05_FantomTumor.jpeg / 06b_PetriKuyu_aruco.jpg için ürettiği x,y,z sabitlenir (yama YAPILMAZ) | `tests/test_koordinat_donusumu_karakterizasyon.py` (yeni, `capraz.atla_yoksa`) | golden değişirse kırmızı → coord_transform'a dokunan her iş görünür olur |

**Bitiş:** 21 karar tabloda; üç kusur ayrı commit'lerde mutasyon kanıtıyla; envanter kapısı petri YOLO
eksikliğinde kırmızı; tam süit yeşil; fantom/petri davranışı henüz yok.

### Faz 1 — Backend Hedef Sağlayıcı + model mührü (kedi davranış-sıfır; yayın: app 1.9.44 backend-only)

| İş | Dosya |
|---|---|
| `servers/ai_pro_hedef.py`: `HedefSaglayici` Protocol, `KediSaglayici` (geç-bağlı delegasyon), `SAGLAYICILAR`, `saglayici_al(model)`; ai_hub import'ları yalnız fonksiyon içinde | yeni |
| `_ai_hedef_modeli` globali (`_ai_loop_lock`); `_localize_organ` (817) ve `_predict_and_drive` (869) ince delegatör; clip 0..0.50 zarfa taşınır (kedi cpu/gpu'dan kaldırılır — bit-bit aynı sonuç) | `servers/ai_router.py` |
| Payload'lara `model`; hazirlik/baslat, calibrate, organ, propose model set (aktif seans/hazırlık + farklı model → 409); start mühürden; stop/teardown sıfırlama; `varsayilan_hedef`e çekme (kedi organ 5 fantoma sızmasın) | `servers/ai_router.py` |
| Dört organ kapısı → `provider.target_ids`; `(0, 1, 2, 3, 4, 5, 6)` literal'i SIFIR kez | `servers/ai_router.py` |
| status/WS/frame yalnız-ek alanlar (3.2) + `hazirlikAsama` + `arastirmaAiProAcik`; cache `model` + tazelik koşulu | `servers/ai_router.py` |
| Bayrak `PEMF_ARASTIRMA_AIPRO` propose/start'ta; `deploy/device.env` satırı + NSSM env yolu (karar #17) | `servers/ai_router.py`, `deploy/device.env`, `scripts/setup_services.ps1` |
| `_ai_hazirlik_hata` → `{kod, mesaj}`; yükleme kameradan ÖNCE; sağlayıcı bazlı join timeout; kamera açılamayınca `_active_session` pasif | `servers/ai_router.py` |
| `efield_live.set_context(..., model=None)`; start/stop/teardown `set_context([])`; `_predictor(model)` router önbelleğinden | `servers/efield_live.py` |
| Kedi XAI baz-noktası fiilen kullanılan achieved_B/duty_sum ile (karar #9) | `servers/ai_router.py` |
| Meta'ya `client_mode` (istemcinin bildirdiği userMode; denetim izi) | `servers/ai_router.py` |

**Kapılar:** mevcut 9 `test_ai_pro_*.py` + `test_kalan_regression_gaps` + `test_em_xai_entegrasyon` +
`test_xai_kalan_a_grubu` + `test_route_contract` HİÇ DEĞİŞTİRİLMEDEN yeşil (davranış-sıfır kanıtı).
`tests/test_ai_pro_model_muhru.py` (yeni): propose `{model:'fantom'}` (stub sağlayıcı) → `specs.model=='fantom'`;
approve; start `{model:'kedi'}` → yanıt `model=='fantom'` (gövde yok sayıldı; mutasyon: gövdeyi oku → kırmızı);
geçersiz model 422; kedi cache'i fantom propose'una 'taze' sayılmaz (mutasyon: tazelikten `model` sil → kırmızı);
aktif seansta farklı model → 409; bayrak kapalı → propose 409 metni 'tezgâh' içerir (mutasyon: kapıyı kaldır →
kırmızı); `max(specs.D) <= AI_PRO_DUTY_MAX_RATIO` (mutasyon: zarf clip'ini kaldır → kırmızı).
`tests/test_ai_pro_saglayici_delegasyon.py` (yeni): `_localize_organ` aktif sağlayıcının `localize`'ına gider;
`ai_pro_hedef.py` kaynağında modül-seviyesi `^from ai_hub|^import ai_hub` SIFIR (mutasyon → kırmızı);
`(0, 1, 2, 3, 4, 5, 6)` literal'i ai_router'da SIFIR (mutasyon → kırmızı); kedi golden: aynı sahte cat_organ
çıktısı için `_extract_organ_target` ve `_predict_and_drive` çıktıları Faz-0 golden ile eşit.
`tests/test_ai_pro_auth_muafiyet_pozitif.py` (yeni): PEMF_REQUIRE_AUTH=1 + LAN dışı IP ile `/api/ai/pro/status`
ve `/api/ai/ai_pro/frame` token'sız 401 DEĞİL (mutasyon: prefix'i sil → kırmızı).
`test_efield_live` imzası korunur; yeni test: mobil seans → `/stop` → `get_context() is None`.
Yeni fixture: `_ai_hedef_modeli` snapshot/restore autouse.

**Bitiş:** veteriner akışı bit-bit aynı; `model` payload→mühür→start zincirinde; route-contract 98 sabit;
auth-muafiyet pozitif kilitli; sağlayıcı kaydında fantom/petri henüz yok; `scripts/pyz_koruma_kapisi.py` yeşil.

### Faz 2 — Fantom ve Petri sağlayıcıları (backend) + koordinat çerçevesi (yayın: app 1.9.45 ile birlikte)

| İş | Dosya |
|---|---|
| `FantomSaglayici`: `load()` 'em_fantom_cv' (kapanış `ai_router.py:2192-2205`'ten modül fonksiyonuna TAŞINIR, analiz ucu da onu çağırır; `test_xai_kalan_a_grubu` `cache["predictor"]` çıpası korunur); `localize()` enjeksiyonlu pipeline, `manual_fallback=False`; `phantom_not_detected` → `ozne_var=False`; adaylar `centroid_px`; güven vekili; ood | `servers/ai_pro_hedef.py`, `servers/ai_router.py` |
| `PetriSaglayici`: `load()` 'em_petri_cv' (yolo_device='cpu', sıfır-kare ısıtma; 2309-2337 taşınır); `yolo_no_well_detected` / `not_a_petri_plate` → `ozne_var=False` + canlı-kamera ipucu (istisna DEĞİL, hazırlığı bitirmez); kalıcı kuyu kimliği; mesafe + sınıf kapısı; hedef 0 = en yüksek güvenli kanserli kuyu; YOLO çağrısı kilitle serileştirilir (analiz ucuyla eş zamanlı) | `servers/ai_pro_hedef.py` |
| `petri_detector.py:69` `SystemExit` → `RuntimeError`; iki döngüde model yükleme bloğu kamerayı bırakan try/finally İÇİNDE | `ai_hub/inference_petri_dish/petri_cv/petri_detector.py`, `servers/ai_router.py` |
| Fantom/petri scaler yollarına em_kedi'deki `yan_dosya_coz` deseni (Docker imajında .pkl elenir) | `ai_hub/inference_em_fantom/inference_em_fantom.py:38-40`, `inference_em_petri.py:43-45` |
| E eşlemesi, `e_cancer/e_healthy`, `ood`, `method`, `mm_per_px` specs/meta'ya; XAI fantom/petri modülünden fiilen kullanılan B/duty ile | `servers/ai_router.py` |
| GPU dalı: `ai_service_enabled()` iken fantom/petri lokalizasyonu `delegate_infer_sync('em_fantom'|'em_petri')`; 422 `domain_mismatch`/`not_a_petri_plate` yanıtı 'kapı reddi' sayılır (CPU fallback döngüsüne DÜŞMEZ, N ardışık redde GPU devri seans boyunca kapanır, log 1 kez); `delegate_json_sync('em_kedi')` ASLA çağrılmaz; tahmin CPU-yerel | `servers/ai_pro_hedef.py` |
| Petri YOLO CPU süresi ve 239 MB ilk yükleme süresi ÖLÇÜLÜR, test log'una yazılır; `join_timeout_s` ölçüme göre | test çıktısı, bu doküman |
| coord_transform: **YAMA YOK** hoca kararı #6 gelmeden. Karar gelirse: iki kopyaya aynı yama (marker→kabin rotasyonu + yapılandırılabilir hedef düzlemi), `cabin_config.py` ×2 parser'a `hedef_duzlem` alanı, yaml ×2, `test_kabin_config_65x50x50` kilidi, golden güncellenir, CHANGELOG'da "AI Hub fantom/petri ArUco koordinatları değişti" AYRI madde, ai_service paritesi | `ai_hub/inference_em_fantom/phantom_cv/{coord_transform,cabin_config}.py`, `ai_hub/inference_petri_dish/petri_cv/{coord_transform,cabin_config}.py`, yaml ×2 |
| Mobil intrinsics: `pl._approx_intrinsics` True (telefon) iken `aruco_pnp` güven vermez → `localized=False` + "Telefon kamerası kalibre değil — kabin kamerasını kullanın" (karar #15) | `servers/ai_pro_hedef.py` |

**Kapılar (CI'da koşan STUB + yerelde gerçek):**
- `tests/test_ai_pro_saglayici_stub.py` (CI, ağırlıksız): sahte `PipelineResult` üreten sahte pipeline'larla
  localize/predict/targets/hint/E-anahtarı/hedef-takibi/sınıf-kapısı/ood/güven-vekili. Mutasyonlar: `result_E`
  anahtarını oku → e_field 0 → kırmızı; ×10 uygula → kırmızı; aruco çarpanını 1.0 yap → piksel modunda localized
  True → kırmızı; mesafe kapısını kaldır → komşu kuyuya kilitlenir → kırmızı; `manual_fallback` regex.
- `tests/test_ai_pro_fantom_saglayici.py` / `test_ai_pro_petri_saglayici.py` (`entegrasyon` marker, `capraz.atla_yoksa`):
  `_FakeCap.read()` → 05_FantomTumor.jpeg / 06b_PetriKuyu_aruco.jpg ile `/hazirlik/baslat {model}` → `subjectDetected`
  True, `targets` ≥1, `method`; propose → `specs.model`, D 7 eleman ≤0.50, `e_field>0`; organ_id 3 → 422;
  `_get_or_load_kedi` çağrı sayacı 0; `PhantomPredictor.__init__` ≤1 / 10 kare; petri: 05 beslenince
  `subjectDetected` False + hint 'yükle/modül/PEMF_AI_' içermez; flap senaryosu: makullik reddi 3 turda STOP,
  sonra hedef dönünce sürüş devam (dur-kalk 30 sn içinde en fazla 1 kez).
- Yayın runbook: yerel tam süit `PEMF_CAPRAZ_KAYNAK_ZORUNLU=1` ile, `-rs` çıktısında entegrasyon testleri ATLANMADI kanıtı.

**Bitiş:** sağlayıcılar gerçek pipeline ile kamerasız testlerde hedef bulur, doğru predictor'la D/P/E üretir,
kedi modelini hiç yüklemez; petri süresi ölçüldü; bayrak KAPALI kalır (tezgâh doğrulaması ve hoca kararı #6
gelmeden araştırmacı Onayla'yı göremez).

### Faz 3 — Frontend: araştırmacı sihirbazı (web) + onay modalı + hata metinleri

İş kalemleri §3.4'te. Ek: `tests/test_dokunma_hedefi_kapisi.py` KALAN_IHLAL=118 değişmez (yeni Pressable'lar ≥44 px);
`test_responsive_grafik_kapisi.py` `kameraKutusu(onizlemeW` sayacı canlı önizleme eklenirse güncellenir (önce kırmızı);
`patientScope.test.ts:108-114` YAZAN listesi yeni dosyalar için; Playwright/Edge görsel doğrulama (web 5 adım).

**Kapılar:** mevcut 5 AiProPanel jest + `aiHubOtonomOnayKapisi` + `scratchModule` + `patientScope` +
`test_ai_pro_asamali_akis.py` DEĞİŞMEDEN yeşil. `AiProPanelArastirma.test.tsx` (yeni, `hedefKumesi='arastirma'`):
kedi organ çipleri ve 'Hayvan aranıyor' YOK, iki kart VAR; Fantom seçilince `/ai/pro/hazirlik/baslat` gövdesi
`model:'fantom'`; status `targets` 2 → 2 Pressable halka; halka 2 → `/ai/pro/organ {organ_id:2, model:'fantom'}`;
model değiştir → sonraki propose yeni modeli taşır (ref); onay modalında 'Hedef', 'Tahmini alan', 3B rozet, OOD;
'Onayla ve Başlat' → `/approve` ÖNCE `/start`; `method:'pixel'` → öneri yok + eylem metni; `arastirmaAiProAcik:false`
→ kartlar pasif 'Deneysel'; seans aktifken kartlar `disabled`; Geri adım 2 → `/hazirlik/durdur`. Kaynak-regex:
hata metinlerinde yasaklı kelimeler yok; `MODELLER_PROFILE_GORE.researcher` kedi içermez (mutasyon → kırmızı);
`AiHubScreen` `/ai/pro/*` çağırmaz. Lint/tsc temiz.

**Bitiş:** araştırmacı web'de 5 adımı kod bilgisi olmadan tamamlar (bayrak açıkken); veteriner ekranı birebir;
tüm mevcut kapılar değişmeden yeşil; yeni kapılar mutasyon kanıtlı.

### Faz 4 — Mobil parite (karar #15'e bağlı), doküman, sürüm, yayın

| İş | Dosya |
|---|---|
| Mobil: `/calibrate {model, client_id}`; `/frame` opsiyonel Form `model`; `mobileResult.targets` → `HedefSecici` (dokun → `/organ`); intrinsics kapısı; kadraj rehberi ("kabin işareti (arka duvar) ve plaka AYNI karede olmalı — telefonu kabin önünden, hafif yukarıdan tutun") **ya da** karar #15 = hayır ise mobilde kartlar "Bu model masaüstü kabin kamerası ister — bilgisayardaki Kontrol → AI Pro ekranını kullanın" | `AiProPanel.tsx`, `servers/ai_router.py` |
| Dokümanlar: `servers/README.md`, `ai_hub/README.md` (:26, :34), `ai_hub/PEMF_AI_Test_Girdileri/00_README_OKU.txt` AI PRO bölümü ('Araştırma Modu: Fantom (05) / Petri (06b ArUco)'), `docs/VERIFICATION.md` AI Pro tezgâh maddesi, **`ai_hub/KABIN_KURULUM_KILAVUZU.md` "Fantom/Petri yerleşimi"** (tepsi konumu, kalınlık, marker görünürlüğü, telefon açısı kısıtı), bu dokümanın DURUM bloğu; README sapmaları (petri/phantom README 5X5_100/5 cm → 5X5_50/10 cm) | docs |
| CHANGELOG (mevcut ASCII üslubuyla): `## app 1.9.44 — … (hasta-güvenliği: sunucu-kameralı AI Pro seansında lokalizasyon her karede patlıyor, bobin sürülmüyordu — düzeltildi; hazırlık ucu seans sürerken hedef değiştirebiliyordu — kapatıldı)`; `## app 1.9.45 (+ mobile 2.3.34) — Araştırma AI Pro: Fantom + Petri`; `versions.json`; `sync_versions.ps1`; `scripts/check_changelog_surum.py` + `test_version_visibility` | CHANGELOG.md, versions.json |
| Paket: `research.zip`'e DOKUNULMAZ; yeni kod yalnız `servers/` (exe PYZ) + `ai_hub/` (Cython .pyd) + `pf/` → deps sha değişmez (`make_base_zip.py` APP_ROOTS); sevk-ağacı ai_hub kapısı + PYZ temizliği kapısı; frozen EXE'de `/api/ai/hazirlik?derin=1` çıktısında `arastirmaAiPro` doğrulanır | build |
| Yayın runbook: backend build + APK build PARALEL KOŞMAZ; iki isim (sürümsüz+sürümlü); manifest en son; "sahip masaüstünü devralınca dur"; yayın yalnız açık "yayınla" ile | runbook |

**Kapılar:** `test_ai_pro_frame_arastirma.py` (yeni): aktif fantom seansında `/frame` (sahip) `model:'fantom'`, `targets`
dolu, `driven` yalnız `localized and session_active and not is_foreign`; yabancı → `driven False`; **eski APK**:
`/calibrate` + `/frame` modelsiz → cat_organ çağrıldı, fantom sağlayıcı çağrılmadı; mobil hazırlık `/calibrate
{model:'petri'}` → kareler `PetriSaglayici.localize`'a gider (mutasyon: calibrate modeli okumasın → kırmızı).
`AiProPanelArastirmaMobil.test.tsx`: 1500 ms kare, halkalar, dokunma → `/organ`, 2 ölçüm → propose `model:'petri'`.

**Bitiş:** web (ve karar #15 evetse APK) aynı sihirbazı sunar; eski APK kedi akışında kırılmaz; dokümanlar güncel;
deps ve research.zip sha değişmedi; yayın notunda hasta-güvenliği maddeleri başta.

### Faz 5 (opsiyonel, ayrı karar) — GPU mikroservis paritesi ve ölü ağırlık temizliği
`ai_service/app.py`'ye `POST /infer/em_fantom/predict`, `/infer/em_petri/predict` (infer_em_kedi 1152-1182 gövdesi
`predictors.get(name)['predictor']` ile genelleştirilir; `app.py:251` `v["onnx"]` KeyError yan bulgusu `v.get`);
`ai_pro_hedef.py` `gpu_predict_name`; parite testi (aynı girdi → CPU == GPU D/P/E golden); `delegate_infer(`
yapısal kapısı (`test_ai_mikroservis_modalite_kapisi:254`) `delegate_infer_sync` için genişletilir.
`make_model_zip.py`'den ~191 MB ölü ağırlık (em_phantom/PhantomNet_v3, em_petri/PetriNet_v3, petri_dish kopyası)
çıkarılması research sha'yı değiştirir (1,61 GB yeniden indirme) → AYRI yayın kararı (#14). Üretimde mikroservis
kapalı (`PEMF_AI_SERVICE_URL` yalnız docker-compose.micro.yml) → ertelenebilir.

---

## 5. Faz 0 — Sahip Kararları (öneri = varsayılan; ✅ işaretlenince KESİN)

| # | Karar | Öneri |
|---|---|---|
| 1 | Hedef politikası (çoklu tümör / çoklu kuyu) | Varsayılan otomatik (en büyük tümör / en yüksek güvenli kanserli kuyu) + araştırmacı kare üstünde TEK hedef değiştirir; çoklu/sıralı sürüş KAPSAM DIŞI |
| 2 | Sağlıklı hedef (EM sınıf 0, kontrol deneyi) izinli mi? | EVET, Adım 1'de kapalı-varsayılan anahtar ile; varsayılan yalnız kanserli |
| 3 | E gösterimi | Onayda hedefte + çevrede (göreli, birimsiz) ve oran; canlı `eField` = hedef sınıfının E'si |
| 4 | Kalibrasyon şartı | Kapalı döngüde ArUco ZORUNLU; ölçek modu (fantom boyu / petri çapı) yalnız AI Hub tek-foto analizinde; piksel/ölçek modunda öneri 409 (tek dal, şerit yok) |
| 5 | achieved_B / duty_sum | Fantom/petri cfg (0.001 T, 2.4) — analiz paneliyle aynı; kedi 0.001/1.5 aynen; XAI baz-noktası tahminle aynı |
| 6 | Fantom/petri fiziksel yerleşim ve koordinat çerçevesi (taban Y=−25 cm + kalınlık; fantom eğitim aralığı x∈[−56,6; −30,6] mm hangi kurulum?) | **HOCA ile** netleştirilir; karar gelmeden coord_transform yaması YAPILMAZ, fantom/petri sürüşü bayrak arkasında |
| 7 | Fantom güven vekili ve eşik | solidity × n_blue_inside × yöntem tavanı (1.0 / 0.25); eşik 0.3 aynen; tezgâhta ölçüm protokolü (kaç kare, kaç konum, kabul ölçütü) yazılır |
| 8 | Duty politikası | Mevcut ortak yol (0..0.50 clip zarfta + normalize 0.50) — yeni sınır eklenmez, mevcut kaldırılmaz |
| 9 | Kedi XAI baz-nokta kayması (tahmin 1.5, açıklama 2.0) bu işte düzeltilsin mi? | EVET (Faz 1, tek satır) |
| 10 | Profil kısıtı yalnız UI'da (backend profil-bilgisiz, auth-muaf değişmezi) | EVET (scratch emsali); backend model alanını doğrular, profili sormaz; istemci modu meta'ya denetim izi olarak yazılır |
| 11 | Yayın kadansı | Faz 0+1 → app 1.9.44 (backend-only); Faz 2+3 → app 1.9.45; mobil 2.3.34 karar #15'e bağlı; launcher 1.9.50 aynen; Faz 5 ertelenir |
| 12 | Terminoloji | Araştırmacıda 'hekim onayı' → 'onay', 'Hasta' → 'Örnek', "Seans Geçmişi"; sekme 'AI Pro', alt başlık 'Fantom / Petri Kapalı-Döngü'; kod/DB/hukuki metin sabit |
| 13 | Simetrik gizleme (kedi araştırmacıda, fantom/petri veterinerde HİÇ görünmez) | EVET (AiHubScreen `modes` bölüşümüyle aynı) |
| 14 | ~191 MB ölü ağırlık research.zip'ten çıkarılsın mı? | AYRI yayın; bu işte dokunulmaz |
| 15 | Mobil (telefon kamerası) fantom/petri kapalı döngü v1'de var mı? | ÖNERİ: HAYIR — v1 yalnız kabin (sunucu) kamerası; telefon intrinsics'i kalibre değil ve marker arka duvarda (tepeden çekimde görünmez). Mobilde kart yönlendirme metni. |
| 16 | AI geçmişi (/ai/log) kaydı | EVET: onay anında `module_id em_fantom|em_petri`, `input_type camera`, `mode=userMode` (denetim izi #10 ile birleşir) |
| 17 | Bayrak taşıyıcısı `PEMF_ARASTIRMA_AIPRO` | `deploy/device.env` satırı (Inno kurulumla servis env'ine iner) + NSSM env; UI status'tan okur |
| 18 | "Araştırma paketi kurulu değil" yönlendirme metni | Launcher'daki gerçek profil-ekleme yolu neyse o (kullanıcıya görünen adıyla; 'Client/Launcher' kelimeleri yasak) — sahip söyler |
| 19 | Petri makullik reddi flap'ında STOP davranışı | Mevcut 3-ardışık STOP + hedef dönünce otomatik devam; şeritte "son görülme" sayacı; test ile kilitlenir |
| 20 | CI'da ağırlıksız stub testleri kabul mü? | EVET (stub CI'da, gerçek pipeline `entegrasyon` marker ile yerelde zorunlu) |
| 21 | Aktif seans/hazırlık sürerken model/hedef değişimi | 409 (sessiz başarı DEĞİL) + UI kilidi |

---

## 6. Test & Regresyon Disiplini

| Katman | Ne | Nerede |
|---|---|---|
| Davranış-sıfır kanıtı | mevcut 9 `test_ai_pro_*` + regression_gaps + em_xai + xai_kalan_a + route_contract DEĞİŞMEDEN yeşil; kedi golden (sahte cat_organ çıktısı → tuple/D/P) | Faz 1 |
| Mühür/kilit | model mührü, gövde yok sayma, tazelik, 409 seans-aktif, bayrak, clip ≤0.50, auth pozitif | Faz 1 |
| Yapısal | ai_hub import yalnız fonksiyon içinde; `(0..6)` literal SIFIR; hazırlık/seans lokalizasyon açılım paritesi; `manual_fallback=False`; `MODELLER_PROFILE_GORE.researcher` kedi yok; yasaklı hata kelimeleri | Faz 1-3 |
| Sağlayıcı (stub, CI) | E anahtarı, ×10 yok, güven vekili, mesafe+sınıf kapısı, kalıcı kimlik, ood, hint | Faz 2 |
| Sağlayıcı (gerçek, yerel) | 05/06b ile uçtan uca hazırlık → propose; predictor tek yükleme; kedi hiç yüklenmez; flap | Faz 2 |
| Frontend | `AiProPanelArastirma` (+Mobil), onay modalı, Geri/kilit, a11y | Faz 3-4 |
| Karakterizasyon | coord_transform mevcut çıktısı golden; yama ancak hoca kararıyla ve CHANGELOG maddesiyle | Faz 0/2 |

**Korunan çıpalar (DEĞİŞTİRİLMEZ):** `kedi_var`, `catDetected`, `_localize_organ`, `_extract_organ_target`,
`_get_or_load_kedi/_catorgan`, `"organ_id": _oid`, `if localized and session_active`, `_ai_hazirlik_durdur_ic()` →
`target=_ai_pro_loop` sırası, `asamaMetni` 4-backtick bloğu ve 'Hayvan aranıyor', deps dizisi
`[hazirlik, mobileResult, organId, duration]`, `cache["predictor"]` adlandırması, 'kamera' + 'konumland' 409 kelimeleri,
`startswith('AI')` mode öneki, `ScrollableModalCard` + testID `ai-onay`. Anlam kayması ("catDetected = özne kadrajda",
"organId = hedef indeksi") kod içinde TEK yerde sözlük yorumu ile kilitlenir (`ai_pro_hedef.py` başlığı).

---

## 7. Riskler ve Azaltma

| Risk | Azaltma |
|---|---|
| Koordinat çerçevesi uyuşmazlığı → yanlış hedefe doz | Bayrak backend'de; karakterizasyon golden; yama yalnız hoca kararıyla; tezgâh doğrulaması (VERIFICATION maddesi) |
| E anahtarı sessiz sıfır | sağlayıcı eşlemesi + `e_field>0` mutasyon testi |
| Birim hatası (×10) | sağlayıcıların ayrı çıkarıcısı; golden |
| Çapraz-model onay | mühür + gövde yok sayma + tazelik + testler |
| Hedef kayması (petri komşu kuyu / sınıf değişimi) | mesafe + sınıf kapısı; kalıcı kimlik |
| Fantom güven vekili kalibresiz | yöntem tavanı yapısal red; tezgâh ölçüm protokolü (#7) |
| Petri organ_id ekstrapolasyonu | `ood` + onay ekranı satırı; hoca teyidi |
| Petri CPU süresi/ilk yükleme | ölçüm; `hazirlikAsama` geri bildirimi; yükleme kameradan önce; join timeout sağlayıcı bazlı |
| Çift kamera / takılı seans | yükleme sırası + kamera-açılamadı yolunda `_active_session` pasif |
| Araştırma-yalnız kurulumda em_kedi yok | sağlayıcı bazlı ısıtma; envanter satırları; `model_paketi` hata sınıfı |
| Backend profil-bilgisiz | mühür/onay korunur (güvenlik değil); `client_mode` denetim izi |
| Test çıpaları / PYZ kapısı / deps sha | §6 korunan çıpalar; import disiplini; yeni dosyalar yalnız servers/ai_hub/pf |
| Mobil marker görünmezliği / telefon intrinsics | karar #15 (v1 web) veya kadraj rehberi + intrinsics kapısı |
| CI ağırlıksız → sahte yeşil | stub testleri CI'da; yerel entegrasyon zorunlu (runbook) |
| Doküman sapmaları | Faz 4 listesi (README, kılavuz, VERIFICATION, CHANGELOG üslubu) |

---

## 8. Kapsam Dışı
Çoklu/sıralı hedef sürüşü; backend'de userMode kapısı; yeni HTTP rotası; backend freq/duty/48 °C sınırı ekleme/kaldırma
(`_AI_PRO_FREQ_HZ=1.0`, `_AI_PRO_MAX_DURATION_MIN=120`, kedi `_MIN_RELIABILITY=0.3` değişmez); model yeniden eğitimi;
AI Hub tek-foto modüllerinin otonom başlatması (yalnız yönlendirme); jeton/ücretlendirme şeması (FREE_MODE=true);
`manual_select` cv2 penceresi; kedi kod yolu/yayın notlarının yeniden yazımı; bulut/Supabase, launcher, firmware.

## 9. Geri Alma Stratejisi
Her faz ayrı commit dizisi ve yayın; Faz 1 refaktörü davranış-sıfır olduğundan geri alma = commit revert (mevcut süit
kanıt). Faz 2/3 bayrak arkasında: `PEMF_ARASTIRMA_AIPRO` kapalıyken araştırmacı yalnız görüntüleme yapar, kedi akışı
etkilenmez. coord_transform yaması tek commit + golden; sorun çıkarsa revert AI Hub analizini eski davranışa döndürür.

## 10. Açık Sorular (hoca / tezgâh)
1. Fantom modeli eğitim çerçevesi (x∈[−56,6; −30,6] mm) hangi fiziksel kurulumu temsil ediyor? Kabin ArUco mm'si mi,
   fantom merkezine göreli mm mi? Tezgâhta 3 konumda ölçülüp EM çıktısıyla karşılaştırılacak.
2. Fantom tepsisi / petri plakası kabinde nereye konuyor (taban Y=−25 cm + kaç cm)? Marker (arka duvar) ve hedef
   aynı kamera karesinde mi?
3. Petri modelinde organ_id=1 (kanser) tahmini eğitimde hiç görülmemiş eksen — kabul mü, uyarı ile mi?
4. Fantom güven vekili için kabul ölçütü (ör. 20 kare × 3 konumda reliability ≥0.5 ve konum sapması ≤5 mm).
5. Petri YOLO CPU süresi (ölçülecek) 10 sn yeniden-lokalize aralığı ve 1 Hz döngüyle uyumlu mu?

---

## Ek A — Keşif kanıtları (özet)
Workflow `wf_1a260571-c25` (16 ajan, 614 araç çağrısı, 45 dk): keşif haritaları backend döngü (17 bağlantı noktası),
EM modeller (21), lokalizasyon (16), frontend (19), mikroservis+paket (16), testler+kapılar (17), kararlar+doküman (23).
Hakem puanları: UX-öncelikli 33 · düşük-risk artımlı 32/30 · mimari-temiz 30,5/29 → kazanan UX-öncelikli; düşük-risk
planından aşılananlar: `hedefKumesi` prop'u (panele hook sokulmaz), kedi golden, bölünmüş yayın kadansı, OOD satırı,
409 seans-aktif kuralı, sağlayıcı bazlı join timeout; mimari-temiz plandan: `MODELLER_PROFILE_GORE` tek kaynak,
`(0..6)` literal sıfır kapısı, güven vekili yapısal red, mikroservis parite testi, `varsayilan_hedef`.
Eleştiri: 51 bulgu (3 P0: hazırlık ucu mutasyonu, mobil hazırlıkta model yolu ×2; P1'ler: clip yeri, mobil intrinsics,
coord_transform paylaşımı, hedef takibi kapıları, pipeline enjeksiyonu, PYZ import, CI stub, bayrak taşıyıcısı,
var olmayan 'Ayarlar → Model paketleri' ekranı, petri metinleri, hedef-kaybı metni) — hepsi bu plana işlendi.

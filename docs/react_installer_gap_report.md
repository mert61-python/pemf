# React Installer Eksik Analiz Raporu

Tarih: 2026-06-04

## Kapsam

Bu rapor `build_tools\build_installer.ps1` ile uretilen setup kurulduktan sonra React tarafinda gorulen eksikleri inceler:

- Akilli Teshis / AI modulleri
- Fotograf yukleme ile analiz
- DEMA simulatör iframe ekrani
- Installer ve runtime frontend paketleme akisi

## Ozet Sonuc

Sorun tek bir React butonu degil. Kurulum paketinde React, backend ve statik asset yollarinin release modu icin birlikte dogrulanmadigi goruluyor.

En kritik kok nedenler:

1. `build_installer.ps1` React web export adimini calistirmiyor. Paket ne zaman uretilirse, o anda `frontend\dist` icinde hangi eski bundle varsa o kuruluma giriyor.
2. Uygulama acilista `APPDATA\PEMF_GUI\frontend_dist` klasorunu bundled frontend'den once kullaniyor. Ayrica `FrontendUpdaterThread` uzak zip indirip bu klasoru degistirebiliyor. Bu nedenle installer icindeki frontend dogru olsa bile runtime'da farkli/ eski frontend calisabiliyor.
3. DEMA simulatör PyInstaller ile `{app}\_internal\dema-terapi-simülatörü\dist` altina giriyor; backend ise `os.getcwd()\dema-terapi-simülatörü\dist` ariyor. Kurulu uygulamada bu yol yanlis oldugu icin `/simulator/index.html` servis edilmiyor ve React iframe gri/kirik belge olarak gorunuyor.
4. AI modelleri opsiyonel component olarak `ProgramData\PEMF_GUI\ai_models` altina kuruluyor; bu makinada modeller mevcut. Ancak AI endpoint hatalari frontend'de sadece genel toast olarak gorunuyor ve FastAPI stdout loglari dosyaya dusmedigi icin kullanici tarafinda tani konulamiyor.
5. Fotograf yukleme akisi web ortaminda daha once image yerine `index.html` gonderiyordu. Kaynak kodda buna karsi duzeltme var; fakat installer/AppData frontend bundle'i yenilenmediyse kullanici hala eski davranisi gorur.

## Kanitlar

### 1. Installer React build almiyor

`build_tools\build_installer.ps1` PyInstaller ve Inno Setup calistiriyor, fakat `frontend` icin `npm run typecheck`, `npx expo export --platform web` veya `frontend\dist` temizleme/dogrulama adimi yok.

Sonuc: Setup, mevcut `frontend\dist` klasorunu oldugu gibi paketliyor.

### 2. Runtime frontend AppData'dan oncelikli servis ediliyor

`servers\frontend_bridge.py` icinde statik root secimi:

```python
app_data_path = Path(os.environ.get("APPDATA", "C:/")) / "PEMF_GUI" / "frontend_dist"
fallback_root = project_root / "frontend" / "dist"
static_root = app_data_path if app_data_path.exists() and (app_data_path / "index.html").exists() else fallback_root
```

Bu davranis nedeniyle `C:\Users\merta\AppData\Roaming\PEMF_GUI\frontend_dist` varsa, kurulumdaki bundled frontend yerine AppData paketi calisir.

Logda da frontend updater davranisi goruluyor:

```text
Frontend Oto-Guncelleyici Basladi. Mevcut Surum: 1.0.0
Frontend guncellemesi basariyla tamamlandi.
...
Frontend Oto-Guncelleyici Basladi. Mevcut Surum: 1.2.4
Frontend zaten guncel.
```

### 3. DEMA simulatör yolu release modda hatali

PyInstaller spec simulatörü su hedefe koyuyor:

```python
datas.append((sim_dir, os.path.join('dema-terapi-simülatörü', 'dist')))
```

Kurulu dosya gercekte burada:

```text
C:\Program Files\PEMF Medical\_internal\dema-terapi-simülatörü\dist\index.html
```

Backend ise su yolu ariyor:

```python
sim_path = os.path.join(os.getcwd(), "dema-terapi-simülatörü", "dist")
```

Kurulu uygulamada `os.getcwd()` genellikle `C:\Program Files\PEMF Medical` oldugu icin backend `C:\Program Files\PEMF Medical\dema-terapi-simülatörü\dist` arar. Dosya `_internal` altinda oldugundan mount yapilmaz. React iframe `/simulator/index.html` isteginde HTML yerine 404/fallback alir.

### 4. AI modelleri var, ama runtime hata yuzeyi zayif

Bu makinada AI modeli component'i kurulmus gorunuyor:

```text
C:\ProgramData\PEMF_GUI\ai_models\ai_hub\cat_landmark\yolo26m-pose.onnx
C:\ProgramData\PEMF_GUI\ai_models\ai_hub\cat_segmentation\yolov8m-seg.onnx
C:\ProgramData\PEMF_GUI\ai_models\ai_hub\cat_thermal\GhostNetV2.onnx
C:\ProgramData\PEMF_GUI\ai_models\ai_hub\feline_reticulocytes\yolov8s.onnx
C:\ProgramData\PEMF_GUI\ai_models\ai_hub\cat_disease\XGBoost.pkl
```

Yani "AI component bos" degil. Buna ragmen moduller calismiyorsa olasi nedenler:

- Eski AppData frontend bundle'i hala hatali upload gonderiyor.
- FastAPI endpoint exception'lari dosyaya structured olarak yazilmiyor.
- React `fetch` hatalarini detayli ekrana basmiyor.
- PyInstaller icinde `ultralytics`, `onnxruntime`, `xgboost` runtime DLL/import hatalari sadece API 500 olarak donuyor olabilir.

### 5. Fotograf yukleme eski bundle'da HTML gonderme hatasi

Daha once backend logunda su gozlenmisti:

```text
DEBUG: Received file size: 1175 bytes
DEBUG: cv2.imdecode returned None. Content starts with: b'<!DOCTYPE html>\n<htm'
```

1175 byte, `frontend\dist\index.html` boyutuyla ayni. Bu, image yerine frontend HTML dosyasinin multipart `file` olarak gittigini gosterir.

Kaynakta bu akisa karsi koruma eklendi; ancak kurulu uygulamanin calistirdigi JS AppData'dan geliyorsa kaynak degisikligi otomatik gecmez.

## Cozum Plani

### A. Build pipeline duzeltmesi

`build_tools\build_installer.ps1` icine PyInstaller'dan once zorunlu React export adimi eklenmeli:

1. `frontend\dist` temizle.
2. `npm ci` veya mevcut lock'a gore dependency dogrula.
3. `npm run typecheck`.
4. `EXPO_ROUTER_DISABLE_RN_NAVIGATION_CHECK=1 npx expo export --platform web`.
5. `frontend\dist\index.html` ve `_expo/static/js/web/*.js` varligini dogrula.
6. Bundle icinde son beklenen fix stringleri veya build marker versiyonu dogrula.

### B. Runtime frontend overwrite kontrolu

`FrontendUpdaterThread` release testlerinde kapatilabilir olmalı:

- `PEMF_DISABLE_FRONTEND_UPDATER=1` env destegi eklenmeli.
- Installer icindeki frontend versiyonu ile AppData versiyonu karsilastirilmali.
- AppData frontend zip'i bozuksa fallback bundled frontend'e donmeli.
- Update zip'i indirildikten sonra `index.html`, JS bundle ve `metadata.json` dogrulanmali.

### C. Statik asset yolu icin tek kaynak

Yeni helper onerisi:

```python
def packaged_resource_path(*parts):
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).parent / "_internal"
    else:
        base = Path(__file__).resolve().parents[1]
    return base.joinpath(*parts)
```

Bu helper hem `frontend_bridge.py` hem `api_server.py` tarafinda kullanilmali.

DEMA mount:

```python
sim_path = packaged_resource_path("dema-terapi-simülatörü", "dist")
```

Frontend fallback:

```python
fallback_root = packaged_resource_path("frontend", "dist")
```

### D. AI endpoint gozlemlenebilirligi

`servers\ai_router.py` icinde her endpoint:

- model path'i loglamali,
- import/model load hatasini loglamali,
- image decode hatasinda content-type, filename ve ilk bytes bilgisini loglamali,
- frontend'e `detail` olarak teknik ama anlasilir hata dondurmeli.

React tarafinda:

- `response.ok` degilse `data.detail` ekranda gorunmeli.
- "Ag/sunucu hatasi" yerine exception mesaji da toast veya debug panelinde gorunmeli.
- Her AI modul icin endpoint status karti eklenmeli.

### E. Kabul testleri

Setup uretilmeden once otomatik test:

1. `npm run typecheck` basarili.
2. `npx expo export --platform web` basarili.
3. `dist\PEMF_GUI\_internal\frontend\dist\index.html` var.
4. `dist\PEMF_GUI\_internal\dema-terapi-simülatörü\dist\index.html` var.
5. `PEMF_GUI.exe` baslatildiktan sonra:
   - `GET http://127.0.0.1:5050/` 200.
   - `GET http://127.0.0.1:8000/api/health` 200.
   - `GET http://127.0.0.1:8000/simulator/index.html` 200.
   - `POST /api/ai/disease` ornek payload ile 200.
   - `POST /api/ai/vision/landmark` gercek jpg ile image decode basarili.
   - `POST /api/ai/vision/segmentation` gercek jpg ile image decode basarili.
   - `POST /api/ai/vision/thermal` gercek jpg ile image decode basarili.
   - `POST /api/ai/vision/reticulocytes` gercek jpg ile image decode basarili.

## Onceliklendirme

1. DEMA path fix: en dusuk risk, en net bozulan ekran.
2. Build script React export zorunlulugu: setup'a eski frontend girmesini engeller.
3. Frontend updater kontrolu: kurulu paketin uzaktan eski/bozuk frontend ile ezilmesini engeller.
4. AI router logging + React detayli hata yuzeyi.
5. Installer sonrasi smoke test scripti.

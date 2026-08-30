# -*- mode: python ; coding: utf-8 -*-
# =============================================================================
# PEMF HEADLESS BACKEND — PyInstaller (onedir) spec.  Faz 4.
# -----------------------------------------------------------------------------
# GUI spec'inden (PEMF_GUI_onedir.spec) uyarlanmıştır. Farklar:
#   * Giriş noktası  : backend_service.py  (main.py DEĞİL -> GUI hiç paketlenmez)
#   * EXCLUDES        : React'e geçildi → Qt/PyQt/pyqtgraph/PyOpenGL SÖKÜLDÜ (myenv'de
#                       kurulu değil, kaynakta import yok). Yalnız tkinter + matplotlib-Qt defansif.
#   * Korunan         : FastAPI/uvicorn, MQTT, STM32 serial, zeroconf, tüm AI/ML
#                       stack, frontend/dist, dema simülatör, bin/mosquitto
#
# Build (TAM CPython 3.10 venv içinde):
#   pyinstaller build_tools\PEMF_Backend_onedir.spec --noconfirm
# Çıktı: dist\PEMF_Backend\PEMF_Backend.exe  (self-contained, Python gerektirmez)
# Doğrula: dist\PEMF_Backend\PEMF_Backend.exe --port 8000
# =============================================================================
import sys
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, collect_dynamic_libs, copy_metadata, collect_all

# --- Proje dizini ---
spec_dir = os.getcwd()
if os.path.basename(spec_dir) == 'build_tools':
    project_path = os.path.abspath(os.path.join(spec_dir, '..'))
else:
    project_path = spec_dir
if project_path not in sys.path:
    sys.path.insert(0, project_path)

version_file = os.path.join(project_path, 'VERSION')
app_version = open(version_file, encoding='utf-8').read().strip() if os.path.exists(version_file) else '0.0.0'

print("=" * 80)
print("PEMF HEADLESS BACKEND BUILD — PyInstaller spec")
print(f"Proje: {project_path}  | Sürüm: {app_version}")
print("=" * 80)

binaries = []
datas = []

# --- Embedded Python DLL'leri: SADECE embeddable ile build edilirse ekle ---
# Tam CPython 3.10 ile build'de bunlar interpreter'dan gelir; embeddable DLL'i
# karıştırmamak için yalnızca embeddable python ile çalışırken eklenir.
# Build reproducibility (audit P2): embeddable Python yolu artık MAKİNEYE-ÖZGÜ HARDCODE değil;
# build'i çalıştıran yorumlayıcıdan (sys.executable) türetilir (PEMF_EMBED_PYTHON ile override).
# Eskiden başka makinede yol eşleşmeyince DLL'ler SESSİZCE atlanıyordu → eksik DLL → runtime çökme.
embedded_python_dir = os.environ.get('PEMF_EMBED_PYTHON') or os.path.dirname(os.path.abspath(sys.executable))
# Embeddable python'da kritik DLL'ler python.exe YANINDADIR; tam CPython'da DLLs/ altında olduğundan
# bu yolda bulunmaz → eklenmez (yorumlayıcı zaten sağlar). Varlık kontrolü iki durumu da doğru yönetir.
for dll_name in ('sqlite3.dll', 'libffi-7.dll', 'libssl-1_1.dll', 'libcrypto-1_1.dll'):
    dll_path = os.path.join(embedded_python_dir, dll_name)
    if os.path.exists(dll_path):
        binaries.append((dll_path, '.'))
        print(f"[OK] Embedded DLL eklendi: {dll_name}")

# --- Üçüncü-parti veri/lib toplama (AI/ML/web) ---
for pkg in ('numpy', 'pandas', 'mediapipe', 'onnxruntime', 'fastapi', 'uvicorn',
            'starlette', 'pydantic', 'zeroconf', 'xgboost'):
    try:
        datas += collect_data_files(pkg)   # xgboost: 'VERSION' veri dosyasi (eksikse disease 500: No such file _internal\xgboost\VERSION)
    except Exception:
        pass
for pkg in ('numpy', 'torch', 'torchvision', 'xgboost'):
    try:
        binaries += collect_dynamic_libs(pkg)
    except Exception:
        pass
try:
    datas += collect_data_files('torch')
    datas += collect_data_files('torchvision')
    datas += collect_data_files('sympy')
except Exception:
    pass
try:
    datas += copy_metadata('onnx') + copy_metadata('torch') + copy_metadata('ultralytics')
except Exception as e:
    print("Metadata uyarısı:", e)

# ⚠️ PAKET METADATA'SI (2026-08-27 SAHA ARIZASI — kök neden). Modül KODUNU toplamak
# YETMEZ: bir kütüphane çalışma anında `importlib.metadata.version("X")` çağırıyorsa,
# X'in .dist-info'su frozen'a KOPYALANMADIĞI sürece `PackageNotFoundError` alır.
# Ölçülen vaka: scratch/CPN zinciri (celldetection → imageio) EXE'de
# "No package metadata was found for imageio" ile ölüyordu; kullanıcı bunu
# "model paketi gerekli" olarak görüyordu (model diskte KURULUYDU).
# `recursive=True` bağımlılık ağacındaki metadata'yı da toplar → aynı sınıf hata
# yeni AI modüllerinde tekrar etmesin.
#
# ⚠️ DENETİM 2026-08-28 #10 — BU BLOK KENDİ HEDEF PAKETİ İÇİN ÇALIŞMIYORDU. Ölçüldü:
# `recursive=True`, ağaçtaki TEK bir eksik dağıtımda (`opencv-python-headless` — bu ortamda
# kurulu olan `opencv-python`) TÜM çağrıyı `PackageNotFoundError` ile düşürüyor. Sonuç:
# celldetection + albumentations + grad-cam metadata'sı HİÇ toplanmıyordu; yani 27 Ağustos
# arızasını çözmek için yazılan önlem, arızanın paketini kapsamıyordu. `except` sessizce
# yutup build'i yeşil bırakıyordu — kapının kendisi sessiz ölmüştü.
#
# Yeni davranış üç kademeli:
#   1) recursive dene (en geniş kapsam),
#   2) patlarsa DÜZ copy_metadata'ya düş — paketin KENDİ .dist-info'su yine toplanır,
#   3) o da patlarsa: paket ortamda KURULUYSA build'i DÜŞÜR (sessiz atlama yok), kurulu
#      değilse yalnız uyar (isteğe bağlı bağımlılık meşru şekilde yok olabilir).
def _metadata_topla(_pkgler):
    from importlib.metadata import PackageNotFoundError
    from importlib.metadata import version as _surum

    _cikti = []
    for _p in _pkgler:
        try:
            _cikti += copy_metadata(_p, recursive=True)
            continue
        except Exception as _me:
            print(f"[metadata] {_p}: recursive basarisiz ({_me}) -> duz metadata deneniyor")
        try:
            _cikti += copy_metadata(_p)
            print(f"[metadata] {_p}: duz metadata toplandi")
            continue
        except Exception as _me2:
            try:
                _v = _surum(_p)
            except PackageNotFoundError:
                print(f"[metadata] {_p}: ortamda KURULU DEGIL, atlaniyor")
                continue
            raise SystemExit(
                f"[metadata] KRITIK: {_p} {_v} kurulu ama .dist-info toplanamadi ({_me2}). "
                f"Frozen EXE'de importlib.metadata.version('{_p}') PackageNotFoundError verir; "
                f"ilgili AI modulu SESSIZCE olur. Build durduruldu."
            )
    return _cikti


# `onnxruntime`: denetim #10 — metadata'sı yoktu, ultralytics onu 'eksik' sanıp çalışma anında
# `PEMF_Backend.exe -m pip install onnxruntime` ile KENDİNİ alt-süreç olarak başlatıyordu
# (exit 2, model başına ~2,9 sn ve destek mühendisini yanıltan kırmızı log).
datas += _metadata_topla((
    'celldetection', 'imageio', 'scikit-image', 'albumentations',
    'pytorch-lightning', 'torchmetrics', 'timm', 'shap', 'captum',
    'grad-cam', 'librosa', 'scikit-learn', 'onnxruntime', 'pi-heif',
))

# --- SQLCipher (AT-REST ŞİFRELEME) — KRİTİK ---
# treatment_history_db lazy try-except ile import ettiğinden PyInstaller static analizi
# sqlcipher3'ü KAÇIRIR → frozen EXE'de paket eksik bundle olur → `from sqlcipher3 import
# dbapi2` ImportError → kod SESSİZCE düz-metne düşer → hasta PII'si şifresiz diskte (KVKK).
# collect_all ile py dosyaları + derlenmiş _sqlite3 (SQLCipher-bağlı) extension'ı açıkça topla.
try:
    from PyInstaller.utils.hooks import collect_all as _collect_all
    _sc_datas, _sc_bins, _sc_hidden = _collect_all('sqlcipher3')
    datas += _sc_datas
    binaries += _sc_bins
    print(f"[OK] sqlcipher3 toplandı: {len(_sc_datas)} data, {len(_sc_bins)} binary, {len(_sc_hidden)} hidden")
    # NOT: collect_all'da binary 0 OLABİLİR — sqlcipher3'ün native _sqlite3 extension'ı datas/hidden
    # üzerinden gelir (NORMAL, bundle eksik DEĞİL; smoke testleri şifrelemeyi doğruladı). Bu yüzden
    # binary-sayısı kontrolü YOK. Gerçek koruma: (1) aşağıdaki except — collect_all HATA verirse
    # (paket build venv'inde yok) build KIRILIR; (2) runtime'da setup_services.ps1 atRestEncrypted=false
    # ise kurulum HATA verir. İki katmanlı güvenlik, false-positive build-kırma yok.
except Exception as _e:
    # ESKİDEN sadece [UYARI] basıp hiddenimports'a düşerdi → sqlcipher eksik EXE SESSİZCE shiplenirdi.
    # ARTIK HARD FAIL: at-rest şifreleme bu medikal cihaz için ZORUNLU; bundle edilemiyorsa build kırılsın.
    raise SystemExit(
        f"[BUILD FAIL] sqlcipher3 bundle edilemedi: {_e}. at-rest şifreleme ZORUNLU (hasta PII/KVKK). "
        "Build venv'inde 'sqlcipher3==0.6.2' kurulu mu? (pip install sqlcipher3==0.6.2)"
    )

# --- Proje veri dosyaları (headless için gerekli olanlar) ---
# Config + credential dosyaları (ProductionConfigManager ilk açılışta üretir)
config_dir = os.path.join(project_path, 'config')
if os.path.exists(config_dir):
    for root, dirs, files in os.walk(config_dir):
        # GÜVENLİK (P0 audit 2026-06-28): config/credentials/ GERÇEK MQTT/HiveMQ/ESP
        # şifrelerini içerir (hivemq_users.json, mosquitto_passwords.txt, secrets_coil_*.h,
        # credentials.json). EXE'ye GÖMME → EXE/disk sızıntısı = tüm broker kimlikleri ele
        # geçer = bobin topic'lerine publish = donanım kontrolü. Runtime'da credential_manager
        # ÜRETİR; cloud-cred fill (production_config_manager) dosya yoksa cred_path.exists()
        # ile ZARİFÇE atlar (yalnız cloud-mode; local broker anon).
        if 'credentials' in dirs:
            dirs.remove('credentials')
        for f in files:
            # GÜVENLİK (P1): config.json GERÇEK Gmail App Password içerir; runtime'da
            # %USERPROFILE%\.pemf_gui\config.json okunur (bu bundled dosya DEĞİL) → sırrı
            # EXE'ye GÖMME. Yalnız config.json.template (boş şablon) ve diğer dosyalar bundle'lanır.
            if f == 'config.json':
                continue
            if f.endswith(('.json', '.template', '.conf', '.txt', '.h')):
                datas.append((os.path.join(root, f), os.path.relpath(root, project_path)))

# GÜVENLİK (P0 audit 2026-06-28): data/config.json ESP provisioning sırları içerir
# (wifi_pass/mqtt_user/mqtt_pass DÜZ-METİN) ve runtime'da headless kodca OKUNMUYOR → EXE'ye
# GÖMME. (Eskiden datas.append ile her klinik PC'sine _internal/data/config.json olarak
# düz-metin kopyalanıyordu — P0 disk sızıntısı.)

# ⚠️ İSTİSNA — SAHİP KARARI (2026-08-19 gece): E-stop BULUT AYNASI provizyonu
# (data/cloud_mqtt_provision.json; YALNIZ mqtt_cloud_host/port/user/pass — wifi_pass DEĞİL)
# pakete GÖMÜLÜR ki klinik "web sitesinden indir-kur" ile bulut E-stop'una otomatik kavuşsun.
# Yukarıdaki P0 kararının bu 4 alan için bilinçli tersine çevrilmesidir; maruziyet sınıfı yeni
# değil (aynı HiveMQ kimliği sahadaki her ESP flash'ında + public repo `esp` dalında; rotasyon
# sahiplikçe reddedildi, kayıtta). Dosya git'e GİRMEZ (build-time üretilir:
# build_tools/make_cloud_provision.py); ilk çalışmada pemf_secrets.json'a taşınır (parola DPAPI).
_cloud_prov = os.path.join(project_path, 'data', 'cloud_mqtt_provision.json')
if os.path.exists(_cloud_prov):
    datas.append((_cloud_prov, 'data'))
    print('[spec] cloud_mqtt_provision.json PAKETE GOMULDU (sahip karari 2026-08-19)')
else:
    print('[spec] UYARI: cloud_mqtt_provision.json YOK -> bulut E-stop aynasi paketde devre disi')

for tmpl in ('pemf_treatment_history_template.db', 'patients_template.db'):
    p = os.path.join(project_path, 'database', tmpl)
    if os.path.exists(p):
        datas.append((p, 'database'))

# Mosquitto broker (EXE içinde de bulunsun; ayrıca bağımsız servis de kurulabilir)
mosquitto_dir = os.path.join(project_path, 'bin', 'mosquitto')
if os.path.exists(mosquitto_dir):
    datas.append((mosquitto_dir, 'bin/mosquitto'))

# Dağıtım profilleri (deploy/device.env, deploy/server.env) → setup_services.ps1 -Mode okur
deploy_dir = os.path.join(project_path, 'deploy')
if os.path.exists(deploy_dir):
    datas.append((deploy_dir, 'deploy'))

# cloudflared (opt-in uzaktan erişim tüneli) — REPODA varsa bundle (offline saha için elle eklenir)
cloudflared_dir = os.path.join(project_path, 'bin', 'cloudflared')
if os.path.exists(cloudflared_dir):
    datas.append((cloudflared_dir, 'bin/cloudflared'))

# NSSM (Windows servis sarmalayıcı) — OFFLINE bundle: internetsiz klinikte servis kurulabilsin
# (eskiden setup_services/install scriptleri nssm.cc'den indiriyordu → offline saha kuramıyordu).
nssm_dir = os.path.join(project_path, 'bin', 'nssm')
if os.path.exists(nssm_dir):
    datas.append((nssm_dir, 'bin/nssm'))

# React frontend (FastAPI '/' kökünden serve eder)
# ⚠️ KAYNAK DİZİN = 'pf' (2026-08-15). Eskiden 'frontend' okunuyordu ve `guii/` altında AYNI
# deponun İKİ klonu vardı (`pf/` geliştirilen, `frontend/` build'in okuduğu). İkisi de
# .gitignore'da olduğu için ayrışma görünmüyordu; ölçüldü: `frontend/` 15 commit GERİDE →
# arayüz düzeltmeleri masaüstü paketine HİÇ ulaşmıyordu. İkinci klon kaldırıldı,
# tests/test_frontend_tek_kaynak.py tekrarını kilitliyor. (Paket İÇİ yol 'frontend/dist'
# olarak KALIR — backend ve launcher orayı arar; değişen yalnız KAYNAK dizin.)
frontend_dir = os.path.join(project_path, 'pf', 'dist')
if os.path.exists(frontend_dir):
    datas.append((frontend_dir, os.path.join('frontend', 'dist')))

# Kurulu sürüm bilgisi (update_manager RUNTIME'da okur → oto-güncelleme sürüm karşılaştırması)
# DENETİM 2026-08-04 (P2): `VERSION` (backend/installer KANALI) bundle EDİLMİYORDU → frozen EXE
# kendi sürümünü okuyamıyor, update_manager `frontend_version.json`'a (frontendOta kanalı, 1.4.x)
# düşüyordu ve bu değer exe kanalının latest.json'ıyla (1.9.x) KARŞILAŞTIRILIYORDU. İki dosya da
# bundle edilir; okuma sırası servers/update_manager.py::_version_paths()'te VERSION önceliklidir.
ver_txt = os.path.join(project_path, 'VERSION')
if os.path.exists(ver_txt):
    datas.append((ver_txt, '.'))

ver_json = os.path.join(project_path, 'frontend_version.json')
if os.path.exists(ver_json):
    datas.append((ver_json, '.'))

# DEMA simülatör (FastAPI '/simulator')
sim_dir = os.path.join(project_path, 'dema-terapi-simülatörü', 'dist')
if os.path.exists(sim_dir):
    datas.append((sim_dir, os.path.join('dema-terapi-simülatörü', 'dist')))

# web_static / templates (varsa servis edilebilir küçük kaynaklar)
for dir_name in ('web_static', 'templates'):
    d_path = os.path.join(project_path, dir_name)
    if os.path.exists(d_path):
        datas.append((d_path, dir_name))

# AI HUB (inference KODU + küçük .pkl/.json). Büyük ONNX'ler aşağıda ai_models ağacıyla gömülür.
# KAYNAK ŞİFRELEME PAROLASI (2026-08-06) — `build_tools/_static_password.py` varsa EXE'ye
# `pemf_source_key` adıyla gömülür; `utils/source_crypto.read_password()` onu arar.
# YOKSA sessizce atlanır → şifresiz build normal çalışır (geliştirme akışı bozulmaz).
# ⚠️ Parola üründe gider: kopyalamayı zorlaştırır, tersine mühendisliği ENGELLEMEZ.
_pw_src = os.path.join(project_path, 'build_tools', '_static_password.py')
if os.path.exists(_pw_src):
    datas.append((_pw_src, '.'))
    print('[OK] kaynak sifreleme parolasi EXE ye gomuldu (pemf_source_key)')
else:
    print('[..] _static_password.py yok -> kaynak sifreleme KAPALI (duz .py kalir)')

ai_hub_dir = os.path.join(project_path, 'ai_hub')
if os.path.exists(ai_hub_dir):
    for root, _, files in os.walk(ai_hub_dir):
        if 'results' in root.split(os.sep):
            continue
        for f in files:
            full = os.path.join(root, f)
            rel = os.path.relpath(root, project_path)
            if f.endswith(('.py', '.json', '.txt', '.yaml', '.yml')):
                datas.append((full, rel))
            # ⚠️ .npz ŞART (düşman-doğrulama 2026-08-27): xai_ref_stats.npz'ler (EM canlı XAI
            # referansları) bu listede olmadığı için frozen EXE'ye HİÇ girmiyordu → üretimde
            # em_kedi/fantom/petri xaiSensitivity sessizce üretilemiyordu (zarif düşüş maskeledi).
            elif f.endswith(('.pkl', '.onnx', '.npy', '.npz')) and os.path.getsize(full) < 5 * 1024 * 1024:
                datas.append((full, rel))

# TÜM AI MODELLERİNİ EXE'YE GÖM (Hugging Face KALDIRILDI → self-contained; ProgramData staging'e
# bağımlı kalma). release_assets/ai_models/** → _internal/ai_models/** ; download_model_sync /
# find_installed_model resource_path("ai_models") köküyle bundle'dan çözer. Akıllı Teşhis + AI Pro
# modellerinin TAMAMI (landmark/disease/segmentation/thermal/reticulocytes/em_*/cat_*/kidney_*/
# histopath/cat_organ + em_kedi) EXE içinde taşınır. Bundle ~+2.1GB büyür.
#
# PEMF_EMBED_MODELS=0 → GÖMME (varsayılan 1 = mevcut davranış, Windows/Linux build'leri
# BİREBİR aynı kalır). Neden gerekli: yayındaki base.zip (1.29 GB, 6191 dosya) ai_models
# İÇERMİYOR — modeller launcher'ın ayrıca indirdiği profil paketlerinden (home/vet/research)
# geliyor ve o zip'lerdeki dosyalar release_assets/ai_models ile BİREBİR AYNI (boyutları
# eşleştirildi). Gömülü build'de kullanıcı aynı 2.1 GB'ı İKİ KEZ indirir ve profil ayrımı
# anlamsızlaşır (vet kullanıcısında research modelleri de bulunur). Yeni platformlar
# (macOS/Linux) yayındaki Windows base'iyle aynı hizada kalsın diye bayrak eklendi.
_embed_models = os.environ.get('PEMF_EMBED_MODELS', '1') != '0'
ai_models_src = os.path.join(project_path, 'release_assets', 'ai_models')
if not _embed_models:
    print("[BILGI] PEMF_EMBED_MODELS=0 -> ai_models GOMULMEDI (modeller profil paketlerinden iner).")
elif os.path.exists(ai_models_src):
    _nmodel = 0
    for root, _, files in os.walk(ai_models_src):
        for f in files:
            full = os.path.join(root, f)
            sub = os.path.relpath(root, ai_models_src)
            rel = 'ai_models' if sub == '.' else os.path.join('ai_models', sub)
            datas.append((full, rel))
            _nmodel += 1
    print(f"[OK] ai_models EXE'ye gomuldu: {_nmodel} dosya ({ai_models_src})")
else:
    print(f"[UYARI] ai_models kaynagi YOK: {ai_models_src} -> modeller GOMULMEDI!")

# --- Bloat filtresi ---
def filter_bloat(items):
    bad_ext = ('.lib', '.a', '.pdb', '.h', '.c', '.cpp', '.md')
    bad_dir = ('test', 'tests', 'testing', 'docs')
    out = []
    for it in items:
        s = it[0].lower()
        if s.endswith(bad_ext):
            continue
        if any(f"\\{n}\\" in s or f"/{n}/" in s for n in bad_dir):
            continue
        out.append(it)
    return out

datas = filter_bloat(datas)
binaries = filter_bloat(binaries)
print(f"Toplam: {len(binaries)} binary, {len(datas)} data")

# --- Hidden imports: SADECE headless paketler (GUI paketleri toplanmaz) ---
hidden = []
for pkg in ('controllers', 'services', 'database', 'servers', 'utils', 'ai',
            'ai_hub', 'cryptography', 'numpy',
            # sklearn: pickled preprocessor/scaler nesneleri unpickle'da sklearn.impute /
            # sklearn.compose / sklearn.pipeline gibi alt modülleri ister; statik import'ta
            # görünmediği için TÜM sklearn toplanmalı (CKD ColumnTransformer "No module
            # named 'sklearn.impute'" hatası). Geleceğe dönük tüm pickled sklearn için.
            'sklearn',
            # XAI Faz 1 (2026-08-26): ai_hub/xai_tabular lazy-import'lari statik analizde
            # gorunmez — shap (Tree/Kernel explainer) + slicer frozen'a acikca toplanir.
            'shap', 'slicer',
            # XAI Faz 2 (2026-08-26): ses/termal Grad-CAM — pytorch_grad_cam + timm
            # (+ttach/safetensors) lazy import; karar #2 geregi klinik CPU yolunda da var.
            'pytorch_grad_cam', 'timm', 'ttach', 'safetensors', 'captum',
            # Scratch/Yara-Kapanma (2026-08-26, KARAR 0.1 docs/scratch-entegrasyon-plani.md):
            # celldetection frozen'a BILEREK girer (sahip karari; deps 6. degisim).
            # ai_hub/inference_paper_dilek_hoca lazy-import eder — statikte gorunmez.
            # ⚠️ transitifleri agir (pytorch-lightning/tensorboard/albumentations);
            # albumentations opencv-python-headless CEKER → cift-cv2 tuzagi:
            # myenv kurulumunda headless KALDIRILIP opencv-python force-reinstall edilir
            # (requirements.txt'teki olculmus kural — grad-cam dersiyle ayni).
            'celldetection'):
    try:
        hidden += collect_submodules(pkg)
    except Exception:
        pass

# cat_sound (ses) deps: librosa mel-spektrogram → numba/llvmlite JIT + soundfile
# (libsndfile DLL) + audioread + imageio_ffmpeg (ffmpeg.exe binary). collect_all
# submodül+data+binary'yi TOPLAR (numba/llvmlite/ffmpeg frozen'da çalışsın diye ŞART).
for _apkg in ('librosa', 'soundfile', 'audioread', 'imageio_ffmpeg',
              'numba', 'llvmlite', 'lazy_loader', 'pooch', 'soxr', 'msgpack'):
    try:
        _ad, _ab, _ah = collect_all(_apkg)
        datas += _ad
        binaries += _ab
        hidden += _ah
    except Exception as _ae:
        print(f"[SES] collect_all({_apkg}) atlandı: {_ae}")

# numba/llvmlite DERLENMİŞ uzantıları (.pyd) — collect_all/collect_dynamic_libs Windows'ta
# .pyd'yi ATLIYOR → frozen'da "cannot import name '_typeconv' from numba.core.typeconv".
# Tüm .pyd'leri paket-göreli yapıyı koruyarak elle binaries'e ekle.
import glob as _glob
import importlib.util as _ilu
for _cext_pkg in ('numba', 'llvmlite', 'soxr'):
    try:
        _sp = _ilu.find_spec(_cext_pkg)
        # SADECE paket (origin=__init__.py) — tek-modülde (soundfile.py) base=site-packages
        # olur ve TÜM site-packages'i tarar (yanlış). soundfile DLL'i collect_all halleder.
        if not _sp or not _sp.origin or not _sp.origin.endswith('__init__.py'):
            continue
        _pbase = os.path.dirname(_sp.origin)
        _proot = os.path.dirname(_pbase)
        for _pyd in _glob.glob(os.path.join(_pbase, '**', '*.pyd'), recursive=True):
            binaries.append((_pyd, os.path.relpath(os.path.dirname(_pyd), _proot)))
    except Exception as _ce:
        print(f"[SES] {_cext_pkg} .pyd toplama hatası: {_ce}")

hidden += [
    'event_bus', 'headless_core', 'backend_service',
    # ⚠️ FELAKET KURTARMA (2026-08-09 denetimi, ENGEL): `PEMF_Backend.exe --kurtarma ...`
    # bunu çağırır. Pakete girmezse, makinesi ölmüş bir veteriner elinde yedek + kurtarma kodu
    # olmasına rağmen zarfı AÇAMAZ (sahada Python yok). Yalnız `tools.kurtarma` bundle edilir;
    # tools/ altındaki diğer araçlar geliştirme içindir.
    'tools', 'tools.kurtarma',
    # web
    'fastapi', 'uvicorn', 'uvicorn.logging', 'uvicorn.loops', 'uvicorn.loops.auto',
    'uvicorn.protocols', 'uvicorn.protocols.http', 'uvicorn.protocols.http.auto',
    'uvicorn.protocols.websockets', 'uvicorn.protocols.websockets.auto',
    'uvicorn.lifespan', 'uvicorn.lifespan.on', 'starlette', 'pydantic',
    'multipart', 'python_multipart', 'websockets',
    # mqtt / net / serial
    'paho.mqtt', 'paho.mqtt.client', 'paho.mqtt.publish', 'paho.mqtt.subscribe',
    'paho.mqtt.enums', 'paho.mqtt.properties', 'paho.mqtt.reasoncodes',
    'paho.mqtt.packettypes', 'paho.mqtt.matcher',
    'zeroconf', 'serial', 'serial.tools', 'serial.tools.list_ports',
    # serial_for_url handler'ları (socket:// STM-simülatör/uzak-seri + rfc2217): PyInstaller dinamik
    # import'u kaçırır → frozen'da serial_for_url("socket://...") ImportError. Açıkça bundle et.
    'serial.urlhandler', 'serial.urlhandler.protocol_socket', 'serial.urlhandler.protocol_rfc2217',
    'serial.urlhandler.protocol_loop',
    'sqlite3', '_sqlite3', 'sqlcipher3', 'sqlcipher3.dbapi2',
    # images
    'PIL', 'PIL.Image',
    # AI / ML
    'cv2', 'onnx', 'onnx.defs', 'onnxruntime', 'onnxruntime.capi',
    'onnxruntime.capi._pybind_state', 'ultralytics',
    'torch', 'torch._C', 'sympy', 'mpmath', 'torchvision', 'torchvision.ops',
    'sklearn', 'sklearn.neighbors', 'sklearn.preprocessing', 'sklearn.ensemble',
    'sklearn.tree', 'sklearn.tree._tree', 'sklearn.utils', 'sklearn.utils._weight_vector',
    'xgboost', 'xgboost.sklearn', 'xgboost.core',
    'scipy', 'scipy.special', 'scipy.special._ufuncs', 'scipy.spatial',
    'scipy.spatial.transform', 'scipy.stats', 'scipy.linalg', 'scipy.sparse',
    'pandas', 'pandas._libs', 'pandas._libs.tslibs', 'pandas._libs.tslibs.base',
    'numpy._core', 'numpy._core._multiarray_umath', 'numpy.core._multiarray_umath',
    # cloud sync (offline-first Supabase)
    'supabase', 'postgrest', 'realtime', 'storage3', 'supabase_auth',
    # matplotlib SADECE Agg (Qt backend yok) — PDF/rapor grafikleri için
    'matplotlib', 'matplotlib.pyplot', 'matplotlib.backends.backend_agg',
    # misc
    'joblib', '_cffi_backend', 'pkg_resources', 'xml.parsers.expat', '_ctypes',
    # first-party: pemf_gui.config headless'te kullanılıyor (database.patient_database)
    'pemf_gui', 'pemf_gui.config',
]
hidden += _sc_hidden if '_sc_hidden' in dir() else []  # sqlcipher3 submodulleri
hidden = list(dict.fromkeys(hidden))  # dedup

a = Analysis(
    [os.path.join(project_path, 'backend_service.py')],
    pathex=[project_path],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden,
    hookspath=[spec_dir],
    hooksconfig={'matplotlib': {'backends': ['Agg']}},
    runtime_hooks=[],
    excludes=[
        # --- GUI: React'e geçildi → Qt/PyQt/pyqtgraph/PyOpenGL TAMAMEN SÖKÜLDÜ.
        # Bu paketler myenv'de KURULU DEĞİL ve kaynakta İMPORT EDİLMİYOR → zaten paketlenemez;
        # exclude satırlarına gerek kalmadı. Defansif kalanlar: tkinter (stdlib) + matplotlib'in
        # Qt backend'leri, ki matplotlib/cv2 transitif bir GUI backend çekmesin (matplotlib
        # yalnız Agg — aşağıdaki hooksconfig ile zorlanıyor). pemf_gui exclude EDİLMEZ:
        # pemf_gui.config headless'te (database.patient_database) kullanılıyor.
        'tkinter',
        'matplotlib.backends.backend_qt5agg', 'matplotlib.backends.backend_qtagg',
        'matplotlib.backends.backend_qt',
        # --- ağır/gereksiz ---
        'tensorflow', 'tensorboard', 'keras', 'torchaudio', 'networkx', 'triton',
        'IPython', 'notebook', 'polars', 'numba', 'llvmlite', 'gevent',
        'onnxruntime.tools', 'onnxruntime.transformers', 'onnxruntime.training',
        'numpy.f2py', 'numpy.distutils', 'pytest',
        'pandas.tests', 'numpy.tests', 'scipy.tests', 'matplotlib.tests',
    ],
    noarchive=False,
    optimize=0,
)

# torch/torchvision .py kaynaklarını at (boyut)
#
# ⚠️ DENETİM 2026-08-28 #07(a): eski filtre `'torch' in x[0].lower()` idi ve YOL-ÇIPASIZ olduğu
# için `ai_hub/xai_tabular/ig_torch.py`yi de yiyordu (adında "torch" geçiyor). ÖLÇÜLDÜ: o modül
# sevk ağacında HİÇ yoktu (compile_pyd hedef listesi 65, ig_torch orada değil), yalnız PYZ'de
# bytecode olarak yaşıyordu. `inference_human_kidney_rna.py:219` onu canlı XAI yolunda lazy
# import eder — yani aşağıdaki PYZ temizliği bu düzeltme OLMADAN yapılsaydı, RNA gen-katkısı
# açıklaması sahada sessizce ölecekti. (Kapı: scripts/sevk_agaci_ai_hub_kapisi.py)
def _torch_kaynagi_mi(hedef: str) -> bool:
    """YALNIZ torch/torchvision paket KÖKÜNDEKİ .py kaynakları (boyut için atılır)."""
    p = hedef.replace('\\', '/').lower()
    return p.endswith('.py') and (p.startswith('torch/') or p.startswith('torchvision/'))


a.datas = [x for x in a.datas if not _torch_kaynagi_mi(x[0])]

# ⚠️ DENETİM 2026-08-28 #07(b) — KOD KORUMASININ ASIL KAPISI.
# `collect_submodules('ai_hub')` ai_hub'ın tüm modüllerini `a.pure`'a, oradan da PYZ arşivine
# BYTECODE olarak gömüyordu; `compile_pyd.py` ise yalnız DİSKTEKİ .py'leri .pyd'ye çevirip
# siliyordu. PyInstaller 6'da `PyiFrozenFinder` aynı dizin için ÖNCE PYZ'ye bakar, orada YOKSA
# python'un FileFinder'ına düşer → PYZ diski HER ZAMAN yener.
#
# ÖLÇÜLDÜ (sevk edilen 1.9.31 EXE'si, çalışan süreçte): yüklü ai_hub `.pyd` sayısı 1/65 — ve o
# tek modül tam olarak `cat_segmentation`, yani PYZ'de ikizi OLMAYAN tek modül. Doğal deney:
# 64 `.pyd` hiç yüklenmiyordu, Cython katmanının koruma katkısı SIFIRDI. EXE'nin PYZ'sinden
# okunabilir bytecode çıkarıldı (docstring + fonksiyon adları dahil), dört koruma kapısı da
# yeşil yanıyordu çünkü dördü de yalnız "DİSKTE düz .py var mı" diye soruyordu.
#
# ai_hub PYZ'den ÇIKARILIR → import zorunlu olarak diskteki .pyd/.pyenc'e düşer.
# ⚠️ YERİNDE (dilim) atama ŞART: PYZ, kod önbelleğini `id(a.pure)` ile arar
# (build_main.py:953 → api.py:109). Listeyi yeniden bağlarsan önbellek düşer ve tüm PYZ
# kaynaklardan yeniden derlenir (build belirgin şekilde yavaşlar).
a.pure[:] = [x for x in a.pure if x[0].split('.')[0] != 'ai_hub']
_ai_kalan = [x[0] for x in a.pure if x[0].split('.')[0] == 'ai_hub']
assert not _ai_kalan, f"ai_hub HALA PYZ'de ({len(_ai_kalan)} giris): {_ai_kalan[:5]}"
print('[KORUMA] ai_hub PYZ disi birakildi -> import diskteki .pyd/.pyenc e duser')

pyz = PYZ(a.pure)

_icon = os.path.join(project_path, 'pemf_gui', 'resources', 'icons', 'pemf_heart_emf_icon.ico')
_version = os.path.join(project_path, 'docs', 'version_info.txt')

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='PEMF_Backend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,                 # servis: NSSM stdout/stderr'i yakalar
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    icon=_icon if os.path.exists(_icon) else None,
    version=_version if os.path.exists(_version) else None,
    uac_admin=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name='PEMF_Backend',
)

print("\n" + "=" * 80)
print(f"HEADLESS BACKEND build hazır: {len(binaries)} binary, {len(datas)} data, {len(hidden)} hidden import")
print("Çıktı: dist/PEMF_Backend/PEMF_Backend.exe")
print("=" * 80)

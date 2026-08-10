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
frontend_dir = os.path.join(project_path, 'frontend', 'dist')
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
            elif f.endswith(('.pkl', '.onnx', '.npy')) and os.path.getsize(full) < 5 * 1024 * 1024:
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
            'sklearn'):
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
a.datas = [x for x in a.datas if not (('torch' in x[0].lower() or 'torchvision' in x[0].lower()) and x[0].endswith('.py'))]

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

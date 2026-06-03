# -*- mode: python ; coding: utf-8 -*-
import sys
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, collect_dynamic_libs, copy_metadata

# ---------------------------------------------------------------------------
# UPX İÇİN ÖZEL FILTRE FONKSİYONU
# ---------------------------------------------------------------------------
def should_exclude_from_upx(filename):
    """
    .NET DLL'leri ve sorunlu dosyaları UPX'ten hariç tut.
    UPX bazı dosyaları sıkıştıramaz (CFG protected, .NET managed code vb.)
    """
    exclude_patterns = [
        # .NET ve Mono
        'System.', 'Unity.', 'UnityEngine.', 'Mono.', 'Assembly-',
        'mscorlib', 'netstandard',
       
        # Unity
        'Cinemachine', 'Timeline', 'VisualScripting',
        
        # Windows Runtime (CFG protected)
        'vcruntime', 'msvcp', 'concrt', 'vccorlib',
        
        # Python
        'python3', 'python39', 'python310',
        
        # Qt6 (CFG protected)
        'Qt6', 'qt6', 'Qt5', 'qt5',
    ]
    
    filename_lower = filename.lower()
    return any(pattern.lower() in filename_lower for pattern in exclude_patterns)

# ---------------------------------------------------------------------------
# ADIM 1: ÇALIŞMA DİZİNİ AYARI
# ---------------------------------------------------------------------------
spec_dir = os.getcwd()
# Eğer current working directory 'build_tools' ise bir üst dizine çıkmalıyız.
if os.path.basename(spec_dir) == 'build_tools':
    project_path = os.path.abspath(os.path.join(spec_dir, '..'))
else:
    project_path = spec_dir

if project_path not in sys.path:
    sys.path.insert(0, project_path)

print("=" * 80)
print("PEMF GUI BUILD - PyInstaller Spec Dosyası (Embedded Python Mode)")
print("=" * 80)
print(f"Spec Dizini: {spec_dir}")
print(f"Proje Dizini: {project_path}")
print("=" * 80)

# ---------------------------------------------------------------------------
# ADIM 2: KRİTİK DLL DOSYALARINI BULMA (EMBEDDED PYTHON)
# ---------------------------------------------------------------------------
binaries = []

# Embedded Python Ana Klasörü
embedded_python_dir = r'C:\Users\merta\Downloads\python-3.10.2-embed-amd64'

print(f"--- DLL Arama Yolu (Embedded Python) ---")
print(f"[OK] Hedef Klasör: {embedded_python_dir}")

# Embedded Python'dan alınacak kesin DLL listesi
embedded_dlls = [
    'sqlite3.dll',
    'libffi-7.dll',
    'libssl-1_1.dll',
    'libcrypto-1_1.dll'
]

dll_found_count = 0
dll_missing_list = []

for dll_name in embedded_dlls:
    dll_path = os.path.join(embedded_python_dir, dll_name)
    if os.path.exists(dll_path):
        if not any(b[0].endswith(dll_name) for b in binaries):
            print(f"[OK] Embedded Klasöründen Eklendi: {dll_name}")
            binaries.append((dll_path, '.'))
            dll_found_count += 1
    else:
        dll_missing_list.append(dll_name)

print(f"\n📊 DLL Özeti: {dll_found_count} eklendi, {len(dll_missing_list)} bulunamadı")
if dll_missing_list:
    print(f"⚠ BULUNAMAYAN DLL'ler: {', '.join(dll_missing_list)}")
    print("  → (Eğer projenizde kullanılmıyorsa bu uyarıyı göz ardı edebilirsiniz)")

print("=" * 80)

# ---------------------------------------------------------------------------
# ADIM 3: DOSYA VE MODÜLLERİ TOPLAMA
# ---------------------------------------------------------------------------
datas = []

# Başarılı olan modüllerin datalarını al
try:
    datas += collect_data_files('numpy')
    binaries += collect_dynamic_libs('numpy')
except: pass
try: datas += collect_data_files('pandas')
except: pass
try: datas += collect_data_files('mediapipe')
except: pass
try:
    datas += collect_data_files('onnxruntime')
except:
    pass

try:
    datas += collect_data_files('fastapi')
    datas += collect_data_files('uvicorn')
    datas += collect_data_files('starlette')
    datas += collect_data_files('pydantic')
except:
    pass

try:
    datas += copy_metadata('onnx')
    datas += copy_metadata('torch')
    datas += copy_metadata('ultralytics')
except Exception as e:
    print("Metadata error:", e)

try:
    datas += collect_data_files('torch')
    binaries += collect_dynamic_libs('torch')
    datas += collect_data_files('torchvision')
    binaries += collect_dynamic_libs('torchvision')
    datas += collect_data_files('xgboost')
    binaries += collect_dynamic_libs('xgboost')
    datas += collect_data_files('sympy')
except Exception as e:
    pass

# Kendi kaynak dosyalarımız
pemf_resources = os.path.join(project_path, 'pemf_gui', 'resources')
if os.path.exists(pemf_resources):
    datas.append((pemf_resources, 'pemf_gui/resources'))

# Styles klasörü (QSS ve design system dosyaları)
styles_dir = os.path.join(project_path, 'styles')
if os.path.exists(styles_dir):
    for root, dirs, files in os.walk(styles_dir):
        for file in files:
            if file.endswith(('.qss', '.py')):
                full_path = os.path.join(root, file)
                rel_dir = os.path.dirname(os.path.relpath(full_path, project_path))
                datas.append((full_path, rel_dir))
    print("[OK] Styles klasörü (QSS + Python) dahil edildi")

# Config dosyaları - SADECE TEMPLATE/DEFAULT VERSIYONLAR
config_templates = ['config.json.template', 'pemf_config.json.template', 'file_inventory.json.template']
for f in config_templates:
    found = False
    for rel_path in [f, os.path.join('config', f), os.path.join('data', f)]:
        search_path = os.path.join(project_path, rel_path)
        if os.path.exists(search_path):
            datas.append((search_path, os.path.dirname(rel_path) if os.path.dirname(rel_path) else '.'))
            print(f"[OK] Config template eklendi: {rel_path}")
            found = True
            break

hivemq_cred = os.path.join(project_path, 'config', 'credentials', 'hivemq_users.json')
if os.path.exists(hivemq_cred):
    datas.append((hivemq_cred, os.path.join('config', 'credentials')))
    print("[OK] HiveMQ Credentials eklendi: config/credentials/hivemq_users.json")

# Database - SADECE BOŞ TEMPLATE (Eğer yoksa, kod çalışma zamanında DB'yi sıfırdan oluşturacaktır)
db_template = os.path.join(project_path, 'database', 'pemf_treatment_history_template.db')
if os.path.exists(db_template):
    datas.append((db_template, 'database'))
    print("[OK] Tedavi geçmişi template DB kullanılıyor.")
else:
    print("ℹ Tedavi geçmişi template bulunamadı, runtime'da otomatik oluşturulacak.")

patients_template = os.path.join(project_path, 'database', 'patients_template.db')
if os.path.exists(patients_template):
    datas.append((patients_template, 'database'))
    print("[OK] Hasta kayıt template DB kullanılıyor.")
else:
    print("ℹ Hasta kayıt template bulunamadı, runtime'da otomatik oluşturulacak.")

# HTML ve Dokümanlar
# NOT: 'lattekurulum' klasörü artık buraya EKLENMİYOR.
# Sürücü kurulumu (VC++ Redist, STM32) artık Inno Setup installer tarafından yapılıyor.
for dir_name in ['templates', 'web_static', 'buildPEMF']:
    d_path = os.path.join(project_path, dir_name)
    if os.path.exists(d_path):
        datas.append((d_path, dir_name))
        print(f"[OK] Klasör eklendi: {dir_name}")

# AI HUB KLASÖRÜ (Tek unified AI dizini: inference kodu + scaler .pkl + onnx)
ai_hub_dir = os.path.join(project_path, 'ai_hub')
if os.path.exists(ai_hub_dir):
    ai_hub_count = 0
    for root, dirs, files in os.walk(ai_hub_dir):
        if 'results' in root.split(os.sep):
            continue
        for file in files:
                if file.endswith(('.py', '.json', '.txt')):
                    full_src_path = os.path.join(root, file)
                    relative_dir = os.path.relpath(root, project_path)
                    datas.append((full_src_path, relative_dir))
                    ai_hub_count += 1
                elif file.endswith('.pkl'):
                    full_src_path = os.path.join(root, file)
                    if os.path.getsize(full_src_path) < 5 * 1024 * 1024:
                        relative_dir = os.path.relpath(root, project_path)
                        datas.append((full_src_path, relative_dir))
                        ai_hub_count += 1
        print(f"[OK] ai_hub: {ai_hub_count} kod dosyası exe içine gömüldü. (ONNX ve büyük PKL'ler runtime'da indirilecek)")
for html_path, dest in [(os.path.join(project_path, 'pemf_optimized_table.html'), '.'),
                        (os.path.join(project_path, 'docs', 'pemf_optimized_table.html'), 'docs')]:
    if os.path.exists(html_path):
        datas.append((html_path, dest))
        break

kullanim_klavuzu = os.path.join(project_path, 'pemf_gui', 'resources', 'docs', 'Kullanim_Klavuzu.pdf')
if os.path.exists(kullanim_klavuzu):
    datas.append((kullanim_klavuzu, 'pemf_gui/resources/docs'))

# ONNX Model Dosyaları artık ai_hub içerisinde bundle ediliyor.
print(f"📦 ONNX modelleri exe bundle'ına dahil edildi.")

# Dataset Klasörü (TAMAMEN ÇIKARILDI - YALNIZCA EĞİTİMDE GEREKLİ)
# 3.37 GB'lık devasa yük engellendi.

# Simülatör Dosyaları
sim_dir = os.path.join(project_path, 'dema-terapi-simülatörü', 'dist')
if os.path.exists(sim_dir):
    datas.append((sim_dir, os.path.join('dema-terapi-simülatörü', 'dist')))

mosquitto_dir = os.path.join(project_path, 'bin', 'mosquitto')
if os.path.exists(mosquitto_dir):
    datas.append((mosquitto_dir, 'bin/mosquitto'))

# FastAPI Frontend Dosyaları
frontend_dir = os.path.join(project_path, 'frontend', 'dist')
if os.path.exists(frontend_dir):
    datas.append((frontend_dir, os.path.join('frontend', 'dist')))


# ---------------------------------------------------------------------------
# ADIM 3.5: GEREKSİZ/AĞIR DOSYALARI FİLTRELEME
# ---------------------------------------------------------------------------
def filter_bloat(item_list, invalid_extensions, invalid_names):
    new_list = []
    for item in item_list:
        src_path = item[0].lower()
        if any(src_path.endswith(ext) for ext in invalid_extensions):
            continue
        # Dizin yollarında mkl, test vs geçiyorsa engelle
        if any(f"\\{name}\\" in src_path or f"/{name}/" in src_path for name in invalid_names):
            continue
        new_list.append(item)
    return new_list

invalid_exts = ['.lib', '.a', '.pdb', '.h', '.c', '.cpp', '.md']
invalid_names = ['test', 'tests', 'testing', 'docs']

print(f"🧹 TEMİZLİK ÖNCESİ: {len(binaries)} Binary, {len(datas)} Data")
datas = filter_bloat(datas, invalid_exts, invalid_names)
binaries = filter_bloat(binaries, invalid_exts, invalid_names)
print(f"🧹 TEMİZLİK SONRASI: {len(binaries)} Binary, {len(datas)} Data")

# ---------------------------------------------------------------------------
# ADIM 4: GİZLİ İÇE AKTARMALAR
# ---------------------------------------------------------------------------
try: windows_modules = collect_submodules('windows')
except: windows_modules = []

try: controllers_modules = collect_submodules('controllers')
except: controllers_modules = []

try: services_modules = collect_submodules('services')
except: services_modules = []

try: database_modules = collect_submodules('database')
except: database_modules = []

try: servers_modules = collect_submodules('servers')
except: servers_modules = []

try: utils_modules = collect_submodules('utils')
except: utils_modules = []

try: pemf_gui_modules = collect_submodules('pemf_gui')
except: pemf_gui_modules = []

try: styles_modules = collect_submodules('styles')
except: styles_modules = []

try: threads_modules = collect_submodules('threads')
except: threads_modules = []

try: ai_modules = collect_submodules('ai')
except: ai_modules = []

try: scripts_modules = collect_submodules('scripts')
except: scripts_modules = []

try: ai_hub_modules = collect_submodules('ai_hub')
except: ai_hub_modules = []

try: crypto_modules = collect_submodules('cryptography')
except: crypto_modules = []

try: numpy_modules = collect_submodules('numpy')
except: numpy_modules = []

# Cryptography zorunlu eklemeleri (Embedded ortamda gözden kaçmasını engellemek için)
hardcoded_crypto = [
    'cryptography', 'cryptography.fernet', 'cryptography.hazmat',
    'cryptography.hazmat.backends', 'cryptography.hazmat.bindings',
    'cryptography.hazmat.primitives', 'cryptography.hazmat.primitives.kdf',
    'cryptography.hazmat.primitives.kdf.pbkdf2', 'cryptography.hazmat.primitives.hashes',
    'cryptography.hazmat.primitives.ciphers', 'cryptography.hazmat.primitives.ciphers.algorithms',
    'cryptography.hazmat.primitives.ciphers.modes', '_cffi_backend',
]
merged_crypto = list(set(crypto_modules + hardcoded_crypto))

hiddenimports = [
    'joblib', 'utils.device_profile', 'utils.hardware_aware_mixin', 'xml.parsers.expat', '_ctypes', 'pkg_resources', 'unittest', 'pytest',
    'onnx', 'onnx.defs', 'onnx.backend', 'onnxsim', 'onnxruntime', 'ultralytics',
] + windows_modules + merged_crypto + controllers_modules + services_modules + database_modules + servers_modules + utils_modules + pemf_gui_modules + styles_modules + threads_modules + ai_modules + scripts_modules + ai_hub_modules + [
    'PyQt6', 'PyQt6.QtCore', 'PyQt6.QtGui', 'PyQt6.QtWidgets', 
    'PyQt6.QtOpenGL', 'PyQt6.QtOpenGLWidgets', 'PyQt6.sip',
    'PyQt6.QtWebEngineCore', 'PyQt6.QtWebEngineWidgets', 'PyQt6.QtWebEngineQuick',
    'matplotlib', 'matplotlib.pyplot', 'matplotlib.figure',
    'matplotlib.backends', 'matplotlib.backends.backend_agg',
    'matplotlib.backends.backend_qt5agg', 'matplotlib.backends.backend_qtagg',
    'matplotlib.backends.backend_qt', 'matplotlib.dates',
    'mpl_toolkits', 'mpl_toolkits.mplot3d',
    'pyqtgraph', 'OpenGL',
    'cv2',
    'torch', 'torch._C', 'sympy', 'mpmath', 'torchvision', 'torchvision.io', 'torchvision.ops', 'torchvision.transforms', 'ultralytics',
] + numpy_modules + [
    'numpy._core', 'numpy._core._multiarray_umath', 'numpy._core.multiarray',
    'numpy._core.numerictypes', 'numpy._core._dtype', 'numpy._core._type_aliases',
    'numpy._core._internal', 'numpy._core.overrides', 'numpy._core.umath',
    'numpy.core._multiarray_umath', 'numpy.core.multiarray', 'numpy.core.numerictypes',
    'pandas', 'pandas._libs', 'pandas._libs.tslibs', 'pandas._libs.tslibs.base',
    'onnxruntime', 'onnxruntime.capi', 'onnxruntime.capi._pybind_state',
    'sklearn', 'sklearn.neighbors', 'sklearn.preprocessing', 'sklearn.ensemble',
    'sklearn.tree', 'sklearn.tree._tree', 'sklearn.utils', 'sklearn.utils._weight_vector',
    'xgboost', 'xgboost.sklearn', 'xgboost.core',
    'scipy', 'scipy.special', 'scipy.special._ufuncs', 'scipy.special.cython_special',
    'scipy.spatial', 'scipy.spatial.transform', 'scipy.stats',
    'scipy.linalg', 'scipy.linalg._fblas', 'scipy.sparse',
    'paho.mqtt', 'paho.mqtt.client', 'paho.mqtt.publish', 'paho.mqtt.subscribe',
    'paho.mqtt.enums', 'paho.mqtt.properties', 'paho.mqtt.reasoncodes',
    'paho.mqtt.packettypes', 'paho.mqtt.matcher',
    'zeroconf', 'event_bus',
    'serial', 'serial.tools', 'serial.tools.list_ports',
    'sqlite3', '_sqlite3',
    'fastapi', 'uvicorn', 'starlette', 'pydantic', 'multipart', 'python_multipart',
]

# ---------------------------------------------------------------------------
# ADIM 5: VERSION INFO
# ---------------------------------------------------------------------------
version_info = {
    'version': '1.0.0.0',
    'company_name': 'PEMF Medical Technologies',
    'file_description': 'PEMF Therapeutic Device Control Software',
    'internal_name': 'PEMF_GUI',
    'legal_copyright': 'Copyright (C) 2026 PEMF Medical Technologies',
    'original_filename': 'PEMF_GUI.exe',
    'product_name': 'PEMF Control Suite',
    'product_version': '1.0.0.0',
}

# ---------------------------------------------------------------------------
# ADIM 6: ANALİZ VE OLUŞTURMA (PRODUCTION-OPTIMIZED)
# ---------------------------------------------------------------------------
a = Analysis(
    [os.path.join(project_path, 'main.py')],
    pathex=[project_path], 
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[spec_dir],
    hooksconfig={'matplotlib': {'backends': ['Qt5Agg', 'QtAgg']}},
    runtime_hooks=[],
    excludes=[
        'networkx', 'triton', 'jinja2.tests', 'IPython', 'notebook',
        'onnxruntime.tools', 'onnxruntime.transformers', 'onnxruntime.training',
        'tensorflow', 'tensorboard', 'keras',
        'PyQt5', 'PySide2', 'PySide6', 'tkinter',
        'gevent', 'numpy.f2py', 'numpy.distutils',
        'pytest', 'matplotlib.tests', 'scipy.tests',
        # --- EKLENEN OPTİMİZASYONLAR (Boyut küçültme) ---
        'torchaudio',
        'PyQt6.QtWebEngine', 'PyQt6.QtWebEngineCore', 'PyQt6.QtWebEngineWidgets',
        'PyQt6.QtQml', 'PyQt6.QtQuick', 'PyQt6.QtQuickWidgets', 'PyQt6.QtQuick3D',
        'polars', 'numba', 'llvmlite',
        # --- Ekstra Test ve Gereksiz Veriler ---
        'pandas.tests', 'numpy.tests', 'numpy.core.tests', 'numpy.distutils.tests', 
        'numpy.random.tests', 'numpy.testing'
    ],
    noarchive=False,
    optimize=0,
)

# (UnityPlayer.dll duplikasyon filtresi iptal edildi, simülatörün çalışması için şart)

# 2. torch ve torchvision içindeki gereksiz binlerce .py kaynak dosyasını çıkar
a.datas = [x for x in a.datas if not (('torch' in x[0].lower() or 'torchvision' in x[0].lower()) and x[0].endswith('.py'))]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='PEMF_GUI',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False, 
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[os.path.join(project_path, 'pemf_gui', 'resources', 'icons', 'pemf_heart_emf_icon.ico')],
    version=os.path.join(project_path, 'docs', 'version_info.txt'),
    uac_admin=False,
    uac_uiaccess=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='PEMF_GUI'
)

# ---------------------------------------------------------------------------
# BUILD ÖZET RAPORU
# ---------------------------------------------------------------------------
print("\n" + "=" * 80)
print("BUILD YAPISI ÖZET (EMBEDDED PYTHON)")
print("=" * 80)
print(f"📁 Proje Dizini: {os.path.basename(project_path)}")
print(f"[OK] Toplam Binary Dosyası (DLL): {len(binaries)}")
print(f"[OK] Toplam Data Dosyası: {len(datas)}")
print(f"[OK] Toplam Hidden Import: {len(hiddenimports)}")
print("\n📦 Embedded Python Kontrolü:")
print(f"  - sqlite3.dll: {'[OK]' if any('sqlite3' in str(b).lower() for b in binaries) else '✗ EKSİK!'}")
print(f"  - libffi-8.dll: {'[OK]' if any('ffi' in str(b).lower() for b in binaries) else '✗ EKSİK!'}")
print(f"  - libssl/crypto: {'[OK]' if any('ssl' in str(b).lower() or 'crypto' in str(b).lower() for b in binaries) else '✗ EKSİK!'}")
print("=" * 80 + "\n")

# -*- mode: python ; coding: utf-8 -*-
import sys
import os
import glob
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

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
        'python3', 'python39',
        
        # Qt6 (CFG protected)
        'Qt6', 'qt6', 'Qt5', 'qt5',
    ]
    
    filename_lower = filename.lower()
    return any(pattern.lower() in filename_lower for pattern in exclude_patterns)

# ---------------------------------------------------------------------------
# ADIM 1: ÇALIŞMA DİZİNİ AYARI
# ---------------------------------------------------------------------------
# Spec dosyası build_tools/ içinde, ama proje root'u bir üst dizin

spec_dir = os.getcwd()
project_path = spec_dir  # Artık doğrudan gui klasörü
if project_path not in sys.path:
    sys.path.insert(0, project_path)

print("=" * 80)
print("PEMF GUI BUILD - PyInstaller Spec Dosyası")
print("=" * 80)
print(f"Spec Dizini: {spec_dir}")
print(f"Proje Dizini: {project_path}")
print("=" * 80)

# ---------------------------------------------------------------------------
# ADIM 2: KRİTİK DLL DOSYALARINI BULMA (AKILLI ARAMA)
# ---------------------------------------------------------------------------
# myenv venv içinde olabilir ama DLL'ler conda base ortamında
# sys.prefix'i kontrol et, DLL yoksa conda ortamına bak
import site

binaries = []

# 1. Aktif Python ortamı (sys.prefix - myenv olabilir)
sys_prefix_dlls = os.path.join(sys.prefix, 'DLLs')
sys_prefix_lib_bin = os.path.join(sys.prefix, 'Library', 'bin')
sys_prefix_scripts = os.path.join(sys.prefix, 'Scripts')

# 2. Conda base ortamı (myenv yoksa DLL'ler buradan)
# site-packages'dan conda yolunu çıkar
conda_env_path = None
for sp in site.getsitepackages():
    if 'conda' in sp and 'envs' in sp:
        # Örnek: C:\Users\merta\.conda\envs\gui\gui\myenv\lib\site-packages -> C:\Users\merta\.conda\envs\gui
        parts = sp.split(os.sep)
        if 'envs' in parts:
            envs_idx = parts.index('envs')
            conda_env_path = os.sep.join(parts[:envs_idx+2])  # .../envs/gui
            break

conda_dlls = os.path.join(conda_env_path, 'DLLs') if conda_env_path else None
conda_lib_bin = os.path.join(conda_env_path, 'Library', 'bin') if conda_env_path else None

print(f"--- DLL Arama Yolları (Aktif Ortam: {os.path.basename(sys.prefix)}) ---")
print(f"✓ Python Prefix: {sys.prefix}")
print(f"1. sys.prefix/DLLs: {sys_prefix_dlls} {'[MEVCUT]' if os.path.exists(sys_prefix_dlls) else '[YOK]'}")
print(f"2. sys.prefix/Library/bin: {sys_prefix_lib_bin} {'[MEVCUT]' if os.path.exists(sys_prefix_lib_bin) else '[YOK]'}")
if conda_env_path:
    print(f"3. Conda env DLLs: {conda_dlls} {'[MEVCUT]' if os.path.exists(conda_dlls) else '[YOK]'}")
    print(f"4. Conda env Library/bin: {conda_lib_bin} {'[MEVCUT]' if os.path.exists(conda_lib_bin) else '[YOK]'}")

# Aranacak kritik dosyalar ve alternatif isimleri
critical_dlls = [
    'libffi-8.dll',                                # _ctypes için KRİTİK (Python 3.14)
    'zlib1.dll',                                   # sıkıştırma
    'sqlite3.dll',                                 # veritabanı - HAYATI ÖNEM
    'libssl-3.dll',                                # SSL - MQTT TLS için KRİTİK (OpenSSL 3.0)
    'libcrypto-3.dll',                             # Kripto - Hashing için KRİTİK (OpenSSL 3.0)
    'libexpat.dll', 'expat.dll',                   # XML parsing - pyexpat için KRİTİK
    'tcl86t.dll', 'tk86t.dll',                     # Tkinter (bazı GUI bileşenleri için)
]

# Sadece mevcut dizinleri ara (myenv + conda)
search_paths = []
if os.path.exists(sys_prefix_dlls):
    search_paths.append(sys_prefix_dlls)
if os.path.exists(sys_prefix_lib_bin):
    search_paths.append(sys_prefix_lib_bin)
if conda_dlls and os.path.exists(conda_dlls):
    search_paths.append(conda_dlls)
if conda_lib_bin and os.path.exists(conda_lib_bin):
    search_paths.append(conda_lib_bin)

dll_found_count = 0
dll_missing_list = []

for dll_name in critical_dlls:
    found = False
    for path in search_paths:
        if not os.path.exists(path):
            continue
            
        full_path = os.path.join(path, dll_name)
        if os.path.exists(full_path):
            print(f"✓ BULUNDU: {dll_name} ({os.path.basename(path)})")
            binaries.append((full_path, '.'))
            found = True
            dll_found_count += 1
            break
    
    if not found:
        # Eğer tam isimle bulunamadıysa glob ile dene (versiyon farklılıkları için)
        pattern = dll_name.split('.')[0] + "*.dll"
        for path in search_paths:
            if not os.path.exists(path): 
                continue
            matches = glob.glob(os.path.join(path, pattern))
            if matches:
                for match in matches:
                    print(f"✓ ALTERNATİF: {os.path.basename(match)} ({os.path.basename(path)})")
                    binaries.append((match, '.'))
                    dll_found_count += 1
                found = True
                break
    
    if not found:
        dll_missing_list.append(dll_name)

print(f"\n📊 DLL Özeti: {dll_found_count} bulundu, {len(dll_missing_list)} eksik")
if dll_missing_list:
    print(f"⚠ EKSİK DLL'ler: {', '.join(dll_missing_list)}")
    print("  → Bu DLL'ler runtime'da sistem PATH'inden yüklenecek")

# ---------------------------------------------------------------------------
# Ek: FFI DLL'lerini kesinlikle dahil et (bazı ortamlarda isim 'ffi.dll' olabilir)
# ---------------------------------------------------------------------------
ffi_patterns = ['*ffi*.dll', 'ffi.dll']
ffi_extra_count = 0
for pattern in ffi_patterns:
    for path in search_paths:
        if not os.path.exists(path):
            continue
        matches = glob.glob(os.path.join(path, pattern))
        if matches:
            for match in matches:
                if (match, '.') not in binaries:
                    print(f"✓ FFI Ek: {os.path.basename(match)} ({os.path.basename(path)})")
                    binaries.append((match, '.'))
                    ffi_extra_count += 1

if ffi_extra_count > 0:
    print(f"📦 {ffi_extra_count} ek FFI DLL eklendi")

print("=" * 80)

# ---------------------------------------------------------------------------
# ADIM 3: DOSYA VE MODÜLLERİ TOPLAMA
# ---------------------------------------------------------------------------
datas = []

# Not: PyQt6, matplotlib, scipy, onnxruntime paket olarak değil modül olarak algılanıyor
# Bu yüzden collect_data_files yerine hiddenimports kullanıyoruz
# Sadece başarılı olanları kullan:
try:
    datas += collect_data_files('numpy')
except:
    pass
try:
    datas += collect_data_files('pandas')
except:
    pass

# Kendi kaynak dosyalarımız
pemf_resources = os.path.join(project_path, 'pemf_gui', 'resources')
if os.path.exists(pemf_resources):
    datas.append((pemf_resources, 'pemf_gui/resources'))

# Styles klasörü (QSS ve design system dosyaları)
styles_dir = os.path.join(project_path, 'styles')
if os.path.exists(styles_dir):
    # QSS dosyalarını ve design system'i dahil et
    for root, dirs, files in os.walk(styles_dir):
        for file in files:
            if file.endswith(('.qss', '.py')):
                full_path = os.path.join(root, file)
                rel_dir = os.path.dirname(os.path.relpath(full_path, project_path))
                datas.append((full_path, rel_dir))
    print("Styles klasörü (QSS + Python) dahil edildi")

# Config dosyaları - SADECE TEMPLATE/DEFAULT VERSIYONLAR (Production için external)
config_templates = [
    'config.json.template',  # Template olarak dahil et
    'pemf_config.json',      # Varsayılan PEMF ayarları
    'file_inventory.json',   # Dosya envanteri (data/ altında da olabilir)
]

# Config dosyalarını hem root hem de config/ altında ara
for f in config_templates:
    found = False
    for rel_path in [f, os.path.join('config', f), os.path.join('data', f)]:
        search_path = os.path.join(project_path, rel_path)
        if os.path.exists(search_path):
            datas.append((search_path, os.path.dirname(rel_path) if os.path.dirname(rel_path) else '.'))
            print(f"Config template eklendi: {rel_path}")
            found = True
            break
    if not found:
        print(f"UYARI: Config template bulunamadı: {f}")

# UYARI: Kullanıcı-spesifik config'ler runtime'da %APPDATA%/PEMF_GUI/ içinde olmalı
# Database - SADECE BOŞ TEMPLATE (Gerçek veri runtime'da oluşturulacak)

# 1. Tedavi Geçmişi Veritabanı Template
db_template = os.path.join(project_path, 'database', 'pemf_treatment_history_template.db')
db_real = os.path.join(project_path, 'database', 'pemf_treatment_history.db')
if os.path.exists(db_template):
    datas.append((db_template, 'database'))
    print("✓ Tedavi geçmişi template DB kullanılıyor (güvenli).")
elif os.path.exists(db_real):
    # Fallback: Mevcut DB varsa kopyala (dikkat: hasta verileri içerebilir!)
    print("⚠ UYARI: Gerçek tedavi DB dahil ediliyor! Production için TEMPLATE oluşturun!")
    print("  Hasta verileri exe içine gömülüyor - GİZLİLİK RİSKİ!")
    datas.append((db_real, 'database'))
else:
    print("⚠ UYARI: Tedavi geçmişi DB dosyası bulunamadı! Runtime'da yeni DB oluşturulacak.")

# 2. Hasta Kayıt Veritabanı Template (YENİ)
patients_template = os.path.join(project_path, 'database', 'patients_template.db')
patients_real = os.path.join(project_path, 'database', 'patients.db')
if os.path.exists(patients_template):
    datas.append((patients_template, 'database'))
    print("✓ Hasta kayıt template DB kullanılıyor (güvenli).")
elif os.path.exists(patients_real):
    print("⚠ UYARI: Gerçek hasta DB dahil ediliyor! Production için TEMPLATE oluşturun!")
    print("  Hasta verileri exe içine gömülüyor - GİZLİLİK RİSKİ!")
    datas.append((patients_real, 'database'))
else:
    print("⚠ UYARI: Hasta kayıt DB dosyası bulunamadı! Runtime'da yeni DB oluşturulacak.")

# HTML ve Dokümanlar
templates_dir = os.path.join(project_path, 'templates')
if os.path.exists(templates_dir):
    datas.append((templates_dir, 'templates'))
    print("Templates klasörü eklendi")
web_static_dir = os.path.join(project_path, 'web_static')
if os.path.exists(web_static_dir):
    datas.append((web_static_dir, 'web_static'))
    print("Web static dosyaları eklendi")
pemf_html = os.path.join(project_path, 'pemf_optimized_table.html')
pemf_html_docs = os.path.join(project_path, 'docs', 'pemf_optimized_table.html')
if os.path.exists(pemf_html):
    datas.append((pemf_html, '.'))
elif os.path.exists(pemf_html_docs):
    datas.append((pemf_html_docs, 'docs'))
    print("PEMF optimized table (docs/) eklendi")
kullanim_klavuzu = os.path.join(project_path, 'pemf_gui', 'resources', 'docs', 'Kullanim_Klavuzu.pdf')
if os.path.exists(kullanim_klavuzu):
    datas.append((kullanim_klavuzu, 'pemf_gui/resources/docs'))
    print("Kullanım Kılavuzu PDF eklendi")

# --- SCRIPTS KLASÖRÜ (generate_user_manual vb.) ---
scripts_dir = os.path.join(project_path, 'scripts')
if os.path.exists(scripts_dir):
    for script_file in os.listdir(scripts_dir):
        if script_file.endswith('.py'):
            script_path = os.path.join(scripts_dir, script_file)
            datas.append((script_path, 'scripts'))
    print("Scripts klasörü eklendi")

# --- UNITY DOSYALARI (Digital Twin) ---
buildPEMF_dir = os.path.join(project_path, 'buildPEMF')
if os.path.exists(buildPEMF_dir):
    print("Unity (buildPEMF) dosyaları ekleniyor...")
    datas.append((buildPEMF_dir, 'buildPEMF'))

# --- ONNX MODEL DOSYALARI (Alt Klasörler Dahil) ---
onnx_model_root = os.path.join(project_path, 'ai', 'models', 'checkpoints')
if os.path.exists(onnx_model_root):
    onnx_count = 0
    # os.walk ile tüm alt dizinleri dolaş (predictor/, autoencoder/, monitor/)
    for root, dirs, files in os.walk(onnx_model_root):
        for file in files:
            if file.endswith('.onnx'):
                full_src_path = os.path.join(root, file)
                # Hedef dizin yapısını koru: ai/models/checkpoints/predictor/best_model.onnx
                relative_dir = os.path.relpath(root, project_path)
                datas.append((full_src_path, relative_dir))
                onnx_count += 1
                print(f"✓ ONNX: {relative_dir}/{file}")
    if onnx_count > 0:
        print(f"📦 Toplam {onnx_count} ONNX model (tüm alt klasörler dahil)")
    else:
        print("⚠ UYARI: Checkpoints klasörü var ama .onnx dosyası bulunamadı!")
else:
    print("⚠ UYARI: ONNX model klasörü bulunamadı: ai/models/checkpoints/")
    print("  AI özellikleri çalışmayabilir!")

# ---------------------------------------------------------------------------
# ADIM 4: GİZLİ İÇE AKTARMALAR
# ---------------------------------------------------------------------------
# Windows modüllerini otomatik topla
try:
    windows_modules = collect_submodules('windows')
    print(f"✓ {len(windows_modules)} windows modülü otomatik toplandı")
except:
    windows_modules = []
    print("⚠ Windows modülleri manuel listelenecek")

hiddenimports = [
    # Sistem
    'xml.parsers.expat', 
    '_ctypes',
    'pkg_resources',
    
    # GUI ve Grafik
    'PyQt6', 'PyQt6.QtCore', 'PyQt6.QtGui', 'PyQt6.QtWidgets', 
    'PyQt6.QtOpenGL', 'PyQt6.QtOpenGLWidgets', 'PyQt6.sip',
    
    # Matplotlib - Tüm kritik modüller
    'matplotlib', 'matplotlib.pyplot', 'matplotlib.figure',
    'matplotlib.backends', 'matplotlib.backends.backend_agg',
    'matplotlib.backends.backend_qt5agg', 'matplotlib.backends.backend_qtagg',
    'matplotlib.backends.backend_qt', 'matplotlib.dates',
    'mpl_toolkits', 'mpl_toolkits.mplot3d',
    
    'pyqtgraph', 'OpenGL', 'OpenGL_accelerate',
    
    # Veri ve Yapay Zeka - Numpy için kritik tüm alt modüller
    'numpy', 'numpy._pyinstaller', 'numpy.core', 
    'numpy.core._multiarray_umath', 'numpy.core.multiarray', 'numpy.core.numerictypes',
    'numpy.core._dtype', 'numpy.core._type_aliases', 'numpy.core._internal',
    'numpy.core.overrides', 'numpy.core.umath', 
    'numpy.fft', 'numpy.linalg', 'numpy.random', 'numpy.ma',
    'numpy.lib', 'numpy.lib.format', 'numpy.distutils',
    
    # Pandas
    'pandas', 'pandas._libs', 'pandas._libs.tslibs', 'pandas._libs.tslibs.base',
    
    # ONNX Runtime
    'onnxruntime', 'onnxruntime.capi', 'onnxruntime.capi._pybind_state',
    
    # Sklearn
    'sklearn', 'sklearn.neighbors', 'sklearn.preprocessing', 'sklearn.ensemble',
    'sklearn.tree', 'sklearn.tree._tree', 'sklearn.utils', 'sklearn.utils._weight_vector',
    
    # Scipy
    'scipy', 'scipy.special', 'scipy.special._ufuncs', 'scipy.special.cython_special',
    'scipy.spatial', 'scipy.spatial.transform', 'scipy.stats',
    'scipy.linalg', 'scipy.linalg._fblas', 'scipy.sparse',
    
    # Ağ ve İletişim
    'paho.mqtt', 'paho.mqtt.client', 'paho.mqtt.publish', 'paho.mqtt.subscribe',
    'paho.mqtt.enums', 'paho.mqtt.properties', 'paho.mqtt.reasoncodes',
    'paho.mqtt.packettypes', 'paho.mqtt.matcher',
    'zeroconf', 'event_bus',
    
    # Database - SQLite için gerekli
    'sqlite3', '_sqlite3',
    
    # Ana Paketler
    'windows', 'database', 'servers', 'utils', 'pemf_gui', 'styles', 'threads', 'ai', 'scripts',
    
    # Scripts Modülleri
    'scripts.generate_user_manual',
    'scripts.migrate_patient_data',
    
    # Windows Modülleri (GUI ekranları)
    'windows.gui_pyqt_v11',
    'windows.splash_screen',
    'windows.sensor_data_window',
    'windows.kpi_dashboard_window',
    'windows.unified_control_window',
    'windows.treatment_history_window',
    'windows.observation_notes_dialog',
    'windows.email_pdf_dialog',
    'windows.ai_mode_controller',
    
    # Utils Modülleri
    'utils.logger_config',
    'utils.patient_input_validator',
    'utils.notification_panel',
    'utils.responsive_utils',
    'utils.metrics_collector',
    'utils.config_manager',
    'utils.production_config_manager',
    'utils.email_sender',
    'utils.email_settings_dialog',
    'utils.error_handler',
    'utils.path_utils',
    'utils.value_utils',
    'utils.pdf_report_generator',
    
    # Database Modülleri
    'database.patient_database',
    'database.treatment_history_db',
    'database.session_manager',
    
    # Threads Modülleri
    'threads.digital_twin_thread',
    'threads.discovery_service_thread',
    'threads.graph_worker',
    'threads.mqtt_thread',
    'threads.portal_checker',
    
    # AI Modülleri - Hybrid Recommender Sistemi
    'ai.hybrid_recommender',
    'ai.config',
    
    # Styles Modülleri - Design System
    'styles.design_tokens',
    'styles.theme_manager',
    'styles.style_builder',
    'styles.mixins',
    'styles.components',
    
    # PEMF GUI Modülleri
    'pemf_gui.config',
    'pemf_gui.serial_manager',
    'pemf_gui.dialogs',
    'pemf_gui.dialogs.serial_dialog',
]

# Windows modüllerini ekle (otomatik toplananlar)
hiddenimports.extend(windows_modules)


# ---------------------------------------------------------------------------
# ADIM 5: VERSION INFO (Endüstriyel Dağıtım için Gerekli)
# ---------------------------------------------------------------------------
version_info = {
    'version': '1.0.0.0',
    'company_name': 'PEMF Medical Technologies',
    'file_description': 'PEMF Therapeutic Device Control Software',
    'internal_name': 'PEMF_GUI',
    'legal_copyright': 'Copyright (C) 2025 PEMF Medical Technologies',
    'original_filename': 'PEMF_GUI.exe',
    'product_name': 'PEMF Control Suite',
    'product_version': '1.0.0.0',
}

print(f"--- Build Info ---")
print(f"Version: {version_info['version']}")
print(f"Product: {version_info['product_name']}")

# ---------------------------------------------------------------------------
# ADIM 6: ANALİZ VE OLUŞTURMA (PRODUCTION-OPTIMIZED)
# ---------------------------------------------------------------------------
a = Analysis(
    [os.path.join(project_path, 'main.py')],
    pathex=[project_path], 
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[spec_dir],  # Custom hooks dizini (paho-mqtt için) - build_tools içinde
    hooksconfig={
        'matplotlib': {
            'backends': ['Qt5Agg', 'QtAgg'],  # PyQt6 backend'leri
        }
    },
    runtime_hooks=[],  # Runtime hooks kaldırıldı
    # Explicitly exclude heavy ML frameworks and optional onnxruntime helpers
    # We DO NOT want to bundle PyTorch into the exe (too large and optional).
    excludes=[
        'torch', 'torchvision', 'torchaudio',
        # Exclude onnxruntime optional transformer/tools modules that import torch
        'onnxruntime.tools', 'onnxruntime.transformers', 'onnxruntime.training',
        'tensorflow', 'tensorboard', 'keras', 
        'PyQt5', 'PySide2', 'PySide6',  # Sadece PyQt6 kullanıyoruz 
        'tkinter', 'IPython', 'notebook', 'gevent',
        # Ek optimizasyon: Test ve debug modülleri
        'unittest', 'pytest', 'nose', 'doctest',
        # Numpy typing circular import fix
        'numpy.typing',
    ],
    noarchive=False,
    optimize=0,  # NumPy add_docstring gereksinimi için docstring'ler korunmalı
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='PEMF_GUI',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX tamamen devre dışı - .NET ve Unity DLL'leri ile uyumsuz
    upx_exclude=[],  # UPX kapalı olduğu için exclude listesi gereksiz
    runtime_tmpdir=None,
    console=False,  # Production build - GUI uygulaması (console penceresi gizli)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    # CODE SIGNING HAZIRLIĞI (Sertifika edindikten sonra aktif edin)
    # Windows için: signtool.exe kullanarak imzalama
    # codesign_identity='SHA1_THUMBPRINT_OF_YOUR_CERTIFICATE',
    codesign_identity=None,  # Şimdilik None (test aşaması)
    entitlements_file=None,
    icon=[os.path.join(project_path, 'pemf_gui', 'resources', 'icons', 'pemf_heart_emf_icon.ico')],
    version=os.path.join(project_path, 'docs', 'version_info.txt'),  # Windows exe properties için version resource dosyası
    uac_admin=True,  # Admin yetkisi iste (serial port ve sistem kaynaklarına erişim için)
    uac_uiaccess=False,
)

# ---------------------------------------------------------------------------
# BUILD ÖZET RAPORU
# ---------------------------------------------------------------------------
print("\n" + "=" * 80)
print("BUILD YAPISI ÖZET")
print("=" * 80)
print(f"🐍 Python Ortamı: {os.path.basename(sys.prefix)}")
print(f"📁 Proje Dizini: {os.path.basename(project_path)}")
print(f"\n✓ Toplam Binary Dosyası (DLL): {len(binaries)}")
print(f"✓ Toplam Data Dosyası: {len(datas)}")
print(f"✓ Toplam Hidden Import: {len(hiddenimports)}")
print("\n📦 Kritik Bileşenler:")
print(f"  - ONNX Modelleri: {'✓ Eklendi' if any('onnx' in str(d) for d in datas) else '✗ EKSİK!'}")
print(f"  - Unity Build: {'✓ Eklendi' if any('buildPEMF' in str(d) for d in datas) else '✗ Yok (opsiyonel)'}")
print(f"  - Database: {'✓ Eklendi' if any('database' in str(d) for d in datas) else '✗ EKSİK!'}")
print(f"  - Styles/QSS: {'✓ Eklendi' if any('styles' in str(d) for d in datas) else '✗ EKSİK!'}")
print(f"  - Templates: {'✓ Eklendi' if any('templates' in str(d) for d in datas) else '✗ Yok'}")
print("\n🔧 DLL Kontrolü:")
print(f"  - sqlite3.dll: {'✓' if any('sqlite3' in str(b).lower() for b in binaries) else '✗ EKSİK!'}")
print(f"  - libffi: {'✓' if any('ffi' in str(b).lower() for b in binaries) else '✗ EKSİK!'}")
print(f"  - ssl/crypto: {'✓' if any('ssl' in str(b).lower() or 'crypto' in str(b).lower() for b in binaries) else '✗ EKSİK!'}")
print("\n⚠ ÖNEMLİ UYARILAR:")
print("  1. Database dosyası gerçek hasta verileri içeriyorsa GİZLİLİK RİSKİ!")
print("  2. Production build için console=False yapın")
print("  3. Code signing için sertifika edinin ve codesign_identity ayarlayın")
print("  4. myenv sanal ortamının aktif olduğundan emin olun!")
print("=" * 80 + "\n")
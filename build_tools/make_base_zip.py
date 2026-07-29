# base.zip'i frozen backend'den kur (frozen .py + taze frontend) + YAPI DOĞRULA (client-kirmasin).
# Yapi: base.zip koku = PEMF_Backend/  (launcher runtime/'e acar -> runtime/PEMF_Backend/PEMF_Backend.exe)
# _internal/ai_models HARIC (profil-zip'lerinde ayri). Scriptler PEMF_Backend/ altina eklenir. ZIP_STORED.
#
# TASINABILIR: tum yollar bu scriptin konumundan (guii\build_tools) turetilir; hard-code C:\ YOK.
#   guii\build_tools\make_base_zip.py  ->  GUII = guii,  DIST = guii\PEMF_BUILD\dist\PEMF_Backend
# Override: python make_base_zip.py [DIST_YOLU]  ( or PEMF_DIST env).  Cikti: guii\pemf-app-packages\base.zip
import zipfile, os, hashlib, tempfile, shutil, sys

HERE = os.path.dirname(os.path.abspath(__file__))
GUII = os.path.dirname(HERE)                                    # guii koku (build_tools'un ustu)
DIST = (sys.argv[1] if len(sys.argv) > 1 else
        os.environ.get('PEMF_DIST') or
        os.path.join(GUII, 'PEMF_BUILD', 'dist', 'PEMF_Backend'))   # varsayilan = guii\PEMF_BUILD (tek-yer)
PARENT = os.path.dirname(DIST)                 # arcname'e PEMF_Backend/ oneki gelsin
OUT = os.path.join(GUII, 'pemf-app-packages', 'base.zip')
SCRIPTS = os.path.join(GUII, 'scripts')
EXCLUDE = 'pemf_backend/_internal/ai_models/'  # kucuk-harf karsilastirma
ADD_SCRIPTS = ['setup_services.ps1', 'start_hotspot.ps1', 'pemf_footprint.ps1', 'pemf_teardown.ps1', 'pemf_uninstall_all.ps1']

if not os.path.isdir(DIST):
    sys.exit('HATA: frozen build yok: %s\n  Once: scripts\\build_backend_exe.ps1 (cikti guii\\PEMF_BUILD)' % DIST)
print('base.zip kuruluyor (ZIP_STORED, ai_models haric)...', flush=True)
print('  DIST =', DIST, flush=True)
n_files = n_skip = 0
with zipfile.ZipFile(OUT, 'w', zipfile.ZIP_STORED, allowZip64=True) as z:
    for root, dirs, files in os.walk(DIST):
        for f in files:
            full = os.path.join(root, f)
            arc = os.path.relpath(full, PARENT).replace('\\', '/')   # PEMF_Backend/...
            if arc.lower().startswith(EXCLUDE):
                n_skip += 1; continue
            z.write(full, arc); n_files += 1
    for s in ADD_SCRIPTS:
        sp = os.path.join(SCRIPTS, s)
        if os.path.exists(sp):
            z.write(sp, 'PEMF_Backend/' + s); n_files += 1
print(f'  yazildi: {n_files} dosya, atlandi (ai_models): {n_skip}', flush=True)

size = os.path.getsize(OUT)
h = hashlib.sha256()
with open(OUT, 'rb') as fp:
    for chunk in iter(lambda: fp.read(1 << 20), b''): h.update(chunk)
sha = h.hexdigest()
print(f'  boyut: {size}  sha256: {sha}', flush=True)

# --- YAPI DOGRULAMA: zip-integrity + extract + kilit yollar ---
print('DOGRULAMA: zip integrity + extract...', flush=True)
with zipfile.ZipFile(OUT) as z:
    bad = z.testzip()
    assert bad is None, f'BOZUK zip girdisi: {bad}'
    names = set(z.namelist())
tmp = tempfile.mkdtemp(prefix='basezip_val_')
try:
    with zipfile.ZipFile(OUT) as z:
        z.extractall(tmp)  # tmp/ = runtime/ benzeri
    checks = {
        'PEMF_Backend/PEMF_Backend.exe (backend_path)': os.path.isfile(os.path.join(tmp, 'PEMF_Backend', 'PEMF_Backend.exe')),
        'PEMF_Backend/_internal/frontend/dist/index.html (frontend)': os.path.isfile(os.path.join(tmp, 'PEMF_Backend', '_internal', 'frontend', 'dist', 'index.html')),
        'PEMF_Backend/_internal/bin/mosquitto/mosquitto.exe': os.path.isfile(os.path.join(tmp, 'PEMF_Backend', '_internal', 'bin', 'mosquitto', 'mosquitto.exe')),
        'ai_models EXCLUDED (olmamali)': not any('/_internal/ai_models/' in n.lower() for n in names),
        'setup_services.ps1 bundled': 'PEMF_Backend/setup_services.ps1' in names,
    }
    allok = all(checks.values())
    for k, v in checks.items():
        print(f'  [{"OK" if v else "FAIL"}] {k}', flush=True)
    print('VALIDATION:', 'PASS' if allok else 'FAIL', flush=True)
    print('BASEZIP_SHA=' + sha, flush=True)
    print('BASEZIP_SIZE=' + str(size), flush=True)
    sys.exit(0 if allok else 1)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

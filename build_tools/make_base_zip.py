# Author: mertaygn, cglrgrkn
# base paketlerini frozen backend'den kur + YAPI DOGRULA (client-kirmasin).
#
# KATMANLI PAKET (2026-08-08, sahip karari "en profesyonel hali"):
#   Eskiden tek base.zip (~1,25 GB) vardi ve TEK SATIRLIK bir yazi degisikligi bile her klinige
#   1,25 GB indiriyordu. Olculdu: paketin ~1,19 GB'i HIC DEGISMEYEN bagimliliklar (torch 271 MB,
#   xgboost 137, cv2 111, llvmlite 85, ffmpeg 84, mediapipe 81, scipy 63, mosquitto/cloudflared 60...),
#   yalniz ~68 MB'i bizim kodumuz (exe + ai_hub .pyd + web arayuzu). Paket ikiye bolundu:
#     base-app.zip   ~68 MB   -> HER surumde degisir (bizim kod)
#     base-deps.zip  ~1,19 GB -> yalniz requirements degisince
#   Siradan bir surum artik 1,25 GB yerine ~68 MB iner.
#
# KENDINI TANIMLAYAN SINIR: app zip'i kendi koklerini `_app_roots.json` icinde tasir. Launcher
# app katmanini guncellerken DISKTEKI eski marker'i okur, o kokleri SILER, sonra yeni app'i acar.
# Boylece yeni surumde KALDIRILAN dosyalar (eski .pyd, eski web bundle parcalari) diskte yasamaz
# ve sinir degisirse launcher'i elle guncellemek gerekmez.
#
# Yapi: zip koku = PEMF_Backend/  (launcher runtime/'e acar -> runtime/PEMF_Backend/PEMF_Backend.exe)
# _internal/ai_models HARIC (profil-zip'lerinde ayri). ZIP_STORED.
#
# TASINABILIR: tum yollar bu scriptin konumundan turetilir; hard-code C:\ YOK.
# Kullanim:  python make_base_zip.py [DIST_YOLU] [--no-monolith]
#
# ⚠️ DENETIM 2026-08-09 (ENGEL) — TEK SURUM, TEK YAZILIM.
# `--monolith` ESKIDEN OPSIYONELDI ve yorumda "normalde GEREKMEZ" yaziyordu. Sonuc olculdu:
# yayindaki base.zip ile base-app+base-deps 53 dosyada FARKLIYDI — PEMF_Backend.exe DAHIL.
# Yani ayni surum numarasi altinda IKI FARKLI YAZILIM dagitiliyordu:
#     client <=1.9.12  -> `runtimes`/`base` okur -> ESKI (bayat) backend
#     client >=1.9.13  -> `layers` okur          -> YENI backend
# Tibbi cihazda bu kabul edilemez: bir sahada bulunan arizanin hangi kodda oldugu bilinemez,
# duzeltme dogrulanamaz. base.zip artik VARSAYILAN olarak her kosuda katmanlarla AYNI
# `app_items + deps_items` kumesinden yeniden uretilir. `--no-monolith` bilinen bir durumda
# (ornegin yalniz katman denemesi) atlamak icindir ve o zaman DISKTEKI bayat base.zip SILINIR —
# yanlislikla eski dosyayi yayinlamak mumkun olmasin.
import hashlib
import json
import os
import shutil
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
GUII = os.path.dirname(HERE)
_args = [a for a in sys.argv[1:] if not a.startswith('--')]
# `--monolith` geriye uyum icin kabul edilir (artik varsayilan); kapatmak icin `--no-monolith`.
MONOLITH = '--no-monolith' not in sys.argv
DIST = _args[0] if _args else os.environ.get('PEMF_DIST') or os.path.join(GUII, 'PEMF_BUILD', 'dist', 'PEMF_Backend')
PARENT = os.path.dirname(DIST)  # arcname'e PEMF_Backend/ oneki gelsin
OUTDIR = os.path.join(GUII, 'pemf-app-packages')
OUT_APP = os.path.join(OUTDIR, 'base-app.zip')
OUT_DEPS = os.path.join(OUTDIR, 'base-deps.zip')
OUT_MONO = os.path.join(OUTDIR, 'base.zip')
SCRIPTS = os.path.join(GUII, 'scripts')
EXCLUDE = 'pemf_backend/_internal/ai_models/'  # kucuk-harf karsilastirma
ADD_SCRIPTS = [
    'setup_services.ps1',
    'start_hotspot.ps1',
    'pemf_footprint.ps1',
    'pemf_teardown.ps1',
    'pemf_uninstall_all.ps1',
]

# ── APP KATMANI SINIRI ────────────────────────────────────────────────────────────────────────
# Bizim urettigimiz, HER surumde degisen seyler. Geri kalan her sey deps'tir.
# NOT: servers/ database/ utils/ ayri dizin olarak GORUNMEZ — PyInstaller onlari .pyc olarak
# PEMF_Backend.exe'nin icine gomer; bu yuzden exe app katmanindadir.
APP_ROOTS_FILE = 'PEMF_Backend/_app_roots.json'
APP_ROOTS = [
    'PEMF_Backend/PEMF_Backend.exe',
    'PEMF_Backend/_internal/ai_hub',
    'PEMF_Backend/_internal/frontend',
    # ⚠️ SURUM DOSYASI APP KATMANINDA OLMALI (2026-08-09 denetimi, Tier 3 tatbikati bulundu).
    # `_internal/VERSION` app kokleri arasinda DEGILDI → deps'e dusuyordu. Sonuc: siradan bir
    # yayin (yalniz app katmani, ~71 MB) surum dosyasini TAZELEMIYORDU. Launcher'in
    # `install::kurulu_surum()`u tam bu dosyayi okur; yani cihaz aylarca eski bir surum numarasi
    # bildirebilir ve GERI CAGIRMA (`min_supported_version`) yanlis surume bakar — duzeltilmis
    # bir cihaz "destek disi" sanilip zorla guncellenir ya da tersi. Surum, tanimi geregi APP'e
    # aittir. Bkz. launcher/core/tests/upgrade_drill.rs::surum_dosyasi_APP_katmaninda.
    'PEMF_Backend/_internal/VERSION',
    # Sinir dosyasi KENDISI de app katmanina aittir. Listede olmazsa launcher onu yedege almaz
    # ve geri alma sinirini okuyamaz -> basarisiz guncelleme geri alinamaz (2026-08-08'de test
    # yakaladi). Launcher ayrica savunma amacli marker'i yedege KOPYALAR; bu satir tutarlilik icin.
    APP_ROOTS_FILE,
] + ['PEMF_Backend/' + s for s in ADD_SCRIPTS]


def _app_katmaninda_mi(arc: str) -> bool:
    a = arc.replace('\\', '/')
    return any(a == r or a.startswith(r + '/') for r in APP_ROOTS)


if not os.path.isdir(DIST):
    sys.exit('HATA: frozen build yok: %s\n  Once: scripts\\build_backend_exe.ps1 (cikti guii\\PEMF_BUILD)' % DIST)

# ── 1) Dosyalari topla ve KATMANA AYIR ────────────────────────────────────────────────────────
app_items, deps_items, n_skip = [], [], 0
for root, dirs, files in os.walk(DIST):
    for f in files:
        full = os.path.join(root, f)
        arc = os.path.relpath(full, PARENT).replace('\\', '/')
        if arc.lower().startswith(EXCLUDE):
            n_skip += 1
            continue
        (app_items if _app_katmaninda_mi(arc) else deps_items).append((full, arc))
for s in ADD_SCRIPTS:
    sp = os.path.join(SCRIPTS, s)
    if os.path.exists(sp):
        app_items.append((sp, 'PEMF_Backend/' + s))

print('Katmanli paket kuruluyor (ZIP_STORED, ai_models haric)...', flush=True)
print('  DIST =', DIST, flush=True)
print(f'  app  : {len(app_items)} dosya', flush=True)
print(f'  deps : {len(deps_items)} dosya   (atlandi ai_models: {n_skip})', flush=True)

# ⚠️ KAYIP DOSYA KAPISI: her dosya TAM BIR katmana gitmeli. Ikisine de girmeyen bir dosya
# kurulumdan SESSIZCE dusper ve backend sahada calismaz. Ayrilma tanim geregi kesisimsiz
# (`_app_katmaninda_mi` ikili karar) — burada TOPLAMI dogruluyoruz.
_toplam = len(app_items) + len(deps_items)
_beklenen = sum(
    1
    for r, d, fs in os.walk(DIST)
    for f in fs
    if not os.path.relpath(os.path.join(r, f), PARENT).replace('\\', '/').lower().startswith(EXCLUDE)
)
_beklenen += sum(1 for s in ADD_SCRIPTS if os.path.exists(os.path.join(SCRIPTS, s)))
if _toplam != _beklenen:
    sys.exit(f'HATA: katmanlara ayirma dosya KAYBETTI/COGALTTI: {_toplam} != {_beklenen}')


# ── BELIRLENIMCI (deterministic) ZIP ──────────────────────────────────────────────────────────
# ⚠️ 2026-08-08'de OLCULDU: base-deps.zip'in BOYUTU birebir ayni kaldigi halde SHA'si her backend
# rebuild'inde DEGISIYORDU. Sebep: zip, dosyalarin MTIME'ini saklar ve PyInstaller her build'de
# tum bagimlilik agacini yeniden yazar (9 farkli zaman damgasi, hepsi o build'in saati).
# Sonuc: icerik hic degismese bile deps katmani "bayat" gorunur ve KATMANLI PAKETIN ASIL KAZANCI
# kaybolur — siradan bir surumde 71 MB yerine yine 1,3 GB yuklemek/indirmek gerekirdi.
# Cozum: girdileri SIRALA + SABIT zaman damgasi + sabit izin bitleri yaz. Boylece sha YALNIZ
# icerige bagli olur. (Zaman damgasi kurulumda kullanilmiyor; acilan dosyalarin tarihi onemsiz.)
SABIT_TARIH = (1980, 1, 1, 0, 0, 0)  # zip formatinin taban tarihi


def _yaz(out, items, extra=None):
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_STORED, allowZip64=True) as z:
        for full, arc in sorted(items, key=lambda x: x[1]):  # sira da belirlenimci olmali
            zi = zipfile.ZipInfo(arc, date_time=SABIT_TARIH)
            zi.compress_type = zipfile.ZIP_STORED
            zi.external_attr = 0o644 << 16
            with open(full, 'rb') as src, z.open(zi, 'w', force_zip64=True) as dst:
                shutil.copyfileobj(src, dst, 1 << 20)
        if extra:
            for arc in sorted(extra):
                zi = zipfile.ZipInfo(arc, date_time=SABIT_TARIH)
                zi.compress_type = zipfile.ZIP_STORED
                zi.external_attr = 0o644 << 16
                z.writestr(zi, extra[arc])
    size = os.path.getsize(out)
    h = hashlib.sha256()
    with open(out, 'rb') as fp:
        for chunk in iter(lambda: fp.read(1 << 20), b''):
            h.update(chunk)
    return size, h.hexdigest()


# app zip'i kendi sinirini tasir → launcher eski kokleri buradan ogrenir.
_roots_json = json.dumps({'roots': APP_ROOTS}, indent=2)
app_size, app_sha = _yaz(OUT_APP, app_items, extra={APP_ROOTS_FILE: _roots_json})
deps_size, deps_sha = _yaz(OUT_DEPS, deps_items)
print(f'  base-app.zip  : {app_size} bayt  sha256 {app_sha}', flush=True)
print(f'  base-deps.zip : {deps_size} bayt  sha256 {deps_sha}', flush=True)

mono_size = mono_sha = None
if MONOLITH:
    print('  tek-parca base.zip (eski client <=1.9.12 icin) uretiliyor...', flush=True)
    mono_size, mono_sha = _yaz(OUT_MONO, app_items + deps_items, extra={APP_ROOTS_FILE: _roots_json})
    print(f'  base.zip      : {mono_size} bayt  sha256 {mono_sha}', flush=True)
elif os.path.exists(OUT_MONO):
    # BAYAT MONOLITH BIRAKMA: diskte kalan eski base.zip, yayin adiminda yanlislikla
    # yuklenirse eski client'lara BAYAT backend gider (bkz. bastaki denetim notu).
    os.remove(OUT_MONO)
    print('  (--no-monolith) diskteki BAYAT base.zip silindi.', flush=True)


def _korumasiz_ai_hub(names):
    """Pakette KORUMASIZ (düz .py) ai_hub modülü var mı? Varsa listesini döner.

    `__init__.py` HARİÇ: paket keşfi ona isimden bakar, derlenmez/şifrelenmez — kasıtlı.
    Bunlar zaten boş/önemsiz dosyalardır, fikri mülkiyet taşımazlar.
    """
    kotu = [
        n
        for n in names
        if '/_internal/ai_hub/' in n.replace('\\', '/').lower()
        and n.lower().endswith('.py')
        and not n.replace('\\', '/').lower().endswith('/__init__.py')
    ]
    if kotu:
        print('\n' + '!' * 74, flush=True)
        print('!! KORUMASIZ KAYNAK: ai_hub icinde duz .py var — PAKETLEME DURDURULDU.', flush=True)
        for n in kotu[:10]:
            print(f'!!   {n}', flush=True)
        if len(kotu) > 10:
            print(f'!!   … +{len(kotu) - 10} dosya', flush=True)
        print('!! Cozum:  python build_tools/compile_pyd.py', flush=True)
        print('!!         (derlenemeyenler icin ayrica: python build_tools/encrypt_sources.py)', flush=True)
        print('!' * 74 + '\n', flush=True)
    return kotu


def _crc_haritasi(yol):
    """zip icindeki ad -> CRC32. Icerik esitligini acmadan, ucuza karsilastirmak icin."""
    with zipfile.ZipFile(yol) as z:
        return {i.filename: i.CRC for i in z.infolist() if not i.is_dir()}


def _monolith_esit():
    """base.zip, base-app + base-deps ile BIREBIR ayni icerigi mi tasiyor?

    Karsilastirma isim kumesi + CRC32 uzerinden yapilir (zip'i acmaya gerek yok). Zaman
    damgalari zaten SABIT_TARIH ile sabitlendiginden, fark = GERCEK icerik farki demektir.
    Monolith uretilmediyse (--no-monolith) dosya diskten SILINMISTIR → karsilastirilacak bir
    sey yok, kapi gecer.
    """
    if not os.path.exists(OUT_MONO):
        return True
    try:
        mono = _crc_haritasi(OUT_MONO)
        katman = _crc_haritasi(OUT_APP)
        katman.update(_crc_haritasi(OUT_DEPS))
    except Exception as e:
        print(f'  !! monolith karsilastirmasi yapilamadi: {e}', flush=True)
        return False
    if mono == katman:
        return True
    eksik = sorted(set(katman) - set(mono))
    fazla = sorted(set(mono) - set(katman))
    farkli = sorted(n for n in (set(mono) & set(katman)) if mono[n] != katman[n])
    print('\n' + '!' * 74, flush=True)
    print('!! base.zip ile base-app+base-deps AYNI DEGIL — ayni surum altinda IKI FARKLI', flush=True)
    print('!! yazilim yayinlanirdi (eski client base.zip, yeni client layers okur).', flush=True)
    for etiket, liste in (('yalniz katmanlarda', eksik), ('yalniz base.zip\'te', fazla), ('ICERIGI FARKLI', farkli)):
        if liste:
            print(f'!!   {etiket}: {len(liste)} dosya', flush=True)
            for n in liste[:5]:
                print(f'!!     {n}', flush=True)
            if len(liste) > 5:
                print(f'!!     … +{len(liste) - 5}', flush=True)
    print('!' * 74 + '\n', flush=True)
    return False


# --- YAPI DOGRULAMA: zip-integrity + iki katmani BIRLIKTE ac + kilit yollar ---
print('DOGRULAMA: zip integrity + katmanli extract...', flush=True)
app_names, deps_names = set(), set()
for out, bucket in ((OUT_APP, app_names), (OUT_DEPS, deps_names)):
    with zipfile.ZipFile(out) as z:
        bad = z.testzip()
        assert bad is None, f'BOZUK zip girdisi ({os.path.basename(out)}): {bad}'
        bucket |= set(z.namelist())

tmp = tempfile.mkdtemp(prefix='basezip_val_')
try:
    # Kurulum sirasi: once deps, sonra app (launcher da boyle yapar).
    for out in (OUT_DEPS, OUT_APP):
        with zipfile.ZipFile(out) as z:
            z.extractall(tmp)
    names = app_names | deps_names
    checks = {
        'PEMF_Backend/PEMF_Backend.exe (backend_path)': os.path.isfile(
            os.path.join(tmp, 'PEMF_Backend', 'PEMF_Backend.exe')
        ),
        'PEMF_Backend/_internal/frontend/dist/index.html (frontend)': os.path.isfile(
            os.path.join(tmp, 'PEMF_Backend', '_internal', 'frontend', 'dist', 'index.html')
        ),
        'PEMF_Backend/_internal/bin/mosquitto/mosquitto.exe': os.path.isfile(
            os.path.join(tmp, 'PEMF_Backend', '_internal', 'bin', 'mosquitto', 'mosquitto.exe')
        ),
        'ai_models EXCLUDED (olmamali)': not any('/_internal/ai_models/' in n.lower() for n in names),
        'setup_services.ps1 bundled': 'PEMF_Backend/setup_services.ps1' in names,
        # ── KOD KORUMASI KAPISI (2026-08-08, sahip ilkesi: "onefile da olsa onedir de olsa
        # client de olsa pyd olmalı") ───────────────────────────────────────────────────
        # Koruma, birinin `compile_pyd.py`'yi çalıştırmayı HATIRLAMASINA bağlı kalmamalı:
        # unutulursa korumasız bir build SESSİZCE yayınlanır ve bunu ancak sahada fark ederiz.
        # Bu kontrol paketlemeyi DURDURUR → koruma prosedürel değil YAPISAL olur.
        'ai_hub KORUMALI (duz .py YOK — pyd/pyenc)': not _korumasiz_ai_hub(names),
        # ── KATMAN KAPILARI (2026-08-08) ────────────────────────────────────────────────
        # Kesisim: ayni dosya iki katmanda olursa hangi surumun kazandigi indirme sirasina
        # kalir — sessiz, teshis edilmesi zor bir karisik-kurulum uretir.
        'katmanlar KESISMIYOR': not (app_names & deps_names - {APP_ROOTS_FILE}),
        # exe app katmaninda olmali; deps'e kacarsa siradan bir surum yine 1,19 GB indirir.
        'exe APP katmaninda': 'PEMF_Backend/PEMF_Backend.exe' in app_names,
        'web arayuzu APP katmaninda': any(n.startswith('PEMF_Backend/_internal/frontend/') for n in app_names),
        'ai_hub APP katmaninda': any(n.startswith('PEMF_Backend/_internal/ai_hub/') for n in app_names),
        'torch DEPS katmaninda': any(n.startswith('PEMF_Backend/_internal/torch/') for n in deps_names),
        'app sinir dosyasi (_app_roots.json) var': APP_ROOTS_FILE in app_names,
        # ── TEK SURUM, TEK YAZILIM KAPISI (2026-08-09 denetimi, ENGEL) ──────────────────
        # Yayindaki base.zip ile base-app+base-deps 53 dosyada FARKLI olcuulmustu (exe dahil):
        # eski client'lar (<=1.9.12) `runtimes`/`base`, yeni client'lar `layers` okudugu icin
        # AYNI surum numarasi altinda IKI FARKLI yazilim dagitiliyordu. Bu kontrol, monolith'in
        # katmanlarin BIREBIR ayni icerigi oldugunu ISPATLAR (isim kumesi + CRC).
        'base.zip == app+deps (icerik birebir)': _monolith_esit(),
    }
    allok = all(checks.values())
    for k, v in checks.items():
        print(f'  [{"OK" if v else "FAIL"}] {k}', flush=True)
    print('VALIDATION:', 'PASS' if allok else 'FAIL', flush=True)
    print('APPZIP_SHA=' + app_sha, flush=True)
    print('APPZIP_SIZE=' + str(app_size), flush=True)
    print('DEPSZIP_SHA=' + deps_sha, flush=True)
    print('DEPSZIP_SIZE=' + str(deps_size), flush=True)
    if mono_sha:
        print('BASEZIP_SHA=' + mono_sha, flush=True)
        print('BASEZIP_SIZE=' + str(mono_size), flush=True)
    sys.exit(0 if allok else 1)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

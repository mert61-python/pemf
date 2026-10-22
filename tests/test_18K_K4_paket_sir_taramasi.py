# -*- coding: utf-8 -*-
"""18K K4 · D3.26 + D3.43 · Y38 — PAKETE SIR GİRMESİN (yayın dosyaları herkese açık depoya çıkar; yayımlanan sır geri alınamaz).

Tek kaynak `build_tools/paket_sir_taramasi.py`; üç çağıran: `make_base_zip` doğrulaması (yerleştirmeden ÖNCE, TÜM katmanlar),
`make_manifest` (sha mühürlenmeden ÖNCE, her yerel paket), Inno `build_installer.ps1` Adım 6.5 (eskiden yalnız UYARI). Y38: bulut E-stop
aynasının kimliği (`cloud_mqtt_provision.json`) pakete GÖMÜLMEZ — spec eklemez, tarama görürse FAIL; izin listesi gerekçeli
(`mosquitto.conf`, `mosquitto_acl.conf`).

Sahteler EN ALT katta: gerçek `make_base_zip` sahte dist ağacında (çıktı `PEMF_PKG_OUT` geçici dizinde — yayın dizinine dokunulmaz),
Inno bloğu GERÇEK metinden çıkarılıp PowerShell 5.1'de koşar, spec sahte PyInstaller ile yürütülür. Belirteçler çalışma anında kurulur
(düşük entropi; depoda belirteç biçimli dizge yok). `make_manifest` KOŞTURULMAZ (ORTAK §1): saf işlev + `main()` sırası ölçülür.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
TARAYICI = KOK / "build_tools" / "paket_sir_taramasi.py"
MAKE_BASE_ZIP = KOK / "build_tools" / "make_base_zip.py"
MANIFEST = KOK / "scripts" / "make_manifest.py"
INNO = KOK / "build_tools" / "build_installer.ps1"
SPEC = KOK / "build_tools" / "PEMF_Backend_onedir.spec"

HF = "hf" + "_" + "SAHTEBELIRTECSAHTEBELIRTECSAHTEBELI"  # 34 karakter — gerçek HF biçimi, düşük entropi
GH = "ghp" + "_" + "SAHTE" * 7 + "S"  # 36 karakter
GHPAT = "github_pat" + "_" + "SAHTE" * 16 + "SA"  # 82 karakter


def _modul(ad: str, yol: Path):
    spec = importlib.util.spec_from_file_location(ad, yol)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.fixture(scope="module")
def tar():
    return _modul("paket_sir_taramasi_18k", TARAYICI)


def _yaz(kok: Path, goreli: str, icerik: str = "x") -> Path:
    p = kok / goreli
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(icerik, encoding="utf-8")
    return p


# ─────────────────────────────── tarayıcı ───────────────────────────────

YASAK_AD_VAKALARI = [
    "_internal/config/pemf_secrets.json",
    "_internal/config/pemf_secrets.yedek.json",
    "_internal/data/credentials.json",
    "_internal/x/credentials_mqtt.json",
    "_internal/deploy/.env",
    "_internal/.env.local",
    "_internal/firmware/Secrets.h",
    "_internal/config/secrets_coil_3.h",
    "_internal/data/cloud_mqtt_provision.json",
    "_internal/config/hivemq_users.json",
    "_internal/config/mosquitto_passwords.txt",
    "_internal/config/bridge_hivemq.conf",
    "_internal/config/credentials/herhangi.txt",
    "_internal/config/config.json",
    "_internal/data/config.json",
]


@pytest.mark.parametrize("goreli", YASAK_AD_VAKALARI)
def test_KRITIK_18K_K4_yasak_ad_ve_yol_YAKALANIR(tar, tmp_path, goreli):
    _yaz(tmp_path, goreli, "{}")
    bulgular, _ = tar.tara([tmp_path])
    assert bulgular and goreli.replace("/", os.sep) in bulgular[0], (goreli, bulgular)


@pytest.mark.parametrize(
    "ad,belirtec", [("hf", HF), ("ghp", GH), ("github_pat", GHPAT)], ids=["hf", "ghp", "github_pat"]
)
@pytest.mark.parametrize(
    "dosya", ["_internal/ai_hub/ayar.json", "_internal/notlar.txt", "_internal/deploy/device.env", "_internal/LISANS"]
)
def test_KRITIK_18K_K4_belirtec_deseni_metin_dosyasinda_YAKALANIR(tar, tmp_path, ad, belirtec, dosya):
    _yaz(tmp_path, dosya, f'{{"token": "{belirtec}"}}\nHF_TOKEN={belirtec}\n')
    bulgular, _ = tar.tara([tmp_path])
    assert len(bulgular) == 1 and "deseni" in bulgular[0], (ad, dosya, bulgular)


def test_18K_K4_zip_TUM_uyeleri_ad_ve_icerikle_taranir(tar, tmp_path):
    z = tmp_path / "base-deps.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("PEMF_Backend/_internal/torch/lib.dll", b"\x00" * 64)
        f.writestr("PEMF_Backend/_internal/deep/a/b/credentials.json", "{}")
        f.writestr("PEMF_Backend/_internal/site/x.py", f"T = '{HF}'\n")
    bulgular, sayi = tar.tara([z])
    assert sayi == 3 and len(bulgular) == 2, bulgular
    assert all(b.startswith("base-deps.zip:") for b in bulgular)


def test_18K_K4_deger_YAZDIRILMAZ_cikis_1(tmp_path):
    _yaz(tmp_path, "_internal/a.json", f'{{"k": "{HF}", "g": "{GH}"}}')
    r = subprocess.run(
        [sys.executable, str(TARAYICI), str(tmp_path)], capture_output=True, text=True, encoding="utf-8", timeout=120
    )
    assert r.returncode == 1, r.stdout + r.stderr
    cikti = r.stdout + r.stderr
    assert "FAIL" in cikti and HF not in cikti and GH not in cikti and "SAHTE" not in cikti, (
        "belirteç değeri çıktıya yazıldı"
    )


def test_18K_K4_zip_OLMAYAN_yayin_dosyasi_ad_ve_icerikle_taranir(tar, tmp_path):
    temiz, sirli = tmp_path / "base-linux.zip", tmp_path / "vet.zip"
    temiz.write_bytes(b"\x00ikili-varlik")
    sirli.write_text(f"token={HF}", encoding="utf-8")
    assert tar.tara([temiz]) == ([], 1)
    bulgular, _ = tar.tara([sirli])
    assert len(bulgular) == 1 and bulgular[0].startswith("vet.zip:"), bulgular


def test_18K_K4_var_olmayan_yol_TEMIZ_SAYILMAZ(tar, tmp_path):
    bulgular, _ = tar.tara([tmp_path / "yok"])
    assert bulgular and "YOK" in bulgular[0]


def test_18K_K4_KARSIT_gercek_benzeri_agac_TEMIZ_izin_listesi_GEREKCELI(tar, tmp_path):
    """Son gerçek derleme çıktısının (2026-10-22, 7226 dosya) sır dışı biçimleri: iki `mosquitto.conf`, `deploy/*.env`, üçüncü taraf
    `config.json`, pip `RECORD` base64url hash'i (`sha256=hf_…` — ölçüldü, 20 karakterlik eski eşiği tetikliyordu), kısa `hf_` adları."""
    _yaz(tmp_path, "_internal/bin/mosquitto/mosquitto.conf", "listener 1883 127.0.0.1\nallow_anonymous true\n")
    _yaz(tmp_path, "_internal/config/mosquitto/mosquitto.conf", "allow_anonymous true\n")
    _yaz(tmp_path, "_internal/config/mosquitto/mosquitto_acl.conf", "topic readwrite pemf/#\n")
    _yaz(tmp_path, "_internal/config/config.json.template", "{}")
    _yaz(
        tmp_path,
        "_internal/deploy/device.env",
        "# PEMF_CLOUDFLARE_TUNNEL_TOKEN=eyJhIjoi...\nPEMF_RATELIMIT_REMOTE_PER_MIN=600\n",
    )
    _yaz(tmp_path, "_internal/transformers/config.json", '{"model_type": "x"}')
    _yaz(tmp_path, "_internal/pytz-2026.2.dist-info/RECORD", "pytz/z/a,sha256=hf_" + "Ab3" * 7 + "-xYz9_q,123\n")
    _yaz(tmp_path, "_internal/huggingface_hub/x.py", "from x import hf_hub_download, hf_raise_for_status\n")
    bulgular, sayi = tar.tara([tmp_path])
    assert sayi == 8 and bulgular == [], bulgular
    for ad, gerekce in tar.IZINLI.items():
        assert len(gerekce) > 30, f"izin listesi girdisi gerekçesiz: {ad}"
        assert "*" not in ad and "?" not in ad, f"izin listesinde joker: {ad}"


# ─────────────────────────────── make_base_zip (GERÇEK betik, sahte dist) ───────────────────────────────


def _sahte_dist(kok: Path) -> Path:
    yardimci = _modul("mbz_tek_dogruluk_18k", KOK / "tests" / "test_make_base_zip_single_truth.py")
    return yardimci._sahte_dist(kok)


def _mbz(dist: Path, cikti: Path):
    return subprocess.run(
        [sys.executable, str(MAKE_BASE_ZIP), str(dist)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "PYTHONIOENCODING": "utf-8", "PEMF_PKG_OUT": str(cikti)},
        timeout=600,
    )


@pytest.mark.parametrize(
    "goreli,icerik",
    [
        ("_internal/config/pemf_secrets.json", "{}"),  # deps katmanı
        ("_internal/deploy/.env", "X=1"),  # APP katmanı (deploy kökü)
        ("_internal/data/cloud_mqtt_provision.json", "{}"),  # APP katmanı — Y38
        ("_internal/torch/notlar.txt", "HF_TOKEN=" + HF),  # deps katmanı, içerik
        ("_internal/frontend/dist/sabit.js", f'var t="{GH}";'),  # APP katmanı, içerik
    ],
    ids=["deps-ad", "app-dotenv", "app-Y38", "deps-hf", "app-gh"],  # kimlikte belirteç görünmesin
)
def test_KRITIK_18K_K4_make_base_zip_SIRLI_paketi_YAYIN_dizinine_koymaz(tmp_path, goreli, icerik):
    dist = _sahte_dist(tmp_path)
    _yaz(dist, goreli, icerik)
    cikti = tmp_path / "paket"
    cikti.mkdir()
    r = _mbz(dist, cikti)
    yazilan = sorted(p.name for p in cikti.iterdir())
    print("K4OLC|mbz|", goreli, r.returncode, yazilan)
    assert r.returncode != 0 and "VALIDATION: FAIL" in r.stdout, f"sırlı paket PASS ({goreli}):\n{r.stdout[-2000:]}"
    assert not {"base-app.zip", "base-deps.zip"} & set(yazilan), f"sırlı paket yayın dizinine kondu: {yazilan}"
    assert HF not in r.stdout + r.stderr and GH not in r.stdout + r.stderr


def test_18K_K4_KARSIT_make_base_zip_izinli_dosyalarla_PASS(tmp_path):
    dist = _sahte_dist(tmp_path)
    _yaz(dist, "_internal/bin/mosquitto/mosquitto.conf", "allow_anonymous true\n")
    _yaz(dist, "_internal/config/mosquitto/mosquitto.conf", "allow_anonymous true\n")
    _yaz(dist, "_internal/deploy/device.env", "PEMF_RATELIMIT_REMOTE_PER_MIN=600\n")
    cikti = tmp_path / "paket"
    cikti.mkdir()
    r = _mbz(dist, cikti)
    assert r.returncode == 0 and "VALIDATION: PASS" in r.stdout and "paket SIR icermiyor" in r.stdout, r.stdout[-2000:]
    assert {"base-app.zip", "base-deps.zip"} <= {p.name for p in cikti.iterdir()}


# ─────────────────────────────── make_manifest (saf işlev + sıra) ───────────────────────────────


@pytest.fixture(scope="module")
def mm():
    return _modul("make_manifest_18k", MANIFEST)  # yalnız tanımlar; main() ÇAĞRILMAZ


def _zip(yol: Path, girdiler: dict[str, str]) -> None:
    with zipfile.ZipFile(yol, "w") as z:
        for ad, icerik in girdiler.items():
            z.writestr(ad, icerik)


@pytest.mark.parametrize(
    "paket", ["base-app.zip", "base-deps.zip", "vet.zip", "research.zip", "research-2.zip", "base-linux-app.zip"]
)
def test_KRITIK_18K_K4_make_manifest_HER_yerel_paketi_tarar(mm, tmp_path, paket):
    _zip(tmp_path / "base-app.zip", {"PEMF_Backend/PEMF_Backend.exe": "E"})
    _zip(tmp_path / paket, {"PEMF_Backend/_internal/data/cloud_mqtt_provision.json": "{}", "m/ayar.json": f'"{HF}"'})
    bulgular = mm.yerel_paket_sir_bulgulari(tmp_path)
    assert len(bulgular) == 2 and all(b.startswith(f"{paket}:") for b in bulgular), bulgular


def test_18K_K4_KARSIT_make_manifest_temiz_ya_da_paketsiz_dizin(mm, tmp_path):
    assert mm.yerel_paket_sir_bulgulari(tmp_path) == [], "paket yokken (acil fren / taşıma) bulgu olmamalı"
    _zip(
        tmp_path / "base-app.zip",
        {"PEMF_Backend/PEMF_Backend.exe": "E", "PEMF_Backend/_internal/bin/mosquitto/mosquitto.conf": "x"},
    )
    (tmp_path / "ilgisiz-credentials.json").write_text("{}", encoding="utf-8")  # yayın varlığı DEĞİL → taranmaz
    assert mm.yerel_paket_sir_bulgulari(tmp_path) == []


def test_KRITIK_18K_K4_make_manifest_MUHURLEMEDEN_once_tarar_ve_REDDE_yazmaz():
    g = MANIFEST.read_text(encoding="utf-8")
    g = g[g.index("def main() -> int:") :]
    i = g.index("_sir = yerel_paket_sir_bulgulari(args.dir)")
    j = g.index('base_url = f"https://github.com/')
    k = g.index("out_path.write_text")
    assert i < j < k, "tarama mühürlemeden (sha / URL / yazım) ÖNCE değil"
    blok = g[i:j]
    assert re.search(r"if _sir:\s*\n(.*\n)*?\s*return 1", blok), "bulguda `return 1` yok"


# ─────────────────────────────── Inno Adım 6.5 (GERÇEK blok, PowerShell 5.1) ───────────────────────────────


def _ps51() -> str:
    s = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    p = s / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    if sys.platform != "win32" or not p.is_file():
        pytest.skip("Windows PowerShell 5.1 yok")
    return str(p)


def _inno_blogu() -> str:
    metin = INNO.read_text(encoding="utf-8-sig")
    bas = metin.index("# --- Adim 6.5")
    son = metin.index("$AiAssetsDir", bas)
    return metin[bas:son]


def _inno_kos(agac: Path, tmp_path: Path) -> tuple[int, str]:
    betik = tmp_path / "adim65.ps1"
    on = (
        "$ErrorActionPreference = 'Stop'\n"
        "function Write-Step { param($m) Write-Host \"ADIM $m\" }\n"
        "function Write-OK { param($m) Write-Host \"OK $m\" }\n"
        "function Write-Warn { param($m) Write-Host \"UYARI $m\" }\n"
        "function Write-Fail { param($m) Write-Host \"HATA $m\"; exit 1 }\n"
        f"$OutputDir = '{agac}'\n$ProjectRoot = '{KOK}'\n$PythonExe = '{sys.executable}'\n"
    )
    betik.write_text(on + _inno_blogu() + "\nexit 0\n", encoding="utf-8-sig")
    r = subprocess.run(
        [_ps51(), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(betik)],
        capture_output=True,
        timeout=300,
    )
    return r.returncode, (r.stdout + r.stderr).decode("utf-8", errors="replace")


def _inno_agaci(tmp_path: Path) -> Path:
    d = tmp_path / "PEMF_Backend"
    _yaz(d, "_internal/config/config.json.template", "{}")
    _yaz(d, "_internal/bin/mosquitto/mosquitto.conf", "allow_anonymous true\n")
    _yaz(d, "_internal/config/mosquitto/mosquitto.conf", "allow_anonymous true\n")
    return d


@pytest.mark.parametrize("goreli", ["_internal/config/pemf_secrets.json", "_internal/config/credentials.json"])
def test_KRITIK_18K_K4_inno_adim65_SIR_dosyasinda_FAIL(tmp_path, goreli):
    d = _inno_agaci(tmp_path)
    _yaz(d, goreli, "{}")
    rc, cikti = _inno_kos(d, tmp_path)
    print("K4OLC|inno|", goreli, rc, cikti.strip().splitlines()[-1:] if cikti.strip() else "")
    assert rc == 1 and "HATA" in cikti, f"Inno Adım 6.5 sırlı ağaçta geçti (rc={rc}):\n{cikti[-1500:]}"


def test_18K_K4_KARSIT_inno_adim65_yalniz_mosquitto_conf_GECER_ve_UYARMAZ(tmp_path):
    rc, cikti = _inno_kos(_inno_agaci(tmp_path), tmp_path)
    assert rc == 0 and "UYARI" not in cikti, f"rc={rc}:\n{cikti[-1500:]}"


# ─────────────────────────────── spec: Y38 provizyon GÖMÜLMEZ ───────────────────────────────

_SPEC_SURUCU = r'''
import json, os, sys, types
spec, cikti = sys.argv[1], sys.argv[2]
_gercek = os.path.exists
os.path.exists = lambda p: True if os.fspath(p).replace("\\", "/").endswith("data/cloud_mqtt_provision.json") else _gercek(p)
def _bos(*a, **k):
    return []
hooks = types.ModuleType("PyInstaller.utils.hooks")
hooks.collect_data_files = hooks.collect_dynamic_libs = hooks.copy_metadata = _bos
hooks.collect_submodules = lambda pkg, *a, **k: [pkg + "._sahte"]
hooks.collect_all = lambda *a, **k: ([], [], [])
pi, ut = types.ModuleType("PyInstaller"), types.ModuleType("PyInstaller.utils")
pi.utils, ut.hooks = ut, hooks
sys.modules.update({"PyInstaller": pi, "PyInstaller.utils": ut, "PyInstaller.utils.hooks": hooks})
yakalanan = {}
class Analysis:
    def __init__(self, scripts, **kw):
        yakalanan["datas"] = [[os.fspath(s), d] for s, d in kw.get("datas", [])]
        self.datas = [(os.path.join(d, os.path.basename(s)), s, "DATA") for s, d in kw.get("datas", [])]
        self.pure, self.scripts, self.binaries, self.zipfiles = [], [], [], []
class _Bos:
    def __init__(self, *a, **k):
        pass
g = {"__name__": "__main__", "__file__": spec, "Analysis": Analysis, "PYZ": _Bos, "EXE": _Bos, "COLLECT": _Bos}
exec(compile(open(spec, encoding="utf-8").read(), spec, "exec"), g)
json.dump(yakalanan, open(cikti, "w", encoding="utf-8"), ensure_ascii=False)
'''


@pytest.mark.skipif(sys.platform != "win32", reason="spec yalnız Windows derlemesinde koşar")
def test_KRITIK_18K_K4_Y38_spec_provizyon_dosyasi_VARKEN_bile_GOMMEZ(tmp_path):
    surucu, cikti = tmp_path / "spec_surucu.py", tmp_path / "datas.json"
    surucu.write_text(_SPEC_SURUCU, encoding="utf-8")
    r = subprocess.run(
        [sys.executable, str(surucu), str(SPEC), str(cikti)],
        cwd=str(KOK),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )
    assert r.returncode == 0 and cikti.exists(), (
        f"spec koşmadı (rc={r.returncode}):\n{r.stdout[-1500:]}\n{r.stderr[-1500:]}"
    )
    datas = json.loads(cikti.read_text(encoding="utf-8"))["datas"]
    assert len(datas) > 5, "spec gerçekten koşmadı (datas boş)"
    gomulen = [s for s, _ in datas if "cloud_mqtt_provision" in s]
    assert not gomulen, f"Y38: bulut E-stop aynası kimliği pakete GÖMÜLÜYOR: {gomulen}"

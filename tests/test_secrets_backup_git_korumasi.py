# Author: mertaygn, cglrgrkn
"""SIR YEDEĞİ GİT KORUMASI — 2. tur denetimi bulgu [2.2] (2026-08-20).

ÖLÇÜLEN DURUM: `secrets_backup.py restore`, dört İZLENEN sır dosyasını (iki `Secrets.h` + iki
`data/config.json`) yazdıktan sonra skip-worktree'yi KULLANICIYA bırakıyordu ve bastığı komut
PowerShell'de çalışmayan bash-tarzı (` \\` devamlı) bir metindi. Adım atlanırsa `git add -A`
GERÇEK sırları PUBLIC repoya stage'ler; üstelik gitleaks'in varsayılan kuralları bu
düşük-entropili WiFi/MQTT sınıfını YAKALAMIYOR (bağımsız çürütme ajanı gerçek içerikte sıfır
bulgu ölçtü) — yani tek kapı da kördü.

DÜZELTME SÖZLEŞMESİ: (1) restore korumayı KENDİSİ uygular (git varsa skip-worktree; dosya
izlenmiyorsa sessiz geç); (2) uygulayamazsa (git yok / komut düştü) YÜKSEK SESLE uyarır ve tek
satırlık, kabuk-bağımsız komutu basar; (3) `.gitleaks.toml`a bu sır sınıfını yakalayan, izlenen
placeholder biçimlerini (boş "" / `<<...GIR>>`) yeşil bırakan ÖZEL kurallar eklenir.
"""

from __future__ import annotations

import importlib
import json
import re
import shutil
import subprocess
import sys
from argparse import Namespace
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]

SIR_DOSYALARI = [
    "firmware/esp8266_pemf_coil/Secrets.h",
    "firmware/esps3_pemf_coil/Secrets.h",
    "firmware/esp8266_pemf_coil/data/config.json",
    "firmware/esps3_pemf_coil/data/config.json",
]


def _git(kok: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(kok), "-c", "user.email=t@t", "-c", "user.name=t", *args],
        capture_output=True,
        text=True,
    )


@pytest.fixture()
def sahte_git_repo(tmp_path, monkeypatch):
    """İzole kök: git repo + İZLENEN placeholder sır dosyaları + gerçek-görünümlü .pemfsec."""
    monkeypatch.syspath_prepend(str(KOK / "build_tools"))
    mod = importlib.import_module("secrets_backup")
    importlib.reload(mod)

    gui = tmp_path / "guii"
    home = tmp_path / "home"
    for rel in SIR_DOSYALARI:
        (gui / rel).parent.mkdir(parents=True, exist_ok=True)
        (gui / rel).write_text("// placeholder\n", encoding="utf-8")
    (gui / "pf/android").mkdir(parents=True)
    (gui / "data").mkdir(parents=True)
    (home / ".pemf-keys").mkdir(parents=True)

    assert _git(gui, "init", "-q").returncode == 0
    assert _git(gui, "add", "-A").returncode == 0
    assert _git(gui, "commit", "-qm", "placeholderlar").returncode == 0

    monkeypatch.setattr(mod, "GUII", gui)
    monkeypatch.setattr(mod, "HOME", home)
    mod._KALEMLER = [
        (ad, gui / rel if not rel.startswith("~") else home / rel[2:], sw)
        for (ad, _y, sw), rel in zip(
            mod._KALEMLER,
            [
                "firmware/esp8266_pemf_coil/Secrets.h",
                "firmware/esps3_pemf_coil/Secrets.h",
                "firmware/esp8266_pemf_coil/data/config.json",
                "firmware/esps3_pemf_coil/data/config.json",
                "data/cloud_mqtt_provision.json",
                "pf/android/keystore.properties",
                "~/.pemf-keys/pemf-release.jks",
            ],
        )
    ]

    # Gerçek-görünümlü içerikli arşiv (değerler apaçık SAHTE ama biçimce gerçek).
    import base64 as b64

    kalemler = []
    for ad, yol, _sw in mod._KALEMLER:
        veri = f"GERCEK-GIBI-{ad}-icerik-9f8e7d\n".encode()
        kalemler.append({"ad": ad, "b64": b64.b64encode(veri).decode("ascii"), "boyut": len(veri)})
    arsiv = gui / "test.pemfsec"
    arsiv.write_text(json.dumps({"_magic": "PEMFSEC2", "sifreli": False, "kalemler": kalemler}), encoding="utf-8")
    return mod, gui, arsiv


def test_KRITIK_restore_skip_worktree_KENDISI_uygular(sahte_git_repo, capsys):
    """restore --force sonrası dört izlenen sır dosyası git'in gözünden DÜŞMÜŞ olmalı:
    `git ls-files -v` → 'S', `git add -A` onları STAGE'LEYEMEZ. Kullanıcı adımı kalmadı."""
    mod, gui, arsiv = sahte_git_repo
    assert mod.cmd_restore(Namespace(inp=str(arsiv), force=True)) == 0

    ls = _git(gui, "ls-files", "-v").stdout.splitlines()
    for rel in SIR_DOSYALARI:
        satir = next((s for s in ls if s.endswith(rel)), "")
        assert satir.startswith("S "), (
            f"{rel} skip-worktree DEĞİL ({satir!r}) — `git add -A` gerçek sırrı stage'ler (bulgu [2.2])"
        )

    # kemer + pantolon askısı: add -A gerçekten stage'leyemiyor
    assert _git(gui, "add", "-A").returncode == 0
    staged = _git(gui, "diff", "--cached", "--name-only").stdout.splitlines()
    sizanlar = [rel for rel in SIR_DOSYALARI if rel in staged]
    assert not sizanlar, f"skip-worktree'ye rağmen stage'lendi: {sizanlar!r}"

    # içerik gerçekten yazıldı (koruma yazmayı engellemedi)
    assert "GERCEK-GIBI" in (gui / SIR_DOSYALARI[0]).read_text(encoding="utf-8")


def test_KRITIK_git_calismazsa_YUKSEK_SESLE_uyarir_ve_dogru_komutu_basar(sahte_git_repo, capsys, monkeypatch):
    """git çağrısı yapılamıyorsa (PATH'te yok vb.) restore YİNE tamamlanır ama sessiz kalmaz:
    yüksek sesli uyarı + TEK SATIRLIK, kabuk-bağımsız komut (bash-tarzı ` \\` devamı YOK)."""
    mod, gui, arsiv = sahte_git_repo

    gercek_run = subprocess.run

    def _git_yok(cmd, *a, **k):
        if cmd and cmd[0] == "git":
            raise FileNotFoundError("git")
        return gercek_run(cmd, *a, **k)

    monkeypatch.setattr(mod.subprocess, "run", _git_yok)
    assert mod.cmd_restore(Namespace(inp=str(arsiv), force=True)) == 0

    cikti = capsys.readouterr().out
    assert "GIT KORUMASI UYGULANAMADI" in cikti, f"yüksek sesli uyarı yok: {cikti!r}"
    tek_satir = [s for s in cikti.splitlines() if "git update-index --skip-worktree" in s]
    assert tek_satir, "elle-koruma komutu basılmadı"
    assert all(rel in tek_satir[0] for rel in SIR_DOSYALARI), (
        f"komut dört izlenen dosyayı TEK satırda saymıyor: {tek_satir[0]!r}"
    )
    assert not tek_satir[0].rstrip().endswith("\\"), "bash-tarzı satır-devamı geri gelmiş (PowerShell'de kırık)"
    # dosyalar yine de yazıldı (koruma hatası restore'u düşürmez)
    assert "GERCEK-GIBI" in (gui / SIR_DOSYALARI[0]).read_text(encoding="utf-8")


def test_KRITIK_D3_git_128_dubious_ownership_YUKSEK_SESLE_uyarir(sahte_git_repo, capsys, monkeypatch):
    """🔴 D3 (denetim 2026-08-24): git VAR ama komutlar exit 128 veriyorsa (dubious ownership /
    bozuk GIT_DIR — taze klonda YAYGIN: repo farklı kullanıcı/yükseltilmiş oturumla klonlanır)
    `ls-files` HER dosyada 128 döner. Eski kod bunu 'izlenmiyor' (returncode != 0) sayıp
    `if not izlenenler: return` ile SESSİZ geçiyordu; sonra kullanıcı safe.directory'yi düzeltip
    `git add -A` yapınca GERÇEK sırlar PUBLIC repoya stage'lenir. 128 (git DÜŞTÜ) ile 1 (gerçekten
    izlenmiyor) AYRI ele alınmalı: 128 → YÜKSEK SESLE uyar (FileNotFoundError ile aynı sözleşme)."""
    mod, gui, arsiv = sahte_git_repo
    gercek_run = subprocess.run

    def _git_128(cmd, *a, **k):
        # git ls-files / update-index → dubious-ownership taklidi: exit 128 (git VAR, komut düştü).
        if cmd and cmd[0] == "git" and any(x in cmd for x in ("ls-files", "update-index")):
            return subprocess.CompletedProcess(
                cmd, 128, stdout="", stderr="fatal: detected dubious ownership in repository"
            )
        return gercek_run(cmd, *a, **k)

    monkeypatch.setattr(mod.subprocess, "run", _git_128)
    assert mod.cmd_restore(Namespace(inp=str(arsiv), force=True)) == 0
    cikti = capsys.readouterr().out
    assert "GIT KORUMASI UYGULANAMADI" in cikti, (
        f"git 128 (dubious ownership) SESSİZ geçti — skip-worktree uygulanmadı ve uyarı da yok; "
        f"safe.directory düzeltilip `git add -A` yapılınca gerçek sırlar stage'lenir (D3): {cikti!r}"
    )
    tek_satir = [s for s in cikti.splitlines() if "git update-index --skip-worktree" in s]
    assert tek_satir and all(rel in tek_satir[0] for rel in SIR_DOSYALARI), (
        f"elle-koruma komutu dört izlenen dosyayı TEK satırda saymıyor: {tek_satir!r}"
    )


def test_KARSIT_KANIT_D3_gercek_untracked_SESSIZ(sahte_git_repo, capsys, monkeypatch):
    """git ÇALIŞIYOR ama dosya GERÇEKTEN izlenmiyorsa (`ls-files --error-unmatch` returncode 1)
    staging riski yoktur → yanlış alarm ÜRETME. 128 (git düştü) ↔ 1 (gerçek untracked) ayrımının
    karşıt-kanıtı: kör 'nonzero = bağır' düzeltmesi bu sessizliği bozardı."""
    mod, gui, arsiv = sahte_git_repo
    gercek_run = subprocess.run

    def _ls_1(cmd, *a, **k):
        if cmd and cmd[0] == "git" and "ls-files" in cmd:
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="")
        return gercek_run(cmd, *a, **k)

    monkeypatch.setattr(mod.subprocess, "run", _ls_1)
    assert mod.cmd_restore(Namespace(inp=str(arsiv), force=True)) == 0
    cikti = capsys.readouterr().out
    assert "GIT KORUMASI UYGULANAMADI" not in cikti, (
        f"gerçekten izlenmeyen (returncode 1) dosyada gereksiz kırmızı uyarı — 128 ile karıştırılmış: {cikti!r}"
    )


def _rmtree_rw(p: Path) -> None:
    """Windows: .git/objects salt-okunur → önce yazılabilir yap, sonra sil."""
    import os
    import stat

    def _onerr(func, yol, _exc):
        os.chmod(yol, stat.S_IWRITE)
        func(yol)

    shutil.rmtree(p, onerror=_onerr)


def test_KARSIT_KANIT_git_repo_degilse_sessiz_gecer(sahte_git_repo, capsys):
    """Kök bir git reposu DEĞİLSE staging riski de yoktur → yanlış alarm üretme (uyarı YOK)."""
    mod, gui, arsiv = sahte_git_repo
    _rmtree_rw(gui / ".git")

    assert mod.cmd_restore(Namespace(inp=str(arsiv), force=True)) == 0
    cikti = capsys.readouterr().out
    assert "GIT KORUMASI UYGULANAMADI" not in cikti, "repo-olmayan kökte gereksiz kırmızı uyarı"


# ── gitleaks ÖZEL KURALLARI — placeholder yeşil, gerçek-görünümlü kırmızı ─────────────────────


def _kural_regexi(kural_id: str) -> re.Pattern:
    metin = (KOK / ".gitleaks.toml").read_text(encoding="utf-8")
    m = re.search(rf'id\s*=\s*"{re.escape(kural_id)}".*?regex\s*=\s*\'\'\'(.*?)\'\'\'', metin, re.S)
    assert m, f".gitleaks.toml içinde `{kural_id}` kuralı yok — düşük-entropili sır sınıfı KÖRDÜR (bulgu [2.2])"
    return re.compile(m.group(1))


def _izlenen_icerik(rel: str) -> str:
    """`git show` çıktısı BAYT okunur (⚠️ text=True cp1254 konsolda UTF-8 içerikte ölür —
    deponun bilinen kodlama tuzağı; make_manifest C1 ile aynı sınıf)."""
    out = subprocess.run(["git", "-C", str(KOK), "show", f"HEAD:{rel}"], capture_output=True).stdout
    return out.decode("utf-8", errors="replace")


def test_KRITIK_gitleaks_kurali_secrets_h_gercek_degeri_yakalar():
    rx = _kural_regexi("pemf-firmware-secrets-h-gercek-deger")
    # İZLENEN gerçek placeholder içerik YEŞİL kalmalı (kural depo tarihçesini kırmızıya boyamasın)
    for rel in ("firmware/esp8266_pemf_coil/Secrets.h", "firmware/esps3_pemf_coil/Secrets.h"):
        izlenen = _izlenen_icerik(rel)
        assert izlenen and not rx.search(izlenen), (
            f"kural, izlenen PLACEHOLDER {rel} üzerinde tetiklendi (yanlış alarm)"
        )
    # gerçek-görünümlü değerler KIRMIZI
    for satir in (
        'static const char* WIFI_SSID_CONST = "KlinikWiFi";',
        'static const char* WIFI_PASS_CONST = "parola123";',
        'static const char* DEFAULT_CLOUD_MQTT_HOST = "abc123.hivemq.cloud";',
        'static const char* DEFAULT_CLOUD_MQTT_USER = "pemfuser";',
        'static const char* DEFAULT_CLOUD_MQTT_PASS = "GizliParola1";',
    ):
        assert rx.search(satir), f"kural gerçek-görünümlü değeri KAÇIRDI: {satir!r}"


def test_KRITIK_gitleaks_kurali_config_json_gercek_degeri_yakalar():
    rx = _kural_regexi("pemf-firmware-config-json-gercek-deger")
    for rel in ("firmware/esp8266_pemf_coil/data/config.json", "firmware/esps3_pemf_coil/data/config.json"):
        izlenen = _izlenen_icerik(rel)
        assert izlenen and not rx.search(izlenen), f"kural, izlenen PLACEHOLDER {rel} üzerinde tetiklendi"
    assert rx.search('"wifi_pass": "parola123"')
    assert rx.search('"mqtt_pass":"GizliParola1"')
    assert not rx.search('"mqtt_pass": ""'), "boş placeholder kırmızıya boyandı"


def test_gitleaks_binarisi_varsa_DAVRANISSAL_dogrulama(tmp_path):
    """gitleaks PATH'teyse kural gerçekten koşularak doğrulanır; yoksa atlanır (CI test işi
    gitleaks kurmaz — tarama ayrı işte action ile koşar)."""
    if not shutil.which("gitleaks"):
        pytest.skip("gitleaks binarisi yok — regex-düzeyi testler yukarıda")
    hedef = tmp_path / "Secrets.h"
    hedef.write_text('static const char* DEFAULT_CLOUD_MQTT_PASS = "GizliParola1";\n', encoding="utf-8")
    r = subprocess.run(
        ["gitleaks", "detect", "--no-git", "-c", str(KOK / ".gitleaks.toml"), "-s", str(tmp_path)],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 1, f"gitleaks gerçek-görünümlü değeri yakalamadı: {r.stdout} {r.stderr}"

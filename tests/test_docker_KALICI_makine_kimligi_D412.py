# -*- coding: utf-8 -*-
"""D4.12 (B-3.49) — Docker backend imajı KALICI bir makine kimliği sağlar; kritik sır fail-closed kalır ama konteyner import'ta ÖLMEZ.

ARIZA: `secrets_manager` Linux'ta kritik anahtarları (`sqlcipher_key`, `patient_fernet_key`) makine kimliğinden (`/etc/machine-id`,
`/var/lib/dbus/machine-id`) türetilen anahtarla sarar (`MKEY:`); kimlik yoksa `critical=True` → RuntimeError (fail-closed, doğru).
`python:3.10-slim` imajında kimlik YOK ve ne Dockerfile ne compose sağlıyor → `PEMF_ENCRYPT_AT_REST=1` (imajın varsayılanı) ile
backend ilk `get_secret('sqlcipher_key')`de ölüyor, konteyner yeniden başlatma döngüsüne giriyor, frontend hiç açılmıyor.

Ölçüm (Docker daemon YOK; `docker build/run` YASAK):
  * GERÇEK giriş betiği (`docker/backend-entrypoint.sh`) `sh` ile koşar — yalnız kimlik yolu tmp'ye çevrilmiş kopyası (betik metninde
    TEK geçmeli). Sonra GERÇEK `secrets_manager` Linux dalı (`_is_windows` → False) kimliği YALNIZ betiğin ürettiği yerden okur:
    `get_secret('sqlcipher_key')` RuntimeError VERMEMELİ; "konteyner yeniden başlatılınca" kimlik DEĞİŞMEMELİ ve sır AYNI çözülmeli.
  * Karşıt: kimlik yokken fail-closed KORUNUR (RuntimeError).
  * İmaj/compose bağlantısı: ENTRYPOINT betiği koşar; betiğin kimlik dizini backend servisinde ADLI birime bağlı (PyYAML ile; Docker CLI
    varsa `docker compose config` çözümüyle de); `/etc/machine-id` imajda o dosyaya bağlı.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path, PurePosixPath

import capraz
import pytest
import yaml
from test_docker_DOCKERFILE_ve_IGNORE_yollari_GUNCEL_D420 import _desenler, _dislanir_mi

KOK = Path(__file__).resolve().parents[1]
BETIK = KOK / "docker" / "backend-entrypoint.sh"
DOCKERFILE = KOK / "docker" / "Dockerfile.backend"
SH = shutil.which("sh")
DOCKER = shutil.which("docker")
COMPOSE_BACKEND = ("docker/docker-compose.yml", "docker/docker-compose.micro.yml")


def _kimlik_yolu() -> str:
    """Betiğin kimlik dosyası (betik metninden; `secrets_manager.MAKINE_KIMLIGI_YOLLARI` ile çapraz denetlenir)."""
    assert BETIK.is_file(), "docker/backend-entrypoint.sh YOK — imaj kalıcı makine kimliği sağlamıyor"
    m = re.findall(r"^KIMLIK=(\S+)\s*$", BETIK.read_text(encoding="utf-8"), re.MULTILINE)
    assert len(m) == 1, f"betikte tek `KIMLIK=` ataması bekleniyor: {m}"
    return m[0].strip("'\"")


def _giris_betigini_kostur(kimlik: Path) -> subprocess.CompletedProcess:
    if SH is None:
        capraz.atla("sh yok")
    metin = BETIK.read_text(encoding="utf-8").replace("\r\n", "\n")
    yol = _kimlik_yolu()
    assert metin.count(yol) == 1, f"kimlik yolu betikte TEK geçmeli (kopyada değiştirilecek): {metin.count(yol)}"
    kopya = kimlik.parent.parent / "giris_kopyasi.sh"
    kopya.write_bytes(metin.replace(yol, kimlik.as_posix()).encode("utf-8"))
    return subprocess.run(
        [SH, kopya.as_posix(), "sh", "-c", "echo KOMUT-KOSTU"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )


@pytest.fixture
def linux_sm(monkeypatch, tmp_path):
    """Linux dalındaki GERÇEK SecretsManager; makine kimliği yalnız testin verdiği yollardan okunur."""
    from utils import file_acl
    from utils import secrets_manager as sm

    monkeypatch.setattr(file_acl, "lock_down_file", lambda *a, **k: True)
    monkeypatch.delenv("PEMF_SQLCIPHER_KEY", raising=False)
    monkeypatch.setenv("PEMF_ENCRYPT_AT_REST", "1")
    monkeypatch.setenv("PEMF_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(sm, "_is_windows", lambda: False)
    sm._cache = None
    yield sm
    sm._cache = None


def test_KRITIK_giris_betigi_KALICI_kimlik_saglar_kritik_sir_COZULUR_B3_49(linux_sm, monkeypatch, tmp_path):
    sm = linux_sm
    kimlik = tmp_path / "pemf_kimlik_birimi" / "machine-id"
    kimlik.parent.mkdir()
    assert _kimlik_yolu() in sm.MAKINE_KIMLIGI_YOLLARI, "betiğin yazdığı yeri secrets_manager OKUMUYOR"
    monkeypatch.setattr(sm, "MAKINE_KIMLIGI_YOLLARI", (str(tmp_path / "etc_machine-id_YOK"), str(kimlik)))

    r = _giris_betigini_kostur(kimlik)
    assert r.returncode == 0 and "KOMUT-KOSTU" in r.stdout, f"giriş betiği CMD'yi koşturmadı:\n{r.stdout}\n{r.stderr}"
    ilk = kimlik.read_text(encoding="utf-8").strip()
    assert re.fullmatch(r"[0-9a-f]{32}", ilk), "üretilen makine kimliği 32 onaltılık değil"

    v1 = sm.get_secret("sqlcipher_key")  # bugün: RuntimeError (makine kimliği yok) → konteyner import'ta ölür
    assert v1, "kritik sır üretilmedi"
    sakli = json.loads(sm.secrets_path().read_text(encoding="utf-8"))["auto"]["sqlcipher_key"]
    assert sakli.startswith(sm._MKEY_PREFIX), "kritik sır makineye-bağlı sarılmadı (düz-metin?)"

    # Konteyner yeniden başlatma / yeniden oluşturma: birim kalır, betik kimliği DEĞİŞTİRMEZ, sır AYNI çözülür.
    sm._cache = None
    r2 = _giris_betigini_kostur(kimlik)
    assert r2.returncode == 0
    assert kimlik.read_text(encoding="utf-8").strip() == ilk, (
        "yeniden başlatmada makine kimliği DEĞİŞTİ (kayıtlı sırlar çözülemez)"
    )
    ayni = sm.get_secret("sqlcipher_key") == v1
    assert ayni, "yeniden başlatma sonrası kritik sır FARKLI döndü"


def test_KARSIT_kimlik_YOKKEN_fail_closed_KORUNUR(linux_sm, monkeypatch, tmp_path):
    sm = linux_sm
    monkeypatch.setattr(sm, "MAKINE_KIMLIGI_YOLLARI", (str(tmp_path / "yok1"), str(tmp_path / "yok2")))
    with pytest.raises(RuntimeError):
        sm.get_secret("sqlcipher_key")
    assert not sm.secrets_path().exists() or "sqlcipher_key" not in sm.secrets_path().read_text(encoding="utf-8"), (
        "kimlik yokken kritik anahtar diske YAZILDI (fail-closed delindi)"
    )


def test_KRITIK_giris_betigi_kimlik_URETEMEZSE_baslatmaz(tmp_path):
    """Rastgele kaynak okunamazsa boş kimlik yazıp CMD'yi koşturmak YOK (sonraki açılışta kimlik değişir → sırlar çözülemez)."""
    if SH is None:
        capraz.atla("sh yok")
    kimlik = tmp_path / "birim" / "machine-id"
    kimlik.parent.mkdir()
    metin = BETIK.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert metin.count("/dev/urandom") == 1
    kopya = tmp_path / "bozuk_kaynak.sh"
    kopya.write_bytes(
        metin.replace(_kimlik_yolu(), kimlik.as_posix())
        .replace("/dev/urandom", (tmp_path / "YOK").as_posix())
        .encode("utf-8")
    )
    r = subprocess.run(
        [SH, kopya.as_posix(), "sh", "-c", "echo KOMUT-KOSTU"], capture_output=True, text=True, timeout=60
    )
    assert r.returncode != 0 and "KOMUT-KOSTU" not in r.stdout, "kimlik üretilemediği hâlde backend başlatıldı"
    assert not kimlik.exists() or not kimlik.read_text(encoding="utf-8").strip(), "bozuk kimlik kalıcı birime yazıldı"


def _dockerfile_talimatlari() -> list[tuple[str, str]]:
    satirlar, birlesik = [], ""
    for s in DOCKERFILE.read_text(encoding="utf-8").replace("\r\n", "\n").splitlines():
        if s.strip().startswith("#") and not birlesik:
            continue
        birlesik += s.rstrip("\\").strip() + " " if s.rstrip().endswith("\\") else s.strip()
        if not s.rstrip().endswith("\\"):
            if birlesik.strip():
                ad, _, arg = birlesik.strip().partition(" ")
                satirlar.append((ad.upper(), arg.strip()))
            birlesik = ""
    return satirlar


def test_KRITIK_imaj_ENTRYPOINT_giris_betigini_kosar_ve_etc_machine_id_birime_bagli():
    t = _dockerfile_talimatlari()
    workdir = [a for ad, a in t if ad == "WORKDIR"][-1]
    giris = [json.loads(a) for ad, a in t if ad == "ENTRYPOINT"]
    assert len(giris) == 1, f"Dockerfile.backend'de tek ENTRYPOINT bekleniyor: {giris}"
    beklenen = str(PurePosixPath(workdir) / BETIK.relative_to(KOK).as_posix())
    assert beklenen in giris[0], f"ENTRYPOINT giriş betiğini ({beklenen}) koşturmuyor: {giris[0]}"
    ignore = Path(str(DOCKERFILE) + ".dockerignore")
    assert not _dislanir_mi(BETIK.relative_to(KOK).as_posix(), _desenler(ignore)), (
        f"giriş betiği {ignore.name} ile build bağlamından DIŞLANIYOR → imajda yok, konteyner açılmaz"
    )
    kimlik = _kimlik_yolu()
    runlar = " ".join(a for ad, a in t if ad == "RUN")
    assert re.search(rf"ln -sf {re.escape(kimlik)} /etc/machine-id(\s|$)", runlar), (
        "/etc/machine-id kalıcı kimlik dosyasına bağlanmıyor (taban imajın kimliği varsa her konteyner onu paylaşır)"
    )
    birimler = [b for ad, a in t if ad == "VOLUME" for b in json.loads(a)]
    assert str(PurePosixPath(kimlik).parent) in birimler, f"kimlik dizini VOLUME değil: {birimler}"


@pytest.mark.parametrize("rel", COMPOSE_BACKEND)
def test_KRITIK_compose_backend_kimlik_dizinine_ADLI_birim_baglar(rel):
    belge = yaml.safe_load((KOK / rel).read_text(encoding="utf-8"))
    hedef = str(PurePosixPath(_kimlik_yolu()).parent)
    adli = set((belge.get("volumes") or {}).keys())
    bulunan = []
    for ad, servis in belge["services"].items():
        b = servis.get("build") or {}
        if not str(b.get("dockerfile", "")).endswith("Dockerfile.backend"):
            continue
        for v in servis.get("volumes") or []:
            kaynak, _, kalan = str(v).partition(":")
            if kalan.split(":")[0] == hedef and kaynak in adli:
                bulunan.append((ad, kaynak))
    assert bulunan, f"{rel}: backend servisinde {hedef} ADLI birime bağlı değil → kimlik konteynerle birlikte kaybolur"


@pytest.mark.parametrize("rel", COMPOSE_BACKEND)
def test_KRITIK_compose_spec_cozumunde_kimlik_birimi_ADLI(rel):
    if DOCKER is None:  # Y205 · S-D5.20: Docker CLI yayın makinesi aracı — ZORUNLU kipte DÜŞER
        capraz.atla("Docker CLI yok — compose-spec kolu (yalnız `config`, daemon gerekmez)")
    r = subprocess.run(
        [DOCKER, "compose", "-f", Path(rel).name, "config", "--format", "json"],
        cwd=str(KOK / "docker"),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    if r.returncode != 0:
        capraz.atla(f"docker compose config koşmadı: {r.stderr.strip()[:300]}")
    hedef = str(PurePosixPath(_kimlik_yolu()).parent)
    servisler = json.loads(r.stdout)["services"]
    bagli = [
        (ad, v.get("source"))
        for ad, s in servisler.items()
        if str((s.get("build") or {}).get("dockerfile", "")).endswith("Dockerfile.backend")
        for v in s.get("volumes") or []
        if v.get("target") == hedef and v.get("type") == "volume" and v.get("source")
    ]
    assert bagli, f"{rel}: compose-spec çözümünde backend {hedef} adlı birime bağlı değil"

# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""FELAKET KURTARMA SAHADA ULAŞILABİLİR Mİ (2026-08-09 denetimi, ENGEL).

ARIZA: kurtarma mekanizmasının TAMAMI vardı —
    utils/backup_recovery.py  → anahtarları 150-bit koda bağlayan şifreli zarf
    tools/kurtarma.py         → zarfı açan/anahtarları yazan araç
    headless_db_maintenance   → zarfı yedeklerin yanına tazeleyen görev
...ama aracın çalıştırılma yolu `python tools/kurtarma.py` idi. Sahadaki üründe PYTHON YOK
(frozen EXE) ve `tools/` pakete girmiyordu.

Yani mekanizmanın hedeflediği kişi — anakartı ölmüş, elinde yalnız yedek dizini, kurtarma kodu
ve yeni bir kurulum olan veteriner — aracı ÇALIŞTIRAMIYORDU. Yedekler SQLCipher ile şifreli,
zarf açılamıyor: koruma kâğıt üzerinde vardı, pratikte YOKTU. Bu, "yedeğiniz var" sanan bir
kliniğin tüm hasta geçmişini kaybetmesi demektir.

ÇÖZÜM: araç, sahaya ZATEN giden tek çalıştırılabilirin alt komutu oldu:
    PEMF_Backend.exe --kurtarma --zarf ...\\kurtarma-zarfi.enc --kod ABCDE-...
"""

import base64
import json
import subprocess
import sys
from pathlib import Path

import pytest

GUII = Path(__file__).resolve().parent.parent


# ── alt komut yönlendirmesi ──────────────────────────────────────────────────


def test_kurtarma_mi_bayragi_ayirir():
    from backend_service import _kurtarma_mi

    assert _kurtarma_mi(["--host", "0.0.0.0"]) is None
    assert _kurtarma_mi(["--kurtarma", "--kodu-goster"]) == ["--kodu-goster"]
    assert _kurtarma_mi(["--kurtarma", "--zarf", "z.enc", "--kod", "ABC"]) == ["--zarf", "z.enc", "--kod", "ABC"]


def test_KRITIK_kurtarma_SUNUCUYU_BASLATMAZ(monkeypatch):
    """Kurtarma anında backend'in çalışması ne gerekli ne de istenir: donanım/port/DB'ye
    dokunmamalı. Sunucu kalkarsa yeni makinede port/servis çakışması olur."""
    import backend_service as bs

    cagrildi = {"sunucu": False, "kurtarma": None}

    def _patlat(*a, **k):
        cagrildi["sunucu"] = True
        raise AssertionError("kurtarma yolunda sunucu kuruldu")

    monkeypatch.setattr(bs, "build_arg_parser", _patlat)

    import tools.kurtarma as tk

    monkeypatch.setattr(tk, "main", lambda argv: cagrildi.__setitem__("kurtarma", argv) or 7)

    assert bs.main(["--kurtarma", "--kodu-goster"]) == 7
    assert cagrildi["kurtarma"] == ["--kodu-goster"]
    assert cagrildi["sunucu"] is False


def test_KRITIK_bayrak_YOKSA_normal_acilis_BOZULMAZ(monkeypatch):
    """Regresyon kapısı: `--kurtarma` yoksa hiçbir şey değişmemeli."""
    import backend_service as bs
    import tools.kurtarma as tk

    monkeypatch.setattr(tk, "main", lambda argv: pytest.fail("kurtarma yanlislikla calisti"))
    monkeypatch.setattr(bs, "build_arg_parser", lambda: (_ for _ in ()).throw(RuntimeError("normal yol")))
    with pytest.raises(RuntimeError, match="normal yol"):
        bs.main(["--port", "8000"])


def test_alt_komut_bayraklari_ANA_AYRISTIRICIYA_sizmaz():
    """`--zarf`/`--kod` ana ayrıştırıcıya giderse argparse 'unrecognized arguments' ile
    SystemExit(2) atardı — kullanıcı sebebi anlaşılmayan bir hata görürdü."""
    from backend_service import build_arg_parser

    with pytest.raises(SystemExit):
        build_arg_parser().parse_args(["--zarf", "x.enc", "--kod", "ABC"])


# ── paketlenebilirlik (frozen EXE'ye giriyor mu) ─────────────────────────────


def test_KRITIK_tools_paketi_IMPORT_EDILEBILIR():
    """PyInstaller namespace-dizinleri bundle etmez → `tools/__init__.py` ŞART."""
    assert (GUII / "tools" / "__init__.py").exists(), "tools/__init__.py yok — frozen EXE'de `tools.kurtarma` bulunamaz"
    import tools.kurtarma  # noqa: F401


def test_KRITIK_spec_kurtarmayi_BUNDLE_EDIYOR():
    """Kaynak-metin kapısı: spec'ten düşerse kurtarma sahada yine ulaşılamaz olur ve bu
    ancak GERÇEK bir felakette fark edilirdi."""
    spec = (GUII / "build_tools" / "PEMF_Backend_onedir.spec").read_text(encoding="utf-8")
    assert "'tools.kurtarma'" in spec, "spec `tools.kurtarma`yi bundle etmiyor"


# ── uçtan uca: zarf üret → başka makine gibi aç ──────────────────────────────


def test_KRITIK_zarf_alt_komutla_ACILIR(tmp_path, monkeypatch):
    """Gerçek felaket senaryosu: elde yalnız zarf + kod var, anahtarlar geri gelmeli."""
    from utils.backup_recovery import build_envelope, generate_recovery_code

    kod = generate_recovery_code()
    anahtarlar = {"sqlcipher_key": "GIZLI-SQLCIPHER", "patient_fernet_key": "GIZLI-FERNET"}
    zarf = tmp_path / "kurtarma-zarfi.enc"
    zarf.write_bytes(build_envelope(kod, anahtarlar))

    import backend_service as bs

    cikti = []
    monkeypatch.setattr("builtins.print", lambda *a, **k: cikti.append(" ".join(map(str, a))))
    rc = bs.main(["--kurtarma", "--zarf", str(zarf), "--kod", kod])
    assert rc == 0, "zarf alt komutla acilamadi"
    metin = "\n".join(cikti)
    assert "sqlcipher_key" in metin


def test_KRITIK_YANLIS_kod_zarfi_ACMAZ(tmp_path, monkeypatch):
    from utils.backup_recovery import build_envelope, generate_recovery_code

    zarf = tmp_path / "kurtarma-zarfi.enc"
    zarf.write_bytes(build_envelope(generate_recovery_code(), {"sqlcipher_key": "GIZLI"}))

    import backend_service as bs

    monkeypatch.setattr("builtins.print", lambda *a, **k: None)
    assert bs.main(["--kurtarma", "--zarf", str(zarf), "--kod", generate_recovery_code()]) != 0, "yanlis kod zarfi acti"


def test_zarf_ANAHTARLARI_DUZ_METIN_tasimaz(tmp_path):
    """Zarf off-site'a kopyalanır; ele geçerse kod olmadan işe yaramamalı."""
    from utils.backup_recovery import build_envelope, generate_recovery_code

    blob = build_envelope(generate_recovery_code(), {"sqlcipher_key": "COK-GIZLI-ANAHTAR"})
    assert b"COK-GIZLI-ANAHTAR" not in blob, "anahtar zarfta DUZ METIN"


# ── gerçek EXE davranışı (dev yorumlayıcısıyla, alt süreçte) ─────────────────


def test_alt_surecte_kurtarma_yardimi_calisir():
    """`python backend_service.py --kurtarma --help` gerçekten kurtarma yardımını basmalı —
    frozen EXE'de kullanıcının göreceği yol budur."""
    import os

    # Gömülü Python `._pth` ile sys.path'i kısıtlar ve PYTHONPATH'i de yok sayar; frozen EXE'de
    # yolu PyInstaller kurar. Testin konusu ALT KOMUT YÖNLENDİRMESİ (ve modül-seviyesi
    # import'ların kurtarma yolunu kırmaması), yorumlayıcı yol kurulumu değil → yolu enjekte et.
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PEMF_HEADLESS": "1"}
    kod = (
        f"import sys, runpy; sys.path.insert(0, r'{GUII}'); "
        "sys.argv = ['PEMF_Backend.exe', '--kurtarma', '--help']; "
        "runpy.run_path(r'backend_service.py', run_name='__main__')"
    )
    r = subprocess.run(
        [sys.executable, "-c", kod],
        cwd=str(GUII),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=180,
    )
    assert "--zarf" in r.stdout, r.stdout[-800:] + r.stderr[-800:]
    assert "--kod" in r.stdout

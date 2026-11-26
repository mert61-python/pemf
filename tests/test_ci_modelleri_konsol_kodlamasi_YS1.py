# -*- coding: utf-8 -*-
"""YS1a (istem 63 · Y320) — GitHub `windows-latest` koşucusunun konsolu cp1252: `scripts/ci_modelleri.py` paketi indirip doğruladı,
sonra "tamam: … doğrulandı" yazarken `UnicodeEncodeError` ("ğ" cp1252'de yok); `main`in `except ValueError` dalı bunu yakalayıp
"!!! liste hatası" yazarken ("ı") AYNI hatayla düştü → çıkış 1, Windows backend işinin testleri HİÇ koşmadı (YAYIN-GUNU.md YG1 4e).
Yerelde görünmedi: koşucularımız `PYTHONIOENCODING=utf-8` kuruyor.

Düzeltme İKİ katman: (1) betik `main` başında stdout / stderr'i UTF-8'e çevirir (`errors="replace"`: yazılamayan karakter düşürmez);
(2) `tests.yml` backend işi `PYTHONIOENCODING: utf-8` taşır (pytest ve diğer betik adımları da aynı konsolda Türkçe yazar).

KAPI (gerçek indirme YOK — sahte depo + yerel sahte paket): betik ALT SÜREÇTE `PYTHONIOENCODING=cp1252` ile (a) başarı yolunda çıkış 0 ve
Türkçe satır okunur, (b) doğrulama hatası yolunda çıkış 1 ve `UnicodeEncodeError` YOK (hata iletisi okunur).
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import yaml

KOK = Path(__file__).resolve().parents[1]
BETIK = KOK / "scripts" / "ci_modelleri.py"
_spec = importlib.util.spec_from_file_location("ci_modelleri_ys1", BETIK)
cm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cm)

ICERIK = {
    "modeller/ai_hub/odak/veri/alan_tablosu.npz": b"ALAN",
    "depo/ai_hub/PEMF_AI_Test_Girdileri/06_PetriKuyu.jpg": b"JPG",
}


def _sahte_depo(tmp_path: Path, zip_icerigi: dict[str, bytes]) -> tuple[Path, Path]:
    """Betiğin BAYT BAYT kopyası sahte depo kökünde (`KOK = parents[1]` → liste sahte depodan okunur) + yerel sahte paket."""
    depo = tmp_path / "depo"
    (depo / "scripts").mkdir(parents=True)
    shutil.copyfile(BETIK, depo / "scripts" / "ci_modelleri.py")
    liste = {"dosyalar": [{"yol": y, "sha256": hashlib.sha256(b).hexdigest()} for y, b in ICERIK.items()]}
    (depo / "scripts" / "ci_modelleri_listesi.json").write_text(json.dumps(liste), encoding="utf-8")
    paket = tmp_path / "paket.zip"
    with zipfile.ZipFile(paket, "w") as z:
        for y, b in zip_icerigi.items():
            z.writestr(y, b)
    return depo, paket


def _cp1252_konsolda_kos(tmp_path: Path, zip_icerigi: dict[str, bytes]) -> subprocess.CompletedProcess:
    depo, paket = _sahte_depo(tmp_path, zip_icerigi)
    ortam = {k: v for k, v in os.environ.items() if k not in ("PYTHONUTF8", "PYTHONIOENCODING")}
    ortam["PYTHONIOENCODING"] = (
        "cp1252"  # GitHub windows-latest koşucusunun konsol kodlaması (sahte EN ALT katta: akış kodlaması)
    )
    hedef = tmp_path / "modeller"
    return subprocess.run(
        [
            sys.executable,
            str(depo / "scripts" / "ci_modelleri.py"),
            "indir",
            "--hedef",
            str(hedef),
            "--depo",
            str(depo),
            "--yerel-zip",
            str(paket),
        ],
        capture_output=True,
        env=ortam,
        timeout=120,
    )


def test_KRITIK_cp1252_konsolda_basari_yolu_CIKIS_0_ve_Turkce_satir_okunur(tmp_path):
    c = _cp1252_konsolda_kos(tmp_path, ICERIK)
    cikti, hata = c.stdout.decode("utf-8", "replace"), c.stderr.decode("utf-8", "replace")
    assert "UnicodeEncodeError" not in hata, f"cp1252 konsolda Türkçe yazım düştü:\n{hata[-800:]}"
    assert c.returncode == 0, f"çıkış {c.returncode}\nstdout:\n{cikti[-800:]}\nstderr:\n{hata[-800:]}"
    assert "tamam: 2 dosya doğrulandı" in cikti, cikti
    assert (tmp_path / "modeller" / "ai_hub" / "odak" / "veri" / "alan_tablosu.npz").read_bytes() == b"ALAN"


def test_KRITIK_cp1252_konsolda_dogrulama_hatasi_CIKIS_1_ileti_okunur_kodlama_cokusu_YOK(tmp_path):
    bozuk = dict(ICERIK)
    bozuk["modeller/ai_hub/odak/veri/alan_tablosu.npz"] = b"BOZUK"
    c = _cp1252_konsolda_kos(tmp_path, bozuk)
    cikti, hata = c.stdout.decode("utf-8", "replace"), c.stderr.decode("utf-8", "replace")
    assert "UnicodeEncodeError" not in hata and "Traceback" not in hata, f"hata yolu kodlamayla düştü:\n{hata[-800:]}"
    assert c.returncode == 1
    assert "SHA-256 uyuşmuyor: modeller/ai_hub/odak/veri/alan_tablosu.npz" in cikti, cikti


class _Akis:
    def __init__(self) -> None:
        self.cagrilar: list[dict] = []

    def reconfigure(self, **kw) -> None:
        self.cagrilar.append(kw)


def test_konsol_utf8_IKI_akisi_da_cevirir_yazilamayan_karakter_DUSURMEZ_reconfigure_olmayan_akisi_atlar(monkeypatch):
    out, err = _Akis(), _Akis()
    monkeypatch.setattr(cm.sys, "stdout", out)
    monkeypatch.setattr(cm.sys, "stderr", err)
    cm._konsol_utf8()
    assert out.cagrilar == [{"encoding": "utf-8", "errors": "replace"}]
    assert err.cagrilar == [{"encoding": "utf-8", "errors": "replace"}]
    monkeypatch.setattr(cm.sys, "stdout", None)  # pythonw / konsolsuz süreçte sys.stdout None olabilir → düşmez
    cm._konsol_utf8()
    assert len(err.cagrilar) == 2


def test_main_konsolu_HER_komutta_once_UTF8e_cevirir(tmp_path, monkeypatch):
    cagri = []
    monkeypatch.setattr(cm, "_konsol_utf8", lambda: cagri.append(1))
    bozuk = tmp_path / "bozuk.json"
    bozuk.write_text("{", encoding="utf-8")
    monkeypatch.setattr(cm, "LISTE", bozuk)
    assert cm.main(["indir", "--hedef", str(tmp_path / "m")]) == 2
    assert cagri == [1]


def test_KRITIK_tests_yml_backend_isi_PYTHONIOENCODING_utf8_tasir():
    is_ = yaml.safe_load((KOK / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8"))["jobs"]["backend"]
    assert (is_.get("env") or {}).get("PYTHONIOENCODING") == "utf-8", (
        "backend işi (windows-latest, konsol cp1252) PYTHONIOENCODING=utf-8 taşımıyor — Türkçe yazan adımlar UnicodeEncodeError ile düşer"
    )

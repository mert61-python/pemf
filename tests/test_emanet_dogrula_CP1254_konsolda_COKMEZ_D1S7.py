# -*- coding: utf-8 -*-
"""DALGA-1 §7 "Dalga 2 (veri)" (D0Ö §6.4 — D3 devri → D5): `hasta_anahtari_emanet.py --dogrula` cp1254 (Türkçe Windows konsolu,
gömülü Python'un varsayılanı) çıktıda ÇÖKÜYORDU: "✓" / "⚠️" cp1254'te kodlanamaz → `UnicodeEncodeError`, kurtarma aracı TAM doğrulama
adımında Traceback ile düşer (operatör "emanet geçerli mi" sorusunun cevabını alamaz). Alt süreç GERÇEK `PYTHONIOENCODING=cp1254`
(katı) ile koşar — conftest yolu / test yakalama akışı devrede değil (hafıza "conftest yolu maskeler"). Ortam: `betik_alt_sureci.yalitik_ortam`
(null kasa, PEMF_* yok, sahte kökler) + sentetik veri kökü."""

from __future__ import annotations

from pathlib import Path

from betik_alt_sureci import kostur, yalitik_ortam
from cryptography.fernet import Fernet

DEPO = Path(__file__).resolve().parents[1]
BETIK = str(DEPO / "scripts" / "hasta_anahtari_emanet.py")


def _ortam(tmp_path: Path, kodlama: str) -> dict:
    env = yalitik_ortam(tmp_path / "ev")
    env["PEMF_DATA_DIR"] = str(tmp_path / "veri")
    env["PYTHONIOENCODING"] = kodlama
    return env


def test_KRITIK_dogrula_cp1254_konsolda_COKMEZ_ve_SONUC_soyler(tmp_path):
    veri = tmp_path / "veri" / "PEMF_GUI"
    veri.mkdir(parents=True)
    (veri / "pemf_secrets.json").write_text(
        '{"auto": {"sqlcipher_key": "d1s7-sql", "patient_fernet_key": "%s"}}' % Fernet.generate_key().decode(),
        encoding="utf-8",
    )
    emanet = tmp_path / "kasa" / "pemf-hasta-anahtari.txt"
    emanet.parent.mkdir()
    p = kostur([BETIK, "--disa-aktar", str(emanet)], cwd=DEPO, env=_ortam(tmp_path, "utf-8"))
    assert p.returncode == 0 and emanet.is_file(), (
        f"aparat: emanet üretilemedi rc={p.returncode}\n{p.stdout[-600:]}{p.stderr[-600:]}"
    )
    p = kostur([BETIK, "--dogrula", str(emanet)], cwd=DEPO, env=_ortam(tmp_path, "cp1254"))
    metin = p.stdout + p.stderr
    assert "UnicodeEncodeError" not in metin and "Traceback" not in metin, f"cp1254 konsolda ÇÖKTÜ:\n{metin[-900:]}"
    assert p.returncode == 0 and "SONUC: EMANET GUNCEL" in p.stdout, f"rc={p.returncode}\n{metin[-900:]}"

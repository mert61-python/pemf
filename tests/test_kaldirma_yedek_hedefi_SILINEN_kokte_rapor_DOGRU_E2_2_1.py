# -*- coding: utf-8 -*-
"""E2-2.1 (2-E incelemesi, A2) — makine dışı yedek hedefi kaldırmanın SİLDİĞİ bir PEMF kökünün İÇİNDEYSE rapor YALAN söyler (A-44).

`Write-PemfMakineDisiYedekRaporu` hedefin durumunu adım 9'da, yani yollar (adım 6) SİLİNDİKTEN SONRA ölçer. Hedef silinen bir kökün
içindeyse (ör. `backup_dir.txt` / `PEMF_BACKUP_DIR` = veri kökü altı ya da kurulum kökü `%LOCALAPPDATA%\\PEMF Vet Client` altı) adım 6
onu siler, adım 9 ise "şu an ERİŞİLEMİYOR … oradaki yedekler bu kaldırmayla SİLİNMEDİ" der; tam temizlikte son satır "makine dışı
yedekler DURUYOR" der. Sıradan kaldırma (bayraksız) kurulum kökünün altındaki yedek kopyalarını da siler ve "HASTA VERİSİ KORUNDU" der.

⛔ Gölge koşum: D2.E04'ün KANITLANMIŞ aparatı (`_APARAT`) DEĞİŞTİRİLMEDEN kullanılır (kök pytest tmp_path altında; kök dışı silme
reddi ARAÇ testiyle önce kanıtlanır).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from test_tam_temizlik_MAKINE_DISI_yedek_raporu_ve_jeton_defteri_D2E04 import (  # noqa: F401  (pytestmark: win32 + pwsh)
    _APARAT,
    _ISTEMCI,
    _PWSH,
    _VERI,
    TEARDOWN,
    _agac,
    _kos,
    pytestmark,
)


def _kos_hedefli(tmp_path: Path, hedef_rel: Path, hasta: bool) -> dict:
    kok = tmp_path / "kok"
    y = _agac(kok)
    hedef = kok / hedef_rel
    hedef.mkdir(parents=True, exist_ok=True)
    for ad in ("pemf_patients_20261009_0300.db", "kurtarma-zarfi.enc", "OKU-KURTARMA.txt"):
        (hedef / ad).write_bytes(b"SENTETIK")
    y["kayit"].write_bytes((str(hedef) + "\r\n").encode("utf-8"))
    aparat = tmp_path / "aparat.ps1"
    aparat.write_text(_APARAT, encoding="utf-8-sig")
    kayit_dosyasi, cikti = tmp_path / "golge.jsonl", tmp_path / "cikti.json"
    arg = [_PWSH, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(aparat), "-Kok", str(kok),
           "-Betik", str(TEARDOWN), "-Kayit", str(kayit_dosyasi), "-Cikti", str(cikti)]  # fmt: skip
    if hasta:
        arg.append("-IncludePatientData")
    p = subprocess.run(arg, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
    assert p.returncode == 0 and cikti.exists(), (
        f"aparat düştü (rc={p.returncode}):\n{p.stdout[-2000:]}\n{p.stderr[-2000:]}"
    )
    s = json.loads(cikti.read_text(encoding="utf-8-sig"))
    s["kayitlar"] = [json.loads(ln) for ln in kayit_dosyasi.read_text(encoding="utf-8-sig").splitlines() if ln.strip()]
    s["engel"] = [r for r in s["kayitlar"] if r["olay"].startswith("ENGEL")]
    s["hedef"] = hedef
    return s


def _dogru_mu(s: dict) -> None:
    hedef, log = s["hedef"], s["log"]
    assert not s["engel"], f"gölge koşumda kök dışı işlem denendi: {s['engel']}"
    assert not hedef.exists(), "aparat: hedef silinmedi, kol anlamsız (hedef silinen kökün içinde olmalı)"
    satir = [ln for ln in log if str(hedef) in ln]
    assert len(satir) == 1, "\n".join(log)
    yalan = [ln for ln in satir if "SİLİNMEDİ" in ln or "DURUYOR" in ln]
    assert not yalan, (
        f"hedef bu kaldırmayla SİLİNDİ ama rapor 'SİLİNMEDİ / DURUYOR' diyor (A-44 yalnız doğrulanan): {yalan}"
    )
    assert "SİLİNDİ" in satir[0], f"rapor silinen makine dışı yedek hedefini SÖYLEMİYOR: {satir[0]}"


def test_KRITIK_tam_temizlik_veri_koku_ICINDEKI_hedef_silinir_rapor_SILINMEDI_DEMEZ_E2_2_1(tmp_path):
    s = _kos_hedefli(tmp_path, _VERI / "PEMF_GUI" / "disari_yedek", hasta=True)
    _dogru_mu(s)
    assert "makine dışı yedekler DURUYOR" not in s["log"][-1], (
        f"son satır silinen hedefi DURUYOR sayıyor: {s['log'][-1]!r}"
    )


def test_KRITIK_sade_kaldirma_kurulum_koku_ICINDEKI_hedef_silinir_rapor_SILINMEDI_DEMEZ_E2_2_1(tmp_path):
    s = _kos_hedefli(tmp_path, _ISTEMCI / "Yedekler", hasta=False)
    _dogru_mu(s)


def test_KARSIT_kok_DISI_hedef_DURUYOR_satiri_degismez_E2_2_1(tmp_path):
    s = _kos(tmp_path, ortam=False, servis=False)
    y = s["agac"]
    e = [ln for ln in s["log"] if str(y["disari_dizin"]) in ln]
    assert len(e) == 1 and "DURUYOR" in e[0] and "4 dosya" in e[0], e
    assert "makine dışı yedekler DURUYOR" in s["log"][-1], s["log"][-1]

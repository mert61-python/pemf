# -*- coding: utf-8 -*-
"""E2-3.8 (2-E incelemesi A3) — D2.75 kapısının KÖR kolları: `KURTARMA_EXE` DİZİNİ launcher'ın gerçek kurulum yoluyla aynı mı;
`--kurtarma --zarf … --kod …` (göster) anahtarın TAMAMINI basmıyor mu.

Ölçüldü (2-E incelemesi A3, 2-E incelemesi kaydı): 2-E'nin kurtarma kümesi (38 test) şu mutantlarda YEŞİL kaldı —
  k2a  `KURTARMA_EXE` = `%LOCALAPPDATA%\\PEMF Vet Client\\PEMF_Backend.exe` (runtime\\PEMF_Backend\\ düştü) → YEŞİL (kapı yalnız
       son sözcüğün `PEMF_Backend.exe` olduğuna bakıyor; yönerge VAR OLMAYAN bir yolu gösterse de geçer)
  k2d  göster kipi anahtarın TAMAMINI basar (`val[:4]…val[-4:]` yerine `val`) → YEŞİL (göster kipinin sızıntısını ölçen kapı yok)
Kapı: (1) `KURTARMA_EXE`, launcher Rust kaynağındaki GERÇEK yol kurucularıyla (`default_install_root` → `runtime_dir` → `backend_path`
→ `backend_exe_name`) parça parça karşılaştırılır; (2) aracın GERÇEK `main`i sentetik zarfla göster kipinde koşar, anahtarın tamamı
ham çıktıda aranır (pozitif kontrol: kısmi gösterim VAR).
"""

from __future__ import annotations

import re
from pathlib import Path

DEPO = Path(__file__).resolve().parents[1]


def _fonksiyon(kaynak: str, ad: str) -> str:
    m = re.search(rf"fn {ad}\b[^{{]*\{{(.*?)\n\}}", kaynak, re.S)
    assert m, f"aparat: launcher kaynağında `fn {ad}` bulunamadı"
    return m.group(1)


def test_KRITIK_KURTARMA_EXE_launcherin_GERCEK_backend_yoluyla_ayni_E238():
    from utils.backup_recovery import KURTARMA_EXE

    ins = (DEPO / "launcher" / "core" / "src" / "install.rs").read_text(encoding="utf-8")
    plat = (DEPO / "launcher" / "core" / "src" / "platform.rs").read_text(encoding="utf-8")
    kok = _fonksiyon(ins, "default_install_root")
    win = kok.split("} else if")[0]
    parcalar = re.findall(r'\.join\("([^"]+)"\)', win)
    assert parcalar[:2] == ["AppData", "Local"], f"aparat: Windows kurulum kökü beklenmedik: {parcalar}"
    runtime = re.findall(r'\.join\("([^"]+)"\)', _fonksiyon(ins, "runtime_dir"))
    backend = re.findall(r'\.join\("([^"]+)"\)', _fonksiyon(ins, "backend_path"))
    exe = re.findall(r'"([^"]+\.exe)"', _fonksiyon(plat, "backend_exe_name"))
    assert runtime and backend and exe, f"aparat: launcher yol kurucuları ayrıştırılamadı: {runtime} {backend} {exe}"
    beklenen = "\\".join(["%LOCALAPPDATA%", *parcalar[2:], *runtime, *backend, exe[0]])
    assert KURTARMA_EXE.strip('"') == beklenen, (
        f"kurtarma yönergesinin EXE yolu launcher'ın kurduğu yerle AYNI DEĞİL:\n  yönerge : {KURTARMA_EXE}\n  launcher: {beklenen}"
    )


def test_KRITIK_goster_kipi_anahtarin_TAMAMINI_basmaz_E238(tmp_path, capsys):
    from utils import backup_recovery as br

    import tools.kurtarma as k

    anahtar = "E238-SENTETIK-ANAHTAR-0123456789-ABCDEFGHIJ"
    kod = br.generate_recovery_code()
    zarf = tmp_path / br.ENVELOPE_NAME
    zarf.write_bytes(br.build_envelope(kod, {"sqlcipher_key": anahtar}))
    assert k.main(["--zarf", str(zarf), "--kod", kod]) == 0
    cikti = capsys.readouterr().out
    assert f"{anahtar[:4]}...{anahtar[-4:]}" in cikti, f"aparat: kısmi gösterim bulunamadı (pozitif kontrol):\n{cikti}"
    assert anahtar not in cikti, "göster kipi (--yaz YOK) anahtarın TAMAMINI ekrana bastı"

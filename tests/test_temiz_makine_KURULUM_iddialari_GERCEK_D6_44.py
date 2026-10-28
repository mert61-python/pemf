# -*- coding: utf-8 -*-
"""D6.44 (Y28) — `docs/TEMIZ-MAKINE.md` Yol A kurulum iddiaları ÜRÜN KAYNAĞIYLA aynı: kurulum dosyası İMZASIZ.

ÖLÇÜLEN DURUM (HEAD ebf1c3fe, 2026-10-28):
  · `docs/TEMIZ-MAKINE.md:24` "Yayımcı: IBIA Teknoloji Ltd. Şti. (UAC uyarısında bu görünmeli)" — `launcher/app/tauri.conf.json`
    `bundle.windows`'ta imza ayarı (`certificateThumbprint` / `signCommand`) YOK, `build_tools/PEMF_Backend_Setup.iss`'te `SignTool`
    YOK → kurulum Authenticode ile imzalanmaz; UAC "Bilinmeyen yayımcı" gösterir. `bundle.publisher` yalnız paket meta verisidir.
    Sahip kararı Y28: kod imzası ŞİMDİLİK alınmaz; belge "Bilinmeyen yayımcı" uyarısını ve SHA ile doğrulamayı anlatır.
  · Gerçek ikilinin imzası (`Get-AuthenticodeSignature`) bu kapıda ÖLÇÜLMEZ (release_assets'e dokunulmaz) — kaynak düzeyinde imza
    yapılandırmasının YOKLUĞU ölçülür; imza yapılandırması eklenirse kapı belgeyi güncellemeye zorlar.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from utils.path_utils import kaynak_kokunu_bul

KOK = Path(kaynak_kokunu_bul(__file__))
BELGE = KOK / "docs" / "TEMIZ-MAKINE.md"
TAURI = KOK / "launcher" / "app" / "tauri.conf.json"
ISS = KOK / "build_tools" / "PEMF_Backend_Setup.iss"


def _yol_a() -> str:
    m = BELGE.read_text(encoding="utf-8")
    bas = m.index("## Yol A")
    son = m.index("\n## ", bas + 5)
    return re.sub(r"~~.*?~~", " ", m[bas:son], flags=re.S)


def _imza_yapilandirmasi_var() -> bool:
    w = json.loads(TAURI.read_text(encoding="utf-8")).get("bundle", {}).get("windows", {})
    tauri_imza = any(k in w for k in ("certificateThumbprint", "signCommand"))
    iss_imza = bool(re.search(r"^\s*SignTool\s*=", ISS.read_text(encoding="utf-8"), re.M | re.I))
    return tauri_imza or iss_imza


def test_KRITIK_kurulum_IMZASIZ_iken_belge_imzali_yayimci_IDDIA_ETMEZ():
    assert not _imza_yapilandirmasi_var(), (
        "imza yapılandırması EKLENMİŞ — Y28 değişti mi? TEMIZ-MAKINE 'Bilinmeyen yayımcı' anlatımını bilinçli güncelleyin"
    )
    a = _yol_a()
    assert not re.search(r"UAC uyarısında bu görünmeli", a), (
        "TEMIZ-MAKINE: imzasız kurulumda UAC yayımcı adı GÖSTERMEZ (Y28)"
    )
    assert not re.search(r"Yayımcı:\s*\*\*I[BİI]{1,2}A", a), "TEMIZ-MAKINE: 'Yayımcı: İBİA' iddiası (imzasız kurulum)"
    for parca in ("Bilinmeyen yayımcı", "Y28", "Get-FileHash", "SHA256", "launcher.sha256"):
        assert parca in a, f"TEMIZ-MAKINE Yol A '{parca}' anmalı (imzasız kurulumun doğrulama yolu — Y28)"

# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""DEV-D5.a (D5 "SONRAKİ OTURUM") — ortak `Test-PemfApiPortDegeri` HATA metni İKİ kurulum yolunda da DOĞRU.

Kusur: metin "backend bu değerde uyarıyla 8000'e düşer, kurulumun sağlık sondası yanlış porta bakar" diyordu. `setup_services.ps1`
kurulum sonunda `/api/health` sondası koşar (doğru), `install_backend_service.ps1` ise HİÇ sağlık sondası koşmaz (S-D5.22) — metin
install yolunda olmayan bir adımı anlatıyordu; eşlik (D5 M-3: iki betik AYNI karar + AYNI metin) yüzünden korunmuştu.
Düzeltme: iki yolda da doğru olan neden — backend uyarıyla 8000'e düşer, profildeki port sessizce yok sayılır.

Metin düzeyinde ölçülür (betik KOŞMAZ); karar / eylem kolları `test_install_backend_service_BOZUK_API_PORT_DURDURUR_Y44_D5M3.py` ve
`test_setup_services_API_PORT_Y44.py`'de (pwsh, gölge aparat).
"""

from __future__ import annotations

import re
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
BETIKLER = {
    "install": KOK / "scripts" / "install_backend_service.ps1",
    "setup": KOK / "scripts" / "setup_services.ps1",
}


def _hata_metni(p: Path) -> str:
    """`$sonuc.Hata = "…" + "…"` atamasının birleşik dize gövdesi (PowerShell çift tırnaklı parçalar)."""
    src = p.read_text(encoding="utf-8-sig")
    m = re.search(r"\$sonuc\.Hata\s*=\s*((?:\"[^\"]*\"\s*\+?\s*)+)", src)
    assert m, f"{p.name}: Test-PemfApiPortDegeri HATA ataması bulunamadı"
    return "".join(re.findall(r"\"([^\"]*)\"", m.group(1)))


def test_KRITIK_ESLIK_iki_betikte_AYNI_HATA_metni_DEV_D5a():
    install, setup = _hata_metni(BETIKLER["install"]), _hata_metni(BETIKLER["setup"])
    assert install == setup, (
        f"Y44 HATA metni iki kurulum yolunda AYRIŞTI (D5 M-3 eşliği):\ninstall={install}\nsetup  ={setup}"
    )


def test_KRITIK_HATA_metni_kurulum_yolunda_OLMAYAN_adimi_anlatmaz_DEV_D5a():
    for kip, p in BETIKLER.items():
        src = p.read_text(encoding="utf-8-sig")
        metin = _hata_metni(p)
        if "/api/health" not in src:
            assert not re.search(r"(?i)sağlık sonda", metin), (
                f"{p.name} sağlık sondası KOŞMUYOR ama HATA metni 'sağlık sondası yanlış porta bakar' diyor: {metin}"
            )
        assert "PEMF_API_PORT geçersiz:" in metin and "düzeltin" in metin and "8000'e düşer" in metin, metin


def test_KARSIT_DEV_D5a_olcut_GERCEK_install_yolunda_saglik_sondasi_YOK():
    """Aparat kendi kendine yeşil olmasın: setup sondası VAR, install sondası YOK (S-D5.22) — değişirse metin yeniden ölçülmeli."""
    assert "/api/health" in BETIKLER["setup"].read_text(encoding="utf-8-sig")
    assert "/api/health" not in BETIKLER["install"].read_text(encoding="utf-8-sig")

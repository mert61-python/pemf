# Author: mertaygn, cglrgrkn
"""D3.04 (B-2.6) · A-02 (sahibin kendi seçeneği, 2026-10-01) — AI geçmişi LİSTESİ ve tek kaydın PDF'i AYNI erişim sınıfında: LAN'dan
TOKEN'SIZ, tünel / uzaktan kimlik ZORUNLU.

ÖLÇÜLEN (HEAD): liste `GET /api/ai/log` LAN'a açık (hasta adı + `result_detail`, sayfa başına 500, keyset ile tamamı) ama tek kaydın
PDF'i `_enforce_privileged` ile LAN'a KAPALI — PDF ucu kapatılırken yazılan tehdit liste ucunda gerçekleşiyordu; sınıflar tutarsızdı.
Sahip A-02'de tutarlılığı A-01 yönünde kurdu (liste kısıtlanmaz, PDF'in LAN token şartı kalkar). Toplu silme ayrıcalıklı KALIR.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

fitz = pytest.importorskip("fitz", reason="PyMuPDF yok -> PDF uretimi yok")
from test_ai_analiz_pdf import analiz  # noqa: E402,F401 — aparat (gerçek AI kaydı)

TUNEL = {"cf-connecting-ip": "203.0.113.4", "cf-ray": "9b-IST"}


def _c(host: str):
    from servers import api_server

    return TestClient(api_server.app, client=(host, 51304))


def test_KRITIK_D3_04_LAN_kimliksiz_liste_ve_PDF_AYNI_sinif_ALIR(analiz):
    _, sid = analiz
    lan = _c("192.168.1.66")
    liste = lan.get("/api/ai/log?limit=5")
    assert liste.status_code == 200, liste.text[:200]
    pdf = lan.get(f"/api/ai/log/{sid}/pdf")
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF", (
        f"A-02: LAN listeyi alıyor ama PDF'i alamıyor ({pdf.status_code})"
    )


def test_KRITIK_D3_04_tunel_kimliksiz_liste_ve_PDF_ALAMAZ(analiz, monkeypatch):
    import servers.auth as auth

    monkeypatch.setattr(auth, "_require", True)  # üretim profili: device.env / launcher PEMF_REQUIRE_AUTH=1
    _, sid = analiz
    t = _c("127.0.0.1")
    assert t.get("/api/ai/log?limit=5", headers=TUNEL).status_code == 401
    r = t.get(f"/api/ai/log/{sid}/pdf", headers=TUNEL)
    assert r.status_code == 401 and r.content[:4] != b"%PDF"


def test_KARSIT_D3_04_toplu_silme_LANdan_kimliksiz_YAPILAMAZ(monkeypatch):
    import servers.auth as auth

    monkeypatch.setattr(auth, "_require", True)
    r = _c("192.168.1.66").post("/api/ai/log/delete_all", json={"confirm": "SIL"})
    assert r.status_code in (401, 403, 428), f"toplu silme LAN'dan kimliksiz geçti ({r.status_code})"

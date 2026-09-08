# Author: mertaygn, cglrgrkn
"""ESP start-ACK'inin ARAYÜZE ULAŞMASI kapısı (sahip, 2026-09-08).

"PWM'i başlatınca ack geliyor mu? Uygulamadan başlayıp başlamadığını anlamıyorum, sadece butona
dokunuyorum." Zincir ölçüldü: ESP8266 `pemf/coil/{id}/ack` ile GERÇEK PWM durumunu (isActive)
yayınlıyor, backend `_start_ack_watch` bunu 2 sn içinde alıyordu ama BAŞARI halinde yalnız
`logging.debug` ediyordu — arayüze hiçbir şey gitmiyor, "Aktif" rozeti 3 sn'lik status
telemetrisinden geliyordu. Artık üç sonuç da (ack / NACK / zaman aşımı) tek `coil_ack` WS olayı.

Bu dosya bekçiyi GERÇEKTEN koşturur (`_wait_ack` mock'lanır, WS yayını yakalanır). Mutasyonla
KIRMIZI kanıtlandı: `_ack_yayinla(True, "ack")` silinince test_KRITIK_onay_arayuze_YAYINLANIR düşer;
frontend `coil_ack` tipi silinince sözleşme testi düşer.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]


@pytest.fixture()
def api(monkeypatch):
    import servers.api_server as api

    bildirimler: list = []
    ws: list = []
    monkeypatch.setattr(api, "_push_notification", lambda msg, sev="info": bildirimler.append((msg, sev)))
    monkeypatch.setattr(api, "_ws_broadcast_sync", lambda m: ws.append(m))
    monkeypatch.setattr(api, "_finish_coil_run", lambda *a, **k: None)
    return api, bildirimler, ws


def _tek_ack(ws: list, coil_id: int) -> dict:
    acks = [m for m in ws if m.get("type") == "coil_ack" and m.get("coilId") == coil_id]
    assert len(acks) == 1, f"tam BİR coil_ack beklenir (bobin {coil_id}); gelen: {ws}"
    return acks[0]


def test_KRITIK_onay_arayuze_YAYINLANIR(api):
    """ESP 'success:true' → coil_ack ok=True + gecikme (ms) + commandId; bildirim/kayıt kapatma YOK."""
    api_mod, bildirimler, ws = api
    api_mod._register_ack("react_7_1")
    api_mod._resolve_ack("react_7_1", True)  # ESP ack'i zaten geldi → bekçi anında döner
    api_mod._start_ack_watch(7, "react_7_1", None)
    m = _tek_ack(ws, 7)
    d = m["data"]
    assert d["ok"] is True and d["reason"] == "ack", f"onay yanlış kodlanmış: {d}"
    assert d["commandId"] == "react_7_1"
    assert isinstance(d["latencyMs"], int) and 0 <= d["latencyMs"] < 2000, f"gecikme ölçülmemiş: {d}"
    assert isinstance(d["ts"], int) and d["ts"] > 1_600_000_000_000
    assert not bildirimler, f"başarılı onayda bildirim ÇIKMAMALI (gürültü): {bildirimler}"


def test_NACK_hem_bildirim_hem_coil_ack_ok_False(api):
    api_mod, bildirimler, ws = api
    api_mod._register_ack("react_6_2")
    api_mod._resolve_ack("react_6_2", False)
    api_mod._start_ack_watch(6, "react_6_2", None)
    d = _tek_ack(ws, 6)["data"]
    assert d["ok"] is False and d["reason"] == "nack"
    assert any("REDDEDİLDİ" in msg and sev == "error" for msg, sev in bildirimler), bildirimler


def test_zaman_asiminda_coil_ack_ok_None_ve_uyari(api, monkeypatch):
    api_mod, bildirimler, ws = api
    monkeypatch.setattr(api_mod, "_START_ACK_TIMEOUT", 0.05)
    api_mod._register_ack("react_8_3")  # ack HİÇ gelmez
    api_mod._start_ack_watch(8, "react_8_3", None)
    d = _tek_ack(ws, 8)["data"]
    assert d["ok"] is None and d["reason"] == "timeout"
    assert any("onayı gelmedi" in msg and sev == "warning" for msg, sev in bildirimler), bildirimler


def test_yayin_hatasi_bekciyi_DUSURMEZ(api, monkeypatch):
    """WS yayını patlasa bile NACK/zaman-aşımı bildirimi ve akış sürer (bekçi tıbbi geri bildirim yolu)."""
    api_mod, bildirimler, _ws = api

    def _patla(_m):
        raise RuntimeError("ws yok")

    monkeypatch.setattr(api_mod, "_ws_broadcast_sync", _patla)
    api_mod._register_ack("react_6_4")
    api_mod._resolve_ack("react_6_4", False)
    api_mod._start_ack_watch(6, "react_6_4", None)  # fırlatmamalı
    assert any(sev == "error" for _m, sev in bildirimler)


def test_KRITIK_frontend_coil_ack_sozlesmesi():
    """Backend'in yayınladığı tip arayüzde TANIMLI ve İŞLENİYOR olmalı (aksi halde olay sessizce düşer)."""
    ws_ts = (KOK / "pf" / "src" / "services" / "wsClient.ts").read_text(encoding="utf-8")
    ctx = (KOK / "pf" / "src" / "context" / "LiveDataContext.tsx").read_text(encoding="utf-8")
    assert re.search(r'\|\s*"coil_ack"', ws_ts), "wsClient.ts WsMessageType 'coil_ack' içermiyor"
    assert re.search(r'case\s+"coil_ack"\s*:', ctx), "LiveDataContext 'coil_ack' olayını işlemiyor"
    assert "deviceAck" in ctx, "LiveDataContext coil_ack'i bobin 'deviceAck' alanına yazmıyor"
    panel = (KOK / "pf" / "src" / "components" / "domain" / "CoilParameterPanel.tsx").read_text(encoding="utf-8")
    assert "deviceAck" in panel and "onayladı" in panel, "panel cihaz onayını göstermiyor"

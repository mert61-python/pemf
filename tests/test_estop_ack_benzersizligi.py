# Author: mertaygn, cglrgrkn
"""E-STOP ACK KİMLİK BENZERSİZLİĞİ — 2. tur denetimi bulgu [3.2] (2026-08-20).

ÖLÇÜLEN DURUM (çürütme ajanı repro'suyla): `command_id = f"estop_{coil}_{int(ms)}"` yalnız
MİLİSANİYE çözünürlüklü — aynı bobine aynı milisaniyede iki E-stop tetiği (manuel buton + ESP
alarmı; alarm dalında debounce yok, her alarm ayrı `_emergency_stop_all` açar) AYNI id'yi üretir.
`_register_ack` ikinci kaydı ilkinin ÜZERİNE yazar, `_wait_ack` ilk tamamlanan bekçide entry'yi
pop'lar → ikinci bekçi ack GELMİŞKEN None (timeout) görür ve acil-durdurma anında SAHTE
"ESP ONAYI GELMEDİ — bobini elle kontrol edin" kırmızı alarmı basar (alarm yorgunluğu — kod
tabanının iki yerde açıkça önemsediği şey). Ek kusur: `_estop_ack_watch`, ESP'nin AÇIKÇA
success=false NACK'lediği durumda da aynı "(2s) ONAYI GELMEDİ" metnini basıyordu — hem teşhis
hem "2s" ibaresi yanlış (NACK anında döner).

DÜZELTME SÖZLEŞMESİ: (1) id'ye süreç-ömürlü sıra numarası eklenir → aynı ms'de bile benzersiz
(⚠️ S3 firmware command_id'yi 35 karakterde kırpar — id o sınırın altında kalmalı);
(2) NACK ayrı, doğru metinle bildirilir; timeout metni değişmez.
"""

from __future__ import annotations

import threading
import time

import pytest

import servers.api_server as api


@pytest.fixture(autouse=True)
def _temiz(monkeypatch):
    with api._pending_acks_lock:
        api._pending_acks.clear()
    monkeypatch.setattr(api, "_ws_broadcast_sync", lambda *a, **k: None)
    yield
    with api._pending_acks_lock:
        api._pending_acks.clear()


def _estop_idleri_topla(monkeypatch):
    """`_emergency_stop_all`i kontrollü koştur; ESP control-topiğine yayınlanan command_id'leri döndür."""
    yayinlar: list = []
    monkeypatch.setattr(api, "_mqtt_publish", lambda t, p=None, *a, **k: yayinlar.append((t, dict(p or {}))) or True)
    monkeypatch.setattr(api, "_push_notification", lambda *a, **k: None)
    monkeypatch.setattr(api, "_estop_cloud_mirror", lambda *a, **k: None)
    monkeypatch.setattr(api.state, "hardware", None)
    # ack-izleme thread'leri 2 sn beklemesin (testi yavaşlatır); izleme bu testin konusu değil.
    monkeypatch.setattr(api, "_estop_ack_watch", lambda *a, **k: None)

    api._emergency_stop_all(reason="test-1")
    api._emergency_stop_all(reason="test-2")
    return [
        p.get("command_id")
        for t, p in yayinlar
        if t.startswith("pemf/coil/") and t.endswith("/control") and str(p.get("command_id", "")).startswith("estop_")
    ]


def test_KRITIK_ayni_milisaniyede_iki_estop_FARKLI_command_id_uretir(monkeypatch):
    """Saat DONDURULMUŞKEN (en kötü durum: her çağrı aynı ms) art arda iki tam E-stop turu —
    aynı bobinin id'leri yine de benzersiz olmalı; yoksa ikinci bekçi ack'i kaybedip sahte
    kırmızı alarm basar."""
    sabit = time.time()
    monkeypatch.setattr(time, "time", lambda: sabit)  # `_emergency_stop_all` içindeki `_t.time` da bunu görür

    idler = _estop_idleri_topla(monkeypatch)
    assert len(idler) >= 6, f"beklenen ≥6 ESP STOP yayını, gelen: {idler!r}"
    assert len(set(idler)) == len(idler), (
        f"AYNI ms'de üretilen command_id'ler çakıştı: {sorted(idler)!r} — _register_ack üzerine "
        "yazar, ikinci bekçi ack gelmişken 'ONAYI GELMEDİ' der (bulgu [3.2])"
    )


def test_KARSIT_KANIT_id_S3_firmware_kirpma_sinirina_sigar(monkeypatch):
    """S3 `cmd.command_id` 35 karakterde kırpılır (esps3 NetworkManager.cpp:955) — benzersizlik
    eki id'yi o sınırın üstüne taşırsa ack eşleşmesi firmware tarafında sessizce kopar."""
    sabit = time.time()
    monkeypatch.setattr(time, "time", lambda: sabit)

    for cid in _estop_idleri_topla(monkeypatch):
        assert cid and len(cid) <= 35, f"command_id S3 kırpma sınırını aşıyor ({len(cid)}): {cid!r}"


def test_KRITIK_NACK_yanlis_timeout_metniyle_BILDIRILMEZ(monkeypatch):
    """ESP açıkça success=false döndüyse teşhis 'onay gelmedi' DEĞİL 'komut reddedildi'dir;
    '2s' ibaresi de yanlıştır (NACK anında döner). Operatör doğru şeye bakmalı."""
    uyarilar: list = []
    monkeypatch.setattr(api, "_push_notification", lambda msg, sev="info": uyarilar.append((msg, sev)))

    api._register_ack("estop_7_nacktest")
    api._resolve_ack("estop_7_nacktest", False)
    api._estop_ack_watch(7, "estop_7_nacktest")

    assert uyarilar, "NACK'te operatör hiç uyarılmadı"
    mesaj = uyarilar[0][0]
    assert "REDDED" in mesaj or "redded" in mesaj, f"NACK teşhisi yanlış: {mesaj!r}"
    assert "GELMEDİ" not in mesaj and "2s" not in mesaj and "2 sn" not in mesaj, (
        f"NACK, timeout metniyle bildirildi (yanlış teşhis): {mesaj!r}"
    )
    assert uyarilar[0][1] == "error"


def test_KARSIT_KANIT_timeout_metni_DEGISMEDI(monkeypatch):
    """Gerçek timeout (ack hiç gelmedi) yolunda mevcut 'ONAYI GELMEDİ' uyarısı aynen kalır."""
    uyarilar: list = []
    monkeypatch.setattr(api, "_push_notification", lambda msg, sev="info": uyarilar.append((msg, sev)))
    orij = api._wait_ack
    monkeypatch.setattr(api, "_wait_ack", lambda cid, timeout: orij(cid, 0.15))

    api._register_ack("estop_8_timeouttest")  # kimse resolve etmeyecek
    api._estop_ack_watch(8, "estop_8_timeouttest")

    assert uyarilar and "GELMEDİ" in uyarilar[0][0], f"timeout uyarısı bozuldu: {uyarilar!r}"


def test_KARSIT_KANIT_onaylanan_estop_yine_sessiz(monkeypatch):
    """Başarılı ack'te alarm yok (mevcut davranış; alarm-yorgunluğu üretme)."""
    uyarilar: list = []
    monkeypatch.setattr(api, "_push_notification", lambda msg, sev="info": uyarilar.append((msg, sev)))

    api._register_ack("estop_6_oktest")
    api._resolve_ack("estop_6_oktest", True)
    api._estop_ack_watch(6, "estop_6_oktest")

    assert not uyarilar, f"onaylı E-stop'ta gereksiz alarm: {uyarilar!r}"

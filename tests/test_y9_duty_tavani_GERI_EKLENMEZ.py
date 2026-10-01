# Author: mertaygn, cglrgrkn
"""D1.06 · B-10.54 — "Backend'e tedavi duty clamp'i GERİ EKLENMEZ" (Ö.4-Y9) DAVRANIŞLA kilitli.

Y9 kararı bugüne kadar yalnız `start_all_coils` yolunda ölçülüyordu; `update_coil`'e ya da
`/api/session/start → _start_stm_coils`'e `min(duty, 50)` tavanı eklenince mevcut süit YEŞİL
kalıyordu (kör kapı). Tavan aynı zamanda "kaydedilen doz = uygulanan doz" değişmezini bozar:
koşu kaydı 90 derken pakete 50 gider.

Kapı GERÇEK `HardwareController`'ı (kayıtçı donanım kuyruğu, `tests/kayitci_donanim.py`) ve
GERÇEK `/api/session/start`'ı koşar; pakete giden duty firmware aynasıyla çözülür, koşu kaydı
tmp tedavi DB'sinin `session_coil_runs` tablosundan okunur.

⚠️ Orkestratör notu (plan D1.06): bipolar bobinlerde firmware duty'yi yarım periyot altında
klempler (Karar-5, Ö.4-Y9 TAŞIYICI firmware sınırı — kapıda "clamp" SAYILMAZ). Bu yüzden yüksek
duty (90) yalnız UNIPOLAR bobinde, bipolar bobinde tavan altı duty (40) kullanılır; aksi hâlde
kapı "kaydedilen ≠ uygulanan" hâlini kilitlerdi. Bipolar tavan ÜSTÜ istek (Y20: firmware NACK'ler →
D1.101; backend'e ve arayüze duty sınırı EKLENMEZ) ayrı kollarda ölçülür: yalnız PAKETTEKİ duty'nin
aynen geçtiği iddia edilir, koşu kaydı İDDİA EDİLMEZ (NACK anlamı D1.101'in konusu). Unipolar/bipolar
ayrımı literalle değil firmware başlığındaki yetenek maskesinden (`tools/stm32_simulator.UNIPOLAR_YETENEK_MASKESI`) türer.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

from kayitci_donanim import gercek_hc, paket_coz  # noqa: E402
from topoloji import TUM_STM  # noqa: E402

import tools.stm32_simulator as sim  # noqa: E402

_UNIPOLAR = [c for c in sorted(TUM_STM) if (sim.UNIPOLAR_YETENEK_MASKESI >> (c - 1)) & 1]
_BIPOLAR = [c for c in sorted(TUM_STM) if c not in _UNIPOLAR]


def test_ON_KOSUL_topolojide_iki_kip_de_var():
    assert _UNIPOLAR and _BIPOLAR, f"unipolar={_UNIPOLAR} bipolar={_BIPOLAR} — kapı kurulamaz"


@pytest.mark.parametrize(("bobin_kumesi", "duty"), [(_UNIPOLAR, 90.0), (_BIPOLAR, 40.0)])
def test_KRITIK_update_coil_duty_PAKETE_AYNEN_gider(bobin_kumesi, duty):
    bobin = bobin_kumesi[0]
    with gercek_hc() as hc:
        assert hc.update_coil(bobin, 100.0, duty, 0.0, duration=1) is True
        paket_duty = paket_coz(hc.core._hw_send_queue.paketler[-1])[0][bobin - 1]
    assert paket_duty == pytest.approx(duty / 100.0), (
        f"bobin {bobin}: istenen duty {duty} → pakette {paket_duty * 100:.1f} — backend'e duty tavanı "
        "GERİ EKLENMİŞ (Ö.4-Y9: tek sınır firmware)"
    )


@pytest.mark.parametrize("bobin", sorted({_BIPOLAR[0], _BIPOLAR[-1]}))
def test_KRITIK_Y20_bipolar_tavan_USTU_duty_update_coil_backendden_AYNEN_gecer(bobin):
    """Bağımsız inceleme (r2): bipolar kol yalnız tavan ALTI (40) kullanıyordu — YALNIZ bipolar bobinlere
    backend tavanı (`min(duty, 0.45)`) eklense kapı yeşil kalıyordu. Y20 tam bunu yasaklar: tavan üstünü
    firmware NACK'ler (D1.101), backend kırpmaz. 1-B inceleme (i7): yalnız `_BIPOLAR[0]` ölçülüyordu — ilk ve
    son bipolar bobin."""
    with gercek_hc() as hc:
        assert hc.update_coil(bobin, 100.0, 90.0, 0.0, duration=1) is True
        paket_duty = paket_coz(hc.core._hw_send_queue.paketler[-1])[0][bobin - 1]
    assert paket_duty == pytest.approx(0.90), (
        f"bipolar bobin {bobin}: duty 90 → pakette {paket_duty * 100:.1f} — backend'e bipolar duty tavanı "
        "EKLENMİŞ (Y20: tek sınır firmware NACK)"
    )


# ── /api/session/start → _start_stm_coils ─────────────────────────────────────


@pytest.fixture
def seans_ortami(tmp_path, monkeypatch):
    from database.treatment_history_db import TreatmentHistoryDB
    from fastapi.testclient import TestClient
    from servers import api_server as api
    from servers import coil_run_tracker, live_state

    db = TreatmentHistoryDB(tmp_path)
    monkeypatch.setattr(api, "_get_treatment_db", lambda: db)
    monkeypatch.setattr(coil_run_tracker, "_treatment_db_getter", lambda: db)
    monkeypatch.setattr(api, "_ws_broadcast_sync", lambda *a, **k: None)
    live_state.stm_komut_kabulu_bildir()  # süreç-geneli red sayacı önceki testten sızmasın
    istemci = TestClient(api.app, client=("127.0.0.1", 51235))
    with gercek_hc() as hc:
        monkeypatch.setattr(api.state, "hardware", hc)
        try:
            yield istemci, db, hc
        finally:
            istemci.post("/api/session/stop", json={})
            live_state.stm_komut_kabulu_bildir()


@pytest.mark.parametrize(("bobin_kumesi", "duty"), [(_UNIPOLAR, 90.0), (_BIPOLAR, 40.0)])
def test_KRITIK_seans_baslat_duty_PAKETE_ve_KOSU_KAYDINA_aynen_gider(seans_ortami, bobin_kumesi, duty):
    istemci, db, hc = seans_ortami
    bobin = bobin_kumesi[0]
    r = istemci.post(
        "/api/session/start",
        json={
            "mode": "Manuel",
            "frequency": 100,
            "duty": duty,
            "phase": 0,
            "intensity": 0.0,
            "duration_minutes": 5,
            "coil_ids": [bobin],
            "patient_name": "Y9Kapisi",
        },
    )
    assert r.status_code == 200, r.text[:300]
    paket_duty = paket_coz(hc.core._hw_send_queue.paketler[-1])[0][bobin - 1]
    assert paket_duty == pytest.approx(duty / 100.0), (
        f"seans yolu: istenen duty {duty} → pakette {paket_duty * 100:.1f} (backend tavanı — Ö.4-Y9)"
    )
    with db._get_connection() as conn:
        kayit = [tuple(s) for s in conn.execute("SELECT coil_id, duty_percent FROM session_coil_runs").fetchall()]
    assert kayit == [(bobin, pytest.approx(duty))], (
        f"koşu kaydı {kayit!r} — kaydedilen doz istenen/uygulanan dozdan farklı (kategori 1)"
    )


def test_KRITIK_Y20_bipolar_tavan_USTU_duty_seans_yolunda_backendden_AYNEN_gecer(seans_ortami):
    """Seans yolu da bipolar tavan üstünü kırpmaz (Y20). Koşu kaydı BİLEREK iddia edilmez (D1.101)."""
    istemci, _db, hc = seans_ortami
    bobin = _BIPOLAR[0]
    r = istemci.post(
        "/api/session/start",
        json={
            "mode": "Manuel",
            "frequency": 100,
            "duty": 90,
            "phase": 0,
            "intensity": 0.0,
            "duration_minutes": 5,
            "coil_ids": [bobin],
            "patient_name": "Y20Kapisi",
        },
    )
    assert r.status_code == 200, r.text[:300]
    paket_duty = paket_coz(hc.core._hw_send_queue.paketler[-1])[0][bobin - 1]
    assert paket_duty == pytest.approx(0.90), (
        f"seans yolu bipolar bobin {bobin}: duty 90 → pakette {paket_duty * 100:.1f} (backend tavanı — Y20)"
    )


# ── D1.10 · B-10.199 (D1.06 ile BİRLEŞİK kapı — orkestratör notu) — ESP yayın yolu ────────────
# Y9'un "kilidi" eskiden `test_nack_gorunurlugu.py`'nin docstring CÜMLESİYDİ (test değil): ESP
# yayın yoluna `min(duty, 50)` eklenince süit YEŞİL kalıyordu. Ayrıca Ö.4-Y9'un ikinci yarısı:
# `normalize_esp_frequency_hz` (≤1000 Hz) TAŞIYICIDIR — 8266 1000 Hz üstünü REDDEDER, kaldırılırsa
# ESP bobini sessizce ölür. ESP slotunun bugün donanımı yok (PEMF_ESP_ENABLED=0) ama kod canlı
# (Ö.4-Y7); kapı ESP alt sistemini AÇIK kurar ve yayını KAYITÇIYA yönlendirir (ağ yok).


@pytest.fixture
def esp_ortami(seans_ortami, monkeypatch):
    from servers import api_server as api
    from topoloji import esp_yolu_gerekir

    esp_yolu_gerekir()
    monkeypatch.setenv("PEMF_ESP_ENABLED", "1")
    monkeypatch.setattr(api, "_broker_reachable", lambda *a, **k: False)  # 127.0.0.1:1883 sondası YOK
    monkeypatch.setattr(api, "_push_notification", lambda *a, **k: None)
    yayinlar: list = []

    def _kaydet(topic, payload):
        yayinlar.append((topic, dict(payload)))
        return False  # ack-bekçisi DOĞMAZ (teste sızmaz)

    monkeypatch.setattr(api, "_mqtt_publish", _kaydet)
    istemci, db, _hc = seans_ortami
    return istemci, db, yayinlar


def _baslat_yuku(yayinlar, bobin, sure: float = 3.0):
    import time as _t

    bitis = _t.monotonic() + sure
    while _t.monotonic() < bitis:  # seans yolu yayını ARKA PLAN iş parçacığında yapar
        for t, p in yayinlar:
            if t == f"pemf/coil/{bobin}/control" and p.get("command") == "start":
                return p
        _t.sleep(0.02)
    raise AssertionError(f"bobin {bobin} için START yayını DENENMEDİ: {yayinlar!r}")


def test_KRITIK_ESP_tekil_kontrol_duty_AYNEN_frekans_TASIYICI_sinirda(esp_ortami):
    from topoloji import ESP_BOBIN

    istemci, _db, yayinlar = esp_ortami
    r = istemci.post(
        f"/api/coil/{ESP_BOBIN}/control",
        json={"freq": 5000.0, "duty": 90.0, "phase": 45.0, "duration": 1, "start": True},
    )
    assert r.status_code == 200, r.text[:300]
    yuk = _baslat_yuku(yayinlar, ESP_BOBIN)
    assert yuk["duty"] == pytest.approx(90.0), f"ESP yayınında duty {yuk['duty']} — backend tavanı (Ö.4-Y9)"
    assert yuk["freq"] == pytest.approx(1000.0), (
        f"ESP yayınında freq {yuk['freq']} — taşıyıcı ESP protokol sınırı (normalize_esp_frequency_hz) "
        "kaldırılmış: 8266 1000 Hz üstünü REDDEDER, bobin sessizce sürülmez"
    )


def test_KRITIK_ESP_seans_yolu_duty_AYNEN_frekans_TASIYICI_ve_KAYIT_ayni(esp_ortami):
    from topoloji import ESP_BOBIN

    istemci, db, yayinlar = esp_ortami
    r = istemci.post(
        "/api/session/start",
        json={
            "mode": "Manuel",
            "frequency": 5000,
            "duty": 90,
            "phase": 0,
            "intensity": 0.0,
            "duration_minutes": 5,
            "coil_ids": [ESP_BOBIN],
            "patient_name": "Y9EspKapisi",
        },
    )
    assert r.status_code == 200, r.text[:300]
    yuk = _baslat_yuku(yayinlar, ESP_BOBIN)
    assert yuk["duty"] == pytest.approx(90.0), f"seans ESP yayınında duty {yuk['duty']} (Ö.4-Y9)"
    assert yuk["freq"] == pytest.approx(1000.0), f"seans ESP yayınında freq {yuk['freq']} (taşıyıcı sınır)"
    with db._get_connection() as conn:
        kayit = [
            tuple(s)
            for s in conn.execute("SELECT coil_id, duty_percent, frequency_hz FROM session_coil_runs").fetchall()
        ]
    assert kayit == [(ESP_BOBIN, pytest.approx(90.0), pytest.approx(1000.0))], (
        f"ESP koşu kaydı {kayit!r} — kayıt, ESP'ye GİDEN değerle aynı olmalı"
    )


def test_KRITIK_ESP_toplu_kontrol_duty_AYNEN_frekans_TASIYICI_sinirda(esp_ortami):
    """Bağımsız inceleme (r2): üç ESP yayın yolundan `/api/coil/batch` kapsanmıyordu — batch yüküne
    `min(payload.duty, 50)` ya da ham `payload.freq` konunca TAM SÜİT yeşil kalıyordu. Tekil yolla aynı
    iddia: duty AYNEN (Ö.4-Y9), freq taşıyıcı ESP sınırında (1000 Hz). Kayıtçı yayın `False` döndüğü
    için koşu kaydı açılmaz (doğrulanmamış yayın) — bu kol kaydı İDDİA ETMEZ."""
    from topoloji import ESP_BOBIN

    istemci, _db, yayinlar = esp_ortami
    r = istemci.post(
        "/api/coil/batch",
        json={"coil_ids": [ESP_BOBIN], "freq": 5000.0, "duty": 90.0, "phase": 0.0, "duration": 60, "start": True},
    )
    assert r.status_code == 200, r.text[:300]
    yuk = _baslat_yuku(yayinlar, ESP_BOBIN)
    assert yuk["duty"] == pytest.approx(90.0), f"batch ESP yayınında duty {yuk['duty']} — backend tavanı (Ö.4-Y9)"
    assert yuk["freq"] == pytest.approx(1000.0), (
        f"batch ESP yayınında freq {yuk['freq']} — taşıyıcı ESP protokol sınırı kaldırılmış (8266 REDDEDER)"
    )


# ── 1-B inceleme (i7): STM API katmanı — `/api/coil/{id}/control` ve `/api/coil/batch` STM dalları ────────
# Plan D1.10'un mutasyon beklentisi "API katmanına `duty=min(duty,50)` → KIRMIZI" idi; r2 düzeltmesi batch'in
# yalnız ESP dalını kapatmıştı. İki STM dalına `min(payload.duty, 50.0)` konunca TAM SÜİT yeşildi (tekil uçtaki
# mevcut testler duty 25 kullanıyor — tavanın altı). Unipolar (Y9) ve bipolar tavan üstü (Y20) iki uçta da.


def _stm_api_istegi(istemci, uc: str, bobin: int, duty: float):
    if uc == "tekil":
        return istemci.post(
            f"/api/coil/{bobin}/control",
            json={"freq": 100.0, "duty": duty, "phase": 0.0, "duration": 1, "start": True},
        )
    return istemci.post(
        "/api/coil/batch",
        json={"coil_ids": [bobin], "freq": 100.0, "duty": duty, "phase": 0.0, "duration": 60, "start": True},
    )


@pytest.mark.parametrize("uc", ["tekil", "batch"])
@pytest.mark.parametrize("kip", ["unipolar_Y9", "bipolar_Y20"])
def test_KRITIK_STM_API_duty_PAKETE_AYNEN_gider(seans_ortami, uc, kip):
    istemci, _db, hc = seans_ortami
    bobin = (_UNIPOLAR if kip == "unipolar_Y9" else _BIPOLAR)[0]
    r = _stm_api_istegi(istemci, uc, bobin, 90.0)
    assert r.status_code == 200, r.text[:300]
    paket_duty = paket_coz(hc.core._hw_send_queue.paketler[-1])[0][bobin - 1]
    assert paket_duty == pytest.approx(0.90), (
        f"{uc} STM ucu ({kip}) bobin {bobin}: duty 90 → pakette {paket_duty * 100:.1f} — API katmanına duty "
        "tavanı EKLENMİŞ (Ö.4-Y9/Y20: tek sınır firmware)"
    )
    # Koşu kaydı İDDİA EDİLMEZ: seans dışı bu iki uç `session_coil_runs` açmıyor (1-B'de ölçüldü: iki uçta da
    # `[]`) — "kayıt 90" iddiası boş kümede KÖR olurdu. Seans yolundaki kayıt yukarıdaki kollarda ölçülür.

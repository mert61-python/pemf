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
kapı "kaydedilen ≠ uygulanan" hâlini kilitlerdi. Bipolar tavan üstü istek: Y20 (firmware NACK'ler,
D1.101) — bu kapının konusu değil. Unipolar/bipolar ayrımı literalle değil firmware başlığındaki
yetenek maskesinden (`tools/stm32_simulator.UNIPOLAR_YETENEK_MASKESI`) türer.
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

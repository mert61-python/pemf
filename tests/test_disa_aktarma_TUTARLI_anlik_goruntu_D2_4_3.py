# -*- coding: utf-8 -*-
"""D2-4.3 (2-D incelemesi, orkestratör · D2.E02'nin dışa aktarma yüzü) — cihaz taşıma yedeği TEK ANLIK GÖRÜNTÜDEN okunur: dışa aktarma
sürerken commit edilen yazım (süren tedavinin seans/koşu satırları ya da bir geri yükleme) paketi KARIŞTIRMAZ.

ÖLÇÜLEN KUSUR (HEAD `a76ee0d`, orkestratör sondası O6): `export_rows` taşınan tabloları AYRI `SELECT`'lerle, açık okuma işlemi OLMADAN
okuyordu (her SELECT kendi anlık görüntüsü). Dışa aktarma `session_coil_runs`'a gelmişken bir REPLACE_ALL geri yükleme commit edilince
dışa aktarma 200 "success" döndü ama paket 4 ESKİ seans + 30 YENİ bobin koşusu / 90 sensör / 30 olay taşıyordu — hepsinin seansı pakette
YOK. O yedek boş cihaza yüklenince 4 seans, 0 bobin koşusu, 0 sensör, 0 olay: uygulanan doz kayıtları SESSİZCE düştü (round-trip doğrulaması
yalnız sayım tutarlılığına bakar). Aynı açık olağan yazımda da var: tedavi sürerken dışa aktarma alınırsa yeni seansın çocuk satırları
ebeveynsiz pakete girer.
DÜZELTME: `export_rows` okumayı tek okuma işleminde yapar (WAL anlık görüntüsü; yazarlar beklemez).
GERÇEK: `/api/data/export` + `/api/data/import` uçları, `TreatmentHistoryDB` (şifresiz; ilke şifreli DB'de aynı), çözülen paket ve boş cihaza
içe aktarma. Zamanlama: dışa aktarmanın bağlantısında SQLite iz geri çağrısı `session_coil_runs` okuması başlarken BİR KEZ bekler (ürün
kodu değişmez; yalnız araya giren commit'in ANINI sabitler).
"""

from __future__ import annotations

import asyncio
import base64
import threading
import time

import pytest
import veri_tasima_aparati as vta

PAROLA = "D2-4-3-parola"


def _bekleten_iz(monkeypatch, tdb):
    vurdu, birak, kullanildi = threading.Event(), threading.Event(), []

    def _iz(sql):
        if not kullanildi and "FROM session_coil_runs ORDER BY id ASC" in (sql or ""):
            kullanildi.append(1)
            vurdu.set()
            birak.wait(30)

    orj = tdb._create_connection

    def _baglanti():
        c = orj()
        c.set_trace_callback(_iz)
        return c

    monkeypatch.setattr(tdb, "_create_connection", _baglanti)
    return vurdu, birak


def _paket_tutarliligi(paket):
    seans = {s["id"] for s in paket["treatment_sessions"]}
    return {
        t: sum(1 for k in paket.get(t) or [] if k.get("session_id") is not None and k.get("session_id") not in seans)
        for t in ("session_coil_runs", "sensor_samples", "session_events", "session_parameters")
    }


@pytest.mark.parametrize("araya_giren", ["seans_yazimi", "geri_yukleme"])
def test_KRITIK_D2_4_3_disa_aktarma_SURERKEN_commit_PAKETI_karistirmaz(monkeypatch, tmp_path, araya_giren):
    import httpx
    from servers import api_server as api
    from utils.data_export import decrypt_bundle

    monkeypatch.setattr(api, "_RL_REMOTE_MAX", 0)
    tdb_a, hdb_a = vta.cihaz_kur(monkeypatch, tmp_path / "A")
    vta.doldur(tdb_a, hdb_a, [f"Yedek{i}" for i in range(6)], seans_basi=2, sensor=2)
    vta.uclari_bagla(monkeypatch, tdb_a, hdb_a)
    yedek = vta.disa_aktar(api.app, parola=PAROLA)["data_b64"]
    tdb, hdb = vta.cihaz_kur(monkeypatch, tmp_path / "B")
    vta.doldur(tdb, hdb, ["Eski1", "Eski2"], seans_basi=2, sensor=2)
    vta.uclari_bagla(monkeypatch, tdb, hdb)
    vurdu, birak = _bekleten_iz(monkeypatch, tdb)

    def _tedavi_suruyor():
        # süren tedavi: YENİ seans + bobin koşusu + sensör + olay (ürünün kendi yazıcılarıyla, ayrı iş parçacığı)
        sid = tdb.start_session(treatment_mode="Manuel", patient_name="Eski1")
        with tdb._get_connection() as c:
            c.execute(
                "INSERT INTO session_coil_runs (session_id, coil_id, started_epoch, ended_epoch, duration_seconds, frequency_hz, "
                "duty_percent, created_at) VALUES (?,?,?,?,?,?,?,?)",
                (sid, 1, 1.0, 2.0, 1.0, 50.0, 25.0, 1.0),
            )
            c.execute(
                "INSERT INTO sensor_samples (session_id, coil_id, sample_ts, temperature_c, created_at) VALUES (?,?,?,?,?)",
                (sid, "1", 1.0, 30.0, 1.0),
            )
            c.commit()
        tdb.record_session_event(sid, "session_started", payload={}, severity="info")

    async def _senaryo():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=api.app, client=("127.0.0.1", 50123)),
            base_url="http://cihaz",
            timeout=120,
        ) as c:
            disa = asyncio.create_task(c.post("/api/data/export", json={"passphrase": PAROLA}))
            t0 = time.monotonic()
            while not vurdu.is_set() and time.monotonic() - t0 < 20:
                await asyncio.sleep(0.02)
            assert vurdu.is_set(), "aparat: dışa aktarma bobin koşusu okumasına gelmedi"
            if araya_giren == "seans_yazimi":
                t = threading.Thread(target=_tedavi_suruyor)
                t.start()
                await asyncio.to_thread(t.join, 20)
                ara = None
            else:
                ara = await c.post(
                    "/api/data/import", json={"passphrase": PAROLA, "blob_b64": yedek, "confirm": "REPLACE_ALL"}
                )
            birak.set()
            return ara, await disa

    ara, r = asyncio.run(_senaryo())
    try:
        assert r.status_code == 200, f"dışa aktarma: {r.status_code} {r.text[:200]}"
        paket = decrypt_bundle(base64.b64decode(r.json()["data_b64"]), PAROLA)
        yetim = _paket_tutarliligi(paket)
        assert not any(yetim.values()), (
            f"{araya_giren}: yedek paketi KARIŞIK — seansı pakette olmayan satırlar {yetim} (seans {len(paket['treatment_sessions'])}, "
            f"koşu {len(paket['session_coil_runs'])}); bu yedekten geri yüklemede doz kayıtları sessizce düşer"
            f"{'' if ara is None else f' · araya giren geri yükleme {ara.status_code}'}"
        )
        # paket boş cihaza tam geliyor (sayım = paket)
        tdb_c, hdb_c = vta.cihaz_kur(monkeypatch, tmp_path / "C")
        vta.uclari_bagla(monkeypatch, tdb_c, hdb_c)
        (rc,) = vta.istekler(
            api.app, [("POST", "/api/data/import", {"passphrase": PAROLA, "blob_b64": r.json()["data_b64"]}, None)]
        )
        assert rc.status_code == 200, rc.text[:200]
        sc = vta.sayimlar(tdb_c, hdb_c)
        for t in ("treatment_sessions", "session_coil_runs", "sensor_samples", "session_events"):
            assert sc[t] == len(paket[t]), f"{t}: paket {len(paket[t])} ↔ geri yüklenen {sc[t]}"
        vta.kapat(tdb_c, hdb_c)
    finally:
        vta.kapat(tdb_a, hdb_a, tdb, hdb)


def test_KARSIT_D2_4_3_olagan_disa_aktarma_DEGISMEZ_ve_baglanti_islem_birakmaz(monkeypatch, tmp_path, caplog):
    from servers import api_server as api

    tdb, hdb = vta.cihaz_kur(monkeypatch, tmp_path / "A")
    vta.doldur(tdb, hdb, ["H1", "H2"], seans_basi=2, sensor=2)
    vta.uclari_bagla(monkeypatch, tdb, hdb)
    s0 = vta.sayimlar(tdb, hdb)
    p = vta.disa_aktar(api.app, parola=PAROLA)
    assert (
        p["counts"]["treatment_sessions"] == s0["treatment_sessions"]
        and p["counts"]["sensor_samples"] == s0["sensor_samples"]
    )
    # okuma işlemi açık kalmamalı: bağlantı havuzda kilit tutmasın (yazım hemen geçer)
    tdb.start_session(treatment_mode="Manuel", patient_name="H1")
    assert "commit edilmemis islemle" not in caplog.text, "dışa aktarma bağlantıyı açık işlemle bıraktı"
    vta.kapat(tdb, hdb)

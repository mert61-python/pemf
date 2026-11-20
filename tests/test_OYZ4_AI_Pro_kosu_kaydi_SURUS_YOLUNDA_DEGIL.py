# -*- coding: utf-8 -*-
"""OYZ4 (zincir 56 AŞAMA 4 · B7 Y30 bulgusu) — AI Pro bobin çalışma kaydı (OTB T-10) SÜRÜŞ YOLUNDA DEĞİL.

ÖLÇÜLEN ARIZA: OTB T-10 (`89713409`) AI Pro sürüşünde telde kabul edilen her bobin için çalışma kaydını (`session_coil_runs`) sürüş
döngüsünün İÇİNDE, bobin başına eşzamanlı DB yazımıyla açıyordu. İlk turda bobin 2–7'nin START'ı her yazım kadar gecikiyor (tedavi DB'si
kilitliyken `busy_timeout` 5 sn × bobin), döngü durdurma denetimine geç varıyordu — tam süit (Y30) `test_ai_pro_tahmin_ORGANI_…` iki
kolunu kırmızıya çevirdi (bisect: ilk kötü commit `89713409`; döngü tahminden sonra gelen STOP'u sürüş ortasında görüp `ai_vision`
yayınlamadan çıkıyor). SÖZLEŞME: kayıt FIFO kayıt işçisinde BEKLENMEDEN yazılır — sürüş kayıt DB'sini beklemez; başlangıç damgası SÜRÜŞ
ANINDA alınır (D2.40: kuyrukta bekleme doz kaydına kaymaz); kuyrukta bekleyen iki tur aynı bobine iki koşu açmaz; kayıt yine açılır ve
durdurmada kapanır (T-10 sözleşmesi aynen). Düzen `test_OTB_T10_AI_Pro_BOBIN_CALISMA_KAYDI` ile aynı (GERÇEK HC + geçici tedavi DB'si)."""

from __future__ import annotations

import time

import ai_pro_aparati as ap
from test_ODK_ai_pro_odak_entegrasyon import M2, P2, _Hat, _hazirlik, _oner, _Sonuc, o  # noqa: F401  aynı düzenek

YAZIM_SN = 0.4  # bobin başına yapay kayıt yazım süresi (kilitli DB benzetimi)


def _kosular(o, sid):
    from utils import dongu_disi_yazim

    assert dongu_disi_yazim.bosalt(30), "kayıt işçisi 30 sn'de boşalmadı"
    with o.db._get_connection() as c:
        return c.execute(
            "SELECT coil_id, started_epoch, ended_epoch FROM session_coil_runs WHERE session_id = ? ORDER BY coil_id, id",
            (sid,),
        ).fetchall()


def _baslat(o, monkeypatch):
    from servers import ai_approval, coil_run_tracker

    gercek = coil_run_tracker._begin_coil_run_govde

    def yavas(*a, **k):
        time.sleep(YAZIM_SN)
        return gercek(*a, **k)

    monkeypatch.setattr(coil_run_tracker, "_begin_coil_run_govde", yavas)
    _hazirlik(o)
    pid = _oner(o, doz_mT=0.4).json()["proposalId"]
    ai_approval.approve(pid, "arastirmaci@test.local")
    assert o.c.post("/api/ai/pro/start", json={"proposal_id": pid}).status_code == 200
    with o.api._session_lock:
        sid = o.api._active_session.get("db_session_id")
    assert sid, "AI Pro seansının DB satırı yok"
    return sid


def test_KRITIK_yavas_kayit_DB_sinde_SURUS_beklemez_damga_SURUS_aninda(o, monkeypatch):
    sid = _baslat(o, monkeypatch)
    _Hat.sonuc = _Sonuc([(P2, M2, 300)])
    t0 = time.time()
    j = ap.kare(o).json()
    sure = time.time() - t0
    assert j.get("driven") is True, j
    surulen = sorted(c["id"] for c in j["perCoil"] if c.get("suruldu"))
    assert len(surulen) >= 3, f"aparat: en az 3 bobin sürülmeli ({surulen})"
    # Eski hâl: bobin başına eşzamanlı yazım → kare yanıtı ≥ len(surulen) × 0,4 sn (7 bobinde ≥ 2,8 sn).
    assert sure < len(surulen) * YAZIM_SN * 0.5, (
        f"kare (sürüş) {sure:.2f} sn sürdü — kayıt yazımı sürüş yolunda ({len(surulen)} bobin × {YAZIM_SN} sn)"
    )
    k = _kosular(o, sid)
    assert [r[0] for r in k] == surulen, f"kayıt yine açılmalı: sürülen {surulen} · kayıt {k}"
    # Damga sürüş anında: son bobinin kaydı ~ (n-1) × 0,4 sn sonra yazıldı ama başlangıcı sürüş anı.
    assert all(t0 - 1.0 <= r[1] <= t0 + sure + 0.2 for r in k), (
        f"başlangıç damgası yazım anından alınmış (sürüş {t0:.2f}–{t0 + sure:.2f}): {[r[1] for r in k]}"
    )
    assert o.c.post("/api/ai/pro/stop").status_code == 200
    k2 = _kosular(o, sid)
    assert [r[0] for r in k2] == surulen and all(r[2] is not None for r in k2), f"durdurmada koşu kapanmadı: {k2}"


def test_arka_planda_ISCIDEN_ve_KAPANMIS_yurutucude_ESZAMANLI_hata_GUNLUGE(monkeypatch, caplog):
    """`arka_planda` FIFO işçide beklemeden koşar; işçinin KENDİSİNDEN (iç içe) ya da yürütücü açılamazken eşzamanlı koşar (kilitlenmez /
    iş kaybolmaz); işçideki hata ERROR günlüğüne yazılır (sessiz yutulmaz)."""
    import logging
    import threading

    from utils import dongu_disi_yazim as dy

    izler: list = []
    dy.sirada_calistir(lambda: dy.arka_planda(lambda: izler.append(threading.current_thread().name)), ad="ic-ice")
    assert dy.bosalt(10) and izler and izler[0].startswith("pemf-kayit-yazim"), izler

    class _Kapali:
        def submit(self, *a, **k):
            raise RuntimeError("cannot schedule new futures after shutdown")

    monkeypatch.setattr(dy, "_isci", lambda: _Kapali())
    dy.arka_planda(lambda: izler.append("eszamanli"))
    assert izler[-1] == "eszamanli"
    monkeypatch.undo()

    def patla():
        raise ValueError("kayit patladi")

    with caplog.at_level(logging.ERROR, logger="utils.dongu_disi_yazim"):
        dy.arka_planda(patla, ad="patlayan kayit")
        assert dy.bosalt(10)
        time.sleep(0.05)
    assert any("patlayan kayit" in r.getMessage() for r in caplog.records), [r.getMessage() for r in caplog.records]


def test_kosu_acma_BEST_EFFORT_bos_liste_kuyruk_hatasi_ve_kayit_hatasi_SURUSU_etkilemez(monkeypatch):
    from servers import ai_router, coil_run_tracker
    from utils import dongu_disi_yazim as dy

    cagri: list = []
    monkeypatch.setattr(dy, "arka_planda", lambda *a, **k: cagri.append(a))
    ai_router._ai_pro_kosulari_ac([])
    assert cagri == [], "boş listede kuyruğa iş girmemeli"

    def kuyruk_patla(*a, **k):
        raise RuntimeError("kuyruk yok")

    monkeypatch.setattr(dy, "arka_planda", kuyruk_patla)
    ai_router._ai_pro_kosulari_ac([(91, 40.0, 0.0)])  # istisna SIZMAZ

    acilan: list = []

    def govde(cid, *a, **k):
        if cid == 91:
            raise RuntimeError("DB yok")
        acilan.append((cid, k.get("_baslangic")))

    monkeypatch.setattr(coil_run_tracker, "_begin_coil_run_govde", govde)
    ai_router._ai_pro_kosulari_yaz([(91, 40.0, 0.0), (92, 50.0, 90.0)], 100, (1.0, 2.0))
    assert acilan == [(92, (1.0, 2.0))], f"bir bobinin kayıt hatası ötekini durdurmamalı: {acilan}"


def test_KRITIK_KARSIT_kuyrukta_bekleyen_iki_tur_ayni_bobine_IKI_kosu_ACMAZ(o, monkeypatch):
    sid = _baslat(o, monkeypatch)
    for _ in range(3):  # ilk turun yazımları kuyrukta bitmeden ikinci / üçüncü tur gelir
        _Hat.sonuc = _Sonuc([(P2, M2, 300)])
        j = ap.kare(o).json()
        assert j.get("driven") is True, j
    surulen = sorted(c["id"] for c in j["perCoil"] if c.get("suruldu"))
    k = _kosular(o, sid)
    assert [r[0] for r in k] == surulen, (
        f"bobin başına TEK koşu beklenir: sürülen {surulen} · kayıt {[r[0] for r in k]}"
    )

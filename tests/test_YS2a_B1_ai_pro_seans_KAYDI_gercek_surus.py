# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""YS2 a · B1 (YG0 25-11, ORTA — kayıt doğruluğu): kendiliğinden durdurulan AI Pro seansı geçmişte "Tamamlandı" YAZMAZ.

ÖLÇÜLEN KUSUR (tezgâh 25-11, `DENETIM\\YAYIN-GUNU.md` YG0 b): plaka doğrulanamadığı / plaka kaydığı için bobinleri durdurulan
(ya da HİÇ sürülmeyen) AI Pro seansı süre dolunca "Tamamlandı · tam süre · hedef doz" diye kapanıyordu:
  - 12:56 seansı (Kuyu D6): bobinler HİÇ sürülmedi, +30 sn "Plaka 30 sn boyunca doğrulanamadı" → geçmiş "Tamamlandı · 2 dk · 1,67 mT".
  - 13:06 seansı (T-8): sürüldü, plaka kaydırıldı, 13:08:04'te durdu, sürüş yeniden başlamadı → "Tamamlandı · 3 dk · 1,43 mT".
Araştırma kaydı / PDF verilmemiş dozu verilmiş gösteriyordu.

İSTENEN (istem 63 YS2 a): "Durduruldu" + neden (plaka kaydı / plaka doğrulanamadı / hedef kaybı) + GERÇEK sürüş süresi + gerçek doz
(sürülmediyse 0). Geçmiş listesi, detay, PDF, CSV ve telefon AYNI kaynaktan (DB satırı + `durdurma_nedeni` parametresi). Eski kayıt
DEĞİŞMEZ (yalnız yeni seanslar). Normal (kesintisiz) seans AYNEN "Tamamlandı".

KAPI: GERÇEK onay akışı + GERÇEK döngü (`ai-pro-dongu`) + GERÇEK HC (kayıtçı kuyruk) + GERÇEK tedavi DB'si (tmp); lokalizasyon /
doz planı sahte (Y300 kapısıyla aynı düzenek). Tolerans penceresi kısaltılır; süre dolumu ürünün kendi `_ai_started_at`'ı geri
alınarak (C2-1.1 kapısıyla aynı yol).
"""

from __future__ import annotations

import threading
import time

import ai_pro_aparati as ap
import numpy as np

D_PLAN = [0.30, 0.31, 0.32, 0.33, 0.34, 0.35, 0.36]
P_PLAN = [0.0, 10.0, 20.0, 30.0, 40.0, 50.0, 60.0]
DONGU_IP = ap.DONGU_IP_ADI
ENGEL_UYUMSUZ = {"engel": "plakaUyumsuz", "engel_ek": {"bulunan": 9, "sapma": 7.3}}
ENGEL_KAYDI = {"engel": "plakaKaydi", "engel_ek": {"gorulen": 17, "sapma": 17.0}}
HEDEF_DOZ = 1.43


class _SahteKamera:
    def __init__(self, *a, **k):
        pass

    def isOpened(self):  # noqa: N802
        return True

    def read(self):
        return True, np.zeros((8, 8, 3), dtype=np.uint8)

    def release(self):
        pass


def _ortam(monkeypatch, tmp_path, *, pencere_s: float, mod: str):
    from servers import ai_pro_hedef

    ns = ap.kur(monkeypatch, tmp_path, dongu_noop=False)
    durum = {"mod": mod, "engel": dict(ENGEL_UYUMSUZ)}

    def _lok(f, oid):
        b = durum["mod"] != "kayip"
        return (b, 10.0, 20.0, 30.0, 0.9 if b else 0.0, None, True)

    def _tahmin(x, y, z, oid):
        sag = ns.air._aktif_saglayici()
        if durum["mod"] == "engel":
            sag.son_odak_engel = dict(durum["engel"])  # ürünün `_odak_predict`i gibi: engel → sıfır plan
            return [0.0] * 7, [0.0] * 7, 0.0
        sag.son_odak_engel = None
        return list(D_PLAN), list(P_PLAN), 0.5

    petri = ai_pro_hedef.saglayici_al("petri")
    monkeypatch.setattr(petri, "son_odak_engel", None, raising=False)
    monkeypatch.setattr(ns.air.cv2, "VideoCapture", _SahteKamera)
    monkeypatch.setattr(ai_pro_hedef.KediSaglayici, "yukle", lambda self: None)
    monkeypatch.setattr(ai_pro_hedef.PetriSaglayici, "yukle", lambda self: None)
    monkeypatch.setattr(ns.air, "_arastirma_aipro_kapisi", lambda s: None)
    monkeypatch.setattr(ns.air, "_duzlem_kalibrasyonu_kapisi", lambda s: None)
    monkeypatch.setattr(ns.air, "_ORGAN_LOCALIZE_INTERVAL_S", 3600.0)
    monkeypatch.setattr(ns.air, "_SABIT_NUMUNE_TOLERANS_S", pencere_s, raising=False)
    monkeypatch.setattr(ns.air, "_localize_organ", _lok)
    monkeypatch.setattr(ns.air, "_predict_and_drive", _tahmin)
    monkeypatch.setattr(ns.air, "_doz_hatasi_bildirilen", {"anahtar": "<test-öncesi>"})
    return ns, durum


def _teldeki_duty(o) -> tuple:
    from kayitci_donanim import paket_coz

    paketler = o.hc.core._hw_send_queue.paketler
    return tuple(round(float(x), 4) for x in paket_coz(paketler[-1])[0][:7]) if paketler else ()


def _dongu_bitmesini_bekle(sure: float) -> bool:
    son = time.monotonic() + sure
    while time.monotonic() < son:
        if not any(t.name == DONGU_IP and t.is_alive() for t in threading.enumerate()):
            return True
        time.sleep(0.05)
    return False


def _satir(ns, sid) -> dict:
    d = ns.db.get_session_details(int(sid)) or {}
    neden = ((d.get("parameters") or {}).get("durdurma_nedeni") or {}).get("value")
    return {
        "durum": d.get("session_status"),
        "sure_dk": d.get("duration_minutes"),
        "doz": d.get("intensity_mt"),
        "neden": neden,
    }


def _kos(
    monkeypatch, tmp_path, *, mod: str, model: str = "petri", organ: int = 1, senaryo=None, pencere_s: float = 1.0
) -> dict:
    """Onaylı seans başlatır, `senaryo(ns, durum)`u koşar, süreyi doldurur, döngü bitince satırı döner."""
    from kayitci_donanim import gercek_hc

    ns, durum = _ortam(monkeypatch, tmp_path, pencere_s=pencere_s, mod=mod)
    if model == "kedi":
        monkeypatch.setattr(ns.air, "_ORGAN_LOCALIZE_INTERVAL_S", 0.0)  # kedi: her tur ölçülür (kayıp görülsün)
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(ns.api.state, "hardware", hc)
            ns.hc = hc
            _pid, r = ap.onayli_baslat(ns, organ=organ, model=model, sure_dk=1)
            assert r.status_code == 200, r.text[:300]
            with ns.api._session_lock:
                sid = ns.api._active_session.get("db_session_id")
            assert sid, "aparat: seans satırı açılmadı"
            ns.db.set_session_meta(sid, intensity_mt=HEDEF_DOZ)  # mühürdeki ODAK dozu (ürün başlatmada yazar)
            if senaryo is not None:
                senaryo(ns, durum)
            # Tedavi süresinin SONUNA gelinmiş gibi (C2-1.1 kapısının yolu): döngünün kendi süre sayacı 60 sn geri; seansın
            # kayıt saati (`start_mono`) de 60 sn geri → duvar saati süresi 1 dk (gerçek sürüş ise yalnız birkaç saniye).
            with ns.api._session_lock:
                ns.api._active_session["start_mono"] = float(ns.api._active_session["start_mono"]) - 60.0
            ns.air._ai_started_at = time.monotonic() - 60.0
            assert _dongu_bitmesini_bekle(8.0), "döngü kendi süre dolumunda bitmedi"
            assert not ap.calisan(ns), "süre dolumunda bobinler DURMADI (ön koşul)"
        return _satir(ns, sid)
    finally:
        ap.dongu_bitir(ns.air)
        ns.air._ai_loop_active = False
        ns.geri()


def _pencere_dolsun(ns, sure: float = 6.0) -> None:
    """Tolerans penceresi (1 sn) dolup STOP gidene dek bekle (bobin sürülmüyor)."""
    assert ap.bekle(lambda: not ap.calisan(ns), sure), "aparat: tolerans STOP'u gelmedi"
    time.sleep(1.5)  # STOP'tan sonra birkaç tur (sürüş yeniden başlamadı)


def test_KRITIK_B1_1256_HIC_SURULMEYEN_seans_DURDURULDU_sure_0_doz_0_neden_plaka(monkeypatch, tmp_path):
    """12:56: plaka baştan doğrulanamadı → bobin HİÇ sürülmedi → "Durduruldu (plaka doğrulanamadı)", 0 dk, doz 0."""

    def _senaryo(ns, durum):
        time.sleep(2.5)  # pencere (1 sn) dolar, STOP gider — sürüş hiç olmadı
        assert not ap.calisan(ns), "aparat: engelli plakada bobin sürüldü"

    satir = _kos(monkeypatch, tmp_path, mod="engel", senaryo=_senaryo)
    assert satir["durum"] == "stopped", (
        f"hiç sürülmeyen AI Pro seansı '{satir['durum']}' yazıldı (B1: Tamamlandı yazmamalı)"
    )
    assert satir["sure_dk"] == 0, f"hiç sürülmeyen seansın süresi {satir['sure_dk']} dk yazıldı (gerçek sürüş 0)"
    assert satir["doz"] == 0, f"hiç sürülmeyen seansın dozu {satir['doz']} mT yazıldı (verilmemiş doz)"
    assert satir["neden"] == "plaka_dogrulanamadi", f"durdurma nedeni kayda yazılmadı: {satir['neden']!r}"


def test_KRITIK_B1_1306_T8_plaka_KAYDI_durdurmasi_DURDURULDU_gercek_sure_doz_korunur(monkeypatch, tmp_path):
    """13:06 (T-8): sürüldü → plaka kaydı → STOP → yeniden sürülmedi → "Durduruldu (plaka kaydı)", sürüş süresi, doz = hedef."""

    def _senaryo(ns, durum):
        assert ap.bekle(lambda: bool(ap.calisan(ns)) and _teldeki_duty(ns) == tuple(D_PLAN), 6), (
            "aparat: plan sürülmedi"
        )
        durum["engel"] = dict(ENGEL_KAYDI)
        durum["mod"] = "engel"
        ns.air._ai_relocalize = True
        _pencere_dolsun(ns)

    satir = _kos(monkeypatch, tmp_path, mod="bulundu", senaryo=_senaryo)
    assert satir["durum"] == "stopped", f"plaka kaydıyla durmuş AI Pro seansı '{satir['durum']}' yazıldı (B1)"
    assert satir["neden"] == "plaka_kaydi", f"neden {satir['neden']!r} (beklenen plaka_kaydi)"
    # Gerçek sürüş yalnız birkaç saniye → 0 dk (duvar saati ise süre dolumuyla ≥ 1 dk yazıyordu).
    assert satir["sure_dk"] == 0, f"süre {satir['sure_dk']} dk — gerçek sürüş değil, duvar saati yazıldı"
    assert satir["doz"] == HEDEF_DOZ, (
        f"sürülmüş seansın hedef dozu {satir['doz']} oldu (sürüldüğü sürece hedef doz verildi)"
    )


def test_KARSIT_B1_kesintisiz_surulen_seans_TAMAMLANDI_AYNEN_neden_yok(monkeypatch, tmp_path):
    """Normal seans: baştan sona sürüldü → "Tamamlandı", süre duvar saatiyle (1 dk), doz hedef, neden YOK (davranış değişmez)."""

    def _senaryo(ns, durum):
        assert ap.bekle(lambda: bool(ap.calisan(ns)) and _teldeki_duty(ns) == tuple(D_PLAN), 6), (
            "aparat: plan sürülmedi"
        )

    satir = _kos(monkeypatch, tmp_path, mod="bulundu", senaryo=_senaryo)
    assert satir["durum"] == "completed", satir
    assert satir["neden"] is None, satir
    assert satir["doz"] == HEDEF_DOZ, satir
    assert satir["sure_dk"] == 1, satir


def test_KARSIT_B1_durup_YENIDEN_surulen_seans_TAMAMLANDI_kalir(monkeypatch, tmp_path):
    """Plaka bir süre doğrulanamadı (STOP) ama yeniden doğrulandı ve süre sonuna dek sürüldü → "Tamamlandı" (neden yok)."""

    def _senaryo(ns, durum):
        assert ap.bekle(lambda: bool(ap.calisan(ns)) and _teldeki_duty(ns) == tuple(D_PLAN), 6), (
            "aparat: plan sürülmedi"
        )
        durum["mod"] = "engel"
        ns.air._ai_relocalize = True
        # Pencere (3 sn) içinde son onaylı plan YENİDEN sürülür (sayılır), pencere dolunca STOP.
        _pencere_dolsun(ns, sure=10.0)
        durum["mod"] = "bulundu"
        ns.air._ai_relocalize = True
        assert ap.bekle(lambda: bool(ap.calisan(ns)), 6), "aparat: plaka doğrulanınca sürüş sürmedi"

    satir = _kos(monkeypatch, tmp_path, mod="bulundu", senaryo=_senaryo, pencere_s=3.0)
    assert satir["durum"] == "completed", satir
    assert satir["neden"] is None, satir
    assert satir["doz"] == HEDEF_DOZ, satir
    assert satir["sure_dk"] == 0, f"durup yeniden sürülen seansın süresi gerçek sürüş değil: {satir}"


def test_KRITIK_B1_kedi_HEDEF_KAYBI_ile_biten_seans_DURDURULDU_neden_hedef_kaybi(monkeypatch, tmp_path):
    """Kedi hattı: hedef kayboldu (N turda STOP), süre bitene dek bulunamadı → "Durduruldu (hedef kaybı)"."""

    def _senaryo(ns, durum):
        assert ap.bekle(lambda: bool(ap.calisan(ns)), 6), "aparat: kedi planı sürülmedi"
        durum["mod"] = "kayip"
        assert ap.bekle(lambda: not ap.calisan(ns), 10), "aparat: hedef kaybı STOP'u gelmedi"
        time.sleep(0.5)

    satir = _kos(monkeypatch, tmp_path, mod="bulundu", model="kedi", organ=2, senaryo=_senaryo)
    assert satir["durum"] == "stopped", satir
    assert satir["neden"] == "hedef_kaybi", satir
    assert satir["doz"] == HEDEF_DOZ, satir


# ── AYNI KAYNAK: geçmiş listesi · seans detayı · CSV · PDF (iki dil) aynı satırdan + aynı etiket ─────────────────────────────────
import csv  # noqa: E402
import io  # noqa: E402

import capraz  # noqa: E402
import pytest  # noqa: E402

BEKLENEN = {"tr": "Durduruldu (plaka kaydı)", "en": "Stopped (plate moved)"}


@pytest.fixture(params=["tr", "en"])
def dil(request):
    from utils import ceviri

    jeton = ceviri.istek_dili_var.set(request.param)
    try:
        yield request.param
    finally:
        ceviri.istek_dili_var.reset(jeton)


def _durmus_seans(tmp_path):
    """Ürünün kapanış yazıcıları ile: "Durduruldu" + `durdurma_nedeni` (YS2 a) — gerçek TreatmentHistoryDB (şifresiz tmp)."""
    from database.treatment_history_db import TreatmentHistoryDB
    from servers import api_server as api

    db = TreatmentHistoryDB(tmp_path / "gecmis")
    sid = db.start_session(treatment_mode="AI Pro · Petri Kuyu · Kuyu D3", patient_name="Petri 1")
    db.end_session(sid, duration_minutes=1, session_status="stopped")
    api._ai_pro_duzeltmesini_yaz(db, sid, {"doz_sifir": False, "neden": "plaka_kaydi"})
    return db, sid


def test_KRITIK_B1_neden_GECMIS_listesi_ve_DETAY_ayni_satirdan(tmp_path):
    from servers import history_router as h

    db, sid = _durmus_seans(tmp_path)
    try:
        satir = next(s for s in db.get_session_history() if s["id"] == sid)
        assert satir["durdurma_nedeni"] == "plaka_kaydi", satir
        detay = h.get_session_full_details(sid, db=db)
        assert detay["session"]["durdurma_nedeni"] == "plaka_kaydi", detay["session"]
    finally:
        db.close()


def test_KRITIK_B1_CSV_durum_sutunu_NEDENLI_iki_dilde(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from servers import api_server as api
    from servers import history_router as hr

    db, sid = _durmus_seans(tmp_path)
    api.app.dependency_overrides[hr.get_db] = lambda: db
    try:
        c = TestClient(api.app, client=("127.0.0.1", 53217))
        for d, beklenen in BEKLENEN.items():
            r = c.get("/api/history/export_csv", headers={"X-PEMF-Dil": d})
            assert r.status_code == 200, r.text[:200]
            tablo = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))
            sutun = tablo[0].index("Durum" if d == "tr" else "Status")
            assert [s[sutun] for s in tablo[1:] if s[0] == str(sid)] == [beklenen], (d, tablo)
    finally:
        api.app.dependency_overrides.pop(hr.get_db, None)
        db.close()


def test_KRITIK_B1_PDF_durum_satiri_NEDENLI(tmp_path, dil):
    fitz = capraz.paket_yoksa_atla("fitz")
    from utils.pdf_report_generator import PDFReportGenerator

    db, sid = _durmus_seans(tmp_path)
    try:
        yol = str(tmp_path / "s.pdf")
        PDFReportGenerator(tmp_path / "gecmis").generate_session_report(session_ids=[sid], output_path=yol)
        with fitz.open(yol) as d:
            metin = " ".join(" ".join(s.get_text().split()) for s in d)
        assert BEKLENEN[dil] in metin, metin[:800]
    finally:
        db.close()


def test_durum_etiketi_BILINMEYEN_ya_da_BOS_neden_EKLENMEZ(dil):
    from utils.seans_durum import durum_etiketi

    yalin = durum_etiketi("stopped")
    assert durum_etiketi("stopped", None) == yalin
    assert durum_etiketi("stopped", "") == yalin
    assert durum_etiketi("stopped", "uydurma_kod") == yalin
    assert durum_etiketi("stopped", "plaka_kaydi") == BEKLENEN[dil]


def test_muhasebe_birim_kollari():
    """Muhasebe: anahtarsız çağrı yok sayılır · bilinmeyen neden hedef kaybına düşer · düzeltilmeyen durum (acil durdurma)
    AYNEN · yinelenen STOP süreyi iki kez saymaz · kayıt sınırı · enerjiliyken kapanış ÖLÇÜLEN süreyi verir."""
    from servers import ai_pro_surus_muhasebesi as m

    for f in (m.basla, m.surdu):
        f(None)
    m.durdu("x", m.NEDEN_PLAKA_KAYDI)
    assert m.kapanis_duzeltmesi(None, "completed") is None
    m.basla(901)
    m.surdu(901, an=0.0)
    m.durdu(901, "bilinmeyen", an=90.0)
    m.durdu(901, "bilinmeyen", an=200.0)  # yinelenen STOP: süre yeniden sayılmaz
    assert m.kapanis_duzeltmesi(901, "completed", an=300.0) == {
        "durum": "stopped",
        "sure_dk": 1,
        "doz_sifir": False,
        "neden": m.NEDEN_HEDEF_KAYBI,
    }
    m.basla(902)
    m.durdu(902, m.NEDEN_PLAKA_KAYDI, an=1.0)
    assert m.kapanis_duzeltmesi(902, "EMERGENCY_STOPPED") is None, "acil durdurma durumu düzeltilmez"
    m.basla(903)
    m.surdu(903, an=0.0)
    m.durdu(903, m.NEDEN_PLAKA_KAYDI, an=10.0)
    m.surdu(903, an=20.0)
    assert m.kapanis_duzeltmesi(903, "completed", an=200.0) == {
        "durum": "completed",
        "sure_dk": 3,
        "doz_sifir": False,
        "neden": None,
    }
    for i in range(m._EN_COK_KAYIT + 3):
        m.basla(1000 + i)
    assert len(m._kayitlar) <= m._EN_COK_KAYIT
    m._kayitlar.clear()


def test_sabit_numune_neden_kodu_ENGELSIZ_karede_son_lokalizasyondan(monkeypatch):
    """Kare reddedildiyse (engel yok) kod son lokalizasyonun plaka engelinden: plakaKaydi → plaka kaydı, yoksa plaka doğrulanamadı."""
    from servers import ai_pro_hedef
    from servers import ai_router as air

    monkeypatch.setattr(air, "_saglayici_meta", lambda: {})
    monkeypatch.setattr(ai_pro_hedef, "plaka_engel_plani", lambda meta: {"engel": "plakaKaydi"})
    assert air._sabit_numune_neden_kodu(None) == "plaka_kaydi"
    monkeypatch.setattr(ai_pro_hedef, "plaka_engel_plani", lambda meta: None)
    assert air._sabit_numune_neden_kodu(None) == "plaka_dogrulanamadi"
    assert air._sabit_numune_neden_kodu({"engel": "plakaKaydi"}) == "plaka_kaydi"


def test_KRITIK_B1_genel_SEANS_DURDUR_ucu_da_ayni_duzeltmeyi_yazar(monkeypatch, tmp_path):
    """Plaka doğrulanamadı (hiç sürülmedi) → operatör genel `/api/session/stop` ile durdurdu → "Durduruldu (plaka doğrulanamadı)",
    0 dk, doz 0 (AI Pro durdur ucuyla aynı kural; kapanış yolu farklı)."""
    from kayitci_donanim import gercek_hc

    ns, durum = _ortam(monkeypatch, tmp_path, pencere_s=1.0, mod="engel")
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(ns.api.state, "hardware", hc)
            ns.hc = hc
            _pid, r = ap.onayli_baslat(ns, organ=1, model="petri", sure_dk=1)
            assert r.status_code == 200, r.text[:300]
            with ns.api._session_lock:
                sid = ns.api._active_session.get("db_session_id")
                ns.api._active_session["start_mono"] = float(ns.api._active_session["start_mono"]) - 30.0
            ns.db.set_session_meta(sid, intensity_mt=HEDEF_DOZ)
            time.sleep(2.5)  # pencere dolar, STOP gider — sürüş hiç olmadı
            rs = ns.c.post("/api/session/stop", json={})
            assert rs.status_code == 200, rs.text[:300]
            assert _dongu_bitmesini_bekle(8.0), "döngü durdurmada bitmedi"
        satir = _satir(ns, sid)
    finally:
        ap.dongu_bitir(ns.air)
        ns.air._ai_loop_active = False
        ns.geri()
    assert satir == {"durum": "stopped", "sure_dk": 0, "doz": 0, "neden": "plaka_dogrulanamadi"}, satir


def test_muhasebe_sid_seans_OKUNAMAZSA_None_doner_dongu_DUSMEZ(monkeypatch):
    """Seans sözlüğü okunamaz (bozuk / yok) → anahtar None: muhasebe yalnız kayıt içindir, döngüyü düşürmez."""
    from servers import ai_router as air
    from servers import api_server as api

    monkeypatch.setattr(api, "_active_session", None)
    assert air._muhasebe_sid() is None

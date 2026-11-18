# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""ODD B-1 · Y300 — petri (SABİT NUMUNE) AI Pro seansında yeniden ölçüm hedefi doğrulayamazsa sürüş KESİLMEZ.

ÖLÇÜLEN KUSUR (ODK-B keşfi 18-11, kum havuzu + gerçek günlük): `_ai_pro_loop` 10 sn'de bir yeniden lokalize ediyor; ölçümlerin
~yarısında görülen kuyular 24'lük düzene oturmuyor → ODAK planı ENGEL (`plakaUyumsuz`) → `_odak_predict` sıfır → "doz modeli
hatası" sayılıp 3 turda STOP → bir sonraki lokalizasyona (~10 sn) kadar bobin yok (sürüş ~10 sn açık / ~10 sn kapalı). Seans
BAŞINDA da ilk ölçüm doğrulanamayınca 10 sn yeniden ölçülmüyor, 3 turda STOP + "hedef kaybı" bildirimi (gerçek kurulumda
14:50:16–14:50:28 arası 3 kez).

KARAR Y300 (sahip): son onaylı planla 30 sn devam + hemen yeniden ölç; 30 sn doğrulanamazsa dur ve ekranda NEDEN; başlangıçta ilk
ölçüm beklenir. Kedi (P2, N turda STOP) DEĞİŞMEZ. ACİL DURDUR / elle durdur / süre AYNEN; mandal, niyet nesli ve kayıp nesli
kapıları devam eden sürüşte de geçerli.

KAPI: GERÇEK onay akışı + GERÇEK döngü (`ai-pro-dongu`) + GERÇEK HC (kayıtçı kuyruk, firmware aynası); lokalizasyon ve doz planı
sahte (sıra denetlenir). Tolerans penceresi testte kısaltılır (`_SABIT_NUMUNE_TOLERANS_S`), tur ~1 sn (ürün).
"""

from __future__ import annotations

import threading

import ai_pro_aparati as ap
import numpy as np
import pytest

D_PLAN = [0.30, 0.31, 0.32, 0.33, 0.34, 0.35, 0.36]
P_PLAN = [0.0, 10.0, 20.0, 30.0, 40.0, 50.0, 60.0]
DONGU_IP = ap.DONGU_IP_ADI
ENGEL = {"engel": "plakaUyumsuz", "engel_ek": {"bulunan": 9, "sapma": 7.3}}


class _SahteKamera:
    def __init__(self, *a, **k):
        pass

    def isOpened(self):  # noqa: N802
        return True

    def read(self):
        return True, np.zeros((8, 8, 3), dtype=np.uint8)

    def release(self):
        pass


def _ortam(monkeypatch, tmp_path, *, pencere_s: float):
    """Döngü ortamı: `durum["mod"]` ∈ {"bulundu", "engel", "kayip"}; `durum["lok_kancasi"]` döngünün lokalizasyonunda çağrılır."""
    from servers import ai_pro_hedef

    ns = ap.kur(monkeypatch, tmp_path, dongu_noop=False)
    durum = {"mod": "bulundu", "lok": 0, "lok_kancasi": None}

    def _lok(f, oid):
        if threading.current_thread().name == DONGU_IP:
            durum["lok"] += 1
            kanca = durum["lok_kancasi"]
            if kanca is not None:
                durum["lok_kancasi"] = None
                kanca()
        b = durum["mod"] != "kayip"
        return (b, 10.0, 20.0, 30.0, 0.9 if b else 0.0, None, True)

    def _tahmin(x, y, z, oid):
        sag = ns.air._aktif_saglayici()
        if durum["mod"] == "engel":
            sag.son_odak_engel = dict(ENGEL)  # ürünün `_odak_predict`i gibi: engel → sıfır plan
            return [0.0] * 7, [0.0] * 7, 0.0
        sag.son_odak_engel = None
        return list(D_PLAN), list(P_PLAN), 0.5

    petri = ai_pro_hedef.saglayici_al("petri")
    monkeypatch.setattr(petri, "son_odak_engel", None, raising=False)
    monkeypatch.setattr(ns.air.cv2, "VideoCapture", _SahteKamera)
    monkeypatch.setattr(ai_pro_hedef.KediSaglayici, "yukle", lambda self: None)
    monkeypatch.setattr(ai_pro_hedef.PetriSaglayici, "yukle", lambda self: None)
    # Araştırma bayrağı (Y145) ve sabit düzlem kalibrasyonu (Y259) kapıları bu dosyanın konusu değil (kendi kapıları var).
    monkeypatch.setattr(ns.air, "_arastirma_aipro_kapisi", lambda s: None)
    monkeypatch.setattr(ns.air, "_duzlem_kalibrasyonu_kapisi", lambda s: None)
    # Kendiliğinden (aralıklı) yeniden ölçüm YOK: yeniden ölçüm yalnız `_ai_relocalize` ile (Y300 "hemen yeniden ölç" ölçülür).
    monkeypatch.setattr(ns.air, "_ORGAN_LOCALIZE_INTERVAL_S", 3600.0)
    monkeypatch.setattr(ns.air, "_SABIT_NUMUNE_TOLERANS_S", pencere_s, raising=False)  # önce-kırmızı: eski üründe yok
    monkeypatch.setattr(ns.air, "_localize_organ", _lok)
    monkeypatch.setattr(ns.air, "_predict_and_drive", _tahmin)
    monkeypatch.setattr(ns.air, "_doz_hatasi_bildirilen", {"anahtar": "<test-öncesi>"})
    return ns, durum


def _teldeki_duty(o) -> tuple:
    from kayitci_donanim import paket_coz

    paketler = o.hc.core._hw_send_queue.paketler
    return tuple(round(float(x), 4) for x in paket_coz(paketler[-1])[0][:7]) if paketler else ()


def _son_ws(o) -> dict:
    for m in reversed(o.ws):
        if isinstance(m, dict) and m.get("type") == "ai_vision":
            return m.get("data") or {}
    return {}


def _bildirimler(o, parca: str) -> list:
    return [m for m, _t in o.bildirim if parca in m]


def _calistir(monkeypatch, tmp_path, *, pencere_s: float, model: str = "petri", organ: int = 1):
    """Bağlam: (ns, durum) — GERÇEK HC + onaylı başlatma; çıkışta döngü durdurulur ve beklenir."""
    from kayitci_donanim import gercek_hc

    class _Baglam:
        def __enter__(self):
            self.ns, self.durum = _ortam(monkeypatch, tmp_path, pencere_s=pencere_s)
            self.hc_ctx = gercek_hc()
            self.ns.hc = self.hc_ctx.__enter__()
            monkeypatch.setattr(self.ns.api.state, "hardware", self.ns.hc)
            return self.ns, self.durum

        def __exit__(self, *a):
            try:
                self.ns.c.post("/api/ai/pro/stop")
                ap.bekle(lambda: not self.ns.air._ai_loop_active, 5)
            finally:
                self.ns.air._ai_loop_active = False
                ap.dongu_bitir(self.ns.air)
                self.ns.hc.stop_all_coils()
                self.hc_ctx.__exit__(None, None, None)
                self.ns.geri()
            return False

    return _Baglam()


def _baslat_ve_sur(ns, *, model="petri", organ=1):
    _pid, r = ap.onayli_baslat(ns, organ=organ, model=model)
    assert r.status_code == 200, r.text[:300]
    assert ap.bekle(lambda: bool(ap.calisan(ns)) and _teldeki_duty(ns) == tuple(D_PLAN), 6), (
        f"aparat: döngü planı sürmedi (çalışan={ap.calisan(ns)})"
    )


# ── Y300: ENGEL turlarında son onaylı plan sürer, kayıp sayılmaz, hemen yeniden ölçülür ───────────────────────────────
def test_KRITIK_petri_ENGEL_turlarinda_SURUS_KESINTISIZ_son_plan_ve_HEMEN_yeniden_olcum(monkeypatch, tmp_path):
    with _calistir(monkeypatch, tmp_path, pencere_s=30.0) as (ns, durum):
        _baslat_ve_sur(ns)
        lok0, paket0 = durum["lok"], ap.paket_sayisi(ns)
        durum["mod"] = "engel"
        ap.bekle(lambda: False, 4.5)  # ≥ 4 tur > N=3: kedi kuralı olsaydı STOP gelirdi
        calisan, duty = ap.calisan(ns), _teldeki_duty(ns)
        surus = ap.surus_paketleri(ns, paket0)
        lok = durum["lok"] - lok0
        ws = _son_ws(ns)
    assert calisan == list(range(1, 8)) and duty == tuple(D_PLAN), (
        f"ENGEL turlarında sürüş KESİLDİ (Y300: son onaylı plan 30 sn sürer): çalışan={calisan}, telde={duty}"
    )
    assert len(surus) >= 3 and all(tuple(round(x, 4) for x in s[:7]) == tuple(D_PLAN) for s in surus), (
        f"son onaylı plan turlarda yeniden SÜRÜLMEDİ (paket={len(surus)})"
    )
    assert lok >= 3, f"ENGEL'de HEMEN yeniden ölçülmedi (4,5 sn'de {lok} lokalizasyon; aralık 3600 sn)"
    assert not _bildirimler(ns, "doz modeli"), f"plaka ENGEL'i 'doz modeli hatası' bildirildi: {ns.bildirim}"
    assert ws.get("dogrulamaKalanSn") is not None and 0 < ws["dogrulamaKalanSn"] <= 30, ws.get("dogrulamaKalanSn")
    assert not ws.get("surusDurduNeden"), ws.get("surusDurduNeden")


def test_KRITIK_petri_pencere_DOLUNCA_STOP_ve_panelde_NEDEN_sonra_dogrulaninca_SURER(monkeypatch, tmp_path):
    from servers import ai_pro_hedef

    with _calistir(monkeypatch, tmp_path, pencere_s=2.5) as (ns, durum):
        _baslat_ve_sur(ns)
        durum["mod"] = "engel"
        durdu = ap.bekle(lambda: ap.calisan(ns) == [], 6)
        ap.bekle(lambda: False, 1.2)  # STOP'tan sonra bir tur daha
        ws = _son_ws(ns)
        stop_sonrasi = ap.paket_sayisi(ns)
        ap.bekle(lambda: False, 1.5)
        yeniden = ap.surus_paketleri(ns, stop_sonrasi)
        neden_bildirimi = _bildirimler(ns, "doğrulanamadı")
        durum["mod"] = "bulundu"
        surdu = ap.bekle(lambda: _teldeki_duty(ns) == tuple(D_PLAN) and bool(ap.calisan(ns)), 5)
        ap.bekle(lambda: False, 1.2)
        ws_sonra = _son_ws(ns)
        with ns.api._session_lock:
            aktif = ns.api._active_session.get("is_active")
    engel_metni = ai_pro_hedef.odak_engel_metni(ENGEL, dil="tr")
    assert durdu, "pencere doldu ama bobinler DURDURULMADI"
    assert not yeniden, (
        f"pencere dolduktan sonra (plaka hâlâ doğrulanamıyor) bobin yeniden SÜRÜLDÜ: {len(yeniden)} paket"
    )
    assert ws.get("surusDurduNeden") and engel_metni in ws["surusDurduNeden"], (
        f"panelde NEDEN yok / engel metni yok: {ws.get('surusDurduNeden')!r}"
    )
    assert len(neden_bildirimi) == 1 and engel_metni in neden_bildirimi[0], (
        f"neden bildirimi tek değil / engel metni yok: {neden_bildirimi}"
    )
    assert surdu and aktif is True, "plaka yeniden doğrulanınca sürüş SÜRMEDİ (seans bitmemeli)"
    assert not ws_sonra.get("surusDurduNeden"), (
        f"sürüş sürerken eski neden panelde kaldı: {ws_sonra.get('surusDurduNeden')!r}"
    )


def test_KRITIK_petri_pencere_SON_BASARILI_plandan_sayilir_seans_basindan_DEGIL(monkeypatch, tmp_path):
    """Pencereden uzun süre doğrulanmış sürüşten SONRA gelen ENGEL yine pencere kadar tolerans alır (sayaç her başarıda tazelenir)."""
    with _calistir(monkeypatch, tmp_path, pencere_s=2.5) as (ns, durum):
        _baslat_ve_sur(ns)
        ap.bekle(lambda: False, 3.5)  # doğrulanmış sürüş > pencere
        durum["mod"] = "engel"
        ap.bekle(lambda: False, 1.2)  # son başarıdan < pencere
        calisan = ap.calisan(ns)
        bildirim = _bildirimler(ns, "doğrulanamadı")
    assert calisan == list(range(1, 8)) and not bildirim, (
        f"pencere seans başından sayıldı: son başarılı plandan {1.2} sn sonra STOP (çalışan={calisan}, bildirim={bildirim})"
    )


def test_KRITIK_petri_seans_BASINDA_ilk_olcum_beklenir_kayip_SAYILMAZ_hemen_yeniden_olculur(monkeypatch, tmp_path):
    from utils import estop_mandali

    with _calistir(monkeypatch, tmp_path, pencere_s=30.0) as (ns, durum):
        durum["mod"] = "kayip"
        kayip0 = estop_mandali.kayip_nesli()
        _pid, r = ap.onayli_baslat(ns, organ=1, model="petri")
        assert r.status_code == 200, r.text[:300]
        ap.bekle(lambda: False, 4.5)
        lok = durum["lok"]
        kayip1 = estop_mandali.kayip_nesli()
        kayip_bildirimi = _bildirimler(ns, "hedef") + _bildirimler(ns, "doğrulanamadı")
        durum["mod"] = "bulundu"
        surdu = ap.bekle(lambda: _teldeki_duty(ns) == tuple(D_PLAN) and bool(ap.calisan(ns)), 5)
    assert lok >= 3, f"seans başında doğrulanamayan ölçüm HEMEN yinelenmedi ({lok} lokalizasyon / 4,5 sn)"
    assert kayip1 == kayip0, "seans başında (ilk ölçüm doğrulanmadan) KAYIP STOP'u verildi"
    assert not kayip_bildirimi, f"seans başında kayıp / durdurma bildirimi: {kayip_bildirimi}"
    assert surdu, "ilk doğrulanan ölçümden sonra sürüş BAŞLAMADI"


# ── Kapılar devam eden sürüşte de geçerli ─────────────────────────────────────────────────────────────────────────────
def test_KRITIK_tolerans_suruşu_KAYIP_NESLI_kapisindan_gecer(monkeypatch, tmp_path):
    """Pencere içinde (son onaylı plan sürerken) bir kayıp STOP'u gelirse (ör. `/frame` yolu) eski gözleme dayanan sürüş REDDEDİLİR."""
    from utils import estop_mandali

    with _calistir(monkeypatch, tmp_path, pencere_s=30.0) as (ns, durum):
        _baslat_ve_sur(ns)
        durum["mod"] = "engel"
        ap.bekle(lambda: False, 1.5)
        assert ap.calisan(ns), "aparat: tolerans sürüşü yok"

        def _kayip_stopu():
            estop_mandali.kayip_nesli_artir()
            ns.api._stop_session_coils(range(1, 8))

        durum["lok_kancasi"] = _kayip_stopu  # sonraki turun ölçümü SIRASINDA (tur aynı turda son planı sürmeye çalışır)
        assert ap.bekle(lambda: durum["lok_kancasi"] is None and not ap.calisan(ns), 4), (
            "aparat: kayıp STOP'u uygulanmadı"
        )
        stop_paket = ap.paket_sayisi(ns)
        ap.bekle(lambda: False, 2.5)
        yeniden = ap.surus_paketleri(ns, stop_paket)
        son = ap.calisan(ns)
    assert not yeniden and son == [], (
        f"kayıp STOP'undan SONRA eski gözlemin planı sürüldü: paket={len(yeniden)} çalışan={son}"
    )


def test_KRITIK_tolerans_suruşu_NIYET_NESLI_kapisindan_gecer(monkeypatch, tmp_path):
    """Pencere içinde durdurma nesli artarsa (acil durdurma / durdurma) aynı turdaki son-plan sürüşü REDDEDİLİR."""
    from utils import estop_mandali

    with _calistir(monkeypatch, tmp_path, pencere_s=30.0) as (ns, durum):
        _baslat_ve_sur(ns)
        durum["mod"] = "engel"
        ap.bekle(lambda: False, 1.5)

        def _durdurma():
            estop_mandali.nesil_artir()
            ns.hc.stop_all_coils()

        durum["lok_kancasi"] = _durdurma
        assert ap.bekle(lambda: durum["lok_kancasi"] is None, 4), "aparat: kanca koşmadı"
        stop_paket = ap.paket_sayisi(ns)
        ap.bekle(lambda: False, 2.0)
        yeniden = ap.surus_paketleri(ns, stop_paket)
        son = ap.calisan(ns)
    assert not yeniden and son == [], f"durdurma neslinden SONRA son plan sürüldü: paket={len(yeniden)} çalışan={son}"


def test_KRITIK_tolerans_suruşu_ACIL_DURDUR_mandalinda_SURMEZ(monkeypatch, tmp_path):
    from utils import estop_mandali

    with _calistir(monkeypatch, tmp_path, pencere_s=30.0) as (ns, durum):
        _baslat_ve_sur(ns)
        durum["mod"] = "engel"
        ap.bekle(lambda: False, 1.5)

        def _acil():
            estop_mandali.mandalla("test-acil")
            ns.hc.stop_all_coils()

        durum["lok_kancasi"] = _acil
        assert ap.bekle(lambda: durum["lok_kancasi"] is None, 4), "aparat: kanca koşmadı"
        stop_paket = ap.paket_sayisi(ns)
        ap.bekle(lambda: False, 2.0)
        yeniden = ap.surus_paketleri(ns, stop_paket)
        son = ap.calisan(ns)
        estop_mandali.sifirla("test-izolasyon")
    assert not yeniden and son == [], (
        f"ACİL DURDUR mandalından SONRA son plan sürüldü: paket={len(yeniden)} çalışan={son}"
    )


# ── KARŞIT: kedi hattı AYNEN (N turda STOP) ─────────────────────────────────────────────────────────────────────────
def test_KARSIT_KEDI_hedef_kaybinda_N_turda_STOP_AYNEN(monkeypatch, tmp_path):
    with _calistir(monkeypatch, tmp_path, pencere_s=30.0) as (ns, durum):
        monkeypatch.setattr(ns.air, "_ORGAN_LOCALIZE_INTERVAL_S", 0.0)  # kedi: her tur ölçülür (kayıp görülsün)
        _baslat_ve_sur(ns, model="kedi", organ=2)
        durum["mod"] = "kayip"
        durdu = ap.bekle(lambda: ap.calisan(ns) == [], 5.5)
        bildirim = _bildirimler(ns, "doğrulanamadı")
        ws = _son_ws(ns)
    assert durdu, "kedi hattında hedef kaybında N turda STOP gelmedi (P2 değişmemeli)"
    assert not bildirim and ws.get("dogrulamaKalanSn") is None and not ws.get("surusDurduNeden"), (bildirim, ws)


def test_KARSIT_KEDI_sifir_doz_DOZ_HATASI_bildirimi_AYNEN(monkeypatch, tmp_path):
    with _calistir(monkeypatch, tmp_path, pencere_s=30.0) as (ns, durum):
        _baslat_ve_sur(ns, model="kedi", organ=2)
        durum["mod"] = "engel"
        durdu = ap.bekle(lambda: ap.calisan(ns) == [], 5.5)
    assert durdu and _bildirimler(ns, "doz modeli"), (
        "kedi hattında sıfır doz 'doz modeli hatası' + N turda STOP AYNEN değil"
    )


# ── Yardımcıların hata yolları: neden metni ve STOP hiçbir koşulda düşmez ─────────────────────────────────────────────
def test_neden_metni_ENGEL_metni_uretilemezse_GENEL_nedene_duser_iki_dilde():
    import servers.ai_router as air

    tr = air._sabit_numune_neden_metni(
        {"engel": "plakaUyumsuz", "engel_ek": {}}, dil="tr"
    )  # eksik yer tutucu (bulunan)
    assert "Plaka ya da kuyular kamerada tanınmadı" in tr and tr.startswith("Plaka 30 sn boyunca doğrulanamadı"), tr
    en = air._sabit_numune_neden_metni(None, dil="en")
    assert en.startswith("The plate could not be verified for 30 s") and "not recognised" in en, en


def test_STOP_kayip_nesli_ya_da_STOP_hata_verse_de_STOP_gider_ve_neden_doner(monkeypatch):
    import servers.ai_router as air
    import servers.api_server as api
    from utils import estop_mandali

    cagri: list = []

    def _patla():
        raise RuntimeError("kayıp nesli (test)")

    monkeypatch.setattr(estop_mandali, "kayip_nesli_artir", _patla)
    monkeypatch.setattr(api, "_stop_session_coils", lambda ids: cagri.append(list(ids)) or [])
    monkeypatch.setattr(api, "_push_notification", lambda m, t="info": None)
    assert air._sabit_numune_stopu(None, bildir=False) and cagri == [list(range(1, 8))], cagri

    def _stop_patla(ids):
        raise RuntimeError("STOP (test)")

    monkeypatch.setattr(api, "_stop_session_coils", _stop_patla)
    assert "doğrulanamadı" in air._sabit_numune_stopu(None, bildir=True)

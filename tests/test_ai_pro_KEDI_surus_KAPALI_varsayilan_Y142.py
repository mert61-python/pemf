# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""Y142 (S-AI1.5, sahip 2026-10-13) — KEDİ AI Pro KAPALI DÖNGÜ SÜRÜŞÜ, kabin ↔ EM eğitim çerçevesi tezgâhta doğrulanana dek KAPALI.

ÖLÇÜLEN DURUM (AI-1 K2 · AI incelemesi §2.1): kedi AI Pro onaylanınca `cat_organ` konumu `em_kedi`ye verilip 7 bobin
sürülüyordu. Hocanın uyarısı "EM'e henüz güvenme, bobine gönderme": kedi kabin çerçevesi ile EM eğitim çerçevesinin aynı
olduğu hiçbir ölçümle kanıtlanmadı; kabin içi eğitim dışı hedef yalnız `ood` ile İŞARETLENİP SÜRÜLÜYORDU.

SÖZLEŞME (Y142): kedi sağlayıcısıyla AI Pro seansının BAŞLATILMASI ve BOBİN SÜRÜŞÜ açık bir bayrak (`PEMF_KEDI_AIPRO_SURUS`)
verilene dek REDDEDİLİR — eylem söyleyen Türkçe iletiyle. Bayrak yok / boş / bozuk → KAPALI (yalnız `1|true|yes|on` açar).
Analiz, hazırlık, öneri (`/propose`) ve onay ekranı GÖRÜNÜR kalır; öneri yanıtı sürüşün kapalı olduğunu söyler, onay ucu
onay MÜHRÜ basmaz (onay = "otonom tedaviyi başlatıyorum" beyanı; başlatılamayan tedavi için kayda "onaylandı" yazılmaz).
Kapı uçtan uca: `/start` (onay YANMAZ), sürüş anı (`/frame` mühür kapısı) ve EN ALT sürüş katı (`_drive_coils_ai_pro` —
döngü ve `/frame` ortak) — GPU servisi kolu dahil. Elle seans (Kontrol), araştırma sağlayıcıları ve ACİL DURDUR ETKİLENMEZ
(Ö.4-Y8). Bayrak açıkken bugünkü davranış AYNEN (süitin geri kalanı bayrak açık koşar — `conftest._kedi_aipro_surus_bugunku`).

KAPI: GERÇEK onay akışı + GERÇEK `HardwareController` (kayıtçı kuyruk, firmware aynası) + GERÇEK `/frame` / döngü / sürüş.
⚠️ Beklenen metin ve bayrak değerleri BURADA sabittir (ürün sabitinden OKUNMAZ — mutasyon hedefi ölçütü taşımasın).
"""

from __future__ import annotations

import ai_pro_aparati as ap
import numpy as np
import pytest

BAYRAK = "PEMF_KEDI_AIPRO_SURUS"
MESAJ = (
    "Kedi AI Pro sürüşü, kabin konumu doğrulanana kadar kapalı. Analizi ve öneriyi inceleyebilirsiniz; "
    "seansı Kontrol ekranından elle başlatın."
)
D7 = [0.30, 0.31, 0.32, 0.33, 0.34, 0.35, 0.36]
P7 = [0.0, 10.0, 20.0, 30.0, 40.0, 50.0, 60.0]

#: Kapalı sayılması GEREKEN değerler (None = değişken YOK). Boş dize ve sayı benzeri bozuk değerler AÇMAZ.
KAPALI = [None, "", " ", "0", "false", "off", "no", "bozuk", "1x", "2", "evet"]
#: Açan değerler (araştırma bayrağıyla AYNI anlam: kırpılır, küçük harfe çevrilir).
ACIK = ["1", "true", "yes", "on", " ON ", "True"]


def _bayrak(mp, deger):
    if deger is None:
        mp.delenv(BAYRAK, raising=False)
    else:
        mp.setenv(BAYRAK, deger)


@pytest.fixture
def o(monkeypatch, tmp_path):
    from kayitci_donanim import gercek_hc

    ns = ap.kur(monkeypatch, tmp_path)
    monkeypatch.setattr(ns.air, "_predict_and_drive", lambda *a, **k: (list(D7), list(P7), 0.5))
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(ns.api.state, "hardware", hc)
            ns.hc = hc
            yield ns
    finally:
        ns.c.post("/api/ai/pro/stop")
        if ns.hc is not None:
            ns.hc.stop_all_coils()
        ns.geri()


def _onayli_kayit(model: str = "kedi", organ: int = 2) -> str:
    """Onaylı öneri kaydı — onay UCUNU atlayarak (eski istemci / yarış: onay bayrak kapanmadan önce alınmış)."""
    from servers import ai_approval

    rec = ai_approval.create("ai_pro", {"organ_id": organ, "duration_minutes": 5, "model": model})
    ai_approval.approve(rec["id"], "hekim@test.local")
    return rec["id"]


def _gpu_kolu(o, monkeypatch):
    """GPU servisi kolu: `ai_service_enabled()` True + EN ALT ağ katı (`delegate_json_sync`) sahte → doz servisten gelir.
    Kolun gerçekten koştuğu çağrı sayacıyla kanıtlanır (`gpu["em_kedi"]`)."""
    gpu = {"em_kedi": 0}

    def _servis(ad, govde, *a, **k):
        assert ad == "em_kedi", f"aparat: beklenmeyen GPU çağrısı {ad!r}"
        gpu["em_kedi"] += 1
        return {
            **{f"D{i}": D7[i - 1] for i in range(1, 8)},
            **{f"P{i}": P7[i - 1] for i in range(1, 8)},
            "result_E": 0.5,
        }

    from servers import ai_pro_hedef

    monkeypatch.setattr(o.air, "ai_service_enabled", lambda: True)
    monkeypatch.setattr(o.air, "delegate_json_sync", _servis)
    # Doz yolu GERÇEK sağlayıcıdan geçsin (aparatın üst kat sahtesi kaldırılır): kedi → `_predict_and_drive_gpu`.
    monkeypatch.setattr(o.air, "_predict_and_drive", _URUN["_predict_and_drive"])
    monkeypatch.setattr(o.air, "_ai_hedef_modeli", ai_pro_hedef.KediSaglayici.ad)
    return gpu


#: Aparatın (ve `o`nun) üst katta yamaladığı ÜRÜN `_predict_and_drive`'ı — yamadan ÖNCE saklanır (GPU kolu gerçek sağlayıcıdan geçsin).
_URUN: dict = {}


@pytest.fixture(autouse=True)
def _urun_predict_sakla():
    from servers import ai_router as air

    _URUN["_predict_and_drive"] = air._predict_and_drive
    _URUN["_ai_pro_loop"] = air._ai_pro_loop  # `ap.kur` döngüyü no-op'a yamalar — döngü kolu GERÇEĞİNİ çağırır
    yield
    _URUN.clear()


# ── /start: başlatma REDDEDİLİR, onay YANMAZ ────────────────────────────────────────────────────────────────────────────


def test_YAPISAL_S_AIK6_bayrak_device_env_ve_launcher_ile_TASINIR_varsayilan_KAPALI():
    """S-AIK.6 açık #1 (LN L8): bayrağın taşıyıcısı yazılı — `deploy/device.env` satırı `=0` (servis kurulumu NSSM'e yazar) ve
    launcher backend ortamına KOŞULSUZ `"0"` varsayılanla geçirir (ortamdaki değer korunur). Y142 bayrağı KAPALI kalır.
    MUTASYON: satırı silin / `=1` yapın ya da launcher varsayılanını `"1"` yapın → KIRMIZI."""
    from pathlib import Path

    kok = Path(__file__).resolve().parents[1]
    satir = [
        s
        for s in (kok / "deploy" / "device.env").read_text(encoding="utf-8").splitlines()
        if s.startswith(f"{BAYRAK}=")
    ]
    assert satir == [f"{BAYRAK}=0"], f"device.env taşıyıcısı yok ya da KAPALI değil: {satir}"
    rs = (kok / "launcher" / "core" / "src" / "install.rs").read_text(encoding="utf-8").replace("\r\n", "\n")
    assert f'pub const ENV_KEDI_AIPRO_SURUS: &str = "{BAYRAK}";' in rs, "launcher sabiti yok"
    assert (
        "        ENV_KEDI_AIPRO_SURUS.to_string(),\n        getenv(ENV_KEDI_AIPRO_SURUS)\n"
        "            .filter(|v| !v.trim().is_empty())\n            .unwrap_or_else(|| \"0\".to_string()),"
    ) in rs, "launcher bayrağı geçirmiyor ya da varsayılanı KAPALI değil"


@pytest.mark.parametrize("deger", KAPALI, ids=lambda d: "YOK" if d is None else repr(d))
def test_KRITIK_Y142_bayrak_KAPALIYKEN_kedi_AI_Pro_BASLATILMAZ_onay_YANMAZ(o, monkeypatch, deger):
    from servers import ai_approval

    _bayrak(monkeypatch, deger)
    pid = _onayli_kayit()
    once = ap.paket_sayisi(o)
    r = o.c.post("/api/ai/pro/start", json={"proposal_id": pid})
    assert r.status_code == 409, f"bayrak {deger!r} iken kedi AI Pro BAŞLADI ({r.status_code}): {r.text[:200]}"
    assert r.json().get("detail") == MESAJ, f"ret metni eylem söylemiyor / farklı: {r.json().get('detail')!r}"
    assert not o.air._ai_loop_active, "ret sonrası döngü bayrağı kalktı"
    with o.api._session_lock:
        assert not o.api._active_session.get("is_active"), "ret sonrası seans AKTİF yazıldı"
    assert ai_approval.dogrula(pid)["status"] == "approved", "başlamayan tedavi hekimin onayını YAKTI (D1.E06)"
    assert not ap.surus_paketleri(o, once) and not ap.calisan(o), "ret sonrası bobin SÜRÜLDÜ"


def test_KRITIK_Y142_GPU_kolu_dahil_baslatma_REDDEDILIR(o, monkeypatch):
    _bayrak(monkeypatch, None)
    gpu = _gpu_kolu(o, monkeypatch)
    pid = _onayli_kayit()
    r = o.c.post("/api/ai/pro/start", json={"proposal_id": pid})
    assert r.status_code == 409 and r.json().get("detail") == MESAJ, (
        f"GPU kolunda kedi başladı: {r.status_code} {r.text[:200]}"
    )
    assert gpu["em_kedi"] == 0  # başlatma doz istemez; GPU kolunun sürüş tarafı aşağıdaki kare testinde ölçülür


# ── /approve: onay mührü basılmaz ──────────────────────────────────────────────────────────────────────────────────────


def test_KRITIK_Y142_onay_ucu_bayrak_KAPALIYKEN_kedi_onerisini_ONAYLAMAZ(o, monkeypatch):
    from servers import ai_approval

    _bayrak(monkeypatch, None)
    rec = ai_approval.create("ai_pro", {"organ_id": 2, "duration_minutes": 5, "model": "kedi"})
    r = o.c.post("/api/ai/pro/approve", json={"proposal_id": rec["id"], "operator_email": "hekim@test.local"})
    assert r.status_code == 409, f"başlatılamayacak tedavi için onay mührü basıldı ({r.status_code}): {r.text[:200]}"
    assert r.json().get("detail") == MESAJ
    assert ai_approval.get(rec["id"])["status"] == "pending", "onay kaydı karara bağlandı"
    # Model alanı OLMAYAN eski öneri kaydı kedi sayılır (`saglayici_al(None)` → kedi) → o da onaylanmaz (fail-closed).
    eski = ai_approval.create("ai_pro", {"organ_id": 2, "duration_minutes": 5})
    r2 = o.c.post("/api/ai/pro/approve", json={"proposal_id": eski["id"], "operator_email": "hekim@test.local"})
    assert r2.status_code == 409 and ai_approval.get(eski["id"])["status"] == "pending", r2.text[:200]


def test_KRITIK_Y142_REDDET_ve_bulunamayan_oneri_DAVRANISI_AYNI(o, monkeypatch):
    """Red ucu kapıdan ETKİLENMEZ (gerekçe kayda geçer); bilinmeyen öneri yine 404."""
    from servers import ai_approval

    _bayrak(monkeypatch, None)
    rec = ai_approval.create("ai_pro", {"organ_id": 2, "duration_minutes": 5, "model": "kedi"})
    r = o.c.post("/api/ai/pro/reject", json={"proposal_id": rec["id"], "reason": "sürüş kapalı — elle uygulanacak"})
    assert r.status_code == 200 and ai_approval.get(rec["id"])["status"] == "rejected", r.text[:200]
    assert o.c.post("/api/ai/pro/approve", json={"proposal_id": "yok-boyle-oneri"}).status_code == 404


# ── /propose + /status: öneri GÖRÜNÜR, sürüşün kapalı olduğu SÖYLENİR ───────────────────────────────────────────────────


def _taze_kedi(o, organ: int = 2):
    import time

    o.air._ai_hedef_modeli = "kedi"
    o.air._ai_organ_id = organ
    o.air._ai_organ_cache.update(
        {
            "x_mm": 10.0,
            "y_mm": 20.0,
            "z_mm": 30.0,
            "reliability": 0.9,
            "localized": True,
            "overlay_bgr": None,
            "at": time.time(),
            "organ_id": organ,
            "kedi_var": True,
            "guven_dokumu": None,
            "model": "kedi",
        }
    )


def test_KRITIK_Y142_oneri_GORUNUR_kalir_ve_SURUSUN_KAPALI_oldugunu_soyler(o, monkeypatch):
    _bayrak(monkeypatch, None)
    _taze_kedi(o)
    r = o.c.post("/api/ai/pro/propose", json={"organ_id": 2, "duration_minutes": 5})
    assert r.status_code == 200, (
        f"Y142 öneriyi de kapattı (analiz/öneri görünür kalmalı): {r.status_code} {r.text[:200]}"
    )
    j = r.json()
    assert j["specs"]["model"] == "kedi" and any(d > 0 for d in j["specs"]["D"]), j["specs"]
    assert j.get("surusAcik") is False, f"öneri sürüşün kapalı olduğunu söylemiyor: {j.get('surusAcik')!r}"
    assert j.get("surusKapaliNedeni") == MESAJ, j.get("surusKapaliNedeni")
    st = o.c.get("/api/ai/pro/status").json()
    assert st.get("kediAiProSurusAcik") is False, (
        f"/status kedi sürüş durumunu taşımıyor: {st.get('kediAiProSurusAcik')!r}"
    )


@pytest.mark.parametrize("deger", ACIK, ids=repr)
def test_KARSIT_Y142_bayrak_ACIKKEN_oneri_ve_durum_SURUS_ACIK_der(o, monkeypatch, deger):
    _bayrak(monkeypatch, deger)
    _taze_kedi(o)
    j = o.c.post("/api/ai/pro/propose", json={"organ_id": 2, "duration_minutes": 5}).json()
    assert j.get("surusAcik") is True and not j.get("surusKapaliNedeni"), j
    assert o.c.get("/api/ai/pro/status").json().get("kediAiProSurusAcik") is True


# ── SÜRÜŞ ANI: mühürlü kedi seansı olsa bile (eski onay / başka yol) bobin SÜRÜLMEZ ────────────────────────────────────


def test_KRITIK_Y142_EN_ALT_KAT_muhurlu_kedi_seansinda_surus_BOBIN_SURMEZ(o, monkeypatch):
    from utils import estop_mandali

    _bayrak(monkeypatch, None)
    ap.muhurlu_seans_yaz(o.api, sure_dk=10, model="kedi")
    once = ap.paket_sayisi(o)
    with estop_mandali.surus_baglami(estop_mandali.nesil()):
        surulen = o.air._drive_coils_ai_pro(D7, P7)
    assert surulen == [] and not ap.surus_paketleri(o, once) and not ap.calisan(o), (
        f"bayrak kapalıyken mühürlü kedi seansı EN ALT katta sürüldü: {surulen} çalışan={ap.calisan(o)}"
    )
    # Mühürde model YOKSA (eski seans) kedi sayılır → yine sürülmez.
    ap.muhurlu_seans_yaz(o.api, sure_dk=10, model="")
    with estop_mandali.surus_baglami(estop_mandali.nesil()):
        assert o.air._drive_coils_ai_pro(D7, P7) == [] and not ap.calisan(o)


@pytest.mark.parametrize("gpu", [False, True], ids=["CPU", "GPU_servisi"])
def test_KRITIK_Y142_kare_yolu_muhurlu_kedi_seansinda_SURMEZ_ve_seans_SURULEBILIR_sayilmaz(o, monkeypatch, gpu):
    _bayrak(monkeypatch, None)
    sayac = _gpu_kolu(o, monkeypatch) if gpu else None
    # ⚠️ Etkin model AÇIKÇA kedi: önceki testten kalan model (ör. "sahte") mühürle uyuşmazsa sürüş anı kapısı model
    # uyuşmazlığından zaten False döner ve Y142 katmanı ölçülmez (mutasyonla görüldü: CPU kolu yalnız bu yüzden yeşildi).
    monkeypatch.setattr(o.air, "_ai_hedef_modeli", "kedi")
    # Sürüş anı kapısının BAĞIMSIZ gözlemi: sürülemez seansta doz HİÇ hesaplanmaz. (EN ALT kat sürüşü zaten keser ve kare
    # yolu sürüş olmayınca `sessionActive`i False'a çeker — o iddia tek başına bu katmanı ölçmez: katman maskesi.)
    tahmin = {"n": 0}
    _ic = o.air._predict_and_drive
    monkeypatch.setattr(
        o.air, "_predict_and_drive", lambda *a, **k: tahmin.__setitem__("n", tahmin["n"] + 1) or _ic(*a, **k)
    )
    o.air._ai_organ_id = 2
    ap.muhurlu_seans_yaz(o.api, sure_dk=10, model="kedi")
    once = ap.paket_sayisi(o)
    j = ap.kare(o).json()
    assert j.get("driven") is not True and not ap.surus_paketleri(o, once) and not ap.calisan(o), (
        f"bayrak kapalıyken kare yolu kediyi sürdü: driven={j.get('driven')} çalışan={ap.calisan(o)}"
    )
    assert j.get("sessionActive") is False, f"kare yolu kedi seansını sürülebilir saydı: {j.get('sessionActive')!r}"
    assert tahmin["n"] == 0, (
        f"sürülemez kedi seansında kare yolu doz hesapladı ({tahmin['n']} kez) — sürüş anı kapısı yok"
    )
    if gpu:
        assert sayac["em_kedi"] == 0, "sürülemeyen seansta GPU doz servisi çağrıldı"


def _dongu_bir_tur(o, monkeypatch):
    """GERÇEK `_ai_pro_loop` bir tur (sahte kamera; mühür + döngü mührü VAR) → (uyku, hatalar, önceki paket sayısı)."""
    from dongu_tek_tur import bir_tur_kos
    from servers import ai_pro_hedef
    from utils import estop_mandali

    monkeypatch.setattr(ai_pro_hedef.KediSaglayici, "yukle", lambda self: None)

    class _Kamera:
        def __init__(self, *a, **k):
            pass

        def isOpened(self):  # noqa: N802
            return True

        def read(self):
            return True, np.zeros((8, 8, 3), dtype=np.uint8)

        def release(self):
            pass

    monkeypatch.setattr(o.air.cv2, "VideoCapture", _Kamera)
    o.air._ai_organ_id = 2
    o.air._ai_hedef_modeli = "kedi"
    o.air._ai_relocalize = True
    ap.muhurlu_seans_yaz(o.api, sure_dk=10, model="kedi", onay_hedefi=2)
    monkeypatch.setattr(o.air, "_ai_dongu_no", o.air._ai_dongu_no + 1)
    muhur = {"nesil": estop_mandali.nesil(), "onay": "test-onay", "dongu": o.air._ai_dongu_no, "hedef": 2}
    o.air._ai_loop_active = True
    once = ap.paket_sayisi(o)
    try:
        uyku, hatalar = bir_tur_kos(lambda: _URUN["_ai_pro_loop"](muhur))
    finally:
        o.air._ai_loop_active = False
    assert not hatalar, hatalar
    assert uyku == 1, f"aparat: döngü bir TUR koşmadı (uyku {uyku}) — kapı vakum olurdu"
    assert o.air._ai_organ_cache.get("localized") is True, "aparat: döngü turunda hedef konumlanmadı (sürüşe varılmadı)"
    return once


def test_KRITIK_Y142_DONGU_muhurlu_kedi_seansi_bir_turda_BOBIN_SURMEZ(o, monkeypatch):
    _bayrak(monkeypatch, None)
    once = _dongu_bir_tur(o, monkeypatch)
    assert not ap.surus_paketleri(o, once) and not ap.calisan(o), (
        f"bayrak kapalıyken döngü kediyi sürdü: çalışan={ap.calisan(o)}"
    )


def test_KARSIT_Y142_DONGU_bayrak_ACIKKEN_bir_turda_7_bobini_SURER(o, monkeypatch):
    _bayrak(monkeypatch, "1")
    once = _dongu_bir_tur(o, monkeypatch)
    assert ap.surus_paketleri(o, once) and sorted(ap.calisan(o)) == list(range(1, 8)), ap.calisan(o)


# ── KARŞIT: bayrak açıkken bugünkü davranış ────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("deger", ACIK, ids=repr)
def test_KARSIT_Y142_bayrak_ACIKKEN_kedi_seansi_BASLAR_ve_kare_yolu_SURER(o, monkeypatch, deger):
    _bayrak(monkeypatch, deger)
    pid = _onayli_kayit()
    r = o.c.post("/api/ai/pro/start", json={"proposal_id": pid})
    assert r.status_code == 200, f"bayrak {deger!r} iken kedi başlamadı: {r.text[:200]}"
    j = ap.kare(o).json()
    assert j.get("driven") is True and sorted(ap.calisan(o)) == list(range(1, 8)), (j.get("driven"), ap.calisan(o))


def test_KARSIT_Y142_bayrak_ACIKKEN_GPU_kolu_SURER(o, monkeypatch):
    _bayrak(monkeypatch, "1")
    gpu = _gpu_kolu(o, monkeypatch)
    pid = _onayli_kayit()
    assert o.c.post("/api/ai/pro/start", json={"proposal_id": pid}).status_code == 200
    j = ap.kare(o).json()
    assert j.get("driven") is True and gpu["em_kedi"] >= 1 and sorted(ap.calisan(o)) == list(range(1, 8)), (
        j.get("driven"),
        gpu,
        ap.calisan(o),
    )


# ── ETKİLENMEYENLER: elle seans, ACİL DURDUR (Ö.4-Y8), araştırma sağlayıcıları ─────────────────────────────────────────


def test_KRITIK_Y142_ELLE_seans_ve_ACIL_DURDUR_ETKILENMEZ(o, monkeypatch):
    _bayrak(monkeypatch, None)
    r = o.c.post(
        "/api/session/start",
        json={"mode": "Manuel", "frequency": 100, "duty": 40, "phase": 0, "duration_minutes": 20, "coil_ids": [1, 2]},
    )
    assert r.status_code == 200 and r.json().get("status") == "success", f"elle seans etkilendi: {r.text[:200]}"
    assert sorted(ap.calisan(o)) == [1, 2], ap.calisan(o)
    e = o.c.post("/api/hardware/emergency_stop")
    assert e.status_code == 200, f"ACİL DURDUR etkilendi: {e.status_code} {e.text[:200]}"
    assert not ap.calisan(o), f"ACİL DURDUR'dan sonra çalışan bobin kaldı: {ap.calisan(o)}"


def test_KRITIK_Y142_ARASTIRMA_saglayicisi_kedi_bayragindan_ETKILENMEZ(o, monkeypatch):
    """Kedi bayrağı KAPALI, araştırma bayrağı AÇIK → araştırma modeli bugünkü gibi başlar ve sürer."""
    from servers import ai_pro_hedef

    class _Sag:
        ad = "sahte"
        title = "Sahte Araştırma"
        subject_label = "sahte özne"
        achieved_B = 0.001
        duty_sum = 2.4
        join_timeout_s = 6.0
        varsayilan_hedef = 0

        def hedef_idleri(self):
            return frozenset({0, 1, 2})

        def yukle(self):
            return None

        def localize(self, frame_bgr, hedef_id):
            return (True, 1.0, 2.0, 3.0, 0.9, None, True, None)

        def predict(self, x, y, z, hedef_id):
            return list(D7), list(P7), 0.3

        def hedef_adi(self, hedef_id):
            return f"Sahte {hedef_id}"

        def ipucu(self, ozne_var, hedef_adi):
            return "sahte ipucu"

        def son_lokalizasyon_meta(self):
            return {}

        def xai_sensitivity(self, *a, **k):
            return None

    _bayrak(monkeypatch, None)
    monkeypatch.setenv("PEMF_ARASTIRMA_AIPRO", "1")
    monkeypatch.setitem(ai_pro_hedef.SAGLAYICILAR, "sahte", _Sag())
    pid = _onayli_kayit(model="sahte")
    r = o.c.post("/api/ai/pro/start", json={"proposal_id": pid})
    assert r.status_code == 200, f"kedi bayrağı araştırma sağlayıcısını da kapattı: {r.text[:200]}"
    j = ap.kare(o).json()
    assert j.get("driven") is True and sorted(ap.calisan(o)) == list(range(1, 8)), (j.get("driven"), ap.calisan(o))

# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.81 · B-5.3 (+ İG-5.3, 5.4, 5.9, 5.11, 5.29, 5.36) — E-stop/durdurma SONRASI uçuştaki START'lar REDDEDİLİR.

ÖLÇÜLEN KUSUR (aday doğrulaması D0, ayrı süreç + tel kaydı): `/frame` ve AI Pro döngüsü seansı tahminden ÖNCE bir kez
denetliyor; tahmin/lokalizasyon 0,3–2,2 sn sürüyor; arada gelen acil durdurma ya da `/ai/pro/stop` STOP'unu gönderiyor,
sonra uçuştaki tur bobinleri YENİDEN enerjiliyordu (döngüsüz kol 11/30, onaylı akış 11/40, `/ai/pro/stop` kolu 2/20; tur
ortasında E-stop'ta kalan bobinler 12/10/8/6 paket; damla serviste 36,5 sn sonra). "Tahmin sonrası yeniden denetim" (yama F)
30'da 1 kaçırdı (denetle-sonra-yap) → denetim `HardwareController`'da DURUM KİLİDİ ALTINDA, nesil jetonuyla yapılmalı.

YARIŞ KAPILARI — tek koşuma güvenilmez, zamanlama ZORLANIR (`threading.Event`), her kol ≥30 deneme; önce-kırmızı ORAN,
sonra-yeşil aynı sayıda 0:
  * TAHMİN PENCERESİ: `_predict_and_drive` Event'te bloklu iken E-stop / `/ai/pro/stop` / `/api/session/stop` gelir.
  * ABA: E-stop → Sıfırla → YENİ seans (elle) açılır, SONRA bloklu eski tur serbest kalır — "seans aktif mi" yeniden
    denetimi bu kolu deler (yeni seans aktif), mandal tek başına deler (sıfırlandı); yalnız nesil jetonu kapatır.
  * TUR ORTASI (İG-5.4): sürüş bobin k'dan sonra bloklanır, E-stop gelir, sürüş devam eder (k=1..4).
  * KİLİT ALTINDA DENETİM: test `HardwareController._state_lock`'u tutarken sürüş iş parçacığı START'a girer; kilide
    TAKILDIĞI an E-stop koşulur, kilit bırakılır. Denetim kilidin DIŞINDAYSA (denetle-sonra-yap) START geçer → KIRMIZI.
Ölçüt: E-stop/durdurma STOP paketinden SONRA donanıma giden duty>0 paket SAYISI (firmware aynası çözücü) ve çalışan bobin.
"""

from __future__ import annotations

import threading
import time

import ai_pro_aparati as ap
import pytest

DENEME = 30


@pytest.fixture
def o(monkeypatch, tmp_path):
    from kayitci_donanim import gercek_hc

    ns = ap.kur(monkeypatch, tmp_path)
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(ns.api.state, "hardware", hc)
            ns.hc = hc
            yield ns
    finally:
        ns.geri()


def _yeni_tur(o):
    """Bir denemeyi temiz başlat: tahmin engeli kur, mandal/AI Pro durumunu sıfırla, onaylı seans aç."""
    o.tahmin.engel = threading.Event()
    o.tahmin.girdi.clear()
    ap.mandali_sifirla(o.c)
    o.c.post("/api/ai/pro/stop")
    ap.mandali_sifirla(o.c)
    _pid, r = ap.onayli_baslat(o)
    assert r.status_code == 200 and r.json().get("status") == "success", f"aparat: AI Pro başlamadı {r.text[:200]}"


def _bloklu_kare(o):
    t, kutu = ap.kare_arka_planda(o)
    assert o.tahmin.girdi.wait(10), "aparat: /frame tahmine ulaşmadı"
    return t, kutu


def _serbest_birak(o, t):
    o.tahmin.engel.set()
    t.join(15)
    assert not t.is_alive(), "aparat: /frame bitmedi"


def _sonuc(o, sonra: int) -> bool:
    """True = bu denemede E-stop/durdurma SONRASI donanım sürüldü ya da bobin çalışır kaldı (İHLAL)."""
    return bool(ap.surus_paketleri(o, sonra)) or bool(ap.calisan(o))


# ── TAHMİN PENCERESİ ─────────────────────────────────────────────────────────────────────────────
def test_KRITIK_tahmin_SIRASINDA_ESTOP_sonra_frame_SURMEZ_N30(o):
    ihlal = 0
    for _ in range(DENEME):
        _yeni_tur(o)
        t, kutu = _bloklu_kare(o)
        o.api._emergency_stop_all("manual")
        sonra = ap.paket_sayisi(o)
        _serbest_birak(o, t)
        ihlal += _sonuc(o, sonra)
    assert ihlal == 0, (
        f"tahmin penceresinde E-stop: {DENEME} denemenin {ihlal}'inde E-stop SONRASI bobin YENİDEN enerjilendi"
    )


def test_KRITIK_ABA_estop_SIFIRLA_yeni_elle_seans_ESKI_tur_SURMEZ_N30(o):
    ihlal = durum_ezildi = 0
    for _ in range(DENEME):
        _yeni_tur(o)
        t, kutu = _bloklu_kare(o)
        o.api._emergency_stop_all("manual")
        ap.mandali_sifirla(o.c)
        r = o.c.post(
            "/api/session/start",
            json={"coil_ids": [6], "frequency": 50, "duty": 5, "phase": 0, "duration_minutes": 5, "mode": "Manuel"},
        )
        assert r.status_code == 200, f"aparat: elle seans açılmadı {r.text[:200]}"
        sonra = ap.paket_sayisi(o)
        n = len(o.ws)
        _serbest_birak(o, t)
        eski_tur = [d for d in ap.surus_paketleri(o, sonra) if any(abs(x - ap.D_AI) < 1e-6 for x in d[:5])]
        ihlal += bool(eski_tur)
        # İG-5.36 (ABA kolu): mandal SIFIRLANDIKTAN sonra bayat AI turu canlı durumu "AI Pro … aktif" diye ezemez —
        # burada mandal kuralı yardım etmez, yalnız nesil (yeni elle seans gerçekten aktif).
        durum_ezildi += any(
            m.get("type") == "session_update"
            and (m.get("data") or {}).get("isActive")
            and str((m.get("data") or {}).get("mode", "")).startswith("AI Pro")
            for m in o.ws[n:]
        )
        o.c.post("/api/session/stop")
    assert ihlal == 0, (
        f"ABA: {DENEME} denemenin {ihlal}'inde E-stop'tan ÖNCEKİ AI turu, Sıfırla + yeni seanstan sonra bobin 1-5'i sürdü"
    )
    assert durum_ezildi == 0, f"ABA: {durum_ezildi}/{DENEME} denemede bayat AI turu yeni seansın canlı durumunu EZDİ"


@pytest.mark.parametrize("durdurma", ["/api/ai/pro/stop", "/api/session/stop"])
def test_KRITIK_tahmin_SIRASINDA_DURDURMA_sonra_frame_SURMEZ_N30(o, durdurma):
    ihlal = 0
    for _ in range(DENEME):
        _yeni_tur(o)
        t, kutu = _bloklu_kare(o)
        r = o.c.post(durdurma)
        assert r.status_code in (200, 409), r.text[:200]
        sonra = ap.paket_sayisi(o)
        _serbest_birak(o, t)
        ihlal += _sonuc(o, sonra)
    assert ihlal == 0, f"{durdurma}: {DENEME} denemenin {ihlal}'inde durdurma SONRASI uçuştaki kare bobini sürdü"


def _yeni_onayli_seans_hemen(o):
    """Durdurmanın HEMEN ardından yeni onaylı AI Pro seansı (operatör yeniden başlattı): yeni MÜHÜR geçerli —
    "sürüş anında seans mühürlü mü" bakışı eski karenin sürüşünü DURDURAMAZ; yalnız nesil ayırt eder."""
    o.air._ai_loop_active = False  # sunucu döngüsü bu kolda no-op; gerçek döngü durdurmada çıkardı
    ap.mandali_sifirla(o.c)
    _pid, r = ap.onayli_baslat(o)
    assert r.status_code == 200 and r.json().get("status") == "success", f"aparat: yeni seans açılmadı {r.text[:200]}"


@pytest.mark.parametrize("durdurma", ["/api/ai/pro/stop", "/api/session/stop", "estop"])
def test_KRITIK_ABA_durdurma_ve_HEMEN_YENI_AI_PRO_seansi_ESKI_kare_SURMEZ_N30(o, durdurma):
    ihlal = 0
    for _ in range(DENEME):
        _yeni_tur(o)
        t, kutu = _bloklu_kare(o)
        if durdurma == "estop":
            o.api._emergency_stop_all("manual")
        else:
            assert o.c.post(durdurma).status_code in (200, 409)
        _yeni_onayli_seans_hemen(o)
        sonra = ap.paket_sayisi(o)
        _serbest_birak(o, t)  # yeni seansa HİÇ kare gönderilmedi: sonrasındaki her AI dozu eski karedendir
        ihlal += bool(ap.surus_paketleri(o, sonra))
    assert ihlal == 0, (
        f"{durdurma} + yeni AI Pro seansı: {DENEME} denemenin {ihlal}'inde DURDURMA ÖNCESİ kare yeni seansta bobin sürdü"
    )


# ── TUR ORTASI (İG-5.4) ──────────────────────────────────────────────────────────────────────────
def test_KRITIK_TUR_ORTASI_estop_kalan_bobinler_START_almaz_k1_4_N32(o, monkeypatch):
    ihlal = 0
    deneme = 0
    for k in (1, 2, 3, 4):
        for _ in range(8):
            deneme += 1
            _yeni_tur(o)
            o.tahmin.engel = None  # bu kolda tahmin bloklanmaz; sürüş bobin k'dan sonra bloklanır
            gecti = threading.Event()
            devam = threading.Event()
            orj = o.hc.update_coil

            def _sarili(cid, *a, _k=k, _orj=orj, _g=gecti, _d=devam, **kw):
                sonuc = _orj(cid, *a, **kw)
                if cid == _k and kw.get("start", True) and not _g.is_set():
                    _g.set()
                    assert _d.wait(10), "aparat: tur-ortası engeli kalkmadı"
                return sonuc

            monkeypatch.setattr(o.hc, "update_coil", _sarili)
            t, kutu = ap.kare_arka_planda(o)
            assert gecti.wait(10), f"aparat: sürüş bobin {k}'ya ulaşmadı"
            o.api._emergency_stop_all("manual")
            sonra = ap.paket_sayisi(o)
            devam.set()
            t.join(15)
            monkeypatch.setattr(o.hc, "update_coil", orj)
            ihlal += _sonuc(o, sonra)
    assert ihlal == 0, f"tur ortasında E-stop: {deneme} denemenin {ihlal}'inde kalan bobinler E-stop SONRASI START aldı"


# ── KİLİT ALTINDA DENETİM (denetle-sonra-yap mutantını yakalar) ────────────────────────────────────
class _IzlenenKilit:
    """`_state_lock` vekili: ANA DIŞI bir iş parçacığı kilidi istediği an `bekleyen` kurulur."""

    def __init__(self, ic, ana):
        self.ic, self.ana, self.bekleyen = ic, ana, threading.Event()

    def acquire(self, *a, **k):
        if threading.current_thread() is not self.ana:
            self.bekleyen.set()
        return self.ic.acquire(*a, **k)

    def release(self):
        self.ic.release()

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *exc):
        self.release()


def test_KRITIK_denetim_DURUM_KILIDI_altinda_kilide_takilan_START_ESTOP_sonrasi_GECMEZ_N30(o, monkeypatch):
    m = ap.mandal_modulu()
    ihlal = 0
    for _ in range(DENEME):
        ap.mandali_sifirla(o.c)
        o.hc.stop_all_coils()
        tok = m.nesil() if m is not None else None
        kilit = _IzlenenKilit(o.hc._state_lock, threading.current_thread())
        monkeypatch.setattr(o.hc, "_state_lock", kilit)
        sonuc: dict = {}
        with kilit:
            kw = {"nesil": tok} if tok is not None else {}
            t = threading.Thread(
                target=lambda: sonuc.update(r=o.hc.update_coil(2, 100.0, 40.0, 0.0, 5, start=True, **kw)), daemon=True
            )
            t.start()
            assert kilit.bekleyen.wait(10), "aparat: sürüş iş parçacığı durum kilidine ulaşmadı"
            o.api._emergency_stop_all("manual")
            sonra = ap.paket_sayisi(o)
        t.join(10)
        monkeypatch.setattr(o.hc, "_state_lock", kilit.ic)
        ihlal += bool(ap.surus_paketleri(o, sonra)) or bool(ap.calisan(o)) or sonuc.get("r") is True
    assert ihlal == 0, (
        f"kilide takılmış START: {DENEME} denemenin {ihlal}'inde E-stop'tan SONRA geçti (denetim kilit altında değil)"
    )


def test_KRITIK_YOLDAN_BAGIMSIZ_bayat_nesil_update_coil_ve_start_all_REDDEDER(o):
    """Çağrı düzeyi (yoldan bağımsız): E-stop ÖNCESİ alınan niyet, Sıfırla'dan SONRA bile kabul edilmez; taze niyet edilir."""
    m = ap.mandal_modulu()
    assert m is not None, "nesil jetonu yok: E-stop öncesi niyeti ayırt edecek mekanizma yok (utils.estop_mandali)"
    tok = m.nesil()
    o.api._emergency_stop_all("manual")
    ap.mandali_sifirla(o.c)
    sonra = ap.paket_sayisi(o)
    assert o.hc.update_coil(1, 100.0, 40.0, 0.0, 5, start=True, nesil=tok) is False, (
        "bayat nesilli update_coil kabul edildi"
    )
    with m.surus_baglami(tok):
        assert o.hc.update_coil(1, 100.0, 40.0, 0.0, 5, start=True) is False, "bağlamdaki bayat nesil yok sayıldı"
        assert o.hc.start_all_coils(100.0, 40.0, 0.0, 5) is False, "start_all_coils bayat nesli yok saydı"
    assert not ap.surus_paketleri(o, sonra)
    assert o.hc.update_coil(1, 100.0, 40.0, 0.0, 5, start=True, nesil=m.nesil()) is True, (
        "TAZE niyet reddedildi (KARŞIT)"
    )


# ── DÖNGÜ (İG-5.29 / İG-5.3 kolu 2 / İG-5.36 teardown etiketi) ──────────────────────────────────────
class _SahteKamera:
    def __init__(self, *a, **k):
        pass

    def isOpened(self):
        return True

    def read(self):
        import numpy as np

        return True, np.zeros((8, 8, 3), dtype=np.uint8)

    def release(self):
        pass


@pytest.fixture
def dongu(monkeypatch, tmp_path):
    """GERÇEK `_ai_pro_loop`: sahte kamera + hızlı lokalizasyon; model yüklemesi no-op."""
    from kayitci_donanim import gercek_hc
    from servers import ai_pro_hedef

    ns = ap.kur(monkeypatch, tmp_path, dongu_noop=False)
    monkeypatch.setattr(ns.air.cv2, "VideoCapture", _SahteKamera)
    monkeypatch.setattr(ai_pro_hedef.KediSaglayici, "yukle", lambda self: None)
    canli = {"n": 0}
    gercek = ns.air._ai_pro_loop

    def _sayan(*a, **k):
        canli["n"] += 1
        try:
            return gercek(*a, **k)
        finally:
            canli["n"] -= 1

    monkeypatch.setattr(ns.air, "_ai_pro_loop", _sayan)
    ns.canli = canli
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(ns.api.state, "hardware", hc)
            ns.hc = hc
            yield ns
    finally:
        ns.air._ai_loop_active = False
        ap.bekle(lambda: canli["n"] == 0, 5)
        ns.geri()


def test_KRITIK_DONGU_tahmin_SIRASINDA_estop_YENIDEN_ENERJI_YOK_ve_etiket_EZILMEZ_N30(dongu):
    o = dongu
    ihlal = etiket_ezildi = 0
    for _ in range(DENEME):
        o.tahmin.engel = threading.Event()
        o.tahmin.girdi.clear()
        ap.mandali_sifirla(o.c)
        o.c.post("/api/ai/pro/stop")
        assert ap.bekle(lambda: o.canli["n"] == 0, 5), "aparat: önceki döngü bitmedi"
        ap.mandali_sifirla(o.c)
        _pid, r = ap.onayli_baslat(o)
        assert r.status_code == 200 and r.json().get("status") == "success", r.text[:200]
        assert o.tahmin.girdi.wait(10), "aparat: döngü tahmine ulaşmadı"
        o.api._emergency_stop_all("manual")
        sonra = ap.paket_sayisi(o)
        o.tahmin.engel.set()
        assert ap.bekle(lambda: o.canli["n"] == 0, 8), "döngü E-stop'tan sonra bitmedi"
        ihlal += _sonuc(o, sonra)
        with o.ls._live_state_lock:
            etiket = o.ls._live_state["activeTreatment"].get("mode")
        etiket_ezildi += etiket != "Acil Durdurma"
    assert ihlal == 0, f"döngü: {DENEME} denemenin {ihlal}'inde E-stop SONRASI bobin YENİDEN enerjilendi"
    assert etiket_ezildi == 0, f"döngü teardown'ı {etiket_ezildi}/{DENEME} denemede 'Acil Durdurma' etiketini EZDİ"


def test_KRITIK_IG511_stop_start_ARDI_ARDINA_DONGULER_BIRIKMEZ(dongu):
    import random

    o = dongu
    rnd = random.Random(511)
    o.tahmin.engel = None
    for _ in range(15):
        ap.mandali_sifirla(o.c)
        _pid, r = ap.onayli_baslat(o)
        assert r.status_code == 200, r.text[:200]
        time.sleep(0.15)
        o.c.post("/api/ai/pro/stop")
        time.sleep(rnd.uniform(0.0, 0.05))
    _pid, r = ap.onayli_baslat(o)
    time.sleep(2.5)  # eski döngülerin bir sonraki tur denetimine ulaşması için (tur ≈ 1 sn)
    assert o.canli["n"] <= 1, f"/stop→/start ardı ardına: {o.canli['n']} AI Pro döngüsü AYNI ANDA canlı (birikiyor)"


# ── /frame canlı durum yazımı (İG-5.36) ───────────────────────────────────────────────────────────
def test_KRITIK_IG536_estop_SONRASI_isActive_true_YAYINI_YOK_etiket_ACIL_DURDURMA_N30(o):
    yayin = ezilme = 0
    for _ in range(DENEME):
        _yeni_tur(o)
        t, kutu = _bloklu_kare(o)
        o.api._emergency_stop_all("manual")
        n = len(o.ws)
        _serbest_birak(o, t)
        yayin += any(m.get("type") == "session_update" and (m.get("data") or {}).get("isActive") for m in o.ws[n:])
        with o.ls._live_state_lock:
            ezilme += o.ls._live_state["activeTreatment"].get("mode") != "Acil Durdurma"
    assert yayin == 0, (
        f"E-stop SONRASI 'isActive:true' WS yayını {yayin}/{DENEME} denemede (uçuştaki /frame canlı durumu yazdı)"
    )
    assert ezilme == 0, f"'Acil Durdurma' etiketi {ezilme}/{DENEME} denemede ezildi"


# ── süre kaynağı = seans mührü (İG-5.9) ───────────────────────────────────────────────────────────
def test_KRITIK_IG59_surus_suresi_SEANS_MUHRUNDEN_bayat_global_KULLANILMAZ(o):
    from kayitci_donanim import paket_coz

    _pid, r = ap.onayli_baslat(o, sure_dk=3)
    assert r.status_code == 200, r.text[:200]
    o.air._ai_duration_min = 1  # başarısız bir /start'tan kalan BAYAT global (İG-5.16 (d))
    o.air._ai_started_at = time.monotonic() - 70  # global'e göre süre DOLMUŞ; mühre göre 3 dk'nın başındayız
    n = ap.paket_sayisi(o)
    j = ap.kare(o).json()
    assert j.get("driven") is True, (
        f"mühre göre süresi dolmamış seansta /frame sürmedi (bayat global): {j.get('driven')}"
    )
    paketler = [paket_coz(p) for p in o.hc.core._hw_send_queue.paketler[n:]]
    sureler = {paketler[-1][3][i] for i in range(5)} if paketler else set()
    assert sureler == {3}, f"telde süre alanı mühürdeki 3 dk değil: {sureler}"
    kalan = [o.hc._coil_deadline[i] - time.monotonic() for i in range(1, 6)]
    assert all(170 <= k <= 181 for k in kalan), f"yazılım deadline'ı mühürden değil: {kalan}"

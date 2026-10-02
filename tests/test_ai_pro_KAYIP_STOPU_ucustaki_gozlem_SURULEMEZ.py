# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""İG-5.1 · 1-C bağımsız inceleme i7-F-1 — hedef-kaybı STOP'undan ÖNCE başlamış "bulundu" gözlemi o STOP'tan sonra SÜREMEZ.

ÖLÇÜLEN KUSUR (i7: zorlanmış zamanlama 30/30, gerçek döngüyle 30/30, iki istemcili doğal zamanlamada ~%16): kayıp STOP'u
sürüş yetkisini BİLEREK kesmez (sahip: hedef yeniden bulununca sürüş sürer). Bulunmuş ama tahminde (ya da lokalizasyonda)
bekleyen UÇUŞTAKİ kare, N kayıp karesinin STOP'undan SONRA geçerli nesille sürüp bobini yeniden enerjiliyordu; STOP yalnız
`seri == N` anında gittiği için hedef kayıp kaldıkça bir daha STOP gelmiyor, döngü de durdurmuyordu → bobinler seans son
tarihine dek HEDEFSİZ enerjili (İG-5.1'in kapattığı zararın aynısı).

DÜZELTME: (1) HEDEF-KAYBI NESLİ (`estop_mandali.kayip_nesli_artir` — sürüş nesli ve mandal DEĞİŞMEZ): her kayıp STOP'u
(döngü ya da `/frame`) STOP'tan ÖNCE artırır; "bulundu" gözlemi LOKALİZASYON BAŞINDA damgalanır; sürüş damga ≠ güncel ise
`HardwareController`da DURUM KİLİDİ ALTINDA reddedilir. Bayat gözlem kayıp sayılır (sayacı sıfırlamaz). (2) ARKA KALKAN:
N ve sonrasındaki HER kayıp karede/turda STOP yinelenir (idempotent; bildirim N'de bir).

KAPI (GERÇEK `HardwareController` + paket kaydı; GERÇEK `/frame`, gerçek döngü):
  KRİTİK A  — tahminde bekleyen kare; N kayıp karesi → STOP; kare bırakılır: STOP'tan sonra duty>0 paket YOK (×30).
  KRİTİK A′ — lokalizasyonda bekleyen kare (gözlem STOP'tan önce başladı, STOP'tan sonra bitti): sürülmez, sayaç sıfırlanmaz (×30).
  KRİTİK C  — gerçek döngü YALNIZ kendi kayıp turlarıyla STOP eder; tahmindeki `/frame` karesi ardından sürmez (×5).
  KRİTİK D  — döngünün KENDİ gözlemi tahmindeyken `/frame` STOP eder; döngü bırakılınca sürmez (×5).
  KRİTİK arka kalkan — kayıp sürerken HERHANGİ bir yolla yeniden enerjilenen bobin bir sonraki kayıp karesinde / turunda durur.
  KARŞIT — uçuşta kare yokken STOP kalıcı; ve her KRİTİK A/A′ denemesinin sonunda hedef yeniden bulununca sürüş SÜRER
  (kayıp nesli aşırı engellemez; seans bitmez).
"""

from __future__ import annotations

import threading

import ai_pro_aparati as ap
import numpy as np
import pytest

N_PIN = 3  # ⚠️ ürünün sabitinden OKUNMAZ (mutant kaynaktan okumak kapıyı kör eder — i7-F-5) — İG-5.1'in değeri
DENEME = 30
DONGU_IP = "ai-pro-dongu"


@pytest.fixture
def o(monkeypatch, tmp_path):
    from kayitci_donanim import gercek_hc

    ns = ap.kur(monkeypatch, tmp_path)
    monkeypatch.setattr(ns.air, "_ORGAN_LOCALIZE_INTERVAL_S", 0.0)  # her kare lokalize eder (gözlem = kare)
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(ns.api.state, "hardware", hc)
            ns.hc = hc
            yield ns
    finally:
        ns.geri()


def _yerellestirme(o, monkeypatch) -> dict:
    """Sahte lokalizasyon: `mod` bulundu/kayip; `engel` kuruluysa BİR "bulundu" lokalizasyonu orada bekler (uçuşta)."""
    durum = {"mod": "bulundu", "engel": None, "girdi": threading.Event()}

    def _lok(f, oid):
        b = durum["mod"] == "bulundu"
        ev = durum["engel"]
        if b and ev is not None:
            durum["engel"] = None  # yalnız bu çağrı bekler
            durum["girdi"].set()
            assert ev.wait(10), "aparat: lokalizasyon engeli 10 sn'de kalkmadı"
        return (b, 10.0, 20.0, 30.0, 0.9 if b else 0.0, None, True)

    monkeypatch.setattr(o.air, "_localize_organ", _lok)
    return durum


def _baslat_ve_sur(o):
    _pid, r = ap.onayli_baslat(o)
    assert r.status_code == 200, r.text[:200]
    assert ap.kare(o).json().get("driven") is True and ap.calisan(o), "aparat: hedef bulunmuşken ilk kare sürmedi"


def _kayip_stopu(o, durum):
    durum["mod"] = "kayip"
    for _ in range(N_PIN):
        ap.kare(o)
    assert ap.calisan(o) == [], f"aparat: {N_PIN} kayıp karesinden sonra STOP yok ({ap.calisan(o)})"
    return ap.paket_sayisi(o)


def _surmedi(o, a_kutu, stop_paket, kol: str):
    a = a_kutu.get("yanit")
    a_driven = a.json().get("driven") if a is not None and a.status_code == 200 else a_kutu.get("hata", a)
    yeniden = ap.surus_paketleri(o, stop_paket)
    calisan = ap.calisan(o)
    assert not yeniden and not calisan, (
        f"{kol}: kayıp STOP'undan ÖNCE başlamış 'bulundu' gözlemi STOP'tan SONRA SÜRDÜ (A.driven={a_driven}, STOP sonrası "
        f"duty>0 paket={len(yeniden)}, çalışan={calisan})"
    )


def _kayip_suruyor_sonra_yeniden_bulma(o, durum, kol: str):
    for _ in range(2 * N_PIN):
        ap.kare(o)  # hedef HÂLÂ kayıp
    assert ap.calisan(o) == [], f"{kol}: hedef kayıpken bobinler yeniden çalışıyor {ap.calisan(o)}"
    # KARŞIT: kayıp nesli aşırı engellemez — hedef YENİDEN bulununca (yeni gözlem) sürüş sürer, seans bitmez.
    durum["mod"] = "bulundu"
    j = ap.kare(o).json()
    assert j.get("driven") is True and ap.calisan(o), (
        f"{kol}: hedef yeniden bulununca sürüş SÜRMEDİ ({j.get('driven')})"
    )
    with o.api._session_lock:
        assert o.api._active_session.get("is_active") is True, f"{kol}: kayıp STOP'u seansı bitirdi"


@pytest.mark.parametrize("deneme", range(DENEME))
def test_KRITIK_TAHMINDE_ucustaki_kare_kayip_STOPundan_sonra_SURULEMEZ(o, monkeypatch, deneme):
    durum = _yerellestirme(o, monkeypatch)
    _baslat_ve_sur(o)
    o.tahmin.engel = threading.Event()  # A: hedef BULUNMUŞ kare tahminde bekler (uçuşta)
    o.tahmin.girdi.clear()
    t, kutu = ap.kare_arka_planda(o)
    assert o.tahmin.girdi.wait(5), "aparat: A tahmine girmedi"
    stop_paket = _kayip_stopu(o, durum)
    o.tahmin.engel.set()
    t.join(10)
    assert not t.is_alive(), "aparat: A bitmedi"
    _surmedi(o, kutu, stop_paket, "A (tahminde)")
    _kayip_suruyor_sonra_yeniden_bulma(o, durum, "A (tahminde)")


@pytest.mark.parametrize("deneme", range(DENEME))
def test_KRITIK_LOKALIZASYONDA_ucustaki_gozlem_kayip_STOPundan_sonra_SURULEMEZ(o, monkeypatch, deneme):
    durum = _yerellestirme(o, monkeypatch)
    _baslat_ve_sur(o)
    ev = threading.Event()
    durum["engel"] = ev  # A′: "bulundu" gözlemi lokalizasyonda bekler (kare STOP'tan ÖNCE, sonuç STOP'tan SONRA)
    durum["girdi"].clear()
    t, kutu = ap.kare_arka_planda(o)
    assert durum["girdi"].wait(5), "aparat: A′ lokalizasyona girmedi"
    stop_paket = _kayip_stopu(o, durum)
    ev.set()
    t.join(10)
    assert not t.is_alive(), "aparat: A′ bitmedi"
    seri = o.air._frame_kayip["seri"]
    _surmedi(o, kutu, stop_paket, "A′ (lokalizasyonda)")
    assert seri > N_PIN, (
        f"bayat 'bulundu' gözlemi kayıp sayacını SIFIRLADI (seri={seri}) — bayat gözlem kayıp sayılmalı"
    )
    _kayip_suruyor_sonra_yeniden_bulma(o, durum, "A′ (lokalizasyonda)")


def test_KARSIT_ucusta_kare_yokken_kayip_STOPu_KALICI(o, monkeypatch):
    for _ in range(3):
        durum = _yerellestirme(o, monkeypatch)
        _baslat_ve_sur(o)
        stop_paket = _kayip_stopu(o, durum)
        for _ in range(2 * N_PIN):
            ap.kare(o)
        assert ap.calisan(o) == [] and not ap.surus_paketleri(o, stop_paket)
        o.c.post("/api/ai/pro/stop")


def test_KRITIK_ARKA_KALKAN_frame_kayip_SURERKEN_yeniden_enerjilenen_bobin_DURDURULUR(o, monkeypatch):
    """(2) katmanı TEK BAŞINA: kayıp STOP'unu atlatan HERHANGİ bir sürüşün vekili olarak bobin 1 yol dışından yeniden
    enerjilenir; hedef hâlâ kayıpken bir sonraki kayıp karesi onu durdurmalı (eskiden STOP yalnız N. karede)."""
    durum = _yerellestirme(o, monkeypatch)
    _baslat_ve_sur(o)
    _kayip_stopu(o, durum)
    assert o.hc.update_coil(1, 1.0, 30.0, 0.0, 5, start=True) is True and ap.calisan(o) == [1], "aparat: vekil sürüş"
    ap.kare(o)  # N+1. kayıp karesi
    assert ap.calisan(o) == [], "kayıp sürerken yeniden enerjilenen bobin sonraki kayıp karesinde DURDURULMADI"


class _SahteKamera:
    def __init__(self, *a, **k):
        pass

    def isOpened(self):
        return True

    def read(self):
        return True, np.zeros((8, 8, 3), dtype=np.uint8)

    def release(self):
        pass


def _dongu_ortami(monkeypatch, tmp_path, durum, tahmin):
    from servers import ai_pro_hedef

    ns = ap.kur(monkeypatch, tmp_path, dongu_noop=False)

    def _lok(f, oid):
        b = durum["kedi"]
        if not b and threading.current_thread().name == DONGU_IP:
            durum["dongu_kayip_turu"] += 1
        return (b, 10.0, 20.0, 30.0, 0.9 if b else 0.0, None, True)

    monkeypatch.setattr(ns.air.cv2, "VideoCapture", _SahteKamera)
    monkeypatch.setattr(ai_pro_hedef.KediSaglayici, "yukle", lambda self: None)
    monkeypatch.setattr(ns.air, "_ORGAN_LOCALIZE_INTERVAL_S", 0.0)
    monkeypatch.setattr(ns.air, "_localize_organ", _lok)
    monkeypatch.setattr(ns.air, "_predict_and_drive", tahmin)
    return ns


@pytest.mark.parametrize("deneme", range(5))
def test_KRITIK_DONGU_kayip_STOPu_tahmindeki_frame_karesini_SURDURMEZ(monkeypatch, tmp_path, deneme):
    """Kol C (yalnız DÖNGÜNÜN kayıp STOP'u): `/frame` karesi A tahminde beklerken kedi kabinden çıkar; bu kolda `/frame`
    kayıp karesi YOK — STOP'u döngü kendi kayıp turlarıyla verir. A bırakılınca sürmemeli."""
    from kayitci_donanim import gercek_hc

    durum = {"kedi": True, "dongu_kayip_turu": 0, "a_bekle": False}
    engel, a_tahminde = threading.Event(), threading.Event()

    def _tahmin(x, y, z, oid):
        if threading.current_thread().name != DONGU_IP and durum.get("a_bekle"):
            durum["a_bekle"] = False
            a_tahminde.set()
            assert engel.wait(15), "aparat: A engeli kalkmadı"
        return [ap.D_AI] * 7, [0.0] * 7, 1.0

    ns = _dongu_ortami(monkeypatch, tmp_path, durum, _tahmin)
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(ns.api.state, "hardware", hc)
            ns.hc = hc
            _pid, r = ap.onayli_baslat(ns)
            assert r.status_code == 200, r.text[:200]
            assert ap.bekle(lambda: bool(ap.calisan(ns)), 5), "aparat: döngü sürmedi"
            durum["a_bekle"] = True
            t, kutu = ap.kare_arka_planda(ns)
            assert a_tahminde.wait(5), "aparat: A tahmine girmedi"
            durum["kedi"] = False
            assert ap.bekle(lambda: durum["dongu_kayip_turu"] >= N_PIN and not ap.calisan(ns), 8), (
                f"aparat: döngü kayıp STOP'u vermedi (tur={durum['dongu_kayip_turu']}, çalışan={ap.calisan(ns)})"
            )
            stop_paket = ap.paket_sayisi(ns)
            engel.set()
            t.join(10)
            a_driven = kutu["yanit"].json().get("driven") if "yanit" in kutu else kutu.get("hata")
            yeniden = ap.surus_paketleri(ns, stop_paket)
            son = ap.calisan(ns)
            ns.c.post("/api/ai/pro/stop")
            ap.bekle(lambda: not ns.air._ai_loop_active, 5)
            assert not yeniden and son == [], (
                f"DÖNGÜNÜN kayıp STOP'undan SONRA tahmindeki /frame karesi sürdü: A.driven={a_driven}, duty>0 paket="
                f"{len(yeniden)}, çalışan={son}"
            )
    finally:
        ns.air._ai_loop_active = False
        ns.geri()


@pytest.mark.parametrize("deneme", range(5))
def test_KRITIK_DONGU_tahmindeki_KENDI_gozlemi_frame_kayip_STOPundan_sonra_SURULEMEZ(monkeypatch, tmp_path, deneme):
    """Kol D (döngünün KENDİ uçuştaki gözlemi): döngü hedefi bulup tahminde beklerken kedi kabinden çıkar; `/frame` N kayıp
    karesiyle STOP verir. Döngü bırakılınca — gözlemi STOP'tan eski — sürmemeli."""
    from kayitci_donanim import gercek_hc

    durum = {"kedi": True, "dongu_kayip_turu": 0, "dongu_bekle": False}
    engel, dongu_tahminde = threading.Event(), threading.Event()

    def _tahmin(x, y, z, oid):
        if threading.current_thread().name == DONGU_IP and durum.get("dongu_bekle"):
            durum["dongu_bekle"] = False
            dongu_tahminde.set()
            assert engel.wait(15), "aparat: döngü engeli kalkmadı"
        return [ap.D_AI] * 7, [0.0] * 7, 1.0

    ns = _dongu_ortami(monkeypatch, tmp_path, durum, _tahmin)
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(ns.api.state, "hardware", hc)
            ns.hc = hc
            _pid, r = ap.onayli_baslat(ns)
            assert r.status_code == 200, r.text[:200]
            assert ap.bekle(lambda: bool(ap.calisan(ns)), 5), "aparat: döngü sürmedi"
            durum["dongu_bekle"] = True
            assert dongu_tahminde.wait(5), "aparat: döngü tahmine girmedi"
            durum["kedi"] = False
            for _ in range(N_PIN):
                ap.kare(ns)  # /frame kayıp sayacı → STOP
            assert ap.calisan(ns) == [], f"aparat: /frame {N_PIN} kayıp karesinden sonra STOP yok {ap.calisan(ns)}"
            stop_paket = ap.paket_sayisi(ns)
            tur0 = durum["dongu_kayip_turu"]
            engel.set()
            assert ap.bekle(lambda: durum["dongu_kayip_turu"] > tur0, 4), "aparat: döngü bırakılınca yeni tur koşmadı"
            yeniden = ap.surus_paketleri(ns, stop_paket)
            ns.c.post("/api/ai/pro/stop")
            ap.bekle(lambda: not ns.air._ai_loop_active, 5)
            assert not yeniden, (
                f"/frame kayıp STOP'undan SONRA döngünün tahmindeki (STOP'tan eski) gözlemi sürdü: duty>0 paket={len(yeniden)}"
            )
    finally:
        ns.air._ai_loop_active = False
        ns.geri()


def test_KRITIK_ARKA_KALKAN_dongu_kayip_SURERKEN_yeniden_enerjilenen_bobin_DURDURULUR(monkeypatch, tmp_path):
    """(2) katmanı döngüde TEK BAŞINA: döngü kaybı sayıp STOP ettikten sonra bobin 1 yol dışından enerjilenir; hedef hâlâ
    kayıpken döngünün sonraki kayıp turu (~1 sn) onu durdurmalı (eskiden STOP yalnız N. turda)."""
    from kayitci_donanim import gercek_hc

    durum = {"kedi": True, "dongu_kayip_turu": 0}
    ns = _dongu_ortami(monkeypatch, tmp_path, durum, lambda x, y, z, oid: ([ap.D_AI] * 7, [0.0] * 7, 1.0))
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(ns.api.state, "hardware", hc)
            ns.hc = hc
            _pid, r = ap.onayli_baslat(ns)
            assert r.status_code == 200, r.text[:200]
            assert ap.bekle(lambda: bool(ap.calisan(ns)), 5), "aparat: döngü sürmedi"
            durum["kedi"] = False
            assert ap.bekle(lambda: durum["dongu_kayip_turu"] >= N_PIN and not ap.calisan(ns), 8), (
                "aparat: döngü STOP yok"
            )
            tur0 = durum["dongu_kayip_turu"]
            assert hc.update_coil(1, 1.0, 30.0, 0.0, 5, start=True) is True and ap.calisan(ns) == [1], "aparat: vekil"
            durdu = ap.bekle(lambda: not ap.calisan(ns), 3.5)
            tur = durum["dongu_kayip_turu"] - tur0
            ns.c.post("/api/ai/pro/stop")
            ap.bekle(lambda: not ns.air._ai_loop_active, 5)
            assert tur >= 1, "aparat: vekil sürüşten sonra döngü kayıp turu koşmadı"
            assert durdu, f"döngü kayıp sürerken ({tur} tur) yeniden enerjilenen bobini DURDURMADI"
    finally:
        ns.air._ai_loop_active = False
        ns.geri()

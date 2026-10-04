# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.75 · B-1.22 · B-1.28 · B-1.29 — backend yaşam döngüsünün STOP yolları (kapanış, açılış mutabakatı, flush bütçesi).

ÖLÇÜLEN KUSURLAR (denetim HEAD 9a47391; 1-F önce-kırmızı f870777):
  (a) B-1.22 — Sinyalle durdurmada (`sc stop`, Ctrl+C) `_shutdown` aktif seansı KAPATMIYOR ve START'ı reddeden bir
      kapanış durumu KURMUYORDU. Sunucu kameralı AI Pro, "Tüm bobinler durduruldu" günlüğünden sonra bobini ≤ 2 sn
      yeniden sürüyordu (denetim 14/20). 1-C'nin sürüş nesli (c5b3c04) uçuştaki AI Pro sürüşünü artık reddediyor; ama
      (i) seans satırı 'active' kalıyor ve sonraki açılışta "Elektrik Kesintisi" diye mühürleniyordu, (ii) niyet
      bağlamı OLMAYAN bir START (iş parçacığı, araç, ESP yayını) kapanış sürerken HC'den ve `_esp_start_yayinla`dan
      GEÇİYORDU.
  (b) B-1.28 — Açılış mutabakatı "aktif seans yok" kararını kilit altında verip kilidi BIRAKIYOR, `stop_all_coils`'u
      SONRA çağırıyordu (TOCTOU): aradaki anda başlayan seansın bobinleri durduruluyordu. MQTT STOP kapsamı ELLE
      `range(1, 9)` idi (topoloji büyüyünce sessizce eksik kalır).
  (c) B-1.29 — STM flush bütçesi duvar saatiyle (`time.time`) ölçülüyordu: saat geri giderse 1,5 sn'lik bütçe
      saniyelerce uzuyor, servis durdurma zaman aşımını aşabiliyordu (denetim 6,55 sn).

TASARIM (plan "uyandırır" notu — TEK tasarım): kapanış, 1-C'nin MEVCUT mandal/nesil yapısının bir durumudur
(`estop_mandali.kapanis_kur`): aynı kilit, aynı nesil, aynı kapı (`baslatma_engeli` / `mandalli_mi`). Yan yana ikinci bir
mandal YOK — bugün mandala bakan her START yolu kapanışı da görür. Ö.4-Y8: kapanış YALNIZ START'ı reddeder; E-stop,
`stop_all_coils`, seans durdurma ve mutabakat STOP'u muaftır (karşıt kollar).
"""

from __future__ import annotations

import logging
import threading
import time
import types

import ai_pro_aparati as ap
import pytest

DENEME = 30


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


def _kapanisi_kaldir():
    """Test yalıtımı: kapanış durumu süreç geneldir (ürün böyle olmalı); sonraki denemeye sızmasın."""
    from utils import estop_mandali

    f = getattr(estop_mandali, "kapanis_kaldir", None)
    if f is not None:
        f()
    estop_mandali.sifirla("test-izolasyon")


def _tum_sifir(paket) -> bool:
    from kayitci_donanim import paket_coz

    return all(x == 0 for x in paket_coz(paket)[0])


class _Cekirdek:
    """`_shutdown`a verilen çekirdek: `quit()` HWSender'ı durdurur → bundan SONRA kuyruğa giren paket porta YAZILMAZ."""

    def __init__(self, kuyruk):
        self.kuyruk = kuyruk
        self.port_kapandi = None

    def quit(self):
        self.port_kapandi = len(self.kuyruk.paketler)

    def porta_yazilan(self):
        n = len(self.kuyruk.paketler) if self.port_kapandi is None else self.port_kapandi
        return self.kuyruk.paketler[:n]


@pytest.fixture
def k(monkeypatch, tmp_path):
    """GERÇEK `_ai_pro_loop` (sahte kamera, hızlı sahte lokalizasyon/doz), GERÇEK onay akışı, GERÇEK HC (kayıtçı kuyruk),
    GERÇEK `backend_service._shutdown`. Sahte olan: bulut/tünel/bakım/zeroconf kapatıcıları (konu dışı; ağ yok)."""
    import backend_service as bs
    from kayitci_donanim import gercek_hc
    from servers import ai_pro_hedef
    from servers import api_server as _api0

    orj_publish = _api0._mqtt_publish  # ap.kur kayıtçıyla değiştirir; son savunma kolu GERÇEĞİNİ çağırır
    ns = ap.kur(monkeypatch, tmp_path, dongu_noop=False)
    ns.orj_publish = orj_publish
    ns.bs = bs
    monkeypatch.setattr(ns.air.cv2, "VideoCapture", _SahteKamera)
    monkeypatch.setattr(ai_pro_hedef.KediSaglayici, "yukle", lambda self: None)
    import servers.sync_worker as _sw
    import servers.tunnel_manager as _tm
    import services.headless_db_maintenance as _hm
    import utils.zeroconf_singleton as _zs

    monkeypatch.setattr(_sw, "get_cloud_sync", lambda: None)
    monkeypatch.setattr(_tm, "stop_tunnel", lambda: None)
    monkeypatch.setattr(_hm, "stop_headless_db_maintenance", lambda: None)
    monkeypatch.setattr(_zs, "close_shared_zeroconf", lambda: None)
    canli = {"n": 0}
    gercek = ns.air._ai_pro_loop

    def _sayan(*a, **kw):
        canli["n"] += 1
        try:
            return gercek(*a, **kw)
        finally:
            canli["n"] -= 1

    monkeypatch.setattr(ns.air, "_ai_pro_loop", _sayan)
    ns.canli = canli
    # Döngünün sürüş DENEMESİ (kabul/ret fark etmez) bittiğinde işaret.
    surus = {"ev": threading.Event()}
    gercek_surus = ns.air._drive_coils_ai_pro

    def _isaretli_surus(D, P):
        try:
            return gercek_surus(D, P)
        finally:
            surus["ev"].set()

    monkeypatch.setattr(ns.air, "_drive_coils_ai_pro", _isaretli_surus)
    ns.surus = surus
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(ns.api.state, "hardware", hc)
            ns.hc = hc
            ns.cekirdek = _Cekirdek(hc.core._hw_send_queue)
            ns.olay = types.SimpleNamespace(shutdown=lambda: None)
            yield ns
    finally:
        ns.air._ai_loop_active = False
        if ns.tahmin.engel is not None:
            ns.tahmin.engel.set()
        ap.bekle(lambda: canli["n"] == 0, 8)
        _kapanisi_kaldir()
        ns.geri()


def _kapat(o):
    o.bs._shutdown(logging.getLogger("test_kapanis"), o.api, o.cekirdek, o.olay)


def _ai_pro_suruyor(o):
    """Taze bir deneme: kapanış kalkık, mandal sıfır, AI Pro seansı sürüyor. → seansın DB kimliği."""
    _kapanisi_kaldir()
    o.cekirdek.port_kapandi = None
    o.tahmin.engel = None
    assert ap.bekle(lambda: o.canli["n"] == 0, 8), "aparat: önceki döngü bitmedi"
    _pid, r = ap.onayli_baslat(o)
    assert r.status_code == 200 and r.json().get("status") == "success", r.text[:300]
    assert ap.bekle(lambda: bool(ap.calisan(o)), 8), "aparat: döngü bobini sürmedi"
    assert ap.bekle(lambda: bool(o.api._active_session.get("db_session_id")), 5), "aparat: seans DB satırı açılmadı"
    return o.api._active_session.get("db_session_id")


def _seans_durumu(o, sid):
    with o.db._get_connection() as conn:
        satir = conn.execute(
            "SELECT session_status, ended_epoch FROM treatment_sessions WHERE id = ?", (sid,)
        ).fetchone()
    return (satir[0], satir[1]) if satir else (None, None)


# ── (a) B-1.22 — kapanış ─────────────────────────────────────────────────────────────────────────────────────────────
def test_KRITIK_kapanista_porta_giden_SON_paket_TUM_DUTY_SIFIR_ucustaki_AI_Pro_STOPtan_sonra_SUREMEZ(k):
    """Zamanlama ZORLANIR: AI Pro döngüsü tahminde bekletilir; `_shutdown`ın STOP'u (`stop_all_coils`) gönderilir gönderilmez
    tahmin serbest bırakılır ve sürüş denemesi bitene dek kapanış BEKLETİLİR (çekirdek `quit()`ten — porttan — ÖNCE).
    Ölçüt: porta yazılan (quit'ten önce kuyruğa giren) SON paket tüm-duty-0. 30 deneme."""
    orj_stop_all = k.hc.stop_all_coils
    kanca = {"aktif": False}

    def _kancali_stop_all():
        sonuc = orj_stop_all()
        if kanca["aktif"] and threading.current_thread() is threading.main_thread():
            kanca["aktif"] = False
            k.surus["ev"].clear()
            k.tahmin.engel.set()  # uçuştaki tur şimdi sürmeyi DENER — kapanışın STOP'undan SONRA, porttan ÖNCE
            assert k.surus["ev"].wait(8), "aparat: serbest bırakılan tur sürüşü denemedi"
        return sonuc

    k.hc.stop_all_coils = _kancali_stop_all
    son_run = []
    for _ in range(DENEME):
        _ai_pro_suruyor(k)
        k.tahmin.engel = threading.Event()
        k.tahmin.girdi.clear()
        assert k.tahmin.girdi.wait(8), "aparat: döngü tahmine ulaşmadı"
        kanca["aktif"] = True
        _kapat(k)
        assert ap.bekle(lambda: k.canli["n"] == 0, 8), "döngü kapanıştan sonra bitmedi"
        yazilan = k.cekirdek.porta_yazilan()
        assert yazilan, "aparat: porta hiç paket yazılmadı"
        if not _tum_sifir(yazilan[-1]):
            son_run.append(len(yazilan))
    assert not son_run, (
        f"kapanışta porta giden SON paket RUN (bobin enerjili, firmware ölü-adamına dek): {len(son_run)}/{DENEME}"
    )


def test_KRITIK_kapanista_aktif_seans_KAPANIR_kayit_Kesintiye_Ugradi(k):
    """`_shutdown` aktif AI Pro seansını kapatır: bellekte pasif, DB satırı 'interrupted' (Kesintiye Uğradı) + bitiş
    zamanı. Eskiden satır 'active' kalıyor, sonraki açılışın kurtarması onu 'Elektrik Kesintisi' diye mühürlüyordu."""
    sid = _ai_pro_suruyor(k)
    _kapat(k)
    assert ap.bekle(lambda: k.canli["n"] == 0, 8), "döngü kapanıştan sonra bitmedi"
    assert not k.api._active_session.get("is_active"), "kapanıştan sonra seans bellekte AKTİF"
    durum, bitis = _seans_durumu(k, sid)
    assert durum == "interrupted" and bitis, (
        f"kapanışta seans kaydı KAPANMADI: durum={durum!r}, ended_epoch={bitis!r} (beklenen 'interrupted' + bitiş)"
    )


def test_KRITIK_kapanista_seans_KAYDI_donanim_STOPundan_SONRA_yazilir(k, monkeypatch):
    """DB yazımı (dakika ortalaması, sensör flush, end_session) yavaş olabilir: STOP'u GECİKTİRMEMELİ (Ö.4-Y8). Kayıt
    kapatılırken telde (kuyrukta) kapanışın tüm-duty-0 paketi ZATEN olmalı."""
    _ai_pro_suruyor(k)
    gercek = k.api._finalize_session_db
    an: dict = {}

    def _kaydeden(*a, **kw):
        if kw.get("reason") == "kapanis":
            an["paketler"] = list(k.hc.core._hw_send_queue.paketler)
        return gercek(*a, **kw)

    monkeypatch.setattr(k.api, "_finalize_session_db", _kaydeden)
    once = len(k.hc.core._hw_send_queue.paketler)
    _kapat(k)
    assert "paketler" in an, "kapanışta seans kaydı hiç kapatılmadı"
    assert any(_tum_sifir(p) for p in an["paketler"][once:]), (
        "kapanışta seans kaydı donanım STOP'undan ÖNCE yazıldı — DB yazımı STOP'u geciktirir"
    )


def test_KRITIK_kapanis_baslamisken_BAGLAMSIZ_START_HC_ve_ESP_yolunda_REDDEDILIR(k, monkeypatch):
    """Niyet bağlamı olmayan START (iş parçacığı / araç; `update_coil` bu durumda YALNIZ mandala bakar) kapanış
    sürerken geçmemeli: HC tekil + tümü, ESP START (`_esp_start_yayinla`) ve tek boğaz `_mqtt_publish` son savunması."""
    from utils import estop_mandali

    _kapat(k)
    sonuc: dict = {}
    once = len(k.hc.core._hw_send_queue.paketler)
    y0 = len(k.yayin)
    niyet: list = []
    monkeypatch.setattr(k.api, "_kaydet_esp_komut_niyeti", lambda t, p, basarili=False: niyet.append((t, p)))
    monkeypatch.setenv("PEMF_ESP_ENABLED", "1")
    import socket as _socket

    def _broker_yok(*a, **kw):  # son savunmayı geçen START broker sondasına ulaşmasın (ağ/bekçi olayı yok)
        raise OSError("test: broker yok")

    monkeypatch.setattr(_socket, "create_connection", _broker_yok)

    def _baglamsiz():
        assert estop_mandali.baglam_nesli() is None
        sonuc["tekil"] = k.hc.update_coil(1, 100, 40, 0, 5, start=True)
        sonuc["tumu"] = k.hc.start_all_coils(100, 40, 0, 5)
        sonuc["esp"] = k.api._esp_start_yayinla(8, {"command": "start", "command_id": "kapanis_t", "duty": 40})
        sonuc["son_savunma"] = k.orj_publish("pemf/coil/8/control", {"command": "start", "command_id": "kapanis_s"})

    t = threading.Thread(target=_baglamsiz, name="baglamsiz")
    t.start()
    t.join(15)
    assert not t.is_alive()
    run = [p for p in k.hc.core._hw_send_queue.paketler[once:] if not _tum_sifir(p)]
    esp_start = [p for _t, p in k.yayin[y0:] if p.get("command") == "start"]
    assert sonuc.get("tekil") is False and sonuc.get("tumu") is False and not run, (
        f"kapanış sürerken bağlamsız START HC'den GEÇTİ: tekil={sonuc.get('tekil')}, tümü={sonuc.get('tumu')}, "
        f"RUN paketi={len(run)}"
    )
    assert sonuc.get("esp") is False and not esp_start, f"kapanış sürerken ESP START YAYINLANDI: {esp_start}"
    assert not niyet, f"kapanış sürerken `_mqtt_publish` son savunması START'ı geçirdi (niyet kaydı): {niyet}"


def test_KRITIK_kapanis_STOPtan_ONCE_kurulur_STOP_aninda_gelen_BAGLAMSIZ_START_REDDEDILIR(k, monkeypatch):
    """1-F inceleme: `_shutdown` sırası (1) kapanış → (3) donanım STOP'u. Kapanış STOP'tan SONRA kurulsa mevcut kollar
    YEŞİL kalıyordu (ölçüldü): son-paket kolunu 1-C'nin nesli korur, bağlamsız-START kolu START'ı `_shutdown` BİTTİKTEN
    sonra dener. Burada bağlamsız START, `_shutdown`ın donanım STOP'u gönderilir gönderilmez (STOP ile kapanış arasındaki
    pencerede) denenir — geçerse bobin STOP'tan SONRA yeniden enerjilenir (firmware ölü-adamına dek)."""
    sonuc: dict = {}
    gercek_stop = k.hc.stop_all_coils  # `gercek_hc`in sayaç sarmalayıcısı (örnek özniteliği) — üstüne sarılır

    def _stop_ardindan_baglamsiz_start(*a, **kw):
        r = gercek_stop(*a, **kw)
        if "tekil" not in sonuc:
            sonuc["once"] = len(k.hc.core._hw_send_queue.paketler)
            t = threading.Thread(
                target=lambda: sonuc.update(tekil=k.hc.update_coil(1, 100, 40, 0, 5, start=True)), name="baglamsiz"
            )
            t.start()
            t.join(10)
        return r

    monkeypatch.setattr(k.hc, "stop_all_coils", _stop_ardindan_baglamsiz_start)
    _kapat(k)
    assert "tekil" in sonuc, "aparat: _shutdown donanım STOP'unu (stop_all_coils) çağırmadı"
    run = [p for p in k.hc.core._hw_send_queue.paketler[sonuc["once"] :] if not _tum_sifir(p)]
    assert sonuc["tekil"] is False and not run, (
        f"kapanışın donanım STOP'u ile kapanış durumu arasındaki pencerede bağlamsız START GEÇTİ: tekil={sonuc['tekil']}, "
        f"RUN paketi={len(run)} — kapanış STOP'tan ÖNCE kurulmalı"
    )


def test_KRITIK_kapanis_Sifirla_ile_KALKMAZ(k):
    """Kapanış operatörün E-stop 'Sıfırla'sı DEĞİLDİR: Sıfırla kapanışı kaldırırsa kapanış penceresinde START geçerdi."""
    _kapat(k)
    k.c.post("/api/hardware/estop_mandali/sifirla", json={"onay": True})
    once = len(k.hc.core._hw_send_queue.paketler)
    kutu: dict = {}
    t = threading.Thread(target=lambda: kutu.update(r=k.hc.update_coil(2, 100, 40, 0, 5, start=True)))
    t.start()
    t.join(10)
    run = [p for p in k.hc.core._hw_send_queue.paketler[once:] if not _tum_sifir(p)]
    assert kutu.get("r") is False and not run, "Sıfırla kapanışı KALDIRDI — kapanış sürerken START geçti"


def test_KARSIT_Y8_kapanis_sirasinda_ACIL_DURDUR_200_ve_STM_STOP_gonderilir_durdurmalar_KAPILANMAZ(k):
    """Ö.4-Y8: kapanış YALNIZ START'ı reddeder. Kapanış sürerken ACİL DURDUR 200 + telde tüm-duty-0 paket + ESP STOP;
    seanssız `/api/session/stop` 200 + STOP; tekil STOP (`update_coil(start=False)`) kuyruğa girer."""
    _kapat(k)
    once = len(k.hc.core._hw_send_queue.paketler)
    y0 = len(k.yayin)
    r = k.c.post("/api/hardware/emergency_stop")
    assert r.status_code == 200, r.text[:200]
    yeni = k.hc.core._hw_send_queue.paketler[once:]
    assert yeni and all(_tum_sifir(p) for p in yeni), f"kapanışta E-stop STM STOP'u GÖNDERİLMEDİ ({len(yeni)} paket)"
    assert any(p.get("command") == "stop" for _t, p in k.yayin[y0:]), "kapanışta E-stop ESP STOP'u yayınlanmadı"
    once2 = len(k.hc.core._hw_send_queue.paketler)
    r2 = k.c.post("/api/session/stop")
    assert r2.status_code == 200, r2.text[:200]
    assert k.hc.update_coil(3, 0, 0, 0, 0, start=False) is True
    yeni2 = k.hc.core._hw_send_queue.paketler[once2:]
    assert len(yeni2) >= 2 and all(_tum_sifir(p) for p in yeni2), "kapanışta seans durdurma / tekil STOP KAPILANDI"


def test_KRITIK_kapanis_DISKE_YAZILMAZ_yeniden_baslatmada_mandal_KURMAZ(k, tmp_path):
    """Kapanış bir E-stop değildir: Y46 mandal dosyasına 'kurulu' yazılmamalı (yoksa her temiz kapanıştan sonra açılışta
    'önceki oturumda ACİL DURDUR — sıfırlanmadı' bandı ve Sıfırla'sız START reddi)."""
    from utils import estop_mandali

    yol = tmp_path / "estop_mandali.json"
    estop_mandali.kalicilik_kur(yol)
    _kapat(k)
    time.sleep(0.3)  # arka plan yazıcısı (varsa) bitsin
    estop_mandali.kalicilik_kapat()
    _kapanisi_kaldir()
    durum = estop_mandali.kalicilik_kur(yol)  # GERÇEK yeniden başlatmanın yükleyicisi
    estop_mandali.kalicilik_kapat()
    assert not durum["aktif"], f"temiz kapanış mandal dosyasına KURULU yazıldı: {durum}"


# ── (b) B-1.28 — açılış mutabakatı ──────────────────────────────────────────────────────────────────────────────────
class _EnjekteKilit:
    """`_session_lock` yerine: İLK bırakılıştan HEMEN SONRA (karar verilip kilit bırakıldığında) aktif bir seans enjekte
    eder — mutabakatın "karar → STOP" aralığı ZORLANIR."""

    def __init__(self, oturum, enjekte):
        self._k = threading.RLock()
        self._oturum = oturum
        self._enjekte = enjekte
        self.enjekte_edildi = False

    def __enter__(self):
        self._k.acquire()
        return self

    def __exit__(self, *a):
        self._k.release()
        if not self.enjekte_edildi:
            self.enjekte_edildi = True
            with self._k:
                self._oturum.update(self._enjekte)
        return False


def _mutabakat(sahte):
    import backend_service as bs

    once = {t.ident for t in threading.enumerate()}
    bs._start_startup_reconcile(sahte, logging.getLogger("test_kapanis_mutabakat"))
    yeni = [t for t in threading.enumerate() if t.name == "startup-reconcile" and t.ident not in once]
    assert len(yeni) == 1, "aparat: startup-reconcile iş parçacığı bulunamadı"
    yeni[0].join(timeout=10.0)
    assert not yeni[0].is_alive(), "aparat: mutabakat 10 sn'de bitmedi"


def test_KRITIK_mutabakat_KARARI_ve_STM_STOPu_AYNI_kilitte_araya_giren_seans_DURDURULMAZ():
    """Karar kilidi bırakılır bırakılmaz seans (bobin 8 dahil) başlar. Ölçüt: `stop_all_coils` seans AKTİFKEN çağrılmaz;
    seansın bobinine (8) enjeksiyondan SONRA mutabakat STOP'u yayınlanmaz; seansın DIŞINDAKİ konulara STOP gider."""
    oturum = {"is_active": False}
    kilit = _EnjekteKilit(oturum, {"is_active": True, "session_id": "yeni", "coil_ids": [1, 8]})
    stop_all_aninda_aktif: list = []
    yayin: list = []

    class _HW:
        def stop_all_coils(self):
            stop_all_aninda_aktif.append(bool(oturum.get("is_active")))
            return True

    def _pub(topic, payload):
        yayin.append((topic, kilit.enjekte_edildi))
        return True

    sahte = types.SimpleNamespace(
        _session_lock=kilit, _active_session=oturum, state=types.SimpleNamespace(hardware=_HW()), _mqtt_publish=_pub
    )
    _mutabakat(sahte)
    assert kilit.enjekte_edildi, "aparat: enjeksiyon olmadı"
    assert stop_all_aninda_aktif and not any(stop_all_aninda_aktif), (
        f"mutabakat kararı kilit DIŞINDA: stop_all_coils araya giren seans AKTİFKEN çağrıldı {stop_all_aninda_aktif}"
    )
    sonra_8 = [t for t, enj in yayin if t == "pemf/coil/8/control" and enj]
    assert not sonra_8, "araya giren seansın bobinine (8) mutabakat STOP'u yayınlandı — seans sessizce öldü"
    assert any(t == "pemf/coil/2/control" for t, _e in yayin), "seans DIŞI konulara mutabakat STOP'u gitmedi"


def test_KRITIK_mutabakat_MQTT_STOP_kapsami_TOPOLOJIDEN_turer_ESPye_DARALTILMAZ(monkeypatch):
    """Kapsam TEK kaynaktan: `live_state` topolojisinin (STM ∪ ESP) birleşimi — elle `range(1, 9)` değil, ESP_COIL_IDS'e
    daraltılmış da değil (önceki süreç eski bir sürüm olabilir: 1.9.50 AI Pro 6-7'ye MQTT START yayınlıyordu). Topoloji
    büyürse (bobin 9) kapsam da büyür."""
    from servers import live_state

    monkeypatch.setattr(live_state, "ESP_COIL_IDS", {8, 9})
    yayin: list = []
    sahte = types.SimpleNamespace(
        _session_lock=threading.Lock(),
        _active_session={"is_active": False},
        state=types.SimpleNamespace(hardware=None),
        _mqtt_publish=lambda t, p: yayin.append((t, p)) or True,
    )
    _mutabakat(sahte)
    bobinler = {int(t.split("/")[2]) for t, p in yayin if p.get("command") == "stop"}
    beklenen = set(live_state.STM_COIL_IDS) | {8, 9}
    assert bobinler == beklenen, (
        f"mutabakat MQTT STOP kapsamı topolojiden türemiyor: {sorted(bobinler)} ≠ {sorted(beklenen)}"
    )


# ── (c) B-1.29 — flush bütçesi ──────────────────────────────────────────────────────────────────────────────────────
def test_KRITIK_STM_flush_butcesi_MONOTONIK_duvar_saati_GERI_gidince_uzamaz(monkeypatch):
    """Ölü gönderici (kuyruk hiç boşalmaz) + duvar saati ilk okumadan sonra 5 sn GERİ: flush ≤ bütçe + ε sürmeli."""
    import backend_service as bs

    gercek_time = time.time
    sayac = {"n": 0}

    def _geri_saran():
        sayac["n"] += 1
        return gercek_time() - (5.0 if sayac["n"] > 1 else 0.0)

    class _Q:
        def empty(self):
            return False

    sahte = types.SimpleNamespace(
        state=types.SimpleNamespace(
            hardware=types.SimpleNamespace(stop_all_coils=lambda: True), core=types.SimpleNamespace(_hw_send_queue=_Q())
        ),
        _mqtt_publish=lambda t, p: True,
    )
    monkeypatch.setattr(time, "time", _geri_saran)
    t0 = time.monotonic()
    try:
        bs._safe_stop_outputs(sahte)
    finally:
        gecen = time.monotonic() - t0
        monkeypatch.setattr(time, "time", gercek_time)
    assert gecen >= bs._STM_FLUSH_BUDGET_S - 0.05, f"aparat: flush bütçesi hiç beklenmedi ({gecen:.2f} sn)"
    assert gecen <= bs._STM_FLUSH_BUDGET_S + 0.6, (
        f"flush bütçesi duvar saatiyle ölçülüyor: saat geri gidince {gecen:.2f} sn sürdü "
        f"(bütçe {bs._STM_FLUSH_BUDGET_S} sn) — servis durdurma zaman aşımı aşılabilir"
    )

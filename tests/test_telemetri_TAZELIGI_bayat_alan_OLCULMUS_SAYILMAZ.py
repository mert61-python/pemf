# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.67 · B-1.3 — STM telemetrisinde ALAN BAŞINA TAZELİK (yalnız GÖSTERİM ve kayıt dürüstlüğü).

KUSUR (plan, d01t53): `measuredFields` kümesi yalnız `add` ile büyüyordu. Bir sensör susunca (kablo
çıktı, I2C koptu, MLX arızası) son değeri `_live_state`te DONUP kalıyor, alan "ölçülüyor" sayılmaya
devam ediyordu: arayüz donmuş sayıyı CANLI gibi gösteriyor, dakika akümülatörü onu her 2 sn'de bir
yeniden örnekleyip DB'ye "ölçüldü" diye yazıyordu.

SAHİP KARARLARI: A-47 + Y2 — termal kesme/engelleme HİÇBİR katmanda yok; tazelik yalnız gösterim
içindir (donmuş değer canlı gösterilmez, ölçüm yoksa '—'). Y6 — ölçülmeyen '—'. Bu kapı yeni bir
durdurma/engelleme EKLEMEZ; yalnız "ölçülüyor" iddiasını dürüstleştirir.

ZAMAN: süreç geneli `time` yamalanmaz (diğer iş parçacıkları etkilenir). Yalnız `api_server`
modülünün gördüğü `time` bir vekille değiştirilir; `monotonic` ileri sarılabilir, gerisi gerçek.

PENCERE: firmware'in `STM_TELE` basma periyodundan TÜRETİLİR (pemf_sensor.c
`SENSOR_ZIRVE_PENCERE_MS`). Pencere periyottan kısa olursa yavaş sensörde '—' titreşimi olur
(plan "uyandırır" notu) — KARŞIT kol bunu ölçer.
"""

from __future__ import annotations

import re
import sys
import time as _gercek_zaman
from pathlib import Path

import pytest
from akim_olcumu_aparati import akim_olcumu_acik  # noqa: F401  (CH4 · Y154: akım sensörü AÇIKKEN yolu)

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(KOK / "tests"))

from dongu_tek_tur import bir_tur_kos  # noqa: E402


class _ModulSaati:
    """`api_server.time` vekili: `monotonic` = gerçek + `ek`; diğer her şey gerçek modül."""

    def __init__(self):
        self.ek = 0.0

    def monotonic(self):
        return _gercek_zaman.monotonic() + self.ek

    def __getattr__(self, ad):
        return getattr(_gercek_zaman, ad)


class _Olay:
    def __init__(self, govde: dict):
        self.event_type = "hardware.stm.telemetry"
        self.data = govde


_ALANLAR = ("objectTemp", "ambientTemp", "magneticMt", "currentA")


@pytest.fixture()
def kur(monkeypatch):
    from servers import api_server as api

    yayinlar: list[dict] = []
    saat = _ModulSaati()
    monkeypatch.setattr(api, "time", saat)
    monkeypatch.setattr(api, "_ws_broadcast_sync", lambda m: yayinlar.append(m))
    monkeypatch.setattr(api, "_push_notification", lambda *a, **k: None)

    def _temizle():
        with api._live_state_lock:
            for i in range(7):
                c = api._live_state["coils"][i]
                for a in _ALANLAR:
                    c[a] = 0.0
                c["measuredFields"] = []
                c["running"] = False
        for i in range(8):
            api._coil_olculen_alanlar.pop(i, None)
            api._coil_last_telemetry.pop(i, None)
        with api._minute_acc_lock:
            api._minute_acc.clear()
        with api._session_lock:
            api._active_session["is_active"] = False

    _temizle()
    yield api, saat, yayinlar
    _temizle()


def _tur(api, coil_id: int):
    """GERÇEK sensör döngüsünün TEK turu (aktif seans + bobin çalışıyor)."""
    with api._live_state_lock:
        api._live_state["coils"][coil_id - 1]["running"] = True
    with api._session_lock:
        api._active_session["is_active"] = True
    uyku, hatalar = bir_tur_kos(api._sensor_persistence_loop)
    assert (uyku, hatalar) == (1, []), f"sensör döngüsü turu: uyku={uyku} hata={hatalar}"


def _olculen(api, coil_id: int) -> list:
    with api._live_state_lock:
        return list(api._live_state["coils"][coil_id - 1].get("measuredFields") or [])


def _acc(api, coil_id: int) -> dict:
    with api._minute_acc_lock:
        return dict(api._minute_acc.get(coil_id) or {})


def _son_coil_status(yayinlar, coil_id):
    son = None
    for m in yayinlar:
        if m.get("type") == "coil_status" and m.get("coilId") == coil_id:
            son = m
    return son


def test_KRITIK_susan_SICAKLIK_measuredFields_ten_DUSER_ve_akumulatore_GIRMEZ(kur):
    """Plan KAPI (d01t53): bobin 6'ya bir kez {T=45, B=1.8}, sonra pencere dışında yalnız B taşıyan 6 olay.

    İddia: `objectTemp` measuredFields'ten DÜŞER (arayüz '—' gösterir; donmuş 45 °C canlı görünmez) ve
    akümülatör sıcaklığı YALNIZ taze olduğu ilk turda biriktirir (t_n == 1). Bugün t_n = 7, listede duruyor.
    """
    api, saat, yayinlar = kur
    api._handle_backend_event(_Olay({"coil_id": 6, "object_temp": 45.0, "magnetic_field": 1.8}))
    _tur(api, 6)
    for k in range(1, 7):
        saat.ek += 10.0  # firmware periyodunun (1 sn) on katı — her adımda sıcaklık bir pencere daha yaşlanır
        api._handle_backend_event(_Olay({"coil_id": 6, "magnetic_field": 1.8 + k / 100}))
        _tur(api, 6)

    olc = _olculen(api, 6)
    assert "objectTemp" not in olc, (
        f"60 sn'dir gelmeyen SICAKLIK hâlâ 'ölçülüyor' sayılıyor (measuredFields={olc}) — arayüz donmuş "
        "45 °C'yi CANLI gibi gösterir"
    )
    assert "magneticMt" in olc, f"her olayda gelen ALAN ölçülmüyor sayıldı: {olc}"
    acc = _acc(api, 6)
    assert acc.get("t_n") == 1, (
        f"bayat sıcaklık akümülatöre {acc.get('t_n')} kez girdi (taze olduğu yalnız 1 tur var) → DB'ye "
        "'ölçüldü' diye yazılır"
    )
    assert acc.get("b_n") == 7, f"taze alan ölçümleri kayboldu: b_n={acc.get('b_n')}"
    cs = _son_coil_status(yayinlar, 6)
    assert cs is not None and "objectTemp" not in (cs["data"].get("measuredFields") or []), (
        f"istemciye giden son coil_status sıcaklığı hâlâ ölçülmüş diyor: {cs}"
    )


@pytest.mark.parametrize(
    "coil_id, govde, alan",
    [
        (1, {"current": 0.412}, "currentA"),  # bobin 1-5: ACS712 akım
        (5, {"current": 0.9}, "currentA"),
        (6, {"object_temp": 45.0, "ambient_temp": 26.0, "magnetic_field": 1.8}, "objectTemp"),  # bobin 6-7: MLX
        (7, {"object_temp": 47.5}, "objectTemp"),
    ],
)
def test_KRITIK_TAMAMEN_susan_sensor_HICBIR_olay_gelmese_de_DUSER_ve_istemciye_YAYINLANIR(kur, coil_id, govde, alan):
    """Sensör tamamen susarsa (hiç yeni satır yok) da alan düşmeli ve istemci bunu GÖRMELİ.

    Yalnız yeni telemetride hesaplanan bir tazelik bu kolu kaçırır: olay gelmez, liste hiç güncellenmez,
    arayüz son `coil_status`'taki listeyle donmuş değeri canlı gösterir.
    """
    api, saat, yayinlar = kur
    api._handle_backend_event(_Olay({"coil_id": coil_id, **govde}))
    assert alan in _olculen(api, coil_id), "aparat: taze ölçüm 'ölçülüyor' sayılmadı"
    saat.ek += 30.0
    yayinlar.clear()
    _tur(api, coil_id)

    olc = _olculen(api, coil_id)
    assert olc == [], f"bobin {coil_id}: 30 sn'dir hiç telemetri yok ama measuredFields={olc}"
    cs = _son_coil_status(yayinlar, coil_id)
    assert cs is not None, (
        f"bobin {coil_id}: alan düştü ama istemciye coil_status GİTMEDİ — arayüz donmuş değeri göstermeye devam eder"
    )
    assert (cs["data"].get("measuredFields") or []) == [], cs
    assert not any(_acc(api, coil_id).get(k, 0) for k in ("t_n", "i_n", "b_n", "amb_n")), (
        f"bobin {coil_id}: bayat değer akümülatöre girdi: {_acc(api, coil_id)}"
    )


def test_KARSIT_firmware_periyodunda_gelen_olcum_TITRESMEZ(kur):
    """KARŞIT: periyodunda (1 sn) gelen, arada bir ve iki ardışık satırı ATLANMIŞ ölçüm hep 'ölçülüyor' kalır.

    Pencere periyottan kısa seçilirse yavaş sensörde '—' titreşimi olur (plan uyandırır notu). Döngü turu
    olaydan 0,9 sn SONRA koşar (olayla aynı anda ölçmek kısa pencereyi göremezdi).
    """
    api, saat, _ = kur
    gelen = {0, 1, 2, 3, 5, 6, 7, 10}  # 4, 8, 9: firmware "UART meşgul → bu turu atla" boşlukları
    for t in range(11):
        saat.ek = float(t)
        if t in gelen:
            api._handle_backend_event(_Olay({"coil_id": 6, "object_temp": 40.0 + t / 10, "magnetic_field": 1.5}))
        saat.ek = t + 0.9
        _tur(api, 6)
        olc = _olculen(api, 6)
        assert "objectTemp" in olc and "magneticMt" in olc, f"t={t}+0,9 sn: taze ölçüm '—'ye düştü: {olc}"
    assert _acc(api, 6).get("t_n") == 11


def test_KRITIK_pencere_FIRMWARE_periyodundan_turer():
    """Pencere elle yazılmış bir sayı değil: firmware `SENSOR_ZIRVE_PENCERE_MS` ile eşlenir."""
    from servers import api_server as api

    kaynak = (KOK / "firmware" / "stm32_pemf" / "Core" / "Src" / "pemf_sensor.c").read_text(encoding="utf-8")
    m = re.search(r"#define\s+SENSOR_ZIRVE_PENCERE_MS\s+(\d+)U", kaynak)
    assert m, "firmware periyot sabiti bulunamadı (araç kör)"
    assert api.STM_TELE_PERIYOT_S * 1000 == int(m.group(1)), (
        f"backend periyodu {api.STM_TELE_PERIYOT_S} sn, firmware {m.group(1)} ms — ayrıştı"
    )
    # En az iki ardışık atlanmış satırı tolere et (UART meşgulken firmware turu atlar), en çok 10 periyot.
    assert 3 * api.STM_TELE_PERIYOT_S <= api.ALAN_TAZELIK_S <= 10 * api.STM_TELE_PERIYOT_S, api.ALAN_TAZELIK_S


# ── 1-D inceleme i2-F-4: işleyicinin KENDİ yayını ve seanssız/duran bobin ──────────────────────────────────────────
def test_KRITIK_isleyici_YAYINI_bayat_sicakligi_olculuyor_DEMEZ_supurgeden_ONCE(kur):
    """Kapının öteki kolları yalnız SÜPÜRGEDEN SONRAKİ durumu ölçüyordu: işleyici her yeni satırda bayat alanı
    "ölçülüyor" diye yayınlasa (süpürge 2 sn'de bir düşürür, sonraki B satırı geri yazar) yeşil kalıyordu. MLX (T) susar,
    manyetik sensör (B) 1 Hz akmaya devam eder → işleyicinin `coil_status` + `sensor_data` yayınında sıcaklık YOK."""
    api, saat, yayinlar = kur
    api._handle_backend_event(_Olay({"coil_id": 6, "object_temp": 45.0, "magnetic_field": 1.8}))
    saat.ek += 10.0  # sıcaklık 10 sn'dir gelmiyor (pencere 5 sn); süpürge turu HENÜZ koşmadı
    yayinlar.clear()
    api._handle_backend_event(_Olay({"coil_id": 6, "magnetic_field": 1.81}))
    for tip in ("coil_status", "sensor_data"):
        m = [y for y in yayinlar if y.get("type") == tip and y.get("coilId") == 6]
        assert m, f"işleyici {tip} yayınlamadı"  # ARA DOĞRULAMA
        mf = m[-1]["data"].get("measuredFields") or []
        assert "objectTemp" not in mf and "magneticMt" in mf, f"{tip} bayat sıcaklığı ölçülüyor diyor: {mf}"


@pytest.mark.parametrize("calisiyor", [False, True], ids=["duran_bobin", "calisan_bobin"])
def test_KRITIK_SEANSSIZ_duran_ya_da_calisan_bobinde_bayat_sicaklik_DUSER(kur, calisiyor):
    """Süpürge "seans olsun olmasın" her turda koşar (kod sözleşmesi); `_tur` yardımcısı her turda seansı ve bobini
    aktif yaptığı için "seanssız / duran bobin" kolu ölçülmüyordu."""
    api, saat, yayinlar = kur
    api._handle_backend_event(_Olay({"coil_id": 6, "object_temp": 47.0}))
    with api._live_state_lock:
        api._live_state["coils"][5]["running"] = calisiyor
    saat.ek += 30.0
    yayinlar.clear()
    uyku, hatalar = bir_tur_kos(api._sensor_persistence_loop)
    assert (uyku, hatalar) == (1, []), f"sensör döngüsü turu: uyku={uyku} hata={hatalar}"
    assert _olculen(api, 6) == [], f"running={calisiyor}, seans yok: 30 sn'dir gelmeyen sıcaklık hâlâ ölçülüyor"
    assert any(y.get("type") == "coil_status" and y.get("coilId") == 6 for y in yayinlar), "istemciye yayın yok"

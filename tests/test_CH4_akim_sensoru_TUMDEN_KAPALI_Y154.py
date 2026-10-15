# Author: mertaygn, cglrgrkn
"""CH4 · Y154 (sahip, 2026-10-15) — AKIM SENSÖRÜ (ACS712) TÜMDEN KAPALI.

SAHİP KARARI: "Akım sensörü TÜMDEN KAPALI: akım hiç gösterilmez ve kaydedilmez; 'Anlık Güç' kalıcı gizli (A-64). Firmware'e
dokunulmaz (satırlar gelir, backend yok sayar); ACİL DURDUR / güvenlik yolları akıma bağlı değil."
ÖLÇÜLEN DURUM (taban `cc76f758`, TD5): aralık içi akım (`C=3,I=2.000` — PSU kapalıyken yüzen girişin de üretebildiği sayı) canlı
duruma (`currentA`, `measuredFields`), WS'ye, sensör CSV'sine ve dakika ortalamasına (doz kaydı) "ölçülmüş" diye giriyordu; doygun /
aralık dışı akım "Akım ölçümü bu bobinde güvenilir değil" bildirimi üretiyordu; ESP yükünün `current`'ı canlı duruma ve CSV'ye
yazılıyordu; sim kipi bobinlere akım uyduruyordu; seans geçmişi (`/details`, `coil_runs.csv`) eski (sahte olabilecek) akımı veriyordu.
SÖZLEŞME: tek bayrak `utils.akim_olcumu` (`PEMF_AKIM_OLCUMU`, varsayılan KAPALI). Kapalıyken akım backend'in GİRİŞİNDE atılır (STM
ayrıştırıcısı + STM olay işleyicisi + ESP sensors/status + sim + sensör CSV'si), geçmiş çıktılarında boş, arayüze `akimOlcumu: false`.
Açıkken TD5 yolu AYNEN (karşıt testler). Güvenlik yolları akım okumaz (statik kapı) — ESP "overcurrent" ALARMI süzülmez (Ö.4-Y8).
"""

from __future__ import annotations

import ast
import csv
import io
import json
import logging
import re
import textwrap
import threading
from pathlib import Path

import pytest

#: Tezgâh / TD5 satırları (gerçek biçim).
GERCEK = "-> STM_TELE: C=3,I=2.000"
DOYGUN = "-> STM_TELE: C=3,I=19.820,X=1"
YUZEN_74A = "-> STM_TELE: C=1,I=74.630"
KARMA = "-> STM_TELE: C=4,T=31.50,I=1.500"
TD5_METNI = "Akım ölçümü bu bobinde güvenilir değil"

KOK = Path(__file__).resolve().parents[1]
API = KOK / "apps" / "backend" / "servers" / "api_server.py"


@pytest.fixture
def kapali(monkeypatch):
    monkeypatch.delenv("PEMF_AKIM_OLCUMU", raising=False)


@pytest.fixture
def acik(monkeypatch):
    monkeypatch.setenv("PEMF_AKIM_OLCUMU", "1")


@pytest.fixture
def cekirdek():
    import headless_core as hcm

    c = hcm.HeadlessCore.__new__(hcm.HeadlessCore)
    c.logger = logging.getLogger("test-ch4")
    c._stm_state_lock = threading.RLock()
    return c


class _Olay:
    def __init__(self, tur, data=None):
        self.event_type = tur
        self.data = data or {}


@pytest.fixture
def api(monkeypatch):
    from servers import api_server as a
    from servers import live_state as ls

    yayin, bildirim, kayit = [], [], []
    monkeypatch.setattr(a, "_ws_broadcast_sync", lambda m: yayin.append(m))
    monkeypatch.setattr(ls, "_ws_broadcast_sync", lambda m: yayin.append(m))
    monkeypatch.setattr(a, "_push_notification", lambda m, s="info": bildirim.append((m, s)))
    monkeypatch.setattr(a._sensor_kaydedici, "kaydet_arka_planda", lambda *x, **k: kayit.append(x))
    monkeypatch.setattr(a._sensor_kaydedici, "kaydet", lambda *x, **k: kayit.append(x))
    monkeypatch.setattr(a, "_reconcile_esp_calisiyor", lambda *x, **k: None)
    with a._live_state_lock:
        for i in range(8):
            coil = a._live_state["coils"][i]
            monkeypatch.setitem(coil, "currentA", 0.0)
            monkeypatch.setitem(coil, "objectTemp", 0.0)
            monkeypatch.setitem(coil, "measuredFields", [])
            monkeypatch.setitem(coil, "akimGuvenilmez", False)
            monkeypatch.setitem(coil, "connected", False)
    for i in range(8):
        monkeypatch.setitem(a._coil_olculen_alanlar, i, {})
    monkeypatch.setattr(a, "_coil_last_telemetry", dict(a._coil_last_telemetry))
    monkeypatch.setattr(a, "_akim_guvenilmez_bildirildi", set())
    return a, yayin, bildirim, kayit


def _akim_tasiyan(yayin):
    """WS yayınlarından sıfırdan farklı akım taşıyanlar (varsayılan 0.0 canlı durum alanıdır, ölçüm değil)."""
    out = []
    for m in yayin:
        d = m.get("data") or {}
        if isinstance(d, dict) and d.get("currentA") not in (None, 0, 0.0):
            out.append(m)
    return out


# ── 1) STM ayrıştırıcısı ──────────────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("satir", [GERCEK, DOYGUN, YUZEN_74A])
def test_KRITIK_kapaliyken_ayristirici_akimi_ATAR_olay_URETMEZ(kapali, cekirdek, satir):
    """Yalnız akım taşıyan satır → olay YOK (taşınacak ölçüm yok); `current` / `current_saturated` / `akim_guvenilmez` yok."""
    assert cekirdek._parse_stm_tele(satir) is None


def test_KRITIK_kapaliyken_karma_satirda_sicaklik_KALIR_akim_GITMEZ(kapali, cekirdek):
    g = cekirdek._parse_stm_tele(KARMA)
    assert g == {"coil_id": 4, "object_temp": 31.5}, g


@pytest.mark.parametrize(
    ("satir", "beklenen"),
    [
        (GERCEK, {"coil_id": 3, "current": 2.0}),
        (DOYGUN, {"coil_id": 3, "current_saturated": True, "akim_guvenilmez": True}),
    ],
)
def test_KARSIT_acikken_TD5_yolu_AYNEN(acik, cekirdek, satir, beklenen):
    assert cekirdek._parse_stm_tele(satir) == beklenen


# ── 2) STM olay işleyicisi (ayrıştırıcıyı atlayan üretici dahil) ─────────────────────────────────────────────────────────────


def test_KRITIK_kapaliyken_akim_CANLI_DURUMA_WSye_KAYDA_BILDIRIME_girmez(kapali, api, cekirdek):
    a, yayin, bildirim, kayit = api
    olaylar = [cekirdek._parse_stm_tele(s) for s in (GERCEK, DOYGUN, KARMA)]
    # Ayrıştırıcıyı atlayan üretici (eski olay biçimi / simülatör): API kendi başına da uygular.
    olaylar += [
        {"coil_id": 3, "current": 2.0},
        {"coil_id": 3, "current": 12.1, "current_saturated": True},
        {"coil_id": 2, "current": 1.0, "akim_guvenilmez": True},
    ]
    for g in olaylar:
        if g is not None:
            a._handle_backend_event(_Olay("hardware.stm.telemetry", g))
    for i in range(8):
        coil = a._live_state["coils"][i]
        assert coil["currentA"] == 0.0, (i + 1, coil)
        assert "currentA" not in coil["measuredFields"], (i + 1, coil)
        assert coil.get("akimGuvenilmez") is False, (i + 1, coil)
        assert "currentA" not in a._coil_olculen_alanlar[i], (i + 1, a._coil_olculen_alanlar[i])
    assert not _akim_tasiyan(yayin), _akim_tasiyan(yayin)
    for _b, _tur, yuk in kayit:
        assert not {"current", "current_saturated", "akim_guvenilmez"} & set(yuk), yuk
    assert not [m for m, _s in bildirim if "Akım" in m or "akım" in m], bildirim
    # Karşıt (vakum değil): karma satırın sıcaklığı yazıldı ve kayda gitti.
    assert a._live_state["coils"][3]["objectTemp"] == pytest.approx(31.5)
    assert "objectTemp" in a._live_state["coils"][3]["measuredFields"]
    assert any(yuk.get("object_temp") == pytest.approx(31.5) for _b, _t, yuk in kayit), kayit


def test_KARSIT_acikken_guvenilir_akim_YAZILIR_guvenilmez_TEK_uyari(acik, api, cekirdek):
    a, _y, bildirim, kayit = api
    a._handle_backend_event(_Olay("hardware.stm.telemetry", cekirdek._parse_stm_tele(GERCEK)))
    coil = a._live_state["coils"][2]
    assert coil["currentA"] == pytest.approx(2.0) and "currentA" in coil["measuredFields"], coil
    assert any("current" in yuk for _b, _t, yuk in kayit), kayit
    for _ in range(3):
        a._handle_backend_event(_Olay("hardware.stm.telemetry", cekirdek._parse_stm_tele(DOYGUN)))
    assert len([m for m, _s in bildirim if TD5_METNI in m]) == 1, bildirim


# ── 3) ESP (MQTT) sensors / status yükü ──────────────────────────────────────────────────────────────────────────────────


class _Mesaj:
    def __init__(self, konu, yuk, retain=False):
        self.topic = konu
        self.payload = json.dumps(yuk).encode("utf-8")
        self.retain = retain


@pytest.mark.parametrize("tur", ["sensors", "status"])
def test_KRITIK_kapaliyken_ESP_yukunun_akimi_CANLI_DURUMA_ve_CSVye_girmez(kapali, api, tur):
    a, yayin, _b, kayit = api
    yuk = {
        "object_temp": 33.25,
        "current": 1.234,
        "max_current": 9.9,
        "current_sensor_ok": True,
        "current_saturated": False,
    }
    a._on_mqtt_message_api(None, None, _Mesaj(f"pemf/coil/8/{tur}", yuk))
    coil = a._live_state["coils"][7]
    assert coil["currentA"] == 0.0, coil
    assert coil["objectTemp"] == pytest.approx(33.2, abs=0.06), "karşıt: sıcaklık yazılmadı — işleyici koşmadı (VAKUM)"
    assert not _akim_tasiyan(yayin), _akim_tasiyan(yayin)
    assert kayit, "sensör kaydı hiç çağrılmadı (VAKUM)"
    for _b, _t, k in kayit:
        assert not {"current", "max_current", "current_sensor_ok", "current_saturated"} & set(k), k


def test_KARSIT_acikken_ESP_akimi_YAZILIR(acik, api):
    a, _y, _b, kayit = api
    a._on_mqtt_message_api(None, None, _Mesaj("pemf/coil/8/sensors", {"current": 1.234}))
    assert a._live_state["coils"][7]["currentA"] == pytest.approx(1.234)
    assert any("current" in k for _b, _t, k in kayit)


def test_KRITIK_kapaliyken_ESP_overcurrent_ALARMI_susturulmaz_TAM_acil_durdurma(kapali):
    """Ö.4-Y8: bayrak akım ÖLÇÜMÜNÜ kapatır, alarmı DEĞİL — 'overcurrent' türü TAM acil durdurmaya gider (yalnız-sıcaklık değil)."""
    from servers import api_server as a

    assert a._esp_asiri_sicaklik_alarmi_mi("overcurrent") is False
    # Birleşik alarm (aşırı sıcaklık + aşırı akım): akım izi TAM acil durdurmaya götürür — yalnız-kendi-bobini DEĞİL.
    # ⚠️ İlk sürümde yalnız "overcurrent" / "overcurrent_temp" vardı: ikisi de sıcaklık desenine zaten uymadığından `current`'ı
    # listeden silen mutant SAĞ KALDI (kayit/CH4_mut_ozet.txt, M11).
    assert a._esp_asiri_sicaklik_alarmi_mi("overtemp_overcurrent") is False
    assert a._esp_asiri_sicaklik_alarmi_mi("over_temperature") is True


# ── 4) Sensör CSV kaydedicisi (tek giriş: STM + ESP) ─────────────────────────────────────────────────────────────────────────


def _csv_satirlari(kok: Path) -> list[dict]:
    satirlar = []
    for f in sorted(kok.rglob("*.csv")):
        satirlar += list(csv.DictReader(io.StringIO(f.read_text(encoding="utf-8"))))
    return satirlar


def test_KRITIK_kapaliyken_sensor_CSVsine_akim_YAZILMAZ(kapali, tmp_path, monkeypatch):
    from servers import sensor_kaydedici as sk

    monkeypatch.setenv("PEMF_SENSOR_LOG", "1")
    k = sk.SensorKaydedici(tmp_path)
    assert k.kaydet(3, "sensors", {"current": 2.5, "current_saturated": True, "max_current": 9, "object_temp": 30.0})
    k.flush()
    satirlar = _csv_satirlari(tmp_path)
    assert len(satirlar) == 1, satirlar
    s = satirlar[0]
    assert s["temp_object"] == "30.0", s
    assert s["current"] == "" and s["current_saturated"] == "" and s["max_current"] == "", s


def test_KARSIT_acikken_sensor_CSVsine_akim_YAZILIR(acik, tmp_path, monkeypatch):
    from servers import sensor_kaydedici as sk

    monkeypatch.setenv("PEMF_SENSOR_LOG", "1")
    k = sk.SensorKaydedici(tmp_path)
    assert k.kaydet(3, "sensors", {"current": 2.5})
    k.flush()
    assert _csv_satirlari(tmp_path)[0]["current"] == "2.5"


# ── 5) Sim kipi ─────────────────────────────────────────────────────────────────────────────────────────────────────────────

from test_sim_GERCEGI_ASMAZ import _tek_tur, izole_sim  # noqa: E402,F401  (aynı aparat: tek tur, yerel uyku yaması)


def test_KRITIK_kapaliyken_sim_akim_UYDURMAZ(kapali, izole_sim, monkeypatch):  # noqa: F811
    api, _ls = izole_sim
    monkeypatch.setitem(api._active_session, "is_active", True)
    monkeypatch.setitem(api._active_session, "duty", 50.0)
    monkeypatch.setitem(api._active_session, "frequency", 50.0)
    monkeypatch.setitem(api._active_session, "coil_ids", [])
    yayinlar = _tek_tur(api, monkeypatch)
    assert [m for m in yayinlar if m.get("type") == "coil_status"], "sim hiç yayın yapmadı (VAKUM)"
    assert not _akim_tasiyan(yayinlar), _akim_tasiyan(yayinlar)[:2]


def test_KARSIT_acikken_sim_akim_URETIR(acik, izole_sim, monkeypatch):  # noqa: F811
    api, _ls = izole_sim
    monkeypatch.setitem(api._active_session, "is_active", True)
    monkeypatch.setitem(api._active_session, "duty", 50.0)
    monkeypatch.setitem(api._active_session, "frequency", 50.0)
    monkeypatch.setitem(api._active_session, "coil_ids", [])
    assert _akim_tasiyan(_tek_tur(api, monkeypatch))


# ── 6) Seans geçmişi çıktıları (eski kayıtlardaki akım — TD5 öncesi sahte olabilir) ───────────────────────────────────────────


class _SahteDb:
    def get_session_details(self, sid):
        return {"id": sid, "session_date": "2026-10-01"}

    def get_run_summaries(self, sid):
        return {11: {"temp_avg": 30.0, "temp_max": 31.0, "current_avg": 74.6, "field_avg": 1.2, "sample_count": 5}}

    def get_session_coil_runs(self, sid):
        return [{"id": 11, "coil_id": 3, "hw_type": "stm32", "frequency_hz": 50, "duty_percent": 40}]

    def get_sensor_samples(self, sid):
        return [{"coil_id": "3", "sample_ts": 1.0, "temperature_c": 30.0, "current_a": 74.6, "magnetic_field_mt": 1.2}]


def test_KRITIK_kapaliyken_seans_ayrintisi_ve_CSV_AKIM_VERMEZ(kapali):
    from servers import history_router as h

    d = h.get_session_full_details(7, db=_SahteDb())
    assert d["sensor_samples"][0]["current_a"] is None, d["sensor_samples"]
    assert d["sensor_samples"][0]["temperature_c"] == 30.0
    ozet = d["coil_runs"][0]["summary"]
    assert ozet.get("current_avg") is None and ozet["temp_avg"] == 30.0, ozet
    r = h.export_coil_runs_csv(7, db=_SahteDb())
    satirlar = list(csv.reader(io.StringIO(r.body.decode("utf-8-sig"))))
    baslik, veri = satirlar[0], satirlar[1]
    assert "74.6" not in veri, veri
    assert veri[baslik.index("Ort.Akim(A)")] == "", (baslik, veri)
    assert veri[baslik.index("Ort.Sicaklik(C)")] == "30.0", veri


def test_KARSIT_acikken_seans_ayrintisi_akimi_VERIR(acik):
    from servers import history_router as h

    d = h.get_session_full_details(7, db=_SahteDb())
    assert d["sensor_samples"][0]["current_a"] == 74.6
    assert d["coil_runs"][0]["summary"]["current_avg"] == 74.6


# ── 7) Arayüze tek bayrak ───────────────────────────────────────────────────────────────────────────────────────────────────


def test_KRITIK_anlik_goruntu_akimOlcumu_bayragini_TASIR(monkeypatch):
    from servers import live_state as ls

    monkeypatch.delenv("PEMF_AKIM_OLCUMU", raising=False)
    assert ls._build_ws_snapshot().get("akimOlcumu") is False
    monkeypatch.setenv("PEMF_AKIM_OLCUMU", "1")
    assert ls._build_ws_snapshot().get("akimOlcumu") is True


@pytest.mark.parametrize("deger", ["", "0", "hayir", "true", " 2 "])
def test_bayrak_varsayilan_KAPALI_yalniz_1_acar(monkeypatch, deger):
    from utils import akim_olcumu as ao

    monkeypatch.setenv("PEMF_AKIM_OLCUMU", deger)
    assert ao.akim_olcumu_acik() is False
    monkeypatch.setenv("PEMF_AKIM_OLCUMU", "1")
    assert ao.akim_olcumu_acik() is True


# ── 8) Güvenlik yolları akıma BAĞLI DEĞİL (ölç ve kanıtla) ────────────────────────────────────────────────────────────────


#: Tanımlayıcı / sözcük SINIRINDA akım izi (⚠️ alt dize DEĞİL: "concurrent" içindeki "current" ilk ölçümde yalancı kırmızı verdi).
_AKIM_IZI_RE = re.compile(
    r"(?<![A-Za-z0-9_])(current|currentA|current_a|current_avg|current_saturated|max_current|akim[A-Za-z0-9_]*|akım"
    r"|ACS712|acs712)(?![A-Za-z0-9_])"
)


def _akim_izleri(kod: str) -> list[str]:
    return sorted({m.group(1) for m in _AKIM_IZI_RE.finditer(kod)})


#: (dosya, işlev / yöntem adı) — ACİL DURDUR, STOP, mandal, watchdog, keep-alive ve E-stop teyidi.
GUVENLIK_YOLLARI = [
    ("apps/backend/servers/api_server.py", "_emergency_stop_all"),
    ("apps/backend/servers/api_server.py", "_emergency_stop_async"),
    ("apps/backend/servers/api_server.py", "emergency_stop"),
    ("apps/backend/servers/api_server.py", "_stop_session_coils"),
    ("apps/backend/servers/api_server.py", "stop_session"),
    ("apps/backend/servers/api_server.py", "_y45_mandal_kur"),
    ("apps/backend/servers/api_server.py", "_esp_telemetry_watchdog"),
    ("apps/backend/servers/api_server.py", "_estop_ack_watch"),
    ("apps/backend/servers/live_state.py", "estop_teyidi_yaz"),
    ("apps/backend/servers/live_state.py", "estop_teyidi_stm_ack"),
    ("apps/backend/controllers/hardware_controller.py", "stop_all_coils"),
    ("apps/backend/controllers/hardware_controller.py", "on_disconnect"),
    ("apps/backend/controllers/hardware_controller.py", "_keep_alive_loop"),
    ("apps/backend/controllers/hardware_controller.py", "stop"),
    ("apps/backend/headless_core.py", "_hw_sender_worker"),
    ("apps/backend/headless_core.py", "hw_stop_yaniti_bekle"),
]


def _islev_kaynagi(dosya: str, ad: str) -> str:
    metin = (KOK / dosya).read_text(encoding="utf-8")
    agac = ast.parse(metin)
    bulunan = [d for d in ast.walk(agac) if isinstance(d, (ast.FunctionDef, ast.AsyncFunctionDef)) and d.name == ad]
    assert bulunan, f"{dosya}::{ad} bulunamadı — güvenlik yolu yeniden adlandırılmış olabilir (kapı listesini güncelle)"
    # Yorum ve belge dizgeleri DEĞİL, kodun kendisi: ast.unparse yorum taşımaz; belge dizgesi ayrıca çıkarılır.
    parcalar = []
    for d in bulunan:
        d = ast.parse(textwrap.dedent(ast.get_source_segment(metin, d)))
        for alt in ast.walk(d):
            if isinstance(alt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)) and alt.body:
                ilk = alt.body[0]
                if isinstance(ilk, ast.Expr) and isinstance(getattr(ilk, "value", None), ast.Constant):
                    alt.body = alt.body[1:] or [ast.Pass()]
        parcalar.append(ast.unparse(d))
    return "\n".join(parcalar)


@pytest.mark.parametrize(("dosya", "ad"), GUVENLIK_YOLLARI)
def test_KRITIK_guvenlik_yolu_AKIM_okumaz(dosya, ad):
    kod = _islev_kaynagi(dosya, ad)
    izler = _akim_izleri(kod)
    assert not izler, f"{dosya}::{ad} akım izi taşıyor: {izler} — ACİL DURDUR / STOP akıma BAĞLANAMAZ (Y154, Ö.4-Y8)"


def test_KRITIK_watchdog_ve_kopma_dallari_AKIM_okumaz():
    """`_handle_backend_event`'in güvenlik dalları (kopma, firmware watchdog, termal olay, STOP onayı) akım okumaz;
    yalnız telemetri dalı akım anahtarlarını taşır (ölçüm yolu)."""
    metin = API.read_text(encoding="utf-8")
    fn = next(
        d for d in ast.walk(ast.parse(metin)) if isinstance(d, ast.FunctionDef) and d.name == "_handle_backend_event"
    )
    dallar = {}
    for d in ast.walk(fn):
        if (
            isinstance(d, ast.If)
            and isinstance(d.test, ast.Compare)
            and isinstance(d.test.left, ast.Attribute)
            and d.test.left.attr == "event_type"
            and isinstance(d.test.comparators[0], ast.Constant)
        ):
            dallar[d.test.comparators[0].value] = ast.unparse(ast.Module(body=d.body, type_ignores=[]))
    for tur in ("hardware.stm.disconnected", "hardware.stm.watchdog_timeout", "hardware.stm.stop_onayi"):
        assert tur in dallar, f"dal {tur} bulunamadı (VAKUM) — bulunanlar: {sorted(dallar)}"
        izler = _akim_izleri(dallar[tur])
        assert not izler, f"{tur} dalı akım izi taşıyor: {izler}"
    assert "current" in _akim_izleri(dallar["hardware.stm.telemetry"]), (
        "karşıt: telemetri dalı akım anahtarını taşımalı (araç kör değil)"
    )

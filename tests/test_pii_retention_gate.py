# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""GERİ DÖNÜŞSÜZ PII MASKELEME — operatör bilmeden çalışmaz (2026-08-09 denetimi, Tier 1).

ARIZA: seans kayıtlarındaki hasta/operatör adı ve notlar, süre dolunca `[REDACTED]` ile GERİ
DÖNÜŞSÜZ maskeleniyordu ve bu tamamen SESSİZ oluyordu. Süre yalnız `PEMF_RETAIN_PII_DAYS`
ortam değişkeniyle ayarlanabiliyordu — hiçbir veteriner bunu bilmez.

Sonuç: klinik 366. günde hasta adı yerine `[REDACTED]` görüyor, sebebini hiçbir yerde
bulamıyor ve "veritabanım bozuldu" diye destek arıyor. Tıbbi-hukuki saklama süresi ülkeye ve
kliniğe göre değişir (KVKK silmeyi ister, açılmış bir dava dosyası saklamayı) → KARAR
OPERATÖRÜNDÜR; yazılım onu sessizce almaz.
"""

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient


def _db(dizin):
    from database.treatment_history_db import TreatmentHistoryDB

    return TreatmentHistoryDB(dizin)


def _eski_seans(db, ad, gun_once):
    """Belirtilen gün kadar önce yapılmış bir seans yaz."""
    tarih = (datetime.now() - timedelta(days=gun_once)).strftime("%Y-%m-%d")
    with db._get_connection() as c:
        cur = c.cursor()
        cur.execute(
            "INSERT INTO treatment_sessions (session_date, start_time, treatment_mode, "
            "patient_name, operator_name) VALUES (?,?,?,?,?)",
            (tarih, "10:00", "Manuel", ad, "Dr. Test"),
        )
        c.commit()
        return cur.lastrowid


def _adlar(db):
    with db._get_connection() as c:
        return sorted(r[0] for r in c.execute("SELECT patient_name FROM treatment_sessions"))


@pytest.fixture
def dolu(tmp_path):
    d = _db(tmp_path)
    _eski_seans(d, "EskiPamuk", 400)  # süre dolmuş
    _eski_seans(d, "YeniBoncuk", 10)  # taze
    yield d
    d.close_connections()


# ── kapı: onay yoksa maskeleme YOK ───────────────────────────────────────────


def test_KRITIK_onay_YOKKEN_maskeleme_YAPILMAZ(dolu):
    r = dolu.apply_data_retention_policy(
        sensor_retain_days=0, event_retain_days=0, dead_outbox_retain_days=0, pii_retain_days=365
    )
    assert r["sessions_pii_redacted"] == 0, "onaysiz GERI DONUSSUZ maskeleme yapildi"
    assert "EskiPamuk" in _adlar(dolu), "hasta adi sessizce silindi"


def test_KRITIK_bekleyen_kayit_sayisi_RAPORLANIR(dolu):
    """Arayüz "ne kaybedeceğini" söyleyebilsin diye sayı raporlanmalı."""
    r = dolu.apply_data_retention_policy(
        sensor_retain_days=0, event_retain_days=0, dead_outbox_retain_days=0, pii_retain_days=365
    )
    assert r["pii_pending"] == 1, f"bekleyen kayit sayisi yanlis: {r}"


def test_onaydan_SONRA_maskeleme_calisir(dolu):
    dolu.pii_onayla(gun=365, sayi=1)
    r = dolu.apply_data_retention_policy(
        sensor_retain_days=0, event_retain_days=0, dead_outbox_retain_days=0, pii_retain_days=365
    )
    assert r["sessions_pii_redacted"] == 1
    assert "[REDACTED]" in _adlar(dolu)
    assert "YeniBoncuk" in _adlar(dolu), "sure dolmamis kayit da maskelendi"


def test_sure_SIFIRSA_hicbir_sey_maskelenmez(dolu):
    """0 = kapalı. Kliniği süresiz saklamaya zorlamak da, silmeye zorlamak da yanlış."""
    dolu.pii_onayla(gun=365, sayi=1)
    r = dolu.apply_data_retention_policy(
        sensor_retain_days=0, event_retain_days=0, dead_outbox_retain_days=0, pii_retain_days=0
    )
    assert r["sessions_pii_redacted"] == 0
    assert "EskiPamuk" in _adlar(dolu)


# ── operatörün seçtiği süre ortam değişkenini EZER ───────────────────────────


def test_KRITIK_operator_suresi_ORTAM_DEGISKENINI_ezer(dolu):
    """Ayar arayüzden yönetilir; env yalnız varsayılandır. Aksi hâlde operatör ekrandan
    değiştirir ama hiçbir şey değişmez."""
    dolu.pii_onayla(gun=365, sayi=1)
    dolu.pii_suresi_yaz(0)  # operatör: KAPALI
    r = dolu.apply_data_retention_policy(
        sensor_retain_days=0, event_retain_days=0, dead_outbox_retain_days=0, pii_retain_days=365
    )
    assert r["sessions_pii_redacted"] == 0, "operator karari yok sayildi"
    assert "EskiPamuk" in _adlar(dolu)


def test_operator_suresi_kalici(tmp_path):
    d = _db(tmp_path)
    try:
        assert d.pii_suresi_oku() is None
        d.pii_suresi_yaz(730)
        assert d.pii_suresi_oku() == 730
    finally:
        d.close_connections()


def test_kuru_calisma_hicbir_seyi_DEGISTIRMEZ(dolu):
    once = _adlar(dolu)
    assert dolu.redaksiyon_bekleyen_sayisi(365) == 1
    assert _adlar(dolu) == once, "on-sayim kayitlari degistirdi"


def test_zaten_maskelenmis_kayit_TEKRAR_SAYILMAZ(dolu):
    dolu.pii_onayla(gun=365, sayi=1)
    dolu.apply_data_retention_policy(
        sensor_retain_days=0, event_retain_days=0, dead_outbox_retain_days=0, pii_retain_days=365
    )
    assert dolu.redaksiyon_bekleyen_sayisi(365) == 0, "maskelenmis kayit bekleyen sayildi"


# ── API ──────────────────────────────────────────────────────────────────────


@pytest.fixture
def api():
    from servers import api_server

    return api_server


@pytest.fixture
def client(api, tmp_path, monkeypatch, dolu):
    monkeypatch.setattr(api, "_app_data_dir", lambda: tmp_path)
    from database import treatment_history_db as thm

    monkeypatch.setattr(thm, "get_treatment_db", lambda _d: dolu)
    return TestClient(api.app, client=("127.0.0.1", 51234))


def test_API_durum_bekleyeni_bildirir(client):
    r = client.get("/api/settings/retention")
    assert r.status_code == 200, r.text[:300]
    g = r.json()
    assert g["pending"] == 1, f"arayuz kac kayit maskelenecegini goremiyor: {g}"
    assert g["acknowledged"] is False
    assert g["days"] == 365


def test_API_onay_maskelemeyi_ACAR(client, dolu):
    assert (
        client.post("/api/settings/retention", json={"acknowledge": True, "acknowledge_days": 365}).status_code == 200
    )
    assert dolu.pii_onayi_var_mi(365) is True
    assert client.get("/api/settings/retention").json()["pending"] == 0


def test_API_sure_ayarlanabilir(client, dolu):
    assert client.post("/api/settings/retention", json={"days": 730}).status_code == 200
    g = client.get("/api/settings/retention").json()
    assert g["days"] == 730 and g["configured"] is True


def test_KRITIK_sure_degistirmek_ONAY_YERINE_GECMEZ(client, dolu):
    """Süreyi değiştirmek tek başına geri dönüşsüz maskelemeyi başlatmamalı."""
    client.post("/api/settings/retention", json={"days": 30})
    assert dolu.pii_onayi_var_mi(30) is False, "sure degisikligi onay sayildi"


def test_gecersiz_sure_REDDEDILIR(client):
    assert client.post("/api/settings/retention", json={"days": -5}).status_code == 400
    assert client.post("/api/settings/retention", json={"days": 999999}).status_code == 400


def test_KRITIK_LANdan_kimliksiz_REDDEDILIR(api):
    """Bu uç tıbbi kaydın kalıcılığını belirler — klinik ağındaki rastgele bir cihaz
    saklama süresini 1 güne çekememeli."""
    lan = TestClient(api.app, client=("192.168.1.77", 51234))
    assert lan.get("/api/settings/retention").status_code == 403
    assert lan.post("/api/settings/retention", json={"days": 1}).status_code == 403


# ── TERMAL KORUMA DÜRÜSTLÜĞÜ (2026-08-09 denetimi, Tier 2) ──────────────────
# `firmware/README.md` "termal koruma sensör/ESP tarafındadır" diyordu. Bu ifade 1-5 numaralı
# bobinler için DOĞRU DEĞİLDİ: STM protokolünde sıcaklık alanı YOK, o bobinlerden hiç ölçüm
# gelmiyor ve tek kesme mantığı (`objectTemp > 48`) hiçbir zaman tetiklenemiyordu (o tarihte 8 bobinin 5'i).
# ⚠️ GÜNCEL (L1-7.2 · i2-F-9; sahip kararı A-47): termal kesme / 48 °C interlock HİÇBİR bobinde YOK — bobin 1-7 STM'de
# (sıcaklık alanı yok), ESP yolu (bobin 8) kapalı. Bu dosyadaki kapılar "koruma var" iddiasının geri gelmesini engeller.
# Yanlış güvence korumasızlıktan tehlikelidir: koruma var sanılınca donanım önlemi ertelenir.


def test_KRITIK_firmware_README_yanlis_termal_iddiasi_ICERMEZ():
    from pathlib import Path

    p = Path(__file__).resolve().parent.parent / "firmware" / "README.md"
    metin = p.read_text(encoding="utf-8")
    assert "termal koruma sensör/ESP tarafındadır. Sahip bunu bilerek" not in metin, (
        "yanlis termal koruma iddiasi geri geldi — 1-5 bobinlerinde sensor/ESP YOK"
    )
    # Sınır AÇIKÇA yazılı olmalı ki donanım önlemi ertelenmesin.
    assert "1-5" in metin and "hiçbir sıcaklık" in metin.replace("HİÇBİR", "hiçbir"), (
        "sinirin kapsami (1-5 bobinlerinde koruma yok) README'de yazmiyor"
    )


def test_STM_protokolunde_sicaklik_alani_YOK():
    """İddianın dayanağı: STM paketi duty/phase/freq/duration taşır, sıcaklık TAŞIMAZ."""
    from pathlib import Path

    hc = (
        Path(__file__).resolve().parent.parent / "apps" / "backend" / "controllers" / "hardware_controller.py"
    ).read_text(encoding="utf-8")
    assert "temperature" not in hc.lower(), "STM kontrolcusune sicaklik eklendi — README/UI sinir notlari GUNCELLENMELI"


# ── D6.53 (B-11.x · Faz 4) — firmware/README topoloji ve termal tablosu BUGÜNKÜ bobin kümeleriyle aynı ──────────────────────
# ÖLÇÜLEN (HEAD ebf1c3fe): `firmware/README.md:42` "ESP bobinler (6-8): ESP32-S3 / ESP8266" ve termal tablosu `:156-157`
# "1-5 STM32 … | 6-8 ESP32 (MQTT)" ↔ `apps/backend/servers/live_state.py` `STM_COIL_IDS = set(range(1, 8))`, `ESP_COIL_IDS = {8}`
# (Faz 4: bobin 6-7 STM'den sürülür, sıcaklıkları `STM_TELE` `T=` alanıyla — MLX90614). Kümeler AST'den okunur (ürün import EDİLMEZ).


def _canli_bobin_kumeleri() -> tuple[set[int], set[int]]:
    import ast
    from pathlib import Path

    kaynak = (Path(__file__).resolve().parent.parent / "apps" / "backend" / "servers" / "live_state.py").read_text(
        encoding="utf-8"
    )
    kume = {}
    for d in ast.walk(ast.parse(kaynak)):
        if (
            isinstance(d, ast.Assign)
            and len(d.targets) == 1
            and getattr(d.targets[0], "id", "") in ("STM_COIL_IDS", "ESP_COIL_IDS")
        ):
            ad = d.targets[0].id
            if isinstance(d.value, ast.Call) and getattr(d.value.func, "id", "") == "set":
                a = d.value.args[0]  # set(range(x, y))
                kume[ad] = set(range(*[ast.literal_eval(x) for x in a.args]))
            else:
                kume[ad] = set(ast.literal_eval(d.value))
    return kume["STM_COIL_IDS"], kume["ESP_COIL_IDS"]


def _aralik(h: str) -> set[int]:
    import re

    m = re.fullmatch(r"\s*(\d+)\s*(?:-\s*(\d+))?\s*", h)
    assert m, f"bobin hücresi ayrıştırılamadı: {h!r}"
    a, b = int(m.group(1)), int(m.group(2) or m.group(1))
    return set(range(a, b + 1))


def test_KRITIK_D6_53_firmware_README_termal_tablosu_GUNCEL_topolojiyle_ayni():
    import re
    from pathlib import Path

    stm, esp = _canli_bobin_kumeleri()
    metin = (Path(__file__).resolve().parent.parent / "firmware" / "README.md").read_text(encoding="utf-8")
    assert "GÜNCEL TOPOLOJİ (Faz 4" in metin, (
        "firmware/README Faz 4 GÜNCEL termal / topoloji tablosu YOK (yalnız eski 1-5 STM · 6-8 ESP tablosu)"
    )
    bas = metin.index("GÜNCEL TOPOLOJİ (Faz 4")
    satirlar = []
    for s in metin[bas:].splitlines()[1:]:
        s = s.lstrip("> ").rstrip()
        if s.startswith("|"):
            satirlar.append(s)
        elif satirlar:
            break
    govde = [s for s in satirlar if re.match(r"\|\s*\d", s)]
    assert govde, "GÜNCEL termal tablosu bulunamadı"
    tablo_stm, tablo_esp = set(), set()
    for s in govde:
        h = [x.strip() for x in s.strip("|").split("|")]
        (tablo_stm if "STM32" in h[1] else tablo_esp if "ESP" in h[1] else set()).update(_aralik(h[0]))
    assert tablo_stm == stm, (
        f"firmware/README GÜNCEL tablo STM bobinleri {sorted(tablo_stm)} ≠ live_state {sorted(stm)}"
    )
    assert tablo_esp == esp, (
        f"firmware/README GÜNCEL tablo ESP bobinleri {sorted(tablo_esp)} ≠ live_state {sorted(esp)}"
    )
    cizgisiz = re.sub(r"~~.*?~~", " ", metin, flags=re.S)
    assert not re.search(r"ESP bobinler \(6-8\)", cizgisiz), (
        "firmware/README topoloji satırı bobin 6-8'i ESP sayıyor (Faz 4: yalnız 8)"
    )

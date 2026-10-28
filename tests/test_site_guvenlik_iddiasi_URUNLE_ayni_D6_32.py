# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D6.32 (B-7.11 · B-7.12) — sitenin GÜVENLİK iddiaları ürünün bugünkü davranışıyla AYNI (çapraz-yüzey kapı).

🔴 ÖLÇÜLEN (HEAD ebf1c3fe):
  (a) Ana sayfa / Özellikler "Klinik Güvenlik" kartı (`apps/web/src/i18n/tr/icerik.json` `ozellik.f5.aciklama`, `config.ts:546-547` FEATURES)
      "Acil durdurma düğmesi, otomatik süre sınırı ve HEDEF KONTROLÜ: seans, uygulanacak bölge güvenle TESPİT EDİLMEDEN BAŞLAMAZ" diyordu.
      Ürün: `/api/session/start` (`apps/backend/servers/api_server.py:3947`) Manuel / Otomatik kipte hedef / bölge / kamera verisi İSTEMEZ
      (`SessionStartPayload.target_condition = ""` varsayılan; bölge tespiti yalnız AI Pro'nun kendi akışında) — hedefsiz Manuel seans 200 ile başlar.
  (b) SSS'teki "sıcaklık kesmesi her koşulda önceliklidir" (B-7.12 = B-11.8) Y166 ile (`be8ca509`) kalktı; termal kesme / 48 °C interlock YOK (A-47,
      `firmware/stm32_pemf/Core/Src/main.c` `PEMF_NTC_TERMAL_ENABLED` varsayılan 0). İddianın GERİ GELMESİ bu kapıda KOŞULSUZ yasak.

ÖLÇÜT:
  (a) Kapı iddiayı ürünün ÖLÇÜLEN davranışına bağlar: GERÇEK `HardwareController` (kayıtçı kuyruk — en alt kat) + izole tedavi DB'si ile hedef / bölge
      verisi OLMAYAN Manuel `/api/session/start` koşulur. 2xx ise (bugün) sitenin TR + EN kataloğu "bölge tespit edilmeden başlamaz" kilidini İDDİA
      EDEMEZ. Uç 503 / 409 dönerse kapı YEŞİL DEMEZ (orkestratör notu C2b: `state.hardware` yokken 503 ile bedava yeşil tuzağı) — ölçüm geçersiz → KIRMIZI.
  (b) "sıcaklık kesmesi / termal koruma / 48 °C" iddiası sitenin kataloğunda, `config.ts`'de ve site belgelerinde KOŞULSUZ yasak (Ö.4 + A-47): firmware
      bayrağını 1 yapmak kapıyı yeşile ÇEVİRMEZ (bayrak okunmaz — yasak değişikliği ödüllendirmez).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

from scripts.i18n import ortak  # noqa: E402

#: (a) bölge / hedef tespiti KİLİDİ iddiası (TR, EN) — "seans … tespit edilmeden başlamaz", "target check".
BOLGE_KILIDI_TR = re.compile(
    r"tespit\s+edilmeden\s+(?:seans\s+)?başla|hedef\s+kontrol[üu]|bölge\s+(?:güvenle\s+)?tespit", re.I
)
BOLGE_KILIDI_EN = re.compile(
    r"(?:does\s+not|won't|will\s+not)\s+start\s+until[^.]{0,60}detected|target\s+check|area\s+has\s+been\s+(?:safely\s+)?detected",
    re.I,
)
#: (b) termal kesme iddiası (TR, EN) — KOŞULSUZ yasak.
TERMAL_TR = re.compile(
    r"sıcaklık\s+kesme|termal\s+(?:koruma|kesme)|aşırı\s+ısınma\s+koruma|ısı\s+kesme|48\s*°\s*C", re.I
)
TERMAL_EN = re.compile(
    r"temperature\s+cut-?\s?off|thermal\s+(?:protection|cut-?\s?off|shutdown)|overheat(?:ing)?\s+protection|48\s*°\s*C",
    re.I,
)

SITE_BELGELERI = ("apps/web/README.md", "apps/web/METIN-KILAVUZU.md")


def _site_katalogu(dil: str) -> dict[str, str]:
    return ortak.duzlestir(ortak.katalog_yukle("site", dil))


def _config_dizgileri() -> str:
    """`config.ts`'nin YORUMSUZ hâli (yorumdaki gerekçe iddia sayılmaz; dizge ve kod sayılır)."""
    src = (KOK / "apps" / "web" / "src" / "config.ts").read_text(encoding="utf-8")
    src = re.sub(r"/\*.*?\*/", " ", src, flags=re.S)
    return "\n".join(re.sub(r"(^|\s)//.*$", " ", s) for s in src.splitlines())


@pytest.fixture
def istemci():
    from fastapi.testclient import TestClient
    from servers import api_server

    with TestClient(api_server.app) as c:
        yield c


@pytest.fixture
def izole_db(tmp_path, monkeypatch):
    from database.treatment_history_db import TreatmentHistoryDB
    from servers import api_server, coil_run_tracker

    kok = tmp_path / "izole_gecmis"
    kok.mkdir(parents=True, exist_ok=True)
    db = TreatmentHistoryDB(kok)
    monkeypatch.setattr(api_server, "_get_treatment_db", lambda: db)
    monkeypatch.setattr(coil_run_tracker, "_treatment_db_getter", lambda: db)
    return db


@pytest.fixture
def hedefsiz_manuel_seans(istemci, izole_db, monkeypatch):
    """GERÇEK HardwareController + kayıtçı kuyrukla hedef / bölge verisi OLMAYAN Manuel seans; (durum kodu, gönderilen paket sayısı)."""
    from kayitci_donanim import gercek_hc
    from servers import api_server, live_state

    monkeypatch.setattr(api_server, "_mqtt_publish", lambda topic, payload: False)
    live_state.stm_komut_kabulu_bildir()
    with gercek_hc() as hc:
        monkeypatch.setattr(api_server.state, "hardware", hc)
        y = istemci.post(
            "/api/session/start",
            json={
                "mode": "Manuel",
                "frequency": 50,
                "duty": 25,
                "phase": 0,
                "intensity": 0.0,
                "duration_minutes": 1,
                "coil_ids": [1],
                "patient_name": "BolgeIddiasi",
            },
        )
        paket = len(hc.core._hw_send_queue.paketler)
        try:
            istemci.post("/api/session/stop")
        except Exception:
            pass
    return y.status_code, y.text[:300], paket


def test_OLCUM_hedefsiz_Manuel_seans_GERCEKTEN_baslar(hedefsiz_manuel_seans):
    """KARŞIT / ön koşul: kapının dayandığı ürün gerçeği ÖLÇÜLÜR — 503 / 409 ile 'bedava yeşil' YOK."""
    kod, govde, paket = hedefsiz_manuel_seans
    assert kod == 200, (
        f"hedefsiz Manuel seans {kod} döndü ({govde!r}) — ölçüm GEÇERSİZ (aparat seansı başlatamadı). Bölge kilidi gerçekten eklendiyse "
        "bu testi ve (a) kolunu YENİ davranışa göre güncelleyin; aparat bozulduysa düzeltin — kapı bunu yeşil saymaz."
    )
    assert paket >= 1, "seans 200 döndü ama donanım kuyruğuna hiç paket gitmedi — ölçüm seans başlatmayı göstermiyor"


def test_KRITIK_site_BOLGE_TESPIT_kilidi_iddia_ETMEZ(hedefsiz_manuel_seans):
    """(a) Ürün hedefsiz Manuel seansı başlatırken site "bölge tespit edilmeden başlamaz" diyemez (TR + EN, katalog + config dizgileri)."""
    kod, _, _ = hedefsiz_manuel_seans
    assert kod == 200, "ölçüm geçersiz — bkz. test_OLCUM_hedefsiz_Manuel_seans_GERCEKTEN_baslar"
    sorun = [f"tr:{k}: {v!r}" for k, v in _site_katalogu("tr").items() if BOLGE_KILIDI_TR.search(v)]
    sorun += [f"en:{k}: {v!r}" for k, v in _site_katalogu("en").items() if BOLGE_KILIDI_EN.search(v)]
    cfg = _config_dizgileri()
    sorun += [f"config.ts: {m.group(0)!r}" for m in BOLGE_KILIDI_TR.finditer(cfg)]
    sorun += [f"config.ts: {m.group(0)!r}" for m in BOLGE_KILIDI_EN.finditer(cfg)]
    assert not sorun, (
        "site, ürünün UYGULAMADIĞI bir başlatma kilidini iddia ediyor (hedefsiz Manuel seans 200 ile başlıyor):\n  "
        + "\n  ".join(sorun)
    )


def test_KRITIK_TERMAL_kesme_iddiasi_KOSULSUZ_yok():
    """(b) "sıcaklık kesmesi / termal koruma / 48 °C" sitenin hiçbir yüzeyinde YOK — firmware bayrağından BAĞIMSIZ (A-47 · Ö.4)."""
    sorun = [f"tr:{k}: {v!r}" for k, v in _site_katalogu("tr").items() if TERMAL_TR.search(v)]
    sorun += [f"en:{k}: {v!r}" for k, v in _site_katalogu("en").items() if TERMAL_EN.search(v)]
    cfg = _config_dizgileri()
    sorun += [f"config.ts: {m.group(0)!r}" for r in (TERMAL_TR, TERMAL_EN) for m in r.finditer(cfg)]
    for rel in SITE_BELGELERI:
        metin = (KOK / rel).read_text(encoding="utf-8")
        sorun += [f"{rel}: {m.group(0)!r}" for r in (TERMAL_TR, TERMAL_EN) for m in r.finditer(metin)]
    assert not sorun, (
        "termal kesme / 48 °C iddiası (ürün termal kesme UYGULAMAZ — A-47; GERİ EKLENMEZ):\n  " + "\n  ".join(sorun)
    )


@pytest.mark.parametrize(
    "dil,metin,beklenen",
    [
        (
            "tr",
            "Acil durdurma, süre sınırı ve hedef kontrolü: seans, uygulanacak bölge güvenle tespit edilmeden başlamaz.",
            True,
        ),
        (
            "en",
            "Emergency stop and target check: a session does not start until the target area has been safely detected.",
            True,
        ),
        (
            "tr",
            "Acil durdurma düğmesi ve otomatik süre sınırı: seans her an durdurulabilir ve ayarlanan süre dolunca sona erer.",
            False,
        ),
        (
            "en",
            "Emergency stop button and automatic time limit: a session can be stopped at any moment and ends when the set duration is up.",
            False,
        ),
    ],
)
def test_KARSIT_KANIT_bolge_deseni_AYIRIYOR(dil, metin, beklenen):
    """Desen eski iddiayı YAKALAR, gerçeğe inmiş metni YAKALAMAZ (vakum / aşırı geniş desen olmasın)."""
    r = BOLGE_KILIDI_TR if dil == "tr" else BOLGE_KILIDI_EN
    assert bool(r.search(metin)) is beklenen


@pytest.mark.parametrize(
    "dil,metin,beklenen",
    [
        ("tr", "acil durdurma, süre sınırı ve sıcaklık kesmesi her koşulda önceliklidir", True),
        ("tr", "termal koruma cihazda gömülü", True),
        ("en", "the temperature cut-off always takes priority", True),
        ("tr", "Canlı sensör ekranı (alan şiddeti mT · sıcaklık °C)", False),
        ("en", "Live sensor screen (field strength mT · temperature °C)", False),
    ],
)
def test_KARSIT_KANIT_termal_deseni_AYIRIYOR(dil, metin, beklenen):
    r = TERMAL_TR if dil == "tr" else TERMAL_EN
    assert bool(r.search(metin)) is beklenen

# Author: mertaygn, cglrgrkn
"""D1.38 · B-10.161 · B-10.162 — firmware uyum kapısı DAVRANIŞLA: uyumlu banner seansı GERÇEKTEN geçirir;
banner → karar zinciri GERÇEK `HeadlessCore._handle_stm_line` ile ölçülür.

ÖLÇÜLEN KÖRLÜK:
  * (B-10.161) `test_stm_firmware_uyum_kapisi::test_KARSIT_KANIT_UYUMLU_bannerda_kapi_KAPANMIYOR`
    `state.hardware`'ı yamalamıyordu → STM seansı uyum kapısına VARMADAN 503 alıyor, `!= 409` kendiliğinden
    geçiyordu. Kapı "hep reddet"e düşse (`is False` → `is not None`) yeşil kalıyordu: uyumlu firmware'de
    HİÇBİR STM seansı başlamaz, klinik durur.
  * (B-10.162) Banner → karar bağı yalnız AST/metinle ölçülüyordu; `_stm_kimligini_isle("")` (banner
    yerine boş dize) ya da çağrının `if False:` altına alınması yeşil kalıyordu → `stm_uyumlu` sonsuza dek
    `None`, uyumsuz kart hiç reddedilmez.

Banner'lardan biri SAHADA ölçülen dizedir (SAHIP-CEVAPLARI Y7, 2026-09-30): kapı bunu UYUMLU saymalı —
saymazsa bir sonraki yayında sahadaki her STM seansı 409 alır (D1.103'ün konusu; burada yalnız bugünkü
karar pinlenir, `uyum_denetle` kuralı DEĞİŞTİRİLMEZ).

⚠️ Ö.4-Y8: uyum kapısı ACİL DURDURMAYI kapılamaz — mevcut `test_KRITIK_UYUMSUZ_firmware_ACIL_DURDURMAYI_engellemez`
korunur; bu dosya yalnız BAŞLATMA yolunu ölçer.
"""

from __future__ import annotations

import pytest
from topoloji import TUM_STM

ESKI_BANNER = "-> STM_READY: DDS v2.3 (5-ch SYM-BIPOLAR uni=0x00 + HW_SYNC@PB1) Waiting for commands..."
YENI_BANNER = "-> STM_READY: DDS v2.3 (7-ch UNIPOLAR tek-bacak uni=0x60 + HW_SYNC@PB1) Waiting for commands..."
#: SAHA (Y7, sahibin salt-okur ölçümü 2026-09-30): saha günlüğündeki `STM_READY` satırının banner'ı.
SAHA_BANNER = "-> STM_READY: DDS v2.3 (7-ch KARMA uni=0x60 + HW_SYNC@PB1)"
BOZUK_BANNER = "-> STM_READY: eski surum, kanal bilgisi yok"


def _karar(banner: str):
    from utils.stm32_kimlik import banner_ayristir, uyum_denetle
    from utils.stm32_transport import STM_PAKET_BOBIN_SAYISI

    return uyum_denetle(banner_ayristir(banner), STM_PAKET_BOBIN_SAYISI)


class _Cekirdek:
    def __init__(self, uyumlu, sebep=""):
        self.stm_uyumlu = uyumlu
        self.stm_uyumsuzluk_sebebi = sebep
        self.stm_is_connected = True

    def get_service_status(self):
        return {}


@pytest.fixture
def seans_ortami(tmp_path, monkeypatch):
    """GERÇEK HC (kayıtçı kuyruk) + tmp tedavi DB'si: STM seansı uyum kapısına ULAŞIR ve geçerse sürer."""
    from database.treatment_history_db import TreatmentHistoryDB
    from fastapi.testclient import TestClient
    from kayitci_donanim import gercek_hc
    from servers import api_server as api
    from servers import coil_run_tracker, live_state

    db = TreatmentHistoryDB(tmp_path)
    monkeypatch.setattr(api, "_get_treatment_db", lambda: db)
    monkeypatch.setattr(coil_run_tracker, "_treatment_db_getter", lambda: db)
    monkeypatch.setattr(api, "_ws_broadcast_sync", lambda *a, **k: None)
    live_state.stm_komut_kabulu_bildir()
    istemci = TestClient(api.app, client=("127.0.0.1", 51236))
    with gercek_hc() as hc:
        hc.baslatilan = []
        _orj = hc.update_coil

        def _sayan(coil_id, *a, **k):
            hc.baslatilan.append(coil_id)
            return _orj(coil_id, *a, **k)

        hc.update_coil = _sayan
        monkeypatch.setattr(api.state, "hardware", hc)
        try:
            yield api, istemci, hc
        finally:
            istemci.post("/api/session/stop", json={})
            db.close_connections()
            live_state.stm_komut_kabulu_bildir()


_GOVDE = {
    "mode": "Manuel",
    "frequency": 100,
    "duty": 40,
    "phase": 0,
    "intensity": 0.0,
    "duration_minutes": 5,
    "coil_ids": [1, 2],
    "patient_name": "UyumDavranis",
}

#: 1-B bağımsız inceleme (i4): bobin kümeleri TOPOLOJİDEN (D1.31 deseni) — kapı yalnız [1, 2] ile sınanıyordu;
#: `min(stm_coils) < 6` koşulu eklenince UYUMSUZ (5-ch) kartta yalnız 6–7'lik seans — tam da o kartın SÜREMEDİĞİ
#: bobinler — 200 alıyordu, kapı YEŞİLDİ.
STM_KUMELERI = [[min(TUM_STM)], [max(TUM_STM)], sorted(TUM_STM)[-2:], sorted(TUM_STM)]
STM_KUME_ID = ["ilk", "son", "son_iki", "tumu"]


@pytest.mark.parametrize("kume", STM_KUMELERI, ids=STM_KUME_ID)
@pytest.mark.parametrize("banner", [YENI_BANNER, SAHA_BANNER], ids=["repo_7ch", "SAHA_Y7"])
def test_KRITIK_UYUMLU_banner_STM_seansini_GERCEKTEN_baslatir(seans_ortami, monkeypatch, banner, kume):
    api, istemci, hc = seans_ortami
    uyumlu, sebep = _karar(banner)
    assert uyumlu is True, f"ön koşul: {banner!r} uyumlu sayılmalı (karar {uyumlu}, {sebep!r}) — D1.103"
    monkeypatch.setattr(api.state, "core", _Cekirdek(uyumlu, sebep), raising=False)
    r = istemci.post("/api/session/start", json={**_GOVDE, "coil_ids": kume})
    assert r.status_code == 200, f"UYUMLU firmware'de STM seansı {r.status_code}: {r.text[:200]} — kapı hep reddediyor"
    assert sorted(set(hc.baslatilan)) == kume, f"seans bobinleri sürmedi: {hc.baslatilan}"


@pytest.mark.parametrize("kume", STM_KUMELERI, ids=STM_KUME_ID)
def test_KARSIT_UYUMSUZ_banner_ayni_aparatla_409_ve_bobin_SURULMEZ(seans_ortami, monkeypatch, kume):
    """Aynı aparatın kapıyı GERÇEKTEN çalıştırdığının kanıtı (yukarıdaki 200 'kapı yok' demek değil) — HER STM
    bobin kümesinde (yalnız 6–7 dahil)."""
    api, istemci, hc = seans_ortami
    uyumlu, sebep = _karar(ESKI_BANNER)
    assert uyumlu is False
    monkeypatch.setattr(api.state, "core", _Cekirdek(uyumlu, sebep), raising=False)
    r = istemci.post("/api/session/start", json={**_GOVDE, "coil_ids": kume})
    assert r.status_code == 409, f"{kume}: {r.status_code} {r.text[:200]}"
    assert hc.baslatilan == [], f"uyumsuz kartta bobin sürülmeye çalışıldı: {hc.baslatilan}"


# ── banner → karar zinciri: GERÇEK _handle_stm_line ──────────────────────────


@pytest.fixture
def cekirdek():
    """Seri port AÇMAYAN `HeadlessCore.__new__` çekirdeği; olay yayını ve bağlantı bayrağı kaydedilir."""
    import logging
    import threading

    import headless_core as hcm

    c = hcm.HeadlessCore.__new__(hcm.HeadlessCore)
    c.logger = logging.getLogger("test-uyum-davranis")
    c._stm_state_lock = threading.RLock()
    c.stm_kimlik = None
    c.stm_uyumlu = None
    c.stm_uyumsuzluk_sebebi = ""
    c.baglanti = []
    c.olaylar = []
    c._set_stm_connected = lambda v: c.baglanti.append(v)
    c._publish_event = lambda tur, veri=None, **k: c.olaylar.append((tur, veri))
    return c


@pytest.mark.parametrize(
    ("banner", "beklenen"),
    [(ESKI_BANNER, False), (YENI_BANNER, True), (SAHA_BANNER, True), (BOZUK_BANNER, None)],
    ids=["eski_5ch", "repo_7ch", "SAHA_Y7", "bozuk"],
)
def test_KRITIK_banner_satiri_GERCEK_isleyiciden_UYUM_kararina_ulasir(cekirdek, banner, beklenen):
    cekirdek._handle_stm_line(banner)
    assert cekirdek.stm_uyumlu is beklenen, (
        f"{banner!r} → stm_uyumlu {cekirdek.stm_uyumlu!r} (beklenen {beklenen!r}) — banner kararı okuyucuya BAĞLI DEĞİL"
    )
    assert True in cekirdek.baglanti, "STM_READY bağlantı bayrağını kaldırmadı"
    if beklenen is False:
        assert "5" in cekirdek.stm_uyumsuzluk_sebebi and "7" in cekirdek.stm_uyumsuzluk_sebebi, (
            cekirdek.stm_uyumsuzluk_sebebi
        )

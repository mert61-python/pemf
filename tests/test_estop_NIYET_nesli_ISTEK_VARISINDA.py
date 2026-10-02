# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.81 · Y4 (1-C bağımsız inceleme i1-F2 + i1-F1 notu) — START niyeti isteğin VARIŞ anındaki sürüş neslini taşır.

ÖLÇÜLEN KUSURLAR (c5b3c04 + F1 düzeltmesi sonrası):
  * i1-F2: `/api/coil/batch` niyet nesli TAŞIMIYORDU (yalnız mandal). Listede ESP bobini STM bobinlerinden önceyse
    ESP yayını (saniyeler) sürerken gelen E-stop + Sıfırla'dan SONRA kalan STM bobinleri E-stop ÖNCESİ niyetle
    sürülüyordu (i1: 3 koşu × 30/30). Tasarım belgesinin "elle yollarda niyet ile sürüş arasında await yok" öncülü
    batch için yanlıştı.
  * i1-F1 notu ([ÇIKARIM] → burada ÖLÇÜLÜR): nesil handler GİRİŞİNDE alınıyordu; FastAPI gövdeyi (JSON, landmark
    görüntüsü) handler'dan ÖNCE okur. Mandallıyken GÖNDERİLMİŞ bir START'ın gövdesi Sıfırla'dan SONRA biterse handler
    yeni nesli alıp sürer — Y4 "mandal kuruluyken hiçbir START kabul edilmez".

DÜZELTME: `api_server._SurusNiyetiVarisDamgasi` (en dıştaki saf ASGI ara katmanı) her isteği, VARIŞ anındaki nesille
`estop_mandali.surus_baglami` içinde koşturur; `HardwareController` ve `_esp_start_yayinla` bu damgayı kilit altında
denetler, uçlar `estop_mandali.niyet_nesli()` ile aynı damgayı okur.

KAPI: gövde bir `threading.Event`'te BEKLETİLİR (TestClient gövdeyi uygulama `receive()` çağırınca okur → ara katman
damgası gövdeden önce alınır). Sıra: E-stop (mandal) → START isteği VARIR → gövde okunurken Sıfırla → gövde biter.
Uçlar: tekil STM, batch STM, legacy `start_coil` / `start_all_coils`, seans başlatma, AI Pro `/start` (+ ardından
`/frame`), AI (Auto) landmark. Her kol 30 deneme; ölçüt donanıma GİDEN duty>0 paket + çalışan bobin (HTTP değil);
409 yanıtının NEDENİ de doğrulanır (gövde ayrıştırma hatasıyla sahte yeşil olmasın). KARŞIT: aynı akışlı gövdeli
istek Sıfırla'dan SONRA varırsa sürer (aparat sürebiliyor).
"""

from __future__ import annotations

import base64
import json
import threading
import types
import urllib.parse

import ai_pro_aparati as ap
import numpy as np
import pytest

DENEME = 30
_SIFIRLA = "/api/hardware/estop_mandali/sifirla"


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


def _ihlal(o, sonra: int) -> bool:
    return bool(ap.surus_paketleri(o, sonra)) or bool(ap.calisan(o))


def _temizle(o):
    o.c.post("/api/session/stop")
    o.c.post("/api/ai/pro/stop")
    ap.mandali_sifirla(o.c)
    o.hc.stop_all_coils()


# ── i1-F2: batch, ESP yayını sürerken E-stop + Sıfırla ─────────────────────────────────────────────────────────────
def _batch_tur(o, monkeypatch, *, sifirla: bool):
    """Bir deneme: batch [8, 1, 2] START; bobin 8'in ESP yayını SÜRERKEN E-stop (+ isteğe bağlı Sıfırla)."""
    ap.mandali_sifirla(o.c)
    o.hc.stop_all_coils()
    gelen, birak = threading.Event(), threading.Event()

    def _yayin(topic, payload):
        if str(payload.get("command")) == "start" and not birak.is_set():
            gelen.set()
            assert birak.wait(10), "aparat: ESP START yayını serbest bırakılmadı"
        o.yayin.append((topic, dict(payload)))
        return True

    monkeypatch.setattr(o.api, "_mqtt_publish", _yayin)
    kutu: dict = {}
    t = threading.Thread(
        target=lambda: kutu.update(
            r=o.c.post(
                "/api/coil/batch",
                json={"coil_ids": [8, 1, 2], "start": True, "freq": 100, "duty": 40, "phase": 0, "duration": 60},
            )
        ),
        daemon=True,
    )
    t.start()
    assert gelen.wait(10), "aparat: bobin 8 ESP START yayını başlamadı"
    o.api._emergency_stop_all("manual")
    sonra = ap.paket_sayisi(o)
    if sifirla:
        assert o.c.post(_SIFIRLA).status_code == 200
    birak.set()
    t.join(15)
    assert not t.is_alive(), "aparat: batch isteği bitmedi"
    return sonra, kutu


def test_KRITIK_batch_ESP_yayini_SURERKEN_estop_SIFIRLA_kalan_STM_bobinleri_ESKI_niyetle_SURULMEZ_N30(o, monkeypatch):
    monkeypatch.setenv("PEMF_ESP_ENABLED", "1")
    ihlal = 0
    ornek = None
    for _ in range(DENEME):
        sonra, _k = _batch_tur(o, monkeypatch, sifirla=True)
        bu = _ihlal(o, sonra)
        ihlal += bu
        if bu and ornek is None:
            ornek = (ap.surus_paketleri(o, sonra)[:1], ap.calisan(o))
    o.hc.stop_all_coils()
    assert ihlal == 0, (
        f"{DENEME} denemenin {ihlal}'inde E-stop ÖNCESİ batch niyeti, E-stop + Sıfırla'dan SONRA STM bobinlerini "
        f"sürdü (ilk örnek duty/çalışan: {ornek})"
    )


def test_KARSIT_batch_sifirla_YOKKEN_kalan_bobinler_REDDEDILIR_bobin8_TELAFI_STOP(o, monkeypatch):
    monkeypatch.setenv("PEMF_ESP_ENABLED", "1")
    sonra, _k = _batch_tur(o, monkeypatch, sifirla=False)
    assert not _ihlal(o, sonra), "karşıt: Sıfırla yokken batch'in kalan bobinleri sürüldü (mandal çalışmıyor)"
    bobin8 = [str(p.get("command")) for tp, p in o.yayin if tp == "pemf/coil/8/control"]
    assert bobin8 and bobin8[-1] == "stop", f"karşıt: bobin 8 telafi STOP'u yok: {bobin8}"


# ── i2-F2b: tekil ESP — giriş denetimi ile ESP yayını ARASINDA gelen durdurma ─────────────────────────────────────
def _tekil_esp_turu(o, monkeypatch, *, durdur: bool):
    """Tekil ESP START'ı girişten geçer; ack kaydında (yayından hemen önce) bekletilir; o sırada (isteğe bağlı)
    seanssız Durdur gelir (nesil++ + ESP STOP); sonra yayın sürer. → bobin 8 için yayınlanan komut sırası."""
    ap.mandali_sifirla(o.c)
    geldi, birak = threading.Event(), threading.Event()
    gercek_kayit = o.api._register_ack

    def _bekleyen_kayit(cid):
        geldi.set()
        assert birak.wait(10), "aparat: ack kaydı serbest bırakılmadı"
        return gercek_kayit(cid)

    monkeypatch.setattr(o.api, "_register_ack", _bekleyen_kayit)
    y0 = len(o.yayin)
    kutu: dict = {}
    t = threading.Thread(
        target=lambda: kutu.update(
            r=o.c.post("/api/coil/8/control", json={"start": True, "freq": 100, "duty": 40, "phase": 0, "duration": 60})
        ),
        daemon=True,
    )
    t.start()
    assert geldi.wait(10), "aparat: tekil ESP START girişten geçmedi"
    if durdur:
        assert o.c.post("/api/session/stop").status_code == 200  # seanssız Durdur: nesil++ + ESP STOP
    birak.set()
    t.join(15)
    assert not t.is_alive(), "aparat: tekil ESP isteği bitmedi"
    monkeypatch.setattr(o.api, "_register_ack", gercek_kayit)
    return [str(p.get("command")) for tp, p in o.yayin[y0:] if tp == "pemf/coil/8/control"]


def test_KRITIK_tekil_ESP_giris_ile_yayin_ARASINDA_durdurma_gelirse_START_YAYINLANMAZ_N30(o, monkeypatch):
    """i2-F2b: `_esp_start_yayinla` nesli iş parçacığı BAŞLARKEN okuyordu → giriş ile yayın arasında gelen seanssız
    Durdur'dan SONRA START yine yayınlanıyordu (telde [stop, start]). Artık isteğin varış damgasını taşır."""
    monkeypatch.setenv("PEMF_ESP_ENABLED", "1")
    ihlal = 0
    ornek = None
    for _ in range(DENEME):
        komutlar = _tekil_esp_turu(o, monkeypatch, durdur=True)
        bu = "stop" in komutlar and komutlar[-1] == "start"
        ihlal += bu
        if bu and ornek is None:
            ornek = komutlar
    assert ihlal == 0, (
        f"{DENEME} denemenin {ihlal}'inde Durdur'dan SONRA uçuştaki tekil ESP START'ı yayınlandı (telde son komut "
        f"START; örnek {ornek})"
    )


def test_KARSIT_tekil_ESP_durdurma_YOKKEN_START_yayinlanir(o, monkeypatch):
    monkeypatch.setenv("PEMF_ESP_ENABLED", "1")
    komutlar = _tekil_esp_turu(o, monkeypatch, durdur=False)
    assert komutlar == ["start"], f"aparat: durdurmasız tekil ESP START yayınlanmadı: {komutlar}"


# ── Varış anı: gövde Sıfırla'dan SONRA biten, mandallıyken VARMIŞ START ────────────────────────────────────────────
def _bekleyen_govde(veri: bytes, girdi: threading.Event, engel: threading.Event):
    """Gövde okunmaya BAŞLAYINCA `girdi` (ara katman damgası bu andan ÖNCE alınmıştır), `engel` kalkınca gövde biter."""

    def _uret():
        girdi.set()
        assert engel.wait(10), "aparat: gövde engeli 10 sn'de kalkmadı"
        yield veri

    return _uret()


def _ai_pro_onayi():
    from servers import ai_approval

    rec = ai_approval.create("ai_pro", {"organ_id": 0, "duration_minutes": 5, "model": "kedi"})
    ai_approval.approve(rec["id"], "hekim@test.local")
    return rec["id"]


_JSON = "application/json"
_FORM = "application/x-www-form-urlencoded"
_LANDMARK_GOVDE = urllib.parse.urlencode(
    {"image_base64": base64.b64encode(b"\xff\xd8\xff\xd9").decode(), "auto_adjust": "true"}
)

# (ad, yol, gövde üretici, içerik türü)
UCLAR = [
    (
        "tekil_STM",
        "/api/coil/1/control",
        lambda: {"start": True, "freq": 100, "duty": 40, "phase": 0, "duration": 60},
        _JSON,
    ),
    (
        "batch_STM",
        "/api/coil/batch",
        lambda: {"coil_ids": [1, 2], "start": True, "freq": 100, "duty": 40, "phase": 0, "duration": 60},
        _JSON,
    ),
    (
        "legacy_start_coil",
        "/api/hardware/command",
        lambda: {"command": "start_coil", "params": {"coil_id": 1, "freq": 100, "duty": 40, "phase": 0, "duration": 1}},
        _JSON,
    ),
    (
        "legacy_start_all",
        "/api/hardware/command",
        lambda: {"command": "start_all_coils", "params": {"freq": 100, "duty": 40, "phase": 0, "duration": 1}},
        _JSON,
    ),
    (
        "seans",
        "/api/session/start",
        lambda: {"coil_ids": [1, 2], "frequency": 100, "duty": 40, "phase": 0, "duration_minutes": 5, "mode": "Manuel"},
        _JSON,
    ),
    ("ai_pro_start", "/api/ai/pro/start", lambda: {"proposal_id": _ai_pro_onayi(), "client_id": ""}, _JSON),
    ("landmark_ai_auto", "/api/ai/vision/landmark", None, _FORM),
]


class _T:
    def __init__(self, a):
        self.a = np.asarray(a, dtype=float)

    def cpu(self):
        return self

    def numpy(self):
        return self.a

    def __getitem__(self, i):
        return _T(self.a[i])

    def __len__(self):
        return len(self.a)


class _Kutular:
    def __len__(self):
        return 1

    def __getitem__(self, i):
        return types.SimpleNamespace(xyxy=_T([[0.0, 0.0, 60.0, 60.0]]))


class _SahteLandmarkModeli:
    def predict(self, *a, **k):
        kp = np.array([[10.0 + (i % 8) * 5.0, 10.0 + (i // 8) * 5.0] for i in range(48)])
        return [types.SimpleNamespace(keypoints=types.SimpleNamespace(xy=_T([kp]), conf=None), boxes=_Kutular())]


@pytest.fixture
def lm(o, monkeypatch):
    from servers import auth

    import ai_hub.cat_landmark.inference_cat_landmark as inf

    monkeypatch.setattr(o.air, "_get_or_load_model", lambda ad, yukleyici: _SahteLandmarkModeli())
    monkeypatch.setattr(inf, "compute_fgs", lambda kp: {"fgs_total": 2, "pain_level": "Mild", "action_units": {}})
    monkeypatch.setattr(auth, "is_local_request", lambda *a, **k: True)
    return o


def _govde(ad, uretec) -> bytes:
    if ad == "landmark_ai_auto":
        return _LANDMARK_GOVDE.encode()
    return json.dumps(uretec()).encode()


def _surdu_mu(o, ad, sonra: int) -> bool:
    """AI Pro `/start` kendisi bobin sürmez (döngü aparatta no-op): seans doğduysa ardından gelen kare sürer."""
    if ad == "ai_pro_start":
        ap.kare(o)
    return _ihlal(o, sonra)


@pytest.mark.parametrize("ad,yol,uretec,tur", UCLAR, ids=[u[0] for u in UCLAR])
def test_KRITIK_mandalliyken_VARAN_START_govdesi_SIFIRLAdan_sonra_bitse_de_SURULMEZ_N30(lm, ad, yol, uretec, tur):
    o = lm
    ihlal = yanlis_neden = 0
    kodlar: list = []
    ornek = None
    for _ in range(DENEME):
        _temizle(o)
        o.api._emergency_stop_all("manual")  # mandal KURULU
        sonra = ap.paket_sayisi(o)
        girdi, engel = threading.Event(), threading.Event()
        veri = _govde(ad, uretec)
        kutu: dict = {}

        def _gonder():
            try:
                kutu["r"] = o.c.post(yol, content=_bekleyen_govde(veri, girdi, engel), headers={"content-type": tur})
            except Exception as e:  # pragma: no cover - aparat tanısı
                kutu["hata"] = e

        t = threading.Thread(target=_gonder, daemon=True, name=f"test-varis-{ad}")
        t.start()
        assert girdi.wait(10), f"aparat: {ad} isteği gövde okumasına ulaşmadı"
        assert o.c.post(_SIFIRLA).status_code == 200  # operatörün Sıfırla'sı — istek VARDIKTAN SONRA
        engel.set()
        t.join(15)
        assert not t.is_alive(), f"aparat: {ad} isteği bitmedi"
        assert "r" in kutu, f"aparat: {ad} yanıt yok {kutu.get('hata')!r}"
        r = kutu["r"]
        assert r.status_code != 422, f"aparat: {ad} gövdesi ayrıştırılamadı (sahte yeşil olurdu): {r.text[:200]}"
        kodlar.append(r.status_code)
        bu = _surdu_mu(o, ad, sonra)
        ihlal += bu
        if bu and ornek is None:
            ornek = (r.status_code, r.text[:160], ap.surus_paketleri(o, sonra)[:1], ap.calisan(o))
        # Operatöre DÜRÜST neden: uçlar girişte 409 + "bayat niyet" der (donanım katmanı da reddeder — yalnız ona
        # güvenen bir uç "error"/"success" der; o ayrı bir gerileme). Landmark analiz döner, sürüşü "atlandı" der.
        if ad == "landmark_ai_auto":
            yanlis_neden += r.json().get("hw_status") != "skipped_estop_latched"
        else:
            yanlis_neden += r.status_code != 409 or r.json().get("detail") != o.api.estop_mandali.NESIL_MESAJI
    _temizle(o)
    assert ihlal == 0 and yanlis_neden == 0, (
        f"{ad}: {DENEME} denemenin {ihlal}'inde MANDALLIYKEN VARAN START, gövdesi Sıfırla'dan sonra bitince donanımı "
        f"sürdü (ilk örnek: {ornek}); {yanlis_neden}'inde yanıt nedeni yanlış; HTTP kodları "
        f"{ {k: kodlar.count(k) for k in set(kodlar)} }"
    )


@pytest.mark.parametrize("ad,yol,uretec,tur", UCLAR, ids=[u[0] for u in UCLAR])
def test_KARSIT_SIFIRLAdan_SONRA_varan_ayni_akisli_START_SURER(lm, ad, yol, uretec, tur):
    o = lm
    _temizle(o)
    o.api._emergency_stop_all("manual")
    assert o.c.post(_SIFIRLA).status_code == 200
    sonra = ap.paket_sayisi(o)
    girdi, engel = threading.Event(), threading.Event()
    engel.set()
    r = o.c.post(yol, content=_bekleyen_govde(_govde(ad, uretec), girdi, engel), headers={"content-type": tur})
    assert r.status_code == 200, f"aparat: {ad} Sıfırla sonrası yeni istek reddedildi: {r.text[:200]}"
    assert _surdu_mu(o, ad, sonra), f"aparat: {ad} Sıfırla sonrası yeni istek donanımı sürmedi ({r.text[:160]})"
    _temizle(o)


def test_KRITIK_niyet_nesli_BAGLAMDAN_yoksa_SIMDIKI():
    from utils import estop_mandali as em

    n = em.nesil()
    assert em.niyet_nesli() == n
    with em.surus_baglami(n - 7):
        assert em.niyet_nesli() == n - 7
    assert em.niyet_nesli() == n

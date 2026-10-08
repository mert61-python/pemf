# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""TEST YARDIMCISI — GERÇEK onay akışıyla AI Pro seansı + GERÇEK `/frame` + GERÇEK `HardwareController`. ⚠️ pytest TOPLAMAZ.

NEDEN (D1.80 · D1.81 · D1.E06): AI Pro kapıları seansı `_active_session`e ELLE `{"mode": "AI Pro"}` yazarak
kuruyordu — `/frame`'in sürüş kapısı tam da bu önek olduğu için o testler önek kapısını ölçemezdi. Bu aparat
seansı ÜRÜNÜN kurduğu gibi kurar: `ai_approval.create → approve → POST /api/ai/pro/start` (onay tüketimi, mühür).

Sahte olan yalnız: görüntü çözümü, lokalizasyon (hızlı, sabit hedef), doz modeli (`_predict_and_drive`; istenirse bir
`threading.Event`te BLOKLANIR — tahmin penceresi zorlanır), sunucu kamerası döngüsü (yalnız `/frame` kollarında no-op),
DB (tmp), yayın/bildirim/WS (kaydedilir). Sürüş (`_drive_coils_ai_pro`), donanım kontrolcüsü ve paket kurucusu GERÇEK.
"""

from __future__ import annotations

import asyncio
import base64
import sys
import threading
import time
import types

import numpy as np

D_AI = 0.30  # sahte doz modelinin bobin başı duty oranı (seans duty'lerinden ayırt edilir)

# ⚠️ TEST İSTEMCİSİ OLAY DÖNGÜSÜ (1-C, ölçüldü): TestClient her istekte AYRI bir iş parçacığında YENİ bir asyncio
# döngüsü açıp kapatır; bu aparatın kapıları aynı istemciye birden çok iş parçacığından EŞZAMANLI istek atar.
# Windows'ta (gömülü Python 3.10.2) varsayılan Proactor döngüsünde bu desen CPython'un kendi uyarısını üretiyordu —
# "<_overlapped.Overlapped …> still has pending operation at deallocation, the process may crash"
# (`asyncio\windows_events.py`, `select`) — ve test süreci ara sıra GC sırasında "Windows fatal exception: access
# violation" ile ÖLÜYORDU (bir günde ≥9 koşu: tam süit, mutasyon ve inceleme koşuları; çökme izi hep TestClient portal
# iş parçacığında "Garbage-collecting"). Aynı kapılar 10 koşuda Proactor ile 3 uyarı, Selector ile 0 uyarı / 0 çökme.
# Ürün (uvicorn) tek ve uzun ömürlü döngüde çalışır; istek başına döngü açıp kapatma yalnız TestClient'a özgüdür →
# yalnız bu aparatın istemcisi Selector döngüsüyle kurulur (ürün kodu ve süitin geri kalanı değişmez; Linux'ta zaten
# Selector).
ISTEMCI_SECENEKLERI = {"loop_factory": asyncio.SelectorEventLoop} if sys.platform == "win32" else {}


def istemci(app):
    """Eşzamanlı istek atan kapılar için TestClient (bkz. ISTEMCI_SECENEKLERI)."""
    from fastapi.testclient import TestClient

    return TestClient(app, backend_options=dict(ISTEMCI_SECENEKLERI))


class _SahteAlanKaydi:
    def seans_basladi(self, *a, **k):
        return None

    def seans_bitti(self, *a, **k):
        return None


def mandal_modulu():
    try:
        from utils import estop_mandali
    except ImportError:  # önce-kırmızı: modül henüz yok
        return None
    return estop_mandali


def mandali_sifirla(c) -> None:
    """Operatörün 'Sıfırla' eylemi (uç yoksa — önce-kırmızı — sessiz)."""
    c.post("/api/hardware/estop_mandali/sifirla", json={"onay": True})


DONGU_IP_ADI = "ai-pro-dongu"


def dongu_bitir(air, sure: float = 10.0) -> int:
    """O-A2-K.1: GERÇEK AI Pro döngüsü (`ai-pro-dongu` iş parçacığı) durdurulur ve BİTMESİ beklenir; yaşayan sayısını döndürür.

    `_ai_loop_active` bayrağını beklemek yetmez — bayrak durdurmada hemen iner, iş parçacığı bir tur daha yaşar ve kapanışında
    (`efield_live.set_context([])` + `seans_bitti`) süreç geneli durumu SONRAKİ testin içinde değiştirir (2-A incelemesi ölçtü:
    E07 bağlam kapısı zamanlamaya bağlı kırmızı). Çağrı testin yıkımında, monkeypatch geri alınmadan ÖNCE yapılır (kapanış
    yan etkisi testin kendi yamalı ortamında kalır). Conftest gözcüsü `_ai_pro_dongusu_sizmaz` kaçağı KIRMIZI yapar."""
    canli = [t for t in threading.enumerate() if t.name == DONGU_IP_ADI and t.is_alive()]
    if canli:
        air._ai_loop_active = False
    for t in canli:
        t.join(timeout=sure)
    return sum(t.is_alive() for t in canli)


def kur(monkeypatch, tmp_path, *, dongu_noop: bool = True):
    """Ortamı kurar ve bir isim alanı döner. Çağıran `with gercek_hc()` bloğunu kendisi açar ve `ns.hc`yi atar."""
    from database.treatment_history_db import TreatmentHistoryDB
    from servers import ai_approval, live_state
    from servers import ai_router as air
    from servers import api_server as api
    from servers import coil_run_tracker as crt

    kok = tmp_path / "gecmis"
    kok.mkdir(exist_ok=True)
    db = TreatmentHistoryDB(kok)
    monkeypatch.setattr(api, "_get_treatment_db", lambda: db)
    monkeypatch.setattr(crt, "_treatment_db_getter", lambda: db)
    monkeypatch.setattr(api, "_kayit_db_hazir", lambda: (True, ""))
    bildirim: list = []
    monkeypatch.setattr(api, "_push_notification", lambda m, t="info": bildirim.append((m, t)))
    ws: list = []
    monkeypatch.setattr(api, "_ws_broadcast_sync", ws.append)
    monkeypatch.setattr(live_state, "_ws_broadcast_sync", ws.append)
    yayin: list = []

    def _yayin(topic, payload):
        yayin.append((topic, dict(payload)))
        return True

    monkeypatch.setattr(api, "_mqtt_publish", _yayin)
    monkeypatch.setattr(api, "_estop_cloud_mirror", lambda *a, **k: None)
    monkeypatch.setattr(api, "_estop_ack_watch", lambda *a, **k: None)
    monkeypatch.setattr(api, "_start_ack_izle_arka_planda", lambda *a, **k: None)
    monkeypatch.setattr(api, "_broker_reachable", lambda timeout=0.3: False)
    monkeypatch.setattr(api, "_seans_alan", _SahteAlanKaydi())
    monkeypatch.setattr(api.state, "core", types.SimpleNamespace(stm_uyumlu=None))
    # TestClient'ın istemcisi ("testclient") yerel sayılmaz → hız sınırı (dakikada N istek) ≥30 denemelik yarış
    # kollarını 429'a düşürür. Sınırlayıcı bu kapıların konusu değil: kapatılır.
    monkeypatch.setattr(api, "_RL_REMOTE_MAX", 0)
    live_state.stm_komut_kabulu_bildir()
    ai_approval.clear()
    # AI Pro globalleri: ürün yazar, monkeypatch test sonunda ESKİ değerlere döndürür.
    for ad in (
        "_ai_loop_active",
        "_ai_owner_client",
        "_ai_organ_id",
        "_ai_duration_min",
        "_ai_started_at",
        "_ai_hedef_modeli",
        "_ai_relocalize",
        "_ai_thread",
    ):
        monkeypatch.setattr(air, ad, getattr(air, ad))
    monkeypatch.setattr(air, "_ai_loop_active", False)
    monkeypatch.setattr(air, "_ai_owner_client", "")
    monkeypatch.setattr(air, "_ai_organ_cache", dict(air._ai_organ_cache))

    async def _decode(*a, **k):
        return np.zeros((8, 8, 3), dtype=np.uint8)

    monkeypatch.setattr(air, "_decode_image", _decode)
    monkeypatch.setattr(air, "_localize_organ", lambda f, o: (True, 10.0, 20.0, 30.0, 0.9, None, True))
    tahmin = types.SimpleNamespace(engel=None, girdi=threading.Event(), sayi=0)

    def _tahmin(x, y, z, o):
        tahmin.sayi += 1
        tahmin.girdi.set()
        if tahmin.engel is not None:
            assert tahmin.engel.wait(10), "aparat: tahmin engeli 10 sn'de kalkmadı"
        return [D_AI] * 7, [0.0] * 7, 1.0

    monkeypatch.setattr(air, "_predict_and_drive", _tahmin)
    if dongu_noop:
        monkeypatch.setattr(air, "_ai_pro_loop", lambda *a, **k: None)
    m = mandal_modulu()
    if m is not None:
        m.sifirla("test-izolasyon")
    with api._session_lock:
        eski = dict(api._active_session)
        api._active_session["is_active"] = False

    def _geri():
        dongu_bitir(air)  # O-A2-K.1: döngünün kapanışı BU testin yamalı ortamında olsun (sonrakine sızmasın)
        if m is not None:
            m.sifirla("test-izolasyon")
        with api._session_lock:
            api._active_session.clear()
            api._active_session.update(eski)
        ai_approval.clear()
        live_state.stm_komut_kabulu_bildir()

    return types.SimpleNamespace(
        api=api,
        air=air,
        ls=live_state,
        db=db,
        c=istemci(api.app),
        ws=ws,
        yayin=yayin,
        bildirim=bildirim,
        tahmin=tahmin,
        geri=_geri,
        hc=None,
    )


def muhurlu_seans_yaz(apis, *, sure_dk: int = 20, model: str = "kedi", baslangic_mono=None, coil_ids=None, **ek):
    """Oturuma AI Pro MÜHRÜNÜ yaz — `api_server.start_ai_session(tur="ai_pro", ...)`ın yazdığı alanlarla AYNI
    (D1.80/D1.81: `/frame` yalnız tür + onay + nesil + model + mühür süresi taşıyan seansta sürer). Onay akışını
    koşmaya gerek olmayan (yalnız `/frame` kapısının BAŞKA bir özelliğini ölçen) testler için. Ek alanlar `ek` ile."""
    from utils import estop_mandali

    # D1.60 (A-16): mühür ONAYLANAN hedefi taşır (`start_ai_session(onay_hedefi=…)` gibi). Verilmezse o anki seçili
    # hedef — testler hedefi mühürden ÖNCE kurar; sonradan değiştiren mühür dışına çıkar (sürülmez).
    hedef = ek.pop("onay_hedefi") if "onay_hedefi" in ek else _secili_hedef()
    with apis._session_lock:
        apis._active_session.clear()
        apis._active_session.update(
            {
                "is_active": True,
                "session_id": "test-ai-pro",
                "mode": "AI Pro · Kedi Organ",
                "tur": "ai_pro",
                "onay_kimligi": "test-onay",
                "surus_nesli": estop_mandali.nesil(),
                "model": model,
                "duration_minutes": int(sure_dk),
                "start_mono": time.monotonic() if baslangic_mono is None else baslangic_mono,
                "coil_ids": list(coil_ids) if coil_ids is not None else list(range(1, 8)),
                "onay_hedefi": hedef,
                **ek,
            }
        )


def _secili_hedef():
    from servers import ai_router as air

    return air._ai_organ_id


def onayli_baslat(o, *, sure_dk: int = 5, organ: int = 0, model: str = "kedi", istemci: str = ""):
    """GERÇEK onay akışı: öner kaydı → hekim onayı → `/api/ai/pro/start`. → (proposal_id, yanıt)."""
    from servers import ai_approval

    rec = ai_approval.create("ai_pro", {"organ_id": organ, "duration_minutes": sure_dk, "model": model})
    ai_approval.approve(rec["id"], "hekim@test.local")
    r = o.c.post("/api/ai/pro/start", json={"proposal_id": rec["id"], "client_id": istemci})
    return rec["id"], r


def kare(o, istemci: str = ""):
    img = base64.b64encode(b"\xff\xd8\xff\xd9").decode()
    return o.c.post("/api/ai/ai_pro/frame", data={"image_base64": img, "client_id": istemci})


def kare_arka_planda(o, istemci: str = ""):
    """`/frame`'i ayrı iş parçacığında başlatır; (iş parçacığı, sonuç kutusu) döner."""
    kutu: dict = {}

    def _calis():
        try:
            kutu["yanit"] = kare(o, istemci)
        except Exception as e:  # pragma: no cover - aparat tanısı
            kutu["hata"] = e

    t = threading.Thread(target=_calis, name="test-frame", daemon=True)
    t.start()
    return t, kutu


def paket_sayisi(o) -> int:
    return len(o.hc.core._hw_send_queue.paketler)


def surus_paketleri(o, once: int) -> list:
    """`once`tan sonra donanıma giden ve en az bir bobini süren (duty>0) paketlerin duty dizileri."""
    from kayitci_donanim import paket_coz

    sonuc = []
    for p in o.hc.core._hw_send_queue.paketler[once:]:
        d = tuple(paket_coz(p)[0])
        if any(x > 0 for x in d):
            sonuc.append(d)
    return sonuc


def calisan(o) -> list:
    return [i for i, s in o.hc.coils_state.items() if s["is_running"]]


def bekle(kosul, sure: float = 5.0, aralik: float = 0.01) -> bool:
    bitis = time.monotonic() + sure
    while time.monotonic() < bitis:
        if kosul():
            return True
        time.sleep(aralik)
    return bool(kosul())

# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""HAZIRLIK UCU MUTASYON KİLİDİ — aktif seansta onaylı hedef DEĞİŞTİRİLEBİLİYORDU (2026-09-08).

ÖLÇÜLEN DURUM: `/api/ai/pro/hazirlik/baslat` üç global mutasyonu (`_ai_organ_id`,
`_ai_relocalize`, cache `localized=False`) `_ai_loop_lock` DIŞINDA ve `_ai_loop_active`
kontrolünden ÖNCE yapıyordu; sahiplik (`_ai_kare_yabanci`) kapısı da yoktu. Sonra kilide girip
"Seans zaten aktif" ile SESSİZ BAŞARI dönüyordu — yani mutasyon kalıcı oluyordu.

Sonuç: onaylı bir AI Pro seansı sürerken (mühürde organ 2) herhangi bir istemci bu auth-muaf uca
`{"organ_id": 5}` gönderirse `_ai_pro_loop` bir sonraki turda `need_localize` koşulunu
(organ_id != cache) sağlar, organ 5'i lokalize eder ve bobinleri ONAYLANMAYAN organa sürer.
`/api/ai/pro/organ` ucunda tam bu senaryo için 403 kapısı VAR; hazırlık ucunda yoktu.

Bu, 2026-08-06 sahip kararının ("hekim önce ne uygulanacağını görür, sonra onaylar" — organ ve
süre GÖVDEDEN değil MÜHÜRDEN okunur) yan kapıdan aşılmasıydı.

DÜZELTME SÖZLEŞMESİ (plan kararı #21): aktif seans/hazırlık sürerken hedef değişimi SESSİZ
BAŞARI değil 409'dur. 200 dönmek ayrıca panel için zararlıydı: `AiProPanel` yanıtı truthy görüp
`setHazirlik(true)` yapıyor ve hiç gelmeyecek bir önizleme için 120 sn bekliyordu (B3 dersi).
"""

import numpy as np
import pytest
from fastapi.testclient import TestClient


class _FakeCap:
    def __init__(self, *a):
        self._open = True

    def isOpened(self):  # noqa: N802  (OpenCV adı)
        return True

    def read(self):
        return True, np.zeros((8, 8, 3), dtype=np.uint8)

    def release(self):
        self._open = False


@pytest.fixture()
def hz_env(monkeypatch):
    """Hazırlık ucunu HTTP üzerinden çağıran ortam; seans durumu testin kontrolünde."""
    import servers.ai_router as air
    import servers.api_server as apis

    snap_cache = dict(air._ai_organ_cache)
    snap_oid = air._ai_organ_id
    snap_owner = air._ai_owner_client
    snap_reloc = air._ai_relocalize
    with apis._session_lock:
        sess_snap = dict(apis._active_session)

    monkeypatch.setattr(air.cv2, "VideoCapture", _FakeCap)
    monkeypatch.setattr(air, "_get_or_load_kedi", lambda: None)
    monkeypatch.setattr(air, "_get_or_load_catorgan", lambda: None)
    monkeypatch.setattr(air, "_localize_organ", lambda f, o: air._extract_organ_target({}, o, None))
    monkeypatch.setattr(air, "_drive_coils_ai_pro", lambda D, P: None)

    air._ai_loop_active = False
    air._ai_hazirlik_active = False
    air._ai_relocalize = False
    air._ai_organ_id = 2
    air._ai_organ_cache.update({"at": 0.0, "organ_id": 2, "localized": True, "kedi_var": True, "reliability": 0.9})
    with apis._session_lock:
        apis._active_session.clear()
        apis._active_session.update({"is_active": False, "mode": "Sistem Hazır"})

    yield air, apis, TestClient(apis.app)

    air._ai_hazirlik_durdur_ic()
    air._ai_loop_active = False
    air._ai_organ_cache.clear()
    air._ai_organ_cache.update(snap_cache)
    air._ai_organ_id = snap_oid
    air._ai_owner_client = snap_owner
    air._ai_relocalize = snap_reloc
    with apis._session_lock:
        apis._active_session.clear()
        apis._active_session.update(sess_snap)


def _seansi_baslat(air, apis, *, sahip: str = "SAHIP"):
    """Onaylı bir AI Pro seansı sürüyormuş gibi durum kur (loop thread'i YOK)."""
    air._ai_loop_active = True
    air._ai_owner_client = sahip
    with apis._session_lock:
        apis._active_session.clear()
        apis._active_session.update({"is_active": True, "session_id": "ai_1", "mode": "AI Pro"})


def test_KRITIK_aktif_seansta_hazirlik_ucu_ONAYLI_HEDEFI_degistiremez(hz_env):
    """Kusurun kendisi. MUTASYON KANITI: `ai_pro_hazirlik_baslat` içindeki organ/relocalize/cache
    yazımlarını `_ai_loop_lock` bloğunun ÖNÜNE taşıyın → bu test KIRMIZI olur."""
    air, apis, client = hz_env
    _seansi_baslat(air, apis)

    r = client.post("/api/ai/pro/hazirlik/baslat", json={"organ_id": 5, "client_id": "SAHIP"})

    assert r.status_code == 409, (
        f"aktif seansta hedef değişimi {r.status_code} döndü — sessiz başarı, mutasyonun kalıcı "
        "olduğunu gizler ve panel hiç gelmeyecek önizlemeyi 120 sn bekler"
    )
    assert air._ai_organ_id == 2, (
        f"ONAYLI seans sürerken hedef organ {air._ai_organ_id} olarak değişti — bobinler mühürde "
        "onaylanmayan organa sürülür (2026-08-06 mühür kararının yan kapıdan aşılması)"
    )
    assert air._ai_organ_cache["localized"] is True, (
        "aktif seansın lokalizasyon cache'i geçersiz kılındı — sürüş bir tur boyunca durur"
    )
    assert air._ai_relocalize is False, "aktif seansta yeniden-lokalizasyon dışarıdan zorlandı"
    assert air._ai_hazirlik_active is False, "seans aktifken önizleme başladı (çift VideoCapture riski)"


def test_KRITIK_aktif_seansta_YABANCI_istemci_403_alir(hz_env):
    """`/api/ai/pro/organ` ucundaki B1 sahiplik kapısının paritesi: seansın sahibi olmayan
    istemci hazırlık ucundan da hedefe dokunamaz."""
    air, apis, client = hz_env
    _seansi_baslat(air, apis, sahip="SAHIP")

    r = client.post("/api/ai/pro/hazirlik/baslat", json={"organ_id": 5, "client_id": "YABANCI"})

    assert r.status_code == 403, f"yabancı istemci hazırlık ucundan hedefe dokunabildi ({r.status_code})"
    assert air._ai_organ_id == 2, "yabancı istemci onaylı hedefi değiştirdi"


def test_KARSIT_KANIT_seans_YOKKEN_hazirlik_hedefi_ayarlar_ve_cache_i_tazeler(hz_env):
    """Karşıt-kanıt: düzeltme "hiçbir zaman değiştirme" mutasyonuna dönüşmemeli. Seans yokken
    hazırlık ucu ESKİ davranışını sürdürür: hedefi ayarlar, bayat lokalizasyonu geçersiz kılar,
    önizlemeyi başlatır (2026-08-25 web kapalı-döngü düzeltmesi)."""
    air, apis, client = hz_env

    r = client.post("/api/ai/pro/hazirlik/baslat", json={"organ_id": 3, "client_id": "PANEL"})

    assert r.status_code == 200, f"seans yokken hazırlık reddedildi ({r.status_code}) — web akışı kırılır"
    assert air._ai_organ_id == 3, "seans yokken seçilen hedef ayarlanmadı — panel yanlış organı lokalize eder"
    assert air._ai_hazirlik_active is True, "önizleme başlamadı — web'de propose 409 döngüsüne geri dönülür"

    # Taze lokalizasyon GERÇEKTEN yapıldı mı: önizleme thread'i `_ai_relocalize` bayrağını hemen
    # tüketir (bayrağın değerine bakmak yarış olurdu) → cache'in YENİ hedefle damgalanmasını ölç.
    import time as _t

    son = _t.time() + 5.0
    while _t.time() < son and air._ai_organ_cache.get("organ_id") != 3:
        _t.sleep(0.05)
    assert air._ai_organ_cache.get("organ_id") == 3, (
        "önizleme yeni hedefi lokalize etmedi (cache eski hedefle damgalı) — panel bayat ölçümden öneri ister"
    )


def test_YAPISAL_hedef_mutasyonu_KILIT_ICINDE_ve_aktiflik_kontrolunden_SONRA(hz_env):
    """Kaynak kapısı: `_ai_organ_id` ataması `with _ai_loop_lock:` bloğundan SONRA gelmeli.
    Davranışsal kapı asıl kanıttır; bu kapı yeniden yazımlarda sıralamanın kazara bozulmasını
    (TOCTOU'nun geri gelmesini) yakalar."""
    from pathlib import Path

    air, _apis, _client = hz_env
    src = Path(air.__file__).read_text(encoding="utf-8")
    i = src.index("def ai_pro_hazirlik_baslat")
    govde = src[i : src.index("\n@ai_router", i + 10)]

    kilit = govde.find("with _ai_loop_lock:")
    atama = govde.find("_ai_organ_id = ")
    assert kilit >= 0, "hazırlık ucu _ai_loop_lock kullanmıyor — TOCTOU (çift VideoCapture) geri geldi"
    assert atama >= 0, "hazırlık ucu hedef organı hiç ayarlamıyor?"
    assert kilit < atama, (
        "hedef organ ataması kilit bloğundan ÖNCE — aktif seans kontrolü yapılmadan mutasyon "
        "uygulanıyor (2026-09-08 kusurunun tam kendisi)"
    )

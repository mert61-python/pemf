# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""SEANS DÖNGÜSÜ LOKALİZASYON AÇILIMI — sunucu-kameralı AI Pro seansı bobin SÜRMÜYORDU (2026-09-08).

ÖLÇÜLEN DURUM (statik + bu dosyanın davranışsal kanıtı): `_extract_organ_target` 2026-08-26'dan
(guven_dokumu / sunum-katmanı XAI) beri 8 eleman döndürüyor. Hazırlık önizlemesi ve mobil
`/ai/ai_pro/frame` yolları sonucu `*l_ek` ile açıyor; SEANS döngüsü 7 isme açıyordu:

    lz, lx, ly, lzz, lrel, lov, lkedi = _localize_organ(frame, _oid)   # 7 hedef ← 8 değer

Python bunu `ValueError: too many values to unpack` ile bitirir; hata döngünün `except Exception`
bloğuna düşer, `localized=False` yazılır ve bobin HİÇ sürülmez. Üstelik `_AI_LOST_STOP_STREAK`
turdan sonra "hedef kaybı" STOP'u yayınlanır — operatöre hedef kaybolmuş gibi görünür, oysa
lokalizasyon hiç çalışmamıştır. Klinikte etkisi: onaylı AI Pro seansı "aktif" görünür ama TEDAVİ
UYGULANMAZ.

NEDEN MEVCUT TESTLER YAKALAMADI: AI Pro süitindeki mock'lar `_localize_organ`ı 6'lı
(test_ai_pro_safety.py:184) ya da 7'li (test_kalan_regression_gaps.py) SAHTE tuple ile
değiştiriyordu — 7 değer 7 isme sorunsuz açılır, kusur maskelenir. Bu dosya sahte uzunluk
KULLANMAZ: tuple'ı GERÇEK `_extract_organ_target` üretir, böylece imza yarın 9 elemana çıksa da
kapı doğru kalır (yapısal çıpa kırılganlığı dersi).

⚠️ Bu dosyanın kapıları ÜRETİM davranışını ölçer: gerçek `_ai_pro_loop` koşar, gerçek tuple akar;
yalnız kamera (cv2), model yükleyicileri, donanım sürüşü ve uyku kabuğu sahtelenir.
"""

import numpy as np
import pytest


class _SahteCv2:
    """`_ai_pro_loop`un dokunduğu asgari OpenCV yüzeyi — GERÇEK kamera açılmaz."""

    INTER_AREA = 3
    IMWRITE_JPEG_QUALITY = 1

    class _Cap:
        def __init__(self, kare):
            self._kare = kare

        def isOpened(self):  # noqa: N802  (OpenCV adı)
            return True

        def read(self):
            return True, self._kare

        def release(self):
            return None

    def __init__(self):
        self._kare = np.zeros((8, 8, 3), dtype=np.uint8)

    def VideoCapture(self, *a, **k):  # noqa: N802  (OpenCV adı)
        return self._Cap(self._kare)

    def imencode(self, *a, **k):
        return True, bytearray(b"jpeg")

    def resize(self, img, *a, **k):
        return img


class _Saat:
    """`time` kabuğu: duvar saati SABİT (yeniden-lokalizasyon aralığı tetiklenmesin),
    `sleep` sayaç düşürür ve sıfırlanınca loop'u kapatır (test asılmaz)."""

    def __init__(self, air, tur: int):
        import time as _t

        self._t = _t
        self._air = air
        self.kalan = int(tur)

    def __getattr__(self, ad):
        return getattr(self._t, ad)

    def time(self):
        return 1_800_000_000.0

    def sleep(self, _sn):
        self.kalan -= 1
        if self.kalan <= 0:
            self._air._ai_loop_active = False


def _gercek_hedef_tuple(air, *, hedef_var: bool):
    """Lokalizasyon tuple'ını ÜRETİM fonksiyonundan üret — uzunluk testte SABİTLENMEZ.

    `_extract_organ_target` cat_organ sonucundan (localized, x, y, z, güven, overlay,
    kedi_var, guven_dokumu) üretir; bu, `_localize_organ`ın üç dönüş yolunun da sözleşmesidir.
    """
    if hedef_var:
        organlar = {
            2: {
                "coord_cabin_cm": [1.0, 2.0, 3.0],
                "reliability": 0.9,
                "reliability_components": {"pose_confidence": 0.9, "calibration_cap": 1.0},
            }
        }
    else:
        organlar = {}
    return air._extract_organ_target(organlar, 2, None)


@pytest.fixture()
def seans_ortami(monkeypatch):
    """Gerçek `_ai_pro_loop`u koşturan ortam; `kos(tur, hedef_var=...)` ile döndürülür."""
    import servers.ai_router as air
    import servers.api_server as apis

    snap_cache = dict(air._ai_organ_cache)
    snap_oid = air._ai_organ_id
    snap_owner = air._ai_owner_client
    with apis._session_lock:
        sess_snap = dict(apis._active_session)

    izler: dict = {"surus": [], "stop": []}
    monkeypatch.setattr(air, "cv2", _SahteCv2())
    monkeypatch.setattr(air, "_get_or_load_kedi", lambda *a, **k: None)
    monkeypatch.setattr(air, "_get_or_load_catorgan", lambda *a, **k: None)
    monkeypatch.setattr(air, "_predict_and_drive", lambda *a, **k: ([0.5] * 7, [0.0] * 7, 1.0))
    monkeypatch.setattr(air, "_drive_coils_ai_pro", lambda D, P: izler["surus"].append((D, P)))
    monkeypatch.setattr(apis, "_stop_session_coils", lambda c=None: izler["stop"].append(list(c or [])))
    monkeypatch.setattr(apis, "_ws_broadcast_sync", lambda *a, **k: None)
    monkeypatch.setattr(apis, "update_live_session_state", lambda *a, **k: None)
    monkeypatch.setattr(apis, "_mqtt_publish", lambda *a, **k: True)
    monkeypatch.setattr(apis, "state", None)  # teardown'daki stop_all_coils yolu no-op
    monkeypatch.setattr(air, "_ai_started_at", 0.0)  # süre-bitişi dalı devre dışı
    monkeypatch.setattr(air, "_ai_relocalize", True)
    monkeypatch.setattr(air, "_ai_organ_id", 2)
    air._ai_organ_cache.update({"at": 0.0, "organ_id": -1, "localized": False, "guven_dokumu": None})
    with apis._session_lock:
        apis._active_session.clear()
        apis._active_session.update({"is_active": True, "session_id": "ai_1", "mode": "AI Pro"})

    def kos(tur: int, *, hedef_var: bool):
        veri = _gercek_hedef_tuple(air, hedef_var=hedef_var)
        monkeypatch.setattr(air, "_localize_organ", lambda *a, **k: veri)
        saat = _Saat(air, tur)
        monkeypatch.setattr(air, "time", saat)
        air._ai_loop_active = True
        air._ai_pro_loop()
        assert saat.kalan <= 0, f"loop {tur} tur DÖNMEDİ (kalan={saat.kalan}) — kapı bir şey ölçmedi"
        return veri

    yield air, izler, kos

    air._ai_loop_active = False
    air._ai_organ_cache.clear()
    air._ai_organ_cache.update(snap_cache)
    air._ai_organ_id = snap_oid
    air._ai_owner_client = snap_owner
    with apis._session_lock:
        apis._active_session.clear()
        apis._active_session.update(sess_snap)


def test_KRITIK_seans_dongusu_GERCEK_tuple_ile_bobinleri_SURER(seans_ortami):
    """Kusurun kendisi: 7'li açılım ← 8'li tuple → her lokalizasyon ValueError, sürüş SIFIR.

    MUTASYON KANITI: `_ai_pro_loop` içindeki açılımı `..., lkedi = _localize_organ(...)` (yıldızsız)
    yaparsanız bu test KIRMIZI olur — sürüş listesi boş kalır ve `localized` False'ta çakılır.
    """
    air, izler, kos = seans_ortami
    veri = kos(2, hedef_var=True)

    assert len(veri) >= 8, (
        f"`_extract_organ_target` {len(veri)} eleman döndürdü — bu kapı 8+ eleman sözleşmesini varsayar; "
        "sözleşme değiştiyse loop açılımlarını da (hazırlık/seans/frame) birlikte güncelleyin"
    )
    assert veri[0] is True, "test verisi hatalı: güven 0.9 ile hedef localized olmalıydı"
    assert izler["surus"], (
        "hedef BULUNMUŞKEN bobinler hiç sürülmedi — seans döngüsü lokalizasyon sonucunu açamıyor "
        "(ValueError yutuluyor); onaylı AI Pro seansı 'aktif' görünür ama tedavi UYGULANMAZ"
    )
    assert air._ai_organ_cache["localized"] is True, "cache 'localized' güncellenmedi (lokalizasyon düştü)"
    assert not izler["stop"], (
        f"hedef bulunuyorken 'hedef kaybı' STOP'u yayınlandı ({izler['stop']!r}) — "
        "lokalizasyon hatası kayıp gibi raporlanıyor"
    )


def test_KRITIK_seans_dongusu_cache_e_GUVEN_DOKUMUNU_yazar(seans_ortami):
    """Hazırlık önizlemesi paritesi: 8. eleman (reliability_components) cache'e YAZILMALI.

    Yazılmazsa /status ve WS `guvenDokumu` seans boyunca hazırlıktan kalan BAYAT değeri (ya da
    None) taşır; panel "Güven %X"in nedenini yanlış gösterir. MUTASYON: cache.update'ten
    "guven_dokumu" satırını silin → KIRMIZI.
    """
    air, izler, kos = seans_ortami
    veri = kos(2, hedef_var=True)

    beklenen = veri[7] if len(veri) > 7 else None
    assert beklenen, "test verisi hatalı: reliability_components üretilmedi"
    assert air._ai_organ_cache.get("guven_dokumu") == beklenen, (
        "seans döngüsü güven dökümünü cache'e yazmıyor — /status ve WS bayat/None değer taşır "
        "(hazırlık döngüsü yazıyor; iki yol AYRIŞMIŞ)"
    )


def test_KARSIT_KANIT_hedef_YOKKEN_surus_YOK_ve_ardisik_kayipta_STOP(seans_ortami):
    """Karşıt-kanıt: düzeltme "her durumda sür" mutasyonuna dönüşmemeli. Hedef yokken
    bobin sürülmez ve eşik dolunca mevcut hedef-kaybı STOP'u çalışır."""
    air, izler, kos = seans_ortami
    esik = air._AI_LOST_STOP_STREAK
    kos(esik, hedef_var=False)

    assert not izler["surus"], "hedef YOKKEN bobinler sürüldü — hedefsiz tedavi"
    assert izler["stop"], f"hedef {esik} ardışık turdur kayıpken bobinler durdurulmadı"
    assert set(izler["stop"][0]) >= set(range(1, 8)), "AI Pro'nun sürdüğü 1-7 bobininin tamamı durdurulmadı"


def test_YAPISAL_hazirlik_ve_seans_lokalizasyonu_AYNI_bicimde_acar():
    """1187 kusuru tam da bu paritenin kopmasından çıktı: 2026-08-26'da tuple 8'e çıkarıldı,
    hazırlık ve mobil yolları güncellendi, seans döngüsü unutuldu. Kapı: `_localize_organ(`
    çağrılarının HEPSİ yıldızlı (esnek) açılım kullanmalı — biri yıldızsızsa KIRMIZI."""
    from pathlib import Path

    import servers.ai_router as air

    src = Path(air.__file__).read_text(encoding="utf-8")
    # Çağrı biçimi yola göre değişiyor (seans/hazırlık doğrudan, mobil kare `asyncio.to_thread`
    # ile) → fonksiyon ADINA ve "sol tarafta tuple açılımı var mı"ya bak, çağrı metnine değil.
    satirlar = []
    for s in src.splitlines():
        if "_localize_organ" not in s or "def " in s or "=" not in s:
            continue
        sol = s.split("=", 1)[0]
        if "," in sol:  # tuple açılımı (tek isme atama değil)
            satirlar.append(s.strip())
    assert len(satirlar) >= 3, (
        f"beklenen üç lokalizasyon çağrısı (hazırlık, seans, mobil kare) bulunamadı: {satirlar!r} — "
        "çağrı yeri taşındıysa bu kapıyı gerçek çağrılara yeniden pinleyin"
    )
    yildizsiz = [s for s in satirlar if "*" not in s.split("=", 1)[0]]
    assert not yildizsiz, (
        f"lokalizasyon sonucunu SABİT sayıda isme açan çağrı(lar) var: {yildizsiz!r} — "
        "tuple bir eleman büyüdüğünde ValueError yutulur ve o yol sessizce ölür "
        "(2026-09-08: seans döngüsü tam bu yüzden hiç bobin sürmüyordu)"
    )

# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""Y59 (sahip, 1-E inceleme S-İ1) — ACİL DURDUR mandal dosyası diske YAZILAMAZSA operatöre söylenir.

ÖLÇÜLEN (1-E inceleme §4 tablosu S1–S4): dosya değiştirilemiyorsa (salt-okunur öznitelik, dosyanın yerinde dizin)
Sıfırla o oturumda mandalı kaldırıyor ama diske yazamıyor → her açılışta mandal GERİ GELİYOR ve bant "sıfırlanmadı"
diyordu; E-stop'un yazımı başarısızsa yeniden başlatmada mandal YOKTU (Y46: "yalnız kaydedilir"). İkisi de yalnız
günlükteydi — Sıfırla `success`, E-stop `success` dönüyordu.

SÖZLEŞME (sahip Y59): Sıfırla ve ACİL DURDUR yanıtı + ekran bildirimi "Mandal dosyası yazılamadı (<yol>) — yeniden
başlatmada mandal [geri gelecek / KORUNMAYACAK]; dosya iznini düzeltin." Davranış AYNEN: ACİL DURDUR yazımı hiç
beklemez (Y46), Sıfırla o oturumda mandalı her durumda kaldırır (Y56). ACİL DURDUR ucu auth-muaf → yanıtında dosya
YOLU yok (yol yalnız kimlikli bildirim ve Sıfırla yanıtında).
"""

from __future__ import annotations

import json
import os
import stat
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from topoloji import TUM_STM

_DOSYA = "estop_mandali.json"


@pytest.fixture
def ortam(monkeypatch, tmp_path):
    from servers import api_server as api
    from utils import estop_mandali

    olaylar: list = []
    bildirimler: list = []

    class _SahteHC:
        coils_state = {b: {"is_running": False} for b in TUM_STM}

        def stop_all_coils(self):
            olaylar.append(("stop", "stm"))
            return True

        def update_coil(self, *a, **k):
            return True

    orj_yaz = estop_mandali._diske_yaz

    def _kayitli_yaz(*a, **k):
        olaylar.append(("yaz", "disk"))
        return orj_yaz(*a, **k)

    monkeypatch.setattr(estop_mandali, "_diske_yaz", _kayitli_yaz)
    monkeypatch.setattr(api.state, "hardware", _SahteHC())
    monkeypatch.setattr(api, "_mqtt_publish", lambda *a, **k: False)
    monkeypatch.setattr(api, "_estop_cloud_mirror", lambda *a, **k: None)
    monkeypatch.setattr(api, "_ws_broadcast_sync", lambda *a, **k: None)
    monkeypatch.setattr(api, "_push_notification", lambda m, t="info", *a, **k: bildirimler.append((t, m)))
    with api._session_lock:
        api._active_session.clear()
    veri = tmp_path / "veri"
    veri.mkdir()
    ns = SimpleNamespace(api=api, mandal=estop_mandali, olaylar=olaylar, bildirimler=bildirimler, veri=veri)
    ns.dosya = veri / _DOSYA
    ns.c = TestClient(api.app, client=("127.0.0.1", 51238))
    yield ns
    estop_mandali.kalicilik_kapat()
    estop_mandali.sifirla("test")
    try:
        if ns.dosya.is_file():
            os.chmod(ns.dosya, stat.S_IREAD | stat.S_IWRITE)
    except OSError:
        pass


def _bekle(kosul, sure=3.0) -> bool:
    son = time.monotonic() + sure
    while time.monotonic() < son:
        if kosul():
            return True
        time.sleep(0.02)
    return kosul()


def _metinler(x):
    """Yanıttaki TÜM metin değerleri (iç içe sözlük/liste)."""
    if isinstance(x, str):
        yield x
    elif isinstance(x, dict):
        for v in x.values():
            yield from _metinler(v)
    elif isinstance(x, (list, tuple)):
        for v in x:
            yield from _metinler(v)


def _salt_okunur(o, aktif: bool) -> None:
    o.dosya.write_text(json.dumps({"aktif": aktif, "neden": "manual"}), encoding="utf-8")
    os.chmod(o.dosya, stat.S_IREAD)


def _sifirla(o):
    return o.c.post("/api/hardware/estop_mandali/sifirla", json={"onay": True})


def _estop_olc(o) -> tuple[dict, float]:
    t0 = time.monotonic()
    sonuc = o.api._emergency_stop_all("manual")
    return sonuc, time.monotonic() - t0


def _estop_beklemedi(o, sure: float) -> None:
    """Y46 aynen: STOP disk yazımından ÖNCE, yanıt beklemesiz; mandal bellekte kurulu."""
    print(f"ESTOP_SURE {sure * 1000:.1f} ms sira={[t for t, _n in o.olaylar]}")
    assert sure < 1.0, f"ACİL DURDUR {sure:.2f} sn sürdü (disk yazımını bekledi mi?)"
    sira = [t for t, _n in o.olaylar]
    assert "stop" in sira, "STOP gitmedi"
    if "yaz" in sira:
        assert sira.index("stop") < sira.index("yaz"), f"disk yazımı STOP'tan ÖNCE: {o.olaylar}"
    assert o.mandal.mandalli_mi() is True


def _uyari_bildirimi(o, parca: str) -> list:
    return [m for t, m in o.bildirimler if "Mandal dosyası yazılamadı" in m and parca in m]


def test_KRITIK_S1_salt_okunur_KURULU_dosya_Sifirla_yaniti_ve_bildirim_GERI_GELECEK_der(ortam):
    o = ortam
    _salt_okunur(o, True)
    o.mandal.kalicilik_kur(o.dosya)
    assert o.mandal.mandalli_mi(), "ön koşul: dosyadan mandal kurulmadı"
    r = _sifirla(o)
    assert r.status_code == 200 and o.mandal.mandalli_mi() is False, f"Y56: Sıfırla mandalı kaldırmalı: {r.text[:200]}"
    md = r.json().get("mandalDosyasi") or {}
    assert md.get("yazilamadi") is True and "geri gelecek" in md.get("mesaj", ""), (
        f"Sıfırla yanıtı dosyanın YAZILAMADIĞINI ve yeniden başlatmada mandalın geri geleceğini söylemiyor: {r.json()}"
    )
    assert str(o.dosya) in md.get("mesaj", ""), "Sıfırla yanıtı (kimlikli uç) dosya yolunu vermiyor"
    assert _bekle(lambda: bool(_uyari_bildirimi(o, "geri gelecek"))), f"ekran bildirimi yok: {o.bildirimler}"
    assert str(o.dosya) in _uyari_bildirimi(o, "geri gelecek")[0]
    o.olaylar.clear()
    sonuc, sure = _estop_olc(o)
    _estop_beklemedi(o, sure)


def test_KRITIK_S3_dosyanin_yerinde_DIZIN_Sifirla_GERI_GELECEK_der(ortam):
    o = ortam
    o.dosya.mkdir()
    o.mandal.kalicilik_kur(o.dosya)
    assert o.mandal.mandalli_mi(), "ön koşul: okunamayan dosya mandalı kurmalı (güvenli taraf)"
    r = _sifirla(o)
    assert r.status_code == 200 and o.mandal.mandalli_mi() is False
    md = r.json().get("mandalDosyasi") or {}
    assert md.get("yazilamadi") is True and "geri gelecek" in md.get("mesaj", ""), r.json()
    assert _bekle(lambda: bool(_uyari_bildirimi(o, "geri gelecek"))), o.bildirimler
    o.olaylar.clear()
    _sonuc, sure = _estop_olc(o)
    _estop_beklemedi(o, sure)


def test_KRITIK_S4_salt_okunur_bos_dosya_ESTOP_yaniti_ve_bildirim_KORUNMAYACAK_der_ESTOP_beklemez(ortam):
    o = ortam
    _salt_okunur(o, False)
    o.mandal.kalicilik_kur(o.dosya)
    assert not o.mandal.mandalli_mi()
    sonuc, sure = _estop_olc(o)
    _estop_beklemedi(o, sure)
    md = sonuc.get("mandalDosyasi") or {}
    assert md.get("yazilamadi") is True and "KORUNMAYACAK" in md.get("mesaj", ""), (
        f"ACİL DURDUR yanıtı mandalın yeniden başlatmada KORUNMAYACAĞINI söylemiyor: {sonuc.get('mandalDosyasi')}"
    )
    # ⚠️ Metin değerleri taranır: `json.dumps` ters bölüleri ikiler, ham yol alt dize olarak hiç eşleşmezdi (ölçüldü: yolu
    # sızdıran mutant bu yüzden yeşil kalıyordu).
    sizan = [m for m in _metinler(sonuc) if str(o.veri) in m or _DOSYA in m]
    assert not sizan, f"auth-muaf E-stop yanıtı dosya YOLUNU sızdırıyor: {sizan}"
    assert _bekle(lambda: bool(_uyari_bildirimi(o, "KORUNMAYACAK"))), f"ekran bildirimi yok: {o.bildirimler}"
    assert str(o.dosya) in _uyari_bildirimi(o, "KORUNMAYACAK")[0]


def test_KARSIT_S2_okunamayan_ama_YAZILABILIR_dosya_Sifirla_UYARMAZ(ortam, monkeypatch):
    """S2 (okuma reddi, `os.replace` başarır): açılışta mandal KURULU (güvenli taraf), Sıfırla diske YAZAR → uyarı YOK."""
    o = ortam
    o.dosya.write_text(json.dumps({"aktif": False}), encoding="utf-8")
    gercek = Path.read_text

    def _okuma_reddi(self, *a, **k):
        if self == o.dosya:
            raise PermissionError(13, "Access is denied")
        return gercek(self, *a, **k)

    monkeypatch.setattr(Path, "read_text", _okuma_reddi)
    o.mandal.kalicilik_kur(o.dosya)
    monkeypatch.setattr(Path, "read_text", gercek)
    assert o.mandal.mandalli_mi()
    r = _sifirla(o)
    assert r.status_code == 200 and not o.mandal.mandalli_mi()
    assert not (r.json().get("mandalDosyasi") or {}).get("yazilamadi"), r.json()
    assert json.loads(o.dosya.read_text(encoding="utf-8"))["aktif"] is False
    o.olaylar.clear()
    sonuc, sure = _estop_olc(o)
    _estop_beklemedi(o, sure)
    assert _bekle(lambda: json.loads(o.dosya.read_text(encoding="utf-8")).get("aktif") is True)
    assert not o.bildirimler or not _uyari_bildirimi(o, ""), f"yazılabilir dosyada yanlış uyarı: {o.bildirimler}"
    assert not (sonuc.get("mandalDosyasi") or {}).get("yazilamadi")


def test_KARSIT_yazilabilir_dosyada_E_stop_ve_Sifirla_UYARMAZ(ortam):
    o = ortam
    o.mandal.kalicilik_kur(o.dosya)
    sonuc, sure = _estop_olc(o)
    _estop_beklemedi(o, sure)
    assert _bekle(lambda: o.dosya.exists() and json.loads(o.dosya.read_text(encoding="utf-8")).get("aktif") is True)
    r = _sifirla(o)
    assert r.status_code == 200
    assert not (r.json().get("mandalDosyasi") or {}).get("yazilamadi")
    assert not (sonuc.get("mandalDosyasi") or {}).get("yazilamadi")
    assert not _uyari_bildirimi(o, ""), o.bildirimler


# ── 1-F inceleme (B-1.1 · B-1.2 · B-1.3) ─────────────────────────────────────────────────────────────────────────────
# Asılı disk: mandal dosyasının `os.replace`'i bırakılana dek bekler (yalnız `estop_mandali` modülünde — başka modül ve
# gerçek disk etkilenmez). Tek olay döngüsü (üretimdeki uvicorn gibi): httpx.ASGITransport + asyncio.run — TestClient her
# istekte yeni döngü açar, ortak varsayılan iş parçacığı havuzunu ölçemezdi.


class _AsiliOs:
    def __init__(self):
        import threading

        self._olay = threading.Event()
        self.bekleyen = 0

    def replace(self, a, b):
        self.bekleyen += 1
        self._olay.wait(30)
        return os.replace(a, b)

    def birak(self):
        self._olay.set()

    def __getattr__(self, ad):
        return getattr(os, ad)


def _tek_dongude(o, govde):
    import asyncio

    import httpx

    async def _kos():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=o.api.app), base_url="http://cihaz") as c:
            return await govde(c)

    return asyncio.run(_kos())


def test_KRITIK_asili_diskte_Sifirla_yaniti_TEMIZ_DEMEZ_mandal_yine_KALKAR(ortam, monkeypatch):
    """B-1.1: yazım 2 sn'de bitmezse Sıfırla eskiden `mandalDosyasi: {yazilamadi: false}` dönüyordu (ölçüldü) — dosya
    güncellenmemişken "sorun yok". Y56 aynen: mandal o oturumda kalkar."""
    o = ortam
    o.mandal.kalicilik_kur(o.dosya)
    _sonuc, sure = _estop_olc(o)
    _estop_beklemedi(o, sure)
    assert _bekle(lambda: o.dosya.exists() and json.loads(o.dosya.read_text(encoding="utf-8")).get("aktif") is True)
    asili = _AsiliOs()
    monkeypatch.setattr(o.mandal, "os", asili)

    async def _govde(c):
        try:
            return await c.post("/api/hardware/estop_mandali/sifirla", json={"onay": True})
        finally:
            asili.birak()

    r = _tek_dongude(o, _govde)
    assert asili.bekleyen >= 1, "aparat: yazım asılı diske ulaşmadı"
    assert r.status_code == 200 and o.mandal.mandalli_mi() is False, f"Y56: Sıfırla mandalı kaldırmalı: {r.text[:200]}"
    md = r.json().get("mandalDosyasi") or {}
    assert md.get("yazilamadi") is True and "bitmedi" in md.get("mesaj", ""), (
        f"yazım 2 sn'de BİTMEDİ ama Sıfırla yanıtı dosyanın güncellendiğini varsayıyor: {md}"
    )
    assert _bekle(lambda: bool(_uyari_bildirimi(o, "bitmedi"))), f"ekran bildirimi yok: {o.bildirimler}"


def test_KRITIK_asili_diskte_tekrarli_Sifirla_ACIL_DURDURu_BEKLETMEZ(ortam, monkeypatch):
    """B-1.2 (Ö.4-Y8): Sıfırla'nın yazımı olay döngüsünün ORTAK havuzunda (`asyncio.to_thread`) koşuyordu; asılı diskte
    her basış bir işçiyi kalıcı tutuyor, havuz dolunca ACİL DURDUR ucunun `to_thread`'i SIRA bekliyordu — ölçüldü:
    20 Sıfırla'dan sonra ACİL DURDUR 6 sn'de yanıt VERMEDİ (1-E'de 0,0 sn). Havuz boyu Python varsayılanı."""
    import asyncio

    o = ortam
    o.mandal.kalicilik_kur(o.dosya)
    asili = _AsiliOs()
    monkeypatch.setattr(o.mandal, "os", asili)
    n = min(32, (os.cpu_count() or 1) + 4) + 2  # ThreadPoolExecutor varsayılan işçi sayısı + pay

    async def _govde(c):
        try:
            r0 = await c.post("/api/hardware/emergency_stop")  # E-stop'un arka plan yazıcısı asılır
            # İlk Sıfırla (mandal KURULU → denetim izi DB yazımı da havuzda) TEK başına; kalanlar eşzamanlı (her biri
            # 2 sn'lik zaman aşımıyla döner) — ölçüm yalnız mandal yazımının havuz kullanımını görür.
            r1 = await c.post("/api/hardware/estop_mandali/sifirla", json={"onay": True})
            assert r1.status_code == 200 and not o.mandal.mandalli_mi(), f"aparat: ilk Sıfırla {r1.status_code}"
            t_s = time.monotonic()
            rs = await asyncio.gather(
                *[c.post("/api/hardware/estop_mandali/sifirla", json={"onay": True}) for _ in range(n - 1)]
            )
            assert {x.status_code for x in rs} == {200} and time.monotonic() - t_s < 10, "aparat: Sıfırla'lar dönmedi"
            t0 = time.monotonic()
            try:
                r = await asyncio.wait_for(c.post("/api/hardware/emergency_stop"), timeout=4.0)
                return r0, r.status_code, time.monotonic() - t0
            except asyncio.TimeoutError:
                return r0, None, time.monotonic() - t0
        finally:
            asili.birak()

    r0, kod, sure = _tek_dongude(o, _govde)
    assert r0.status_code == 200 and asili.bekleyen >= 1, "aparat: ilk E-stop ya da asılı yazım olmadı"
    assert kod == 200 and sure < 1.0, (
        f"asılı diskte {n} Sıfırla'dan sonra ACİL DURDUR {sure:.1f} sn'de yanıt vermedi (kod={kod}) — Sıfırla'nın yazımı "
        "ortak iş parçacığı havuzunu tüketti"
    )


def test_KRITIK_izin_DUZELTILINCE_uyari_KALKAR_ve_sonuc_DISKTEKI_durumu_soyler(ortam):
    """B-1.3: başarılı yazım hem uyarıyı kaldırmalı hem diskteki durumu güncellemeli. Mevcut kollar dosyayı açılıştan
    önce bozuyordu; ikisini silen mutantlar 35/35 YEŞİL kaldı (ölçüldü)."""
    o = ortam
    o.mandal.kalicilik_kur(o.dosya)
    _sonuc, sure = _estop_olc(o)
    _estop_beklemedi(o, sure)
    assert _bekle(lambda: o.dosya.exists() and json.loads(o.dosya.read_text(encoding="utf-8")).get("aktif") is True)
    os.chmod(o.dosya, stat.S_IREAD)  # sonradan salt-okunur (yedekleme / güvenlik aracı)
    r = _sifirla(o)
    md = r.json().get("mandalDosyasi") or {}
    assert md.get("yazilamadi") is True and "geri gelecek" in md.get("mesaj", ""), (
        f"diskte KURULU mandal varken Sıfırla yazamadı — yanıt yeniden başlatmada mandalın GERİ GELECEĞİNİ söylemiyor: {md}"
    )
    os.chmod(o.dosya, stat.S_IREAD | stat.S_IWRITE)  # operatör izni düzeltir
    r2 = _sifirla(o)
    assert json.loads(o.dosya.read_text(encoding="utf-8")).get("aktif") is False, "aparat: yazım diske gitmedi"
    assert not (r2.json().get("mandalDosyasi") or {}).get("yazilamadi"), (
        f"izin düzeltilip yazım BAŞARILI olduktan sonra yanıt hâlâ 'yazılamadı' diyor: {r2.json().get('mandalDosyasi')}"
    )

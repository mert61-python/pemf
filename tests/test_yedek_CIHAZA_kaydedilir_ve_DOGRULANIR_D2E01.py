# -*- coding: utf-8 -*-
"""D2.E01 (İG-6.20) — backend yarısı: `/api/data/export` `kaydet: true` → şifreli yedek CİHAZIN masaüstüne yazılır ve GERİ OKUNARAK
doğrulanır; yanıt yol + boyut + `dogrulandi` taşır, içeriği taşımaz.

ÖLÇÜLEN KUSUR (ADAY-DOGRULAMA-D2 İG-6.20): Ayarlar'daki "Şifreli Yedek Oluştur" dosyayı yalnız tarayıcıya `<a download>` ile verip
dosyanın oluşup oluşmadığını bilmeden "Yedek oluşturuldu" diyordu (CDP `deny` kolunda dosya 0, tost "oluşturuldu"). Masaüstü WebView2'de
`<a download>` sessizce ölebiliyor (09-11). Arayüz yarısı: `apps/ui/src/screens/__tests__/SettingsVeriTasima.D2E01_E03.web.test.tsx`.
Masaüstü dizini conftest'in `_masaustunu_koru` sahte dizinidir (gerçek masaüstüne yazılmaz). Disk arızası en alt katta (`os.replace`).
"""

from __future__ import annotations

import base64

from veri_tasima_aparati import PAROLA, cihaz_kur, doldur, istekler, kapat, uclari_bagla


def _kur(tmp_path, monkeypatch):
    from servers import api_server as api

    tdb, hdb = cihaz_kur(monkeypatch, tmp_path / "A")
    uclari_bagla(monkeypatch, tdb, hdb)
    doldur(tdb, hdb, ["Mia", "Pamuk"], seans_basi=1)
    return api, tdb, hdb


def test_KRITIK_D2E01_kaydet_ile_yedek_MASAUSTUNE_yazilir_GERI_OKUNUP_dogrulanir_icerik_yanitta_yok(
    tmp_path, monkeypatch, _masaustunu_koru
):
    api, tdb, hdb = _kur(tmp_path, monkeypatch)
    try:
        (r,) = istekler(api.app, [("POST", "/api/data/export", {"passphrase": PAROLA, "kaydet": True}, None)])
        assert r.status_code == 200, r.text[:300]
        g = r.json()
        assert "data_b64" not in g, "cihaza kaydedilen yedeğin içeriği yanıtta da taşındı"
        assert g.get("dogrulandi") is True and g.get("bayt", 0) > 0, g
        from pathlib import Path

        yol = Path(g["yol"])
        assert yol.parent == _masaustunu_koru and yol.exists(), f"yedek masaüstü dizinine yazılmadı: {g}"
        assert yol.stat().st_size == g["bayt"]
        from utils.data_export import decrypt_bundle

        paket = decrypt_bundle(yol.read_bytes(), PAROLA)
        assert len(paket["treatment_sessions"]) == 2 and len(paket["patient_db"]) == 2
        assert [p.name for p in _masaustunu_koru.iterdir() if p.name.endswith(".tmp")] == [], (
            "geçici yazım dosyası kaldı"
        )
    finally:
        kapat(tdb, hdb)


def test_KRITIK_D2E01_disk_yazimi_DUSERSE_500_ve_dosya_KALMAZ(tmp_path, monkeypatch, _masaustunu_koru):
    api, tdb, hdb = _kur(tmp_path, monkeypatch)
    import os

    gercek = os.replace

    def _dolu(src, dst, *a, **k):
        if str(src).endswith(".pemfbak.yazim.tmp"):
            raise OSError(28, "No space left on device (aparat)")
        return gercek(src, dst, *a, **k)

    monkeypatch.setattr(os, "replace", _dolu)
    try:
        (r,) = istekler(api.app, [("POST", "/api/data/export", {"passphrase": PAROLA, "kaydet": True}, None)])
        assert r.status_code == 500, f"disk yazımı düştü ama yanıt {r.status_code}: {r.text[:200]}"
        assert "OLUŞTURULMADI" in r.json().get("detail", "")
        assert list(_masaustunu_koru.iterdir()) == [], (
            f"başarısız yedekten dosya kaldı: {list(_masaustunu_koru.iterdir())}"
        )
    finally:
        kapat(tdb, hdb)


def test_KRITIK_D2E01_kaydet_CIHAZ_DISINDAN_reddedilir_dosya_yazilmaz(tmp_path, monkeypatch, _masaustunu_koru):
    """Telefon / LAN istemcisi cihazın masaüstündeki dosyayı göremez — o yol içeriği yanıtta alır."""
    api, tdb, hdb = _kur(tmp_path, monkeypatch)
    from servers import auth

    monkeypatch.setattr(auth, "check_token", lambda t: t == "cihaz-jetonu")
    try:
        (r,) = istekler(
            api.app,
            [("POST", "/api/data/export", {"passphrase": PAROLA, "kaydet": True}, {"X-API-Key": "cihaz-jetonu"})],
            client=("192.168.1.77", 51000),
        )
        assert r.status_code == 400, r.text[:300]
        assert list(_masaustunu_koru.iterdir()) == []
    finally:
        kapat(tdb, hdb)


def test_KARSIT_D2E01_kaydetSIZ_istek_bugunku_gibi_icerigi_dondurur(tmp_path, monkeypatch, _masaustunu_koru):
    api, tdb, hdb = _kur(tmp_path, monkeypatch)
    try:
        (r,) = istekler(api.app, [("POST", "/api/data/export", {"passphrase": PAROLA}, None)])
        assert r.status_code == 200
        assert base64.b64decode(r.json()["data_b64"]).startswith(b"PEMFDATA1")
        assert "yol" not in r.json() and list(_masaustunu_koru.iterdir()) == []
    finally:
        kapat(tdb, hdb)


def test_KRITIK_D2E01_dosya_YARIM_yazilirsa_dogrulama_YAKALAR_500_ve_yarim_dosya_KALMAZ(
    tmp_path, monkeypatch, _masaustunu_koru
):
    """Disk/dosya sistemi arızası (ör. dolu disk, kopan ağ sürücüsü) son adda YARIM içerik bırakır: geri okuma doğrulaması bunu
    yakalar, yarım `.pemfbak` "yedek" diye kalmaz."""
    api, tdb, hdb = _kur(tmp_path, monkeypatch)
    import os

    gercek = os.replace

    def _yarim(src, dst, *a, **k):
        if str(src).endswith(".pemfbak.yazim.tmp"):
            with open(src, "rb") as f:
                veri = f.read()
            with open(dst, "wb") as f:
                f.write(veri[: len(veri) // 2])
            os.remove(src)
            return None
        return gercek(src, dst, *a, **k)

    monkeypatch.setattr(os, "replace", _yarim)
    try:
        (r,) = istekler(api.app, [("POST", "/api/data/export", {"passphrase": PAROLA, "kaydet": True}, None)])
        assert r.status_code == 500, f"yarım yazılan yedek 'başarılı' döndü: {r.status_code} {r.text[:200]}"
        assert list(_masaustunu_koru.iterdir()) == [], f"yarım yedek dosyası kaldı: {list(_masaustunu_koru.iterdir())}"
    finally:
        kapat(tdb, hdb)

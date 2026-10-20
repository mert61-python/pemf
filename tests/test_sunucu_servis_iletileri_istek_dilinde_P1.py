# -*- coding: utf-8 -*-
"""I18N-P1 · SUNUCU 10h — servis katmanı (güncelleme yöneticisi + ayar kaydı reddi) iletileri istek dilinde.

Gerçek ekran metni: `update_manager` (API `error` / `message`: kanal kapalı, URL pini, SHA256 / imza, aktif tedavi, rollback) ve
okunamayan `config.json`da ayar kaydı reddi (503 gövdesi). Geri kalan ~109 metin günlük / iç istisna / komut argümanı / MQTT konusu /
üretilen dosya içeriği / DB'ye yazılan veri (muaf, gerekçeli).

Türkçe çıktı ESKİ kodun çıktısıyla BAYT BAYT aynıdır (beklenen metinler taşıma ÖNCESİ kaynaktan sabitlenmiştir). ⚠️ Güvenlik mantığı
(URL pini, SHA256, Authenticode, aktif tedavi kapısı) DEĞİŞMEDİ: aynı koşullar aynı reddi verir — yalnız ileti dili. MUTASYON: katalog TR
değeri değişirse / çağrı ham metne dönerse / durum önbelleği çevirisi kalkarsa → KIRMIZI.
"""

from __future__ import annotations

import contextlib
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
for p in (KOK, KOK / "apps" / "backend"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from utils import ceviri  # noqa: E402

GH = "https://github.com/mert61-python/pemf-update/releases/download/v9.9.9/i.exe"
ESKI_KANAL_KAPALI = (
    "Bu cihazın güncellemelerini PEMF Vet Client (launcher) yönetiyor. Eski EXE güncelleme "
    "kanalı kapalıdır — iki ayrı kurulum ve ikiye bölünmüş hasta veritabanı riski taşır."
)


@contextlib.contextmanager
def dilde(dil):
    jeton = ceviri.istek_dili_var.set(dil)
    try:
        yield
    finally:
        ceviri.istek_dili_var.reset(jeton)


@pytest.fixture
def um(monkeypatch):
    import servers.update_manager as m

    m._status.clear()
    monkeypatch.setattr(m, "_applying", False, raising=False)
    return m


@pytest.fixture
def um_acik(um, monkeypatch):
    monkeypatch.setenv("PEMF_LEGACY_EXE_UPDATE", "1")
    return um


# ── kanal kapalı (VARSAYILAN) ────────────────────────────────────────────────────────────────────────────
def test_KRITIK_kanal_kapali_iletisi_TR_bayt_bayt_EN_istek_dilinde(um, monkeypatch):
    monkeypatch.delenv("PEMF_LEGACY_EXE_UPDATE", raising=False)
    assert um.apply_update() == {"ok": False, "error": ESKI_KANAL_KAPALI}
    assert um.rollback() == {"ok": False, "error": ESKI_KANAL_KAPALI}
    assert um.get_status()["message"] == ESKI_KANAL_KAPALI
    en = (
        "This device's updates are managed by PEMF Vet Client (launcher). The old EXE update channel is closed — it risks two "
        "separate installations and a split patient database."
    )
    with dilde("en"):
        assert um.apply_update() == {"ok": False, "error": en}
        assert um.rollback() == {"ok": False, "error": en}
        assert um.get_status()["message"] == en


# ── URL pini (güvenlik ret metinleri) ────────────────────────────────────────────────────────────────────
URL_VAKALARI = [
    (
        "ftp://github.com/x",
        "Güncelleme URL'si HTTPS değil — indirilmedi (güvenlik).",
        "The update URL is not HTTPS — not downloaded (security).",
    ),
    (
        "https://evil@github.com/x",
        "Güncelleme URL'si kullanıcı bilgisi (@) içeriyor — indirilmedi (güvenlik).",
        "The update URL contains user information (@) — not downloaded (security).",
    ),
    (
        "https://github.com/mert61-python/pemf-update/../../x/y.exe",
        "Güncelleme URL'si nokta-segmenti/kodlanmış ayraç içeriyor (repo pini atlatma) — indirilmedi (güvenlik).",
        "The update URL contains dot segments / encoded separators (repository pin bypass) — not downloaded (security).",
    ),
    (
        "https://github.com/baska/repo/releases/x.exe",
        "Güncelleme URL'si beklenen repo dışında (/baska/repo) — indirilmedi (güvenlik).",
        "The update URL is outside the expected repository (/baska/repo) — not downloaded (security).",
    ),
    (
        "https://raw.githubusercontent.com/x/y.exe",
        "Güncelleme kaynağı (raw.githubusercontent.com) yol pini uygulanamayan bir GitHub adresi — yalnız beklenen deponun sürüm "
        "varlığı kabul edilir; indirilmedi (güvenlik).",
        "The update source (raw.githubusercontent.com) is a GitHub address where the path pin cannot be applied — only a release asset of the "
        "expected repository is accepted; not downloaded (security).",
    ),
    (
        "https://evil.example.com/x.exe",
        "Güncelleme host'u beklenen release sunucusu değil (evil.example.com) — indirilmedi (güvenlik).",
        "The update host (evil.example.com) is not the expected release server — not downloaded (security).",
    ),
]


@pytest.mark.parametrize("url, tr, en", URL_VAKALARI)
def test_KRITIK_url_pini_reddi_TR_bayt_bayt_EN_istek_dilinde_KARAR_ayni(um, url, tr, en):
    ok, hata = um._validate_installer_url(url)
    assert ok is False and hata == tr
    with dilde("en"):
        ok_en, hata_en = um._validate_installer_url(url)
    assert ok_en is False and hata_en == en  # ret KARARI dilden bağımsız


def test_url_pini_gecerli_kaynak_hala_kabul_edilir(um):
    assert um._validate_installer_url(GH) == (True, "")
    with dilde("en"):
        assert um._validate_installer_url(GH) == (True, "")


# ── apply / rollback ret iletileri (kanal açık) ──────────────────────────────────────────────────────────
def _kos(f):
    return f()


def test_KRITIK_apply_reddi_iletileri_TR_bayt_bayt_EN_istek_dilinde(um_acik, monkeypatch):
    um = um_acik
    # güncelleme yok
    um._status.update({"available": False})
    assert um.apply_update() == {"ok": False, "error": "Uygulanacak güncelleme yok."}
    # aktif tedavi
    um._status.update({"available": True, "installerUrl": GH, "currentVersion": "1.0.0", "latestVersion": "9.9.9"})
    monkeypatch.setattr(um, "_has_active_treatment", lambda: True)
    assert um.apply_update() == {"ok": False, "error": "Aktif tedavi sürüyor — güncelleme seans bitince yapılabilir."}
    # URL pini (iletinin KENDİSİ `_validate_installer_url`den)
    monkeypatch.setattr(um, "_has_active_treatment", lambda: False)
    um._status.update({"installerUrl": "http://x/y.exe"})
    assert um.apply_update() == {"ok": False, "error": "Güncelleme URL'si HTTPS değil — indirilmedi (güvenlik)."}
    # zaten sürüyor
    um._status.update({"installerUrl": GH})
    monkeypatch.setattr(um, "_applying", True)
    assert um.apply_update() == {"ok": False, "error": "Güncelleme zaten sürüyor."}
    monkeypatch.setattr(um, "_applying", False)

    with dilde("en"):
        um._status.update({"available": False})
        assert um.apply_update() == {"ok": False, "error": "There is no update to apply."}
        um._status.update({"available": True, "installerUrl": GH})
        monkeypatch.setattr(um, "_has_active_treatment", lambda: True)
        assert um.apply_update() == {
            "ok": False,
            "error": "A treatment is in progress — the update can be applied after the session ends.",
        }
        monkeypatch.setattr(um, "_has_active_treatment", lambda: False)
        monkeypatch.setattr(um, "_applying", True)
        assert um.apply_update() == {"ok": False, "error": "An update is already in progress."}


def test_KRITIK_rollback_reddi_iletileri_TR_bayt_bayt_EN_istek_dilinde(um_acik, monkeypatch):
    um = um_acik
    um._status.update({"previousStable": None})
    assert um.rollback() == {
        "ok": False,
        "error": "Geri dönülecek önceki kararlı sürüm tanımlı değil (manifest 'previousStable' yok).",
    }
    um._status.update({"previousStable": {"version": "1.3.0", "installerUrl": GH, "sha256": "ab" * 32}})
    monkeypatch.setattr(um, "_has_active_treatment", lambda: True)
    assert um.rollback() == {"ok": False, "error": "Aktif tedavi sürüyor — rollback seans bitince yapılabilir."}
    monkeypatch.setattr(um, "_has_active_treatment", lambda: False)
    um._status.update({"previousStable": {"version": "1.3.0", "installerUrl": GH, "sha256": ""}})
    monkeypatch.setattr(um, "_pinli_ac", lambda *a, **k: _SahteYanit(b"x"))
    monkeypatch.setattr(um, "_download_to", lambda r, f, limit, what: f.write(b"x") or 1)
    assert um.rollback() == {
        "ok": False,
        "error": "previousStable SHA256 yok — doğrulanamayan installer ÇALIŞTIRILMADI (güvenlik).",
    }
    with dilde("en"):
        um._status.update({"previousStable": None})
        assert um.rollback() == {
            "ok": False,
            "error": "No previous stable version is defined to go back to (the manifest has no 'previousStable').",
        }
        um._status.update({"previousStable": {"version": "1.3.0", "installerUrl": GH, "sha256": ""}})
        assert um.rollback() == {
            "ok": False,
            "error": "previousStable has no SHA256 — the installer that could not be verified was NOT RUN (security).",
        }


class _SahteYanit:
    def __init__(self, veri):
        self.veri = veri

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self, n=-1):
        return self.veri


def test_KRITIK_apply_sha256_yok_ve_uyusmazlik_TR_bayt_bayt_EN_istek_dilinde(um_acik, monkeypatch):
    """İndirme sahte; SHA256 kapısı GERÇEK: manifest SHA256'sız → çalıştırılmaz; uyuşmazsa → İPTAL (iki dilde de AYNI karar, installer BAŞLAMAZ)."""
    um = um_acik
    monkeypatch.setattr(um, "_has_active_treatment", lambda: False)
    monkeypatch.setattr(um, "_pinli_ac", lambda *a, **k: _SahteYanit(b"x"))
    monkeypatch.setattr(um, "_download_to", lambda r, f, limit, what: f.write(b"x") or 1)
    calisan = []
    monkeypatch.setattr(um.subprocess, "Popen", lambda *a, **k: calisan.append(a))
    um._status.update(
        {"available": True, "installerUrl": GH, "currentVersion": "1.0.0", "latestVersion": "9.9.9", "sha256": ""}
    )
    assert um.apply_update() == {
        "ok": False,
        "error": "Güncelleme manifest'inde SHA256 yok — doğrulanamayan installer ÇALIŞTIRILMADI (güvenlik).",
    }
    um._status.update({"sha256": "ab" * 32})
    r = um.apply_update()
    assert r["ok"] is False
    assert r["error"].startswith("SHA256 uyuşmadı (beklenen abababababab… geldi ")
    assert r["error"].endswith("…) — güncelleme İPTAL.")
    with dilde("en"):
        um._status.update({"sha256": ""})
        assert um.apply_update() == {
            "ok": False,
            "error": "The update manifest has no SHA256 — the installer that could not be verified was NOT RUN (security).",
        }
        um._status.update({"sha256": "ab" * 32})
        r_en = um.apply_update()
    assert r_en["error"].startswith("SHA256 mismatch (expected abababababab… got ") and r_en["error"].endswith(
        "…) — update CANCELLED."
    )
    assert calisan == [], "doğrulanamayan installer BAŞLATILDI"


# ── durum önbelleği: Türkçe VERİ değişmez, gösterim istek dilinde ─────────────────────────────────────────
def test_KRITIK_durum_onbellegi_hata_metni_veri_degismez_gosterim_istek_dilinde(um_acik):
    um = um_acik
    um._status.update({"checked": True, "error": "Güncelleme kontrolü başarısız", "currentVersion": "1.0.0"})
    assert um.get_status()["error"] == "Güncelleme kontrolü başarısız"
    with dilde("en"):
        assert um.get_status()["error"] == "Update check failed"
    assert um._status["error"] == "Güncelleme kontrolü başarısız", "gösterim çevirisi önbellekteki VERİYİ değiştirdi"
    um._status.update({"error": "başka bir hata"})
    with dilde("en"):
        assert um.get_status()["error"] == "başka bir hata"  # tanınmayan değer aynen


# ── GERÇEK uç: /api/update/status ───────────────────────────────────────────────────────────────────────
def test_KRITIK_update_status_ucu_kanal_iletisi_istek_dilinde(um, monkeypatch):
    from fastapi.testclient import TestClient
    from servers import api_server as api_mod

    monkeypatch.delenv("PEMF_LEGACY_EXE_UPDATE", raising=False)
    istemci = TestClient(api_mod.app, client=("127.0.0.1", 51939))
    assert istemci.get("/api/update/status").json()["message"] == ESKI_KANAL_KAPALI
    en = istemci.get("/api/update/status", headers={"X-PEMF-Dil": "en"}).json()["message"]
    assert en.startswith("This device's updates are managed by PEMF Vet Client (launcher).")


# ── ayar kaydı reddi (okunamayan config.json → 503) ─────────────────────────────────────────────────────
def test_KRITIK_ayar_kaydi_reddi_503_gövdesi_istek_dilinde(monkeypatch):
    from fastapi.testclient import TestClient
    from servers import api_server as api_mod
    from servers import settings_router as sr
    from utils import production_config_manager as pcm

    sahip = pcm._sahip()

    def _reddet(_veri):
        raise sahip.ConfigKaydiReddedildi(ceviri.t("sistem.hata.ayarKaydedilmedi", neden="PermissionError"))

    monkeypatch.setattr(sr, "save_settings", _reddet)
    monkeypatch.setattr(sr, "load_settings", lambda: {})
    istemci = TestClient(api_mod.app, client=("127.0.0.1", 51939))
    govde = {"clinic_name": "x"}
    tr = istemci.post("/api/settings/", json=govde)
    assert tr.status_code == 503
    assert tr.json()["detail"].startswith(
        "Ayar KAYDEDILMEDI: config.json okunamiyor (PermissionError). Mevcut dosya korunuyor"
    )
    en = istemci.post("/api/settings/", json=govde, headers={"X-PEMF-Dil": "en"})
    assert en.status_code == 503
    assert en.json()["detail"].startswith("Setting NOT SAVED: config.json cannot be read (PermissionError).")


def test_ayar_kaydi_reddi_GERCEK_uretici_iletisi_TR_bayt_bayt(tmp_path, monkeypatch):
    """Kaynağın GERÇEK ürettiği istisna iletisi (`ProductionConfigManager.save_config`) eski metinle bayt bayt aynı + EN."""
    from utils import production_config_manager as pcm

    yonetici = pcm.ProductionConfigManager.__new__(pcm.ProductionConfigManager)
    yonetici._user_config_unreadable = "PermissionError"
    yonetici._kirli = True
    yonetici._config = {}
    yonetici._get_app_data_dir = lambda: tmp_path
    eski = (
        "Ayar KAYDEDILMEDI: config.json okunamiyor (PermissionError). Mevcut dosya korunuyor "
        "(varsayilanlarla ezilmedi). Yapilacak: dosyayi uygulamayi kuran Windows hesabiyla acin ya da izinlerini "
        "duzelttirin; bozuksa yedekteki pemf_config_<tarih>.json dosyasini config.json olarak geri yukleyin."
    )
    kaydet = next(
        (a for a in ("save_config", "save", "_save_config") if hasattr(pcm.ProductionConfigManager, a)),
        None,
    )
    assert kaydet, "kayıt yöntemi bulunamadı"
    with pytest.raises(pcm._sahip().ConfigKaydiReddedildi) as e:
        getattr(yonetici, kaydet)()
    assert str(e.value) == eski
    with dilde("en"):
        with pytest.raises(pcm._sahip().ConfigKaydiReddedildi) as e_en:
            getattr(yonetici, kaydet)()
    assert str(e_en.value).startswith(
        "Setting NOT SAVED: config.json cannot be read (PermissionError). The existing file is kept"
    )


# ── başarı iletileri (installer BAŞLAR): iletiler Popen'dan ÖNCE hesaplanır ───────────────────────────────
def _basarili_kur(um, monkeypatch):
    import hashlib

    monkeypatch.setattr(um, "_has_active_treatment", lambda: False)
    monkeypatch.setattr(um, "_pinli_ac", lambda *a, **k: _SahteYanit(b"x"))
    monkeypatch.setattr(um, "_download_to", lambda r, f, limit, what: f.write(b"x") or 1)
    monkeypatch.setattr(um, "_verify_authenticode", lambda p: "valid")
    calisan = []
    monkeypatch.setattr(um.subprocess, "Popen", lambda *a, **k: calisan.append(a))
    return hashlib.sha256(b"x").hexdigest(), calisan


def test_KRITIK_apply_basari_iletisi_TR_bayt_bayt_EN_istek_dilinde(um_acik, monkeypatch):
    um = um_acik
    sha, calisan = _basarili_kur(um, monkeypatch)
    um._status.update(
        {"available": True, "installerUrl": GH, "currentVersion": "1.0.0", "latestVersion": "9.9.9", "sha256": sha}
    )
    r = um.apply_update()
    assert r == {
        "ok": True,
        "message": "Güncelleme indirildi + doğrulandı, kurulum başladı. Servis birazdan yeni sürümle yeniden başlar.",
    }
    assert len(calisan) == 1
    um._applying = False
    with dilde("en"):
        r_en = um.apply_update()
    assert r_en == {
        "ok": True,
        "message": "The update was downloaded and verified, installation has started. The service will restart shortly with the new version.",
    }
    assert len(calisan) == 2


def test_KRITIK_apply_ileti_hatasi_baslamis_kurulumu_UYGULANAMADI_gostermez(um_acik, monkeypatch):
    """İleti Popen'dan ÖNCE hesaplanır: katalog / çeviri çökerse installer HİÇ başlamaz (eskiden: başladıktan sonra çökerse 'uygulanamadı' denirdi)."""
    um = um_acik
    sha, calisan = _basarili_kur(um, monkeypatch)
    um._status.update(
        {"available": True, "installerUrl": GH, "currentVersion": "1.0.0", "latestVersion": "9.9.9", "sha256": sha}
    )
    asil = ceviri.t

    def _patlat(anahtar, *a, **k):
        if anahtar == "guncelleme.apply.basladi":
            raise RuntimeError("katalog çöktü")
        return asil(anahtar, *a, **k)

    monkeypatch.setattr(ceviri, "t", _patlat)
    r = um.apply_update()
    assert r["ok"] is False
    assert calisan == [], "ileti hatası installer'ı BAŞLATTI (ileti Popen'dan önce hesaplanmalı)"


def test_KRITIK_rollback_basari_iletisi_TR_bayt_bayt_EN_istek_dilinde(um_acik, monkeypatch):
    um = um_acik
    sha, calisan = _basarili_kur(um, monkeypatch)
    um._status.update({"previousStable": {"version": "1.3.0", "installerUrl": GH, "sha256": sha}})
    assert um.rollback() == {
        "ok": True,
        "message": "Önceki kararlı sürüme (1.3.0) dönülüyor. Servis birazdan yeniden başlar.",
    }
    um._applying = False
    with dilde("en"):
        assert um.rollback() == {
            "ok": True,
            "message": "Going back to the previous stable version (1.3.0). The service will restart shortly.",
        }
    assert len(calisan) == 2

# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.117 · B-10.128 · B-10.151 — eski EXE güncelleme kanalının yetki kapısı TOKEN'SIZ LAN isteğiyle, `rollback()`'teki
installer-sonrası koruma DAVRANIŞLA ölçülür. Ürün bugün doğru (kanal varsayılan KAPALI); kapılar KÖRDÜ.

ÖLÇÜLEN KÖRLÜKLER (kör mutantlar, 1-H):
  * `tests/test_guncelleme_uclari_yetki.py` kaynakta `"_yetki_kapisi(request)" in govde` ve
    `"enforce_privileged(request)" in kapi` METNİNİ arıyordu: handler'daki çağrı YORUMA alınınca (`# _yetki_kapisi(request)`)
    ya da kapı `if False: enforce_privileged(request)` yapılınca YEŞİL kalıyordu → `PEMF_LEGACY_EXE_UPDATE=1` dağıtımında
    klinik hotspot'undaki kimliksiz bir cihaz sessiz installer / geri alma tetikleyebilirdi.
  * `test_p2p3_regression_gaps.py::test_guncelleme_guardi_installer_baslayinca_ACIK_kalir` var olmayan `rollback_update`
    adını arıyor, bulamayınca `continue` ediyordu → `rollback()`'in "installer başlayınca guard AÇIK kalır" koruması HİÇ
    ölçülmüyordu (finally'yi `if True:` yapan mutant yeşil).

KAPI: (a) GERÇEK router + GERÇEK auth: LAN istemcisi (192.168.137.x, token'sız), kanal AÇIK → apply/rollback 403 ve
`update_manager` işlevi ÇAĞRILMAZ; karşıt: loopback → işleve ulaşır. (b) GERÇEK `rollback()` başarı yolu (ağ = yamalı
`_pinli_ac`, Popen SAHTE — installer çalışmaz): installer başlatıldıktan SONRA `_applying` AÇIK kalır.
"""

from __future__ import annotations

import hashlib
import io
import types

import pytest

URL = "https://github.com/mert61-python/pemf-update/releases/download/exe-v1.0.0/PEMF_Setup.exe"
GOVDE = b"MZ-sahte-installer"


@pytest.fixture()
def um(monkeypatch):
    from servers import update_manager as m

    monkeypatch.setenv("PEMF_LEGACY_EXE_UPDATE", "1")
    monkeypatch.setattr(m, "_applying", False)
    monkeypatch.setattr(m, "_applying_since", None)
    return m


@pytest.mark.parametrize("uc,islev", [("/api/update/apply", "apply_update"), ("/api/update/rollback", "rollback")])
def test_KRITIK_LAN_tokensiz_istek_YETKI_kapisina_takilir(um, monkeypatch, uc, islev):
    from fastapi.testclient import TestClient
    from servers import api_server as api

    cagri: list[str] = []
    monkeypatch.setattr(um, islev, lambda: cagri.append(islev) or {"ok": False, "error": "kayitci"})
    r = TestClient(api.app, client=("192.168.137.50", 50117)).post(uc)
    assert r.status_code in (401, 403), (
        f"token'sız LAN isteği {uc} → {r.status_code} (yetki kapısı yok/devre dışı): kimliksiz cihaz installer/geri alma "
        "tetikleyebilir"
    )
    assert cagri == [], f"yetki reddedilmeden önce {islev} ÇAĞRILDI: {cagri}"


@pytest.mark.parametrize("uc,islev", [("/api/update/apply", "apply_update"), ("/api/update/rollback", "rollback")])
def test_KARSIT_loopback_istegi_isleve_ULASIR(um, monkeypatch, uc, islev):
    from fastapi.testclient import TestClient
    from servers import api_server as api

    cagri: list[str] = []
    monkeypatch.setattr(um, islev, lambda: cagri.append(islev) or {"ok": False, "error": "kayitci"})
    r = TestClient(api.app, client=("127.0.0.1", 50118)).post(uc)
    assert r.status_code == 200 and cagri == [islev], (r.status_code, r.text[:200], cagri)


class _Yanit(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def test_KRITIK_rollback_installer_BASLAYINCA_guard_ACIK_kalir(um, monkeypatch):
    """Installer servisi durdurup EXE'yi değiştirecek: guard o pencerede kapanırsa `/session/start` ve `/ai/pro/start`
    yeniden serbest kalır ve TAM O ANDA tedavi başlatılabilir."""
    popen: list[list[str]] = []
    monkeypatch.setattr(
        um,
        "_status",
        {
            "checked": True,
            "available": False,
            "currentVersion": "1.1.0",
            "previousStable": {"version": "1.0.0", "installerUrl": URL, "sha256": hashlib.sha256(GOVDE).hexdigest()},
            "error": "",
        },
    )
    monkeypatch.setattr(um, "_has_active_treatment", lambda: False)
    monkeypatch.setattr(um, "_pinli_ac", lambda url, timeout, headers=None: _Yanit(GOVDE))
    monkeypatch.setattr(um, "_verify_authenticode", lambda p: "valid")
    # yalnız update_manager'ın `subprocess` adı değişir (küresel Popen'e dokunulmaz)
    monkeypatch.setattr(um, "subprocess", types.SimpleNamespace(Popen=lambda argv, **k: popen.append(list(argv))))
    sonuc = um.rollback()
    assert sonuc.get("ok") is True and popen, f"aparat: rollback başarı yoluna ulaşmadı: {sonuc}"
    assert um._applying is True, (
        "rollback installer'ı BAŞLATTIKTAN sonra guard KAPANDI — installer servisi durdururken yeni seans/AI Pro başlar"
    )

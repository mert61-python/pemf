# -*- coding: utf-8 -*-
"""E2-1.2 (2-E incelemesi, A1) — açılış sır kilidi (`backend_service._harden_secret_file_acls`) UYGULANAMAYINCA eylem söyleyen ERROR
satırı HİÇ basılmaz: `basarisiz` sayacı yalnız `lock_down_file` İSTİSNA atarsa artar, oysa `lock_down_file` her hatayı YUTUP False döner
(icacls hata kodu / zaman aşımı / D2.79'un yeni "SID okunamadı" dalı). Sonuç: sır dosyaları (`pemf_secrets.json`, `.pemf_key_v2`,
`.sqlcipher_key`, `api_token.txt`, `*.plain.bak*`) makinedeki diğer kullanıcılara açık kalabilirken günlükte yalnız dosya başına
WARNING ve "uygulandı: N dosya" INFO'su (daha küçük N) görünür; "UYGULANAMADI … YAPILACAK" ERROR'u ölü daldır.

Arıza EN ALT katta, iki gerçek biçimde: (a) icacls hata koduyla döner (`check=True` → `CalledProcessError`, file_acl yutar);
(b) sürecin SID'i okunamaz (D2.79 dalı, `_surec_sid` → None). GERÇEK `_harden_secret_file_acls` + GERÇEK `lock_down_file`.
Kilit hiç uygulanmadığı için diskte ACL değişmez (aparat temizliği gerekmez).
"""

from __future__ import annotations

import logging
import os
import subprocess

import pytest

pytestmark = pytest.mark.skipif(os.name != "nt", reason="NTFS ACL (icacls) yalnız Windows")


class _Topla(logging.Handler):
    def __init__(self):
        super().__init__(logging.DEBUG)
        self.kayitlar = []

    def emit(self, r):
        self.kayitlar.append(r)


@pytest.mark.parametrize("ariza", ["icacls_hata_kodu", "surec_sid_okunamadi"])
def test_KRITIK_acilis_sir_kilidi_UYGULANAMAZSA_ERROR_ve_YAPILACAK_basilir_E2_1_2(tmp_path, monkeypatch, ariza):
    import backend_service as bs
    import utils.file_acl as fa

    app = tmp_path / "PEMF_GUI"
    app.mkdir()
    for ad in ("pemf_secrets.json", ".pemf_key_v2", "patients.db.plain.bak"):
        (app / ad).write_text("x", encoding="utf-8")

    if ariza == "icacls_hata_kodu":

        def _icacls(args, **k):  # icacls.exe 5 (erişim engellendi) ile döner → check=True CalledProcessError
            raise subprocess.CalledProcessError(5, args, output=b"", stderr=b"Erisim engellendi.")

        monkeypatch.setattr(fa.subprocess, "run", _icacls)
    else:
        monkeypatch.setattr(fa, "_surec_sid", lambda: None)

    lg = logging.getLogger("e2_1_2_acilis")
    t = _Topla()
    lg.addHandler(t)
    try:
        bs._harden_secret_file_acls(app, lg)
    finally:
        lg.removeHandler(t)
    hatalar = [r.getMessage() for r in t.kayitlar if r.levelno >= logging.ERROR]
    assert any("UYGULANAMADI" in m and "YAPILACAK" in m for m in hatalar), (
        f"[{ariza}] {len(list(app.iterdir()))} sır dosyasının hiçbiri kilitlenemedi ama eylem söyleyen ERROR basılmadı "
        f"(basarisiz sayacı ölü dal); günlük: {[(r.levelname, r.getMessage()[:80]) for r in t.kayitlar]}"
    )


def test_KARSIT_kilit_TUTARSA_ERROR_yok_dosya_YOKSA_basarisiz_sayilmaz_E2_1_2(tmp_path, monkeypatch):
    """Karşıt: kilit tutunca ERROR yok; aday listesindeki VAR OLMAYAN dosya (ör. `.sqlcipher_key` hiç yok) başarısızlık sayılmaz."""
    import backend_service as bs
    import utils.file_acl as fa

    app = tmp_path / "PEMF_GUI"
    app.mkdir()
    (app / "pemf_secrets.json").write_text("x", encoding="utf-8")
    monkeypatch.setattr(fa, "lock_down_file", lambda p, keep_current_user=False: os.path.exists(str(p)))
    lg = logging.getLogger("e2_1_2_karsit")
    t = _Topla()
    lg.addHandler(t)
    try:
        bs._harden_secret_file_acls(app, lg)
    finally:
        lg.removeHandler(t)
    assert not [r for r in t.kayitlar if r.levelno >= logging.ERROR], [r.getMessage() for r in t.kayitlar]
